"""Find the subreddits your past matches came from, so they can be tracked.

    python -m hyperparse.discover Reddit_Shadow_Protocol.xlsx [--min 2]

Reads the subreddit column of every tab that has one (Sheet1, reddit,
New Cases, or an Excel file this app wrote), drops subreddits already in
config.toml, excluded ones, user profiles (u_...) and vehicle subs, and
prints a `discovered = [...]` list to paste into config.toml.
"""
from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

from openpyxl import load_workbook

from . import config

VEHICLE = re.compile(r"car|bike|motor|vehicle|himalayan|triumph|honda|ather|royalenfield|ktm|"
                     r"xev|mahindra|tata(motors|ev)|mechanic|scooter|kia|seltos|creta|pulsar|ns\d{3}|yamaha|ev(s|india)?$", re.I)


def count_subreddits(xlsx: Path) -> collections.Counter:
    cnt: collections.Counter = collections.Counter()
    wb = load_workbook(xlsx, read_only=True)
    for ws in wb.worksheets:
        rows = ws.iter_rows(values_only=True)
        header = next(rows, None) or ()
        cols = [i for i, h in enumerate(header) if str(h).strip().lower() == "subreddit"]
        if not cols:
            continue
        col = cols[0]
        for r in rows:
            if r and len(r) > col and r[col]:
                cnt[str(r[col]).strip()] += 1
    return cnt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hyperparse.discover")
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--min", type=int, default=2, help="minimum past matches (default 2)")
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.toml"))
    a = ap.parse_args(argv)

    cfg = config.load(a.config).raw
    known = {s.lower() for s in cfg["subreddits"]["insurance"] + cfg["subreddits"]["regional"]}
    known |= {s.lower() for s in cfg["filters"]["exclude_subreddits"]}
    cnt = count_subreddits(a.xlsx)
    total = sum(cnt.values())
    picked = [(s, n) for s, n in cnt.most_common()
              if n >= a.min and s.lower() not in known
              and not s.lower().startswith("u_") and not VEHICLE.search(s)]
    covered = sum(n for s, n in cnt.items() if s.lower() in known) + sum(n for _, n in picked)

    print(f"# {total} past rows in {len(cnt)} subreddits; tracked + these {len(picked)} "
          f"cover {covered / max(total, 1):.0%}")
    print("discovered = [")
    line = " "
    for s, _ in picked:
        item = f' "{s}",'
        if len(line) + len(item) > 96:
            print(line)
            line = " "
        line += item
    if line.strip():
        print(line)
    print("]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
