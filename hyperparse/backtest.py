"""Compare the app with your past data, post by post.

    python -m hyperparse.backtest Reddit_Shadow_Protocol.xlsx --from 2026-10-27 --to 2026-10-29

Takes the rows your old Reddit-search setup saved for those days (IST), runs
this app over the same days through Arctic Shift's archive, and reports:
  - found by both / missed by the app / found only by the app,
  - why each missed post was missed,
  - an Excel report: output/backtest_<from>_<to>.xlsx
"""
from __future__ import annotations

import argparse
import collections
import logging
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

from . import config
from .arctic_shift import ArcticShiftClient
from .scoring import IST
from .scraper import Scraper

log = logging.getLogger("hyperparse.backtest")


def load_old_rows(xlsx: Path) -> dict[str, dict]:
    """post rows from every tab with post_id + created_utc + subreddit columns."""
    out: dict[str, dict] = {}
    wb = load_workbook(xlsx, read_only=True)
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        head = [str(h or "").strip().lower() for h in (next(rows, None) or ())]
        need = ("post_id", "created_utc", "subreddit")
        if not all(n in head for n in need):
            continue
        ix = {n: head.index(n) for n in head if n}
        for r in rows:
            if not r or len(r) <= ix["subreddit"] or not r[ix["post_id"]]:
                continue
            pid = str(r[ix["post_id"]]).strip()
            when = r[ix["created_utc"]]
            if isinstance(when, str):
                try:
                    when = datetime.strptime(when[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
            if not isinstance(when, datetime):
                continue
            g = lambda k: r[ix[k]] if k in ix and len(r) > ix[k] else ""
            out.setdefault(pid, {
                "post_id": pid, "when": when.replace(tzinfo=IST), "subreddit": str(g("subreddit")),
                "title": str(g("title") or ""), "matched": str(g("matched_terms") or ""),
                "source_type": str(g("source_type") or "post"), "tab": ws.title,
            })
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hyperparse.backtest")
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--from", dest="start", required=True, help="first day, YYYY-MM-DD (IST)")
    ap.add_argument("--to", dest="end", required=True, help="last day, YYYY-MM-DD (IST), included")
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.toml"))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")

    start = datetime.strptime(a.start, "%Y-%m-%d").replace(tzinfo=IST)
    end = datetime.strptime(a.end, "%Y-%m-%d").replace(tzinfo=IST) + timedelta(days=1)
    s = config.load(a.config)
    subs = s["subreddits"]
    group = {}
    for name in ("discovered", "regional", "insurance"):           # later wins
        for sub in subs.get(name, []):
            group[sub.lower()] = name

    all_old = load_old_rows(a.xlsx)
    old = {k: v for k, v in all_old.items()
           if start <= v["when"] < end and v["source_type"] == "post"}
    log.info("old data: %d posts between %s and %s", len(old), a.start, a.end)

    client = ArcticShiftClient(s.user_agent, s["run"].get("rpm_arctic", 60),
                               s["run"].get("arctic_max_pages", 30))
    res = Scraper(s, client).run(start.timestamp(), end.timestamp())
    new_posts = {r[0]: r for r in res.rows if r[7] == "post"}
    new_comments = [r for r in res.rows if r[7] == "comment"]
    log.info("app: %d posts + %d comments matched, %d items read",
             len(new_posts), len(new_comments), res.scanned)

    # Would each discovered sub still be on the list without these days' rows?
    before = collections.Counter(v["subreddit"].lower() for v in all_old.values() if v["when"] < start)
    after_ = collections.Counter(v["subreddit"].lower() for v in all_old.values() if v["when"] >= end)
    outside = before + after_

    both = sorted(set(old) & set(new_posts))
    missed = sorted(set(old) - set(new_posts))
    extra = sorted(set(new_posts) - set(old))

    def why(pid: str) -> str:
        sub = old[pid]["subreddit"].lower()
        if sub not in group:
            return "subreddit not tracked"
        if pid in res.seen_posts:
            return "read, but did not pass the keyword rules"
        return "tracked, but not in the archive for that time (deleted/removed or time differs)"

    reasons = collections.Counter(why(p) for p in missed)
    by_group = collections.defaultdict(lambda: [0, 0])
    for p in old:
        g = group.get(old[p]["subreddit"].lower(), "not tracked")
        by_group[g][0] += 1
        by_group[g][1] += p in new_posts
    in_sample = sum(1 for p in both if group.get(old[p]["subreddit"].lower()) == "discovered"
                    and outside[old[p]["subreddit"].lower()] < 2)

    pct = lambda x, n: f"{x / n:.0%}" if n else "-"
    lines = [
        f"BACKTEST {a.start} .. {a.end} (IST)",
        f"Old setup found {len(old)} posts. The app found {len(new_posts)} posts "
        f"(+{len(new_comments)} comments the old setup never saved).",
        f"  Found by both:        {len(both):4}  = {pct(len(both), len(old))} of the old posts",
        f"  Missed by the app:    {len(missed):4}",
    ]
    lines += [f"      {n:4}  {r}" for r, n in reasons.most_common()]
    lines += [f"  Found only by the app: {len(extra):3}  (new posts the old setup missed)", "",
              "  Old posts per subreddit group (caught / total):"]
    for g in ("insurance", "regional", "discovered", "not tracked"):
        t, c = by_group.get(g, [0, 0])
        if t:
            lines.append(f"      {g:12} {c:4} / {t:<4} {pct(c, t)}")
    if in_sample:
        lines.append(f"  Note: {in_sample} of the 'both' posts are in discovered subreddits that are "
                     f"only on the list because of these days' rows.")
    report = "\n".join(lines)
    print("\n" + report + "\n")

    # Excel report
    out = s.output_dir / f"backtest_{a.start}_{a.end}.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    for line in lines:
        ws.append([line])
    ws.column_dimensions["A"].width = 110

    def sheet(title, head, data):
        w = wb.create_sheet(title)
        w.append(head)
        for c in w[1]:
            c.font = Font(bold=True)
        for row in data:
            w.append(row)
        w.freeze_panes = "A2"
        w.auto_filter.ref = w.dimensions

    o = lambda p: old[p]
    sheet("Missed by app", ["post_id", "created (IST)", "subreddit", "group", "title", "old matched_terms", "why"],
          [[p, o(p)["when"].strftime("%Y-%m-%d %H:%M"), o(p)["subreddit"],
            group.get(o(p)["subreddit"].lower(), "not tracked"), o(p)["title"], o(p)["matched"], why(p)]
           for p in missed])
    sheet("Found by both", ["post_id", "created (IST)", "subreddit", "title", "old matched_terms", "app matched_terms"],
          [[p, o(p)["when"].strftime("%Y-%m-%d %H:%M"), o(p)["subreddit"], o(p)["title"], o(p)["matched"],
            new_posts[p][6]] for p in both])
    sheet("Only the app", ["post_id", "created (IST)", "subreddit", "title", "matched_terms", "link"],
          [[p, new_posts[p][1], new_posts[p][2], new_posts[p][3], new_posts[p][6], new_posts[p][5]] for p in extra])
    sheet("App comments", ["id", "created (IST)", "subreddit", "matched_terms", "link"],
          [[r[0], r[1], r[2], r[6], r[5]] for r in new_comments])
    wb.save(out)
    log.info("report: %s", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
