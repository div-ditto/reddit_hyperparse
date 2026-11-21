"""Arctic Shift reader - a free, open Reddit archive (no login, no key).

https://github.com/ArthurHeitmann/arctic_shift  - API base below.
Posts and comments are archived the moment they are posted, so the last
24 hours are available. Limits: searches are per subreddit (no search across
all of Reddit), and score / num_comments stay 0-1 for ~36 hours, so they
are left blank here.

The service asks users to "be considerate": one shared, paced request
stream, and Retry/X-RateLimit-Reset is obeyed.

Same interface as RedditClient (probe / listing / comments / stats / mode),
so the scraper uses either one unchanged.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Iterator

import requests

from .reddit_client import Item, RateLimiter, RedditBlocked

log = logging.getLogger(__name__)

_LISTING = re.compile(r"^/r/([^/]+)/(new|comments|search)$")


class ArcticShiftClient:
    BASE = "https://arctic-shift.photon-reddit.com/api"
    mode = "arctic-shift"
    supports_global_search = False
    max_workers = 2          # fewer parallel requests: it is a free, shared service

    def __init__(self, user_agent: str, rpm: float = 60, max_pages: int = 30, timeout: float = 60):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self.limiter = RateLimiter(rpm)
        self.max_pages = max_pages
        self.timeout = timeout
        self.stats = {"requests": 0, "errors": 0}
        self.warnings: list[str] = []

    # ------------------------------------------------------------ http
    def _get(self, path: str, params: dict) -> list[dict]:
        last = ""
        for attempt in range(5):
            self.limiter.wait()
            try:
                r = self.session.get(self.BASE + path, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last = str(exc)
                self.stats["errors"] += 1
                time.sleep(2 ** attempt)
                continue
            self.stats["requests"] += 1
            if r.status_code == 200:
                try:
                    body = r.json()
                except ValueError:
                    last = "answer was not JSON"
                    continue
                if isinstance(body, dict) and body.get("error"):
                    last = str(body["error"])
                    if "timed out" in last.lower() and attempt == 0:
                        continue                      # the docs say one retry often works
                    raise RedditBlocked(f"Arctic Shift {path}: {last}")
                return (body.get("data") if isinstance(body, dict) else body) or []
            if r.status_code == 429:
                wait = float(r.headers.get("X-RateLimit-Reset") or 10)
                log.info("Arctic Shift asked to slow down; waiting %.0fs", wait)
                self.limiter.pause(min(wait + 1, 120))
                last = "HTTP 429"
                continue
            if r.status_code == 422 and "timeout" in r.text.lower():
                # "Timeout. Maybe slow down a bit": back off, then retry.
                wait = 5 * (attempt + 1)
                log.info("Arctic Shift busy (%s); waiting %ds", path, wait)
                self.limiter.pause(wait)
                last = "server busy (timeout)"
                continue
            if r.status_code >= 500:
                last = f"HTTP {r.status_code}"
                time.sleep(2 ** attempt)
                continue
            raise RedditBlocked(f"Arctic Shift {path}: HTTP {r.status_code} {r.text[:120]}", r.status_code)
        self.stats["errors"] += 1
        raise RedditBlocked(f"Arctic Shift {path}: no answer after retries ({last})")

    # ------------------------------------------------------------ interface
    def probe(self, subreddit: str) -> None:
        self._get("/posts/search", {"subreddit": subreddit, "limit": 1, "sort": "desc"})

    def listing(self, path: str, params: dict | None = None, *,
                stop_before: float = 0.0, max_pages: int = 10) -> Iterator[Item]:
        """'/r/a+b/new' -> posts, '/r/a+b/comments' -> comments, '/r/a+b/search' ->
        all posts (matched locally). Everything since `stop_before`."""
        m = _LISTING.match(path)
        if not m:
            return                                   # no all-of-Reddit search here
        endpoint = "/comments/search" if m.group(2) == "comments" else "/posts/search"
        for sub in m.group(1).split("+"):
            try:
                yield from self._window(endpoint, sub, stop_before)
            except RedditBlocked as exc:
                self.warnings.append(f"r/{sub} skipped: {exc}")
                log.warning("r/%s skipped: %s", sub, exc)

    def comments(self, post_id: str, limit: int = 100) -> list[Item]:
        rows = self._get("/comments/search", {"link_id": f"t3_{post_id}", "limit": limit})
        return [i for i in map(_comment, rows) if i]

    # ------------------------------------------------------------ paging
    def _window(self, endpoint: str, sub: str, since: float) -> Iterator[Item]:
        after = int(since)
        seen: set[str] = set()
        convert = _comment if endpoint.startswith("/comments") else _post
        for _ in range(self.max_pages):
            rows = self._get(endpoint, {"subreddit": sub, "after": after, "sort": "asc", "limit": 100})
            for d in rows:
                if d.get("id") in seen:
                    continue
                seen.add(d.get("id"))
                it = convert(d)
                if it:
                    yield it
            if len(rows) < 100:
                return
            last = int(float(rows[-1].get("created_utc") or after))
            after = last if last > after else after + 1   # same-second items: dedupe above
        msg = f"r/{sub}: more than {self.max_pages * 100} items in the window, the rest skipped"
        self.warnings.append(msg)
        log.warning(msg)


def _post(d: dict) -> Item | None:
    if not d.get("id"):
        return None
    return Item("t3", d["id"], d["id"], d.get("subreddit") or "", d.get("title") or "",
                d.get("selftext") or "", _u(d.get("author")), float(d.get("created_utc") or 0),
                "https://www.reddit.com" + (d.get("permalink") or f"/comments/{d['id']}/"))


def _comment(d: dict) -> Item | None:
    cid, post = d.get("id"), str(d.get("link_id") or "").removeprefix("t3_")
    if not cid or not post:
        return None
    sub = d.get("subreddit") or ""
    return Item("t1", cid, post, sub, "(comment)", d.get("body") or "", _u(d.get("author")),
                float(d.get("created_utc") or 0),
                f"https://www.reddit.com/r/{sub}/comments/{post}/comment/{cid}/")


def _u(name: str | None) -> str:
    return f"/u/{name}" if name else ""
