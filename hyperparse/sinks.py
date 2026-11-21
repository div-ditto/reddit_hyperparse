"""Where rows go: the Google Sheet (via the Apps Script web app) and Excel."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import requests
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .scoring import IST
from .scraper import HEADERS

log = logging.getLogger(__name__)

DITTO_FILL = PatternFill("solid", fgColor="B7E1CD")
HEADER_FILL = PatternFill("solid", fgColor="E4E4E7")
WIDTHS = [12, 20, 22, 60, 22, 60, 45, 10, 8, 12, 14, 22]


# ---------------------------------------------------------------- Google Sheet
class SheetError(RuntimeError):
    pass


class SheetSink:
    """Talks to doPost() in apps_script/Code.gs (actions: ping, ids, push)."""

    CHUNK = 500

    def __init__(self, url: str, key: str, timeout: float = 120):
        self.url, self.key, self.timeout = url, key, timeout

    def _call(self, action: str, **extra) -> dict:
        r = requests.post(self.url, json={"key": self.key, "action": action, **extra},
                          timeout=self.timeout, allow_redirects=True)
        try:
            data = r.json()
        except ValueError:
            raise SheetError(
                f"The sheet web app did not answer with JSON (HTTP {r.status_code}). "
                "In Apps Script set Deploy > Manage deployments > Who has access = 'Anyone', "
                "and check SHEET_WEBAPP_URL ends in /exec.") from None
        if not data.get("ok"):
            raise SheetError(f"Sheet said: {data.get('error') or data}")
        return data

    def ping(self) -> dict:
        return self._call("ping")

    def known_ids(self) -> set[str]:
        return set(map(str, self._call("ids").get("ids", [])))

    def push(self, rows: list[list]) -> tuple[int, int]:
        added = skipped = 0
        for i in range(0, len(rows), self.CHUNK):
            data = self._call("push", rows=[[_cell(v) for v in r] for r in rows[i:i + self.CHUNK]])
            added += int(data.get("added", 0))
            skipped += int(data.get("skipped", 0))
        return added, skipped


def _cell(v):
    return "" if v is None else v


# ---------------------------------------------------------------- Excel
def write_excel(rows: list[list], out_dir: Path) -> tuple[Path, Path]:
    """Writes this run's file and merges into reddit_master.xlsx (deduped by post_id)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(IST).strftime("%Y-%m-%d_%H%M")
    run_path = out_dir / f"reddit_{stamp}.xlsx"
    _save(rows, run_path, "New Cases")

    master = out_dir / "reddit_master.xlsx"
    existing: list[list] = []
    if master.exists():
        ws = load_workbook(master, read_only=True).active
        existing = [list(r) for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
    seen = {str(r[0]) for r in existing}
    merged = existing + [r for r in rows if str(r[0]) not in seen]
    merged.sort(key=lambda r: str(r[1] or ""), reverse=True)
    try:
        _save(merged, master, "All")
    except PermissionError:
        # Open in Excel on Windows: keep this run's file, update the master next time.
        log.warning("%s is open in another program; master not updated this run "
                    "(this run's rows are in %s)", master.name, run_path.name)
    return run_path, master


def _save(rows: list[list], path: Path, title: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = HEADER_FILL
    for r in rows:
        ws.append(list(r))
        for c in ws[ws.max_row]:
            if isinstance(c.value, str) and c.value.startswith("="):
                c.data_type = "s"   # Reddit text, not a formula
        if "ditto" in str(r[6]).lower():
            for c in ws[ws.max_row]:
                c.fill = DITTO_FILL
        link = ws.cell(ws.max_row, 6)
        if str(link.value).startswith("http"):
            link.hyperlink = link.value
            link.font = Font(color="1155CC", underline="single")
    for i, w in enumerate(WIDTHS, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    wb.save(path)

