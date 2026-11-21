"""Collects matching posts + comments from the last N hours.

Strategy (far fewer requests than one search per keyword group):
  1. Insurance subs, as ONE multireddit: every new post and every new comment
     in the window, matched locally against all keywords.
  2. Regional subs, as ONE multireddit search for the umbrella phrases.
  3. All of Reddit: brand / plan names, in chunks of 12 per search.
  4. Comments of matched posts found by 2 and 3 (insurance-sub comments are
     already covered by 1).
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .config import Settings
from .matching import Matcher
from .reddit_client import Item, RedditBlocked, RedditClient
from .scoring import Scorer, to_ist

log = logging.getLogger(__name__)

HEADERS = [
    "post_id", "created_utc", "subreddit", "title", "author", "permalink",
    "matched_terms", "source_type", "score", "num_comments",
    "priority_score", "priority_breakdown",
]


@dataclass
class Result:
    rows: list[list] = field(default_factory=list)
    scanned: int = 0
    failures: list[str] = field(default_factory=list)
    seconds: float = 0.0
    seen_posts: set[str] = field(default_factory=set)   # every post id read (for backtests)


def _q(term: str) -> str:
    return f'"{term}"' if " " in term else term


def _time_filter(hours: float) -> str:
    return "day" if hours <= 24 else "week" if hours <= 168 else "month"


class Scraper:
    def __init__(self, settings: Settings, client: RedditClient, known_ids: set[str] | None = None):
        self.s = settings
        self.cfg = settings.raw
        self.client = client
        self.matcher = Matcher(self.cfg)
        self.scorer = Scorer(self.cfg)
        self.known = set(known_ids or ())
        subs = self.cfg["subreddits"]
        self.insurance = {s.lower() for s in subs["insurance"]}
        self.regional = {s.lower() for s in subs["regional"]}

    def run(self, start: float | None = None, end: float | None = None) -> Result:
        """Last `lookback_hours`, or a fixed past window [start, end) (unix seconds)."""
        t0 = time.time()
        res = Result()
        cutoff = start if start is not None else t0 - self.s.lookback_hours * 3600
        end = end if end is not None else float("inf")
        if end != float("inf") and hasattr(self.client, "until"):
            self.client.until = end
        pages = self.cfg["run"]["max_pages_per_listing"]
        subs = self.cfg["subreddits"]
        kw = self.cfg["keywords"]
        tf = _time_filter(self.s.lookback_hours)
        insurance_set = {s.lower() for s in subs["insurance"]}

        # name -> (subreddits or None for all of Reddit, path suffix, params)
        jobs: dict[str, tuple[list[str] | None, str, dict]] = {
            "insurance posts": (subs["insurance"], "/new", {}),
            "insurance comments": (subs["insurance"], "/comments", {}),
            "regional search": (subs["regional"], "/search", {
                "q": " OR ".join(map(_q, kw["umbrella"])),
                "restrict_sr": "on", "sort": "new", "t": tf}),
        }
        # Sources without an all-of-Reddit search (Arctic Shift) read the
        # "discovered" subreddits instead - where past brand matches came from.
        has_search = getattr(self.client, "supports_global_search", True)
        if not has_search and subs.get("discovered"):
            jobs["discovered posts"] = (subs["discovered"], "/new", {})
        glob = kw["global"] if has_search else []
        for i in range(0, len(glob), 12):
            jobs[f"global search {i // 12 + 1}"] = (None, "/search", {
                "q": "(" + " OR ".join(map(_q, glob[i:i + 12])) + ")",
                "sort": "new", "t": tf, "type": "link"})

        items: dict[str, Item] = {}
        workers = getattr(self.client, "max_workers", None) or self.cfg["run"]["workers"]
        with ThreadPoolExecutor(workers) as pool:
            futs = {pool.submit(self._collect, subs_, suffix, params, cutoff, pages): name
                    for name, (subs_, suffix, params) in jobs.items()}
            for f in as_completed(futs):
                name = futs[f]
                try:
                    got = f.result()
                    log.info("%-22s %4d items", name, len(got))
                    for it in got:
                        items.setdefault(it.kind + it.id, it)
                except RedditBlocked as exc:
                    res.failures.append(f"{name}: {exc}")
                    log.error("%s: %s", name, exc)
                except Exception as exc:  # keep the other jobs' data
                    res.failures.append(f"{name}: {exc!r}")
                    log.exception("%s failed", name)

        items = {k: v for k, v in items.items() if v.created_utc < end}
        res.scanned = len(items)
        res.seen_posts = {it.id for it in items.values() if it.kind == "t3"}
        now = time.time()
        rows: list[list] = []
        need_comments: list[Item] = []

        for it in sorted(items.values(), key=lambda x: x.created_utc, reverse=True):
            row = self._row(it, now)
            if row is None:
                continue
            rows.append(row)
            if it.kind == "t3" and it.subreddit.lower() not in insurance_set:
                need_comments.append(it)

        # Comments on matched posts outside the insurance subs.
        if need_comments:
            with ThreadPoolExecutor(workers) as pool:
                futs = {pool.submit(self.client.comments, p.id): p for p in need_comments}
                for f in as_completed(futs):
                    post = futs[f]
                    try:
                        for c in f.result():
                            if not cutoff <= c.created_utc < end or ("t1" + c.id) in items:
                                continue
                            items["t1" + c.id] = c
                            c.post_id = c.post_id or post.id
                            c.subreddit = c.subreddit or post.subreddit
                            row = self._row(c, now)
                            if row:
                                rows.append(row)
                    except Exception as exc:
                        res.failures.append(f"comments of {post.id}: {exc}")
                        log.warning("comments of %s failed: %s", post.id, exc)

        rows.sort(key=lambda r: (r[10], r[1]), reverse=True)
        res.rows = rows
        res.seconds = time.time() - t0
        return res

    def _collect(self, subs: list[str] | None, suffix: str, params: dict,
                 cutoff: float, pages: int) -> list[Item]:
        """Read one listing. Subreddit lists are read as one multireddit
        (r/a+b+c); if Reddit refuses that (e.g. one sub went private), read
        them one by one and skip the ones that fail."""
        if not subs:
            return list(self.client.listing(suffix, params, stop_before=cutoff, max_pages=pages))
        try:
            return list(self.client.listing(f"/r/{'+'.join(subs)}{suffix}", params,
                                            stop_before=cutoff, max_pages=pages))
        except RedditBlocked as exc:
            if len(subs) == 1 or exc.status not in (403, 404):
                raise
            log.warning("combined read refused (%s); reading %d subreddits one by one",
                        exc.status, len(subs))
        out: list[Item] = []
        for sub in subs:
            try:
                out += self.client.listing(f"/r/{sub}{suffix}", params,
                                           stop_before=cutoff, max_pages=pages)
            except RedditBlocked as exc:
                if exc.status not in (403, 404):
                    raise
                log.warning("r/%s skipped: %s", sub, exc)
        return out

    def _row(self, it: Item, now: float) -> list | None:
        if self.matcher.sub_excluded(it.subreddit):
            return None
        is_post = it.kind == "t3"
        text = f"{it.title}\n{it.text}" if is_post else it.text
        if self.matcher.is_motor(text):
            return None
        matched = self.matcher.match(text)
        if not matched:
            return None
        # Outside the insurance subs a post needs a brand/plan name (regional subs:
        # or "health/term insurance"), as the old Reddit searches required.
        # Otherwise words like "deductible" or "GMC" would flood the sheet.
        sub_l = (it.subreddit or "").lower()
        if is_post and sub_l not in self.insurance:
            found = {m.lower() for m in matched}
            ok = found & self.matcher.brand_terms
            if sub_l in self.regional:
                ok = ok or found & self.matcher.umbrella_terms
            if not ok:
                return None
        row_id = it.id if is_post else f"{it.post_id}_{it.id}"
        if row_id in self.known:
            return None
        self.known.add(row_id)
        src = "post" if is_post else "comment"
        total, breakdown = self.scorer.score(it.created_utc, it.subreddit, it.title, matched, src, now)
        return [
            row_id, to_ist(it.created_utc), it.subreddit, it.title if is_post else "(comment)",
            it.author, it.permalink, ", ".join(matched), src,
            "" if it.score is None else it.score,
            "" if it.num_comments is None else it.num_comments,
            total, breakdown,
        ]
