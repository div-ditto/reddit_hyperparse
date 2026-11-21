"""End-to-end run against a fake Reddit API (OAuth mode)."""
import time
from pathlib import Path

import requests
from openpyxl import load_workbook

from hyperparse import config
from hyperparse.reddit_client import RedditClient
from hyperparse.scraper import Scraper
from hyperparse.sinks import write_excel

NOW = time.time()


def post(pid, sub, title, body="", age_h=1.0):
    return {"kind": "t3", "data": {"id": pid, "subreddit": sub, "title": title, "selftext": body,
            "author": "alice", "created_utc": NOW - age_h * 3600, "score": 5, "num_comments": 2,
            "permalink": f"/r/{sub}/comments/{pid}/x/"}}


def comment(cid, pid, sub, body, age_h=0.5, replies=None):
    return {"kind": "t1", "data": {"id": cid, "link_id": f"t3_{pid}", "subreddit": sub,
            "body": body, "author": "bob", "created_utc": NOW - age_h * 3600, "score": 1,
            "permalink": f"/r/{sub}/comments/{pid}/x/{cid}/", "replies": replies or ""}}


def listing(children, after=None):
    return {"kind": "Listing", "data": {"children": children, "after": after}}


class FakeClient(RedditClient):
    def __init__(self, routes):
        super().__init__("test", "id", "secret", rpm_oauth=100000)
        self.routes, self.calls = routes, []

    def _bearer(self):
        return "tok"

    def _get(self, url, params, auth):
        path = url.replace("https://oauth.reddit.com", "")
        self.calls.append((path, params.get("after")))
        r = requests.Response()
        body = self.routes.get((path, params.get("after")), self.routes.get(path))
        if body is None:
            r.status_code = 404
            r._content = b"{}"
            return r
        import json
        r.status_code, r._content = 200, json.dumps(body).encode()
        return r


def make_routes(cfg):
    ins = "+".join(cfg["subreddits"]["insurance"])
    reg = "+".join(cfg["subreddits"]["regional"])
    return {
        # page 1 -> page 2 -> stops at old post (older than 14h)
        (f"/r/{ins}/new", None): listing([
            post("p1", "HealthInsuranceIndia", "Star Health or Niva Bupa?"),
            post("p2", "personalfinanceindia", "Weekend plans", "nothing relevant"),
        ], after="t3_p2"),
        (f"/r/{ins}/new", "t3_p2"): listing([
            post("p3", "TermInsuranceIndia", "Need advice: sum assured", age_h=3),
            post("old", "TermInsuranceIndia", "HDFC Life old post", age_h=30),
        ], after="t3_old"),
        f"/r/{ins}/comments": listing([
            comment("c1", "p2", "personalfinanceindia", "Try Ditto Insurance for advice"),
            comment("c2", "p2", "personalfinanceindia", "my car insurance via ICICI Lombard"),
        ]),
        # regional multireddit refused -> per-sub fallback; only r/mumbai answers
        "/r/mumbai/search": listing([post("p4", "mumbai", "Best health insurance for parents?")]),
        "/search": listing([post("p5", "AusFinance", "Star Health"),          # excluded sub
                            post("p6", "IndiaInvestments", "HDFC ERGO claim story")]),
        "/comments/p6": [listing([post("p6", "IndiaInvestments", "")]), listing([
            comment("c3", "p6", "IndiaInvestments", "Policybazaar sold me this", replies=listing([
                comment("c4", "p6", "IndiaInvestments", "Same with Tata AIG")]))])],
        "/comments/p4": [listing([]), listing([])],
    }


def test_pipeline(tmp_path: Path):
    s = config.load(Path(__file__).resolve().parent.parent / "config.toml", lookback_hours=14)
    s.raw["run"]["workers"] = 2
    client = FakeClient(make_routes(s.raw))
    res = Scraper(s, client, known_ids={"p3"}).run()
    ids = {r[0]: r for r in res.rows}

    assert set(ids) == {"p1", "p2_c1", "p4", "p6", "p6_c3", "p6_c4"}, ids.keys()
    assert ids["p1"][6] == "Star Health, Niva Bupa" and ids["p1"][7] == "post"
    assert ids["p2_c1"][6] == "Ditto Insurance" and ids["p2_c1"][3] == "(comment)"
    assert ids["p1"][5].startswith("https://www.reddit.com/r/HealthInsuranceIndia/")
    assert res.rows == sorted(res.rows, key=lambda r: (r[10], r[1]), reverse=True)
    assert not any(c[1] == "t3_old" for c in client.calls)  # stopped paging at the cutoff
    assert res.failures == []

    run_file, master = write_excel(res.rows, tmp_path)
    ws = load_workbook(run_file).active
    assert ws.max_row == 1 + len(res.rows)
    ditto_row = next(r for r in ws.iter_rows(min_row=2) if r[0].value == "p2_c1")
    assert ditto_row[0].fill.fgColor.rgb.endswith("B7E1CD")
    # second run merges into master without duplicates
    write_excel(res.rows[:2], tmp_path)
    assert load_workbook(master).active.max_row == 1 + len(res.rows)
