"""python -m hyperparse  [--hours 24] [--no-sheet] [--no-excel] [--dry-run]"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import config
from .arctic_shift import ArcticShiftClient
from .reddit_client import RedditBlocked, RedditClient
from .scraper import Scraper
from .sinks import SheetError, SheetSink, write_excel

log = logging.getLogger("hyperparse")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hyperparse", description="Reddit insurance mentions -> Sheet + Excel")
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.toml"))
    ap.add_argument("--hours", type=float, help="look-back window (default: config / LOOKBACK_HOURS)")
    ap.add_argument("--no-sheet", action="store_true", help="do not push to the Google Sheet")
    ap.add_argument("--no-excel", action="store_true", help="do not write Excel files")
    ap.add_argument("--dry-run", action="store_true", help="scrape and print only")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    s = config.load(a.config, a.hours)
    client = make_client(s)
    log.info("mode=%s  window=last %.0fh", client.mode, s.lookback_hours)
    try:
        client.probe(s["subreddits"]["insurance"][0])
    except (RedditBlocked, RuntimeError) as exc:
        log.error("cannot read Reddit: %s", exc)
        _summary(f"### Reddit HyperParse\n- **FAILED**: cannot read Reddit ({client.mode} mode): {exc}")
        return 2

    sheet = None
    known: set[str] = set()
    use_sheet = not (a.no_sheet or a.dry_run)
    if use_sheet:
        if s.sheet_url and s.sheet_key:
            sheet = SheetSink(s.sheet_url, s.sheet_key)
            try:
                known = sheet.known_ids()
                log.info("sheet connected, %d ids already there", len(known))
            except (SheetError, OSError) as exc:
                log.error("sheet not reachable: %s", exc)
                sheet = None
        else:
            log.warning("SHEET_WEBAPP_URL / SHEET_KEY not set: sheet push skipped")

    res = Scraper(s, client, known).run()
    log.info("scanned %d items, %d new matching rows in %.0fs (%s)",
             res.scanned, len(res.rows), res.seconds, client.stats)

    lines = [f"### Reddit HyperParse - last {s.lookback_hours:.0f}h",
             f"- mode: **{client.mode}**, scanned {res.scanned}, new rows **{len(res.rows)}**"]

    if a.dry_run:
        for r in res.rows[:50]:
            print(f"{r[10]:>3}  {r[1]}  r/{r[2]:<22} {r[3][:70]}  [{r[6]}]")

    sheet_failed = False
    if sheet and res.rows:
        try:
            added, skipped = sheet.push(res.rows)
            log.info("sheet: %d added to New Cases, %d skipped", added, skipped)
            lines.append(f"- sheet: {added} added, {skipped} already there")
        except (SheetError, OSError) as exc:
            sheet_failed = True
            log.error("sheet push failed: %s", exc)
            lines.append(f"- sheet push FAILED: {exc}")

    if not (a.no_excel or a.dry_run):
        run_file, master = write_excel(res.rows, s.output_dir)
        log.info("excel: %s  (master: %s)", run_file, master)
        lines.append(f"- excel: `{run_file.name}`")

    for f in res.failures + getattr(client, "warnings", []):
        lines.append(f"- warning: {f}")
    _summary("\n".join(lines))

    # Fail the run (red in GitHub) only when we got nothing useful.
    if res.failures and res.scanned == 0:
        return 2
    return 1 if sheet_failed else 0


def make_client(s: config.Settings):
    """SOURCE=auto (default): Reddit API if keys are set, else Arctic Shift.
    SOURCE=reddit | arctic forces one."""
    src = (os.environ.get("SOURCE") or s["run"].get("source", "auto")).lower()
    has_keys = bool(s.reddit_client_id and s.reddit_client_secret)
    if src == "reddit" or (src == "auto" and has_keys):
        return RedditClient(s.user_agent, s.reddit_client_id, s.reddit_client_secret,
                            s["run"]["rpm_oauth"], s["run"]["rpm_public"])
    return ArcticShiftClient(s.user_agent, s["run"].get("rpm_arctic", 60),
                             s["run"].get("arctic_max_pages", 30))


def _summary(md: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(md + "\n")


if __name__ == "__main__":
    sys.exit(main())
