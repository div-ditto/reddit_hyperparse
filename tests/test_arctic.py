"""Arctic Shift source against a fake server."""
import json
import time
from pathlib import Path

import requests

from hyperparse import config
from hyperparse.arctic_shift import ArcticShiftClient
from hyperparse.scraper import Scraper

NOW = time.time()


def p(pid, sub, title, body="", age_h=1.0):
    return {"id": pid, "subreddit": sub, "title": title, "selftext": body, "author": "alice",
            "created_utc": int(NOW - age_h * 3600), "permalink": f"/r/{sub}/comments/{pid}/x/",
            "score": 1, "num_comments": 0}


def c(cid, pid, sub, body, age_h=0.5):
    return {"id": cid, "link_id": f"t3_{pid}", "subreddit": sub, "body": body, "author": "bob",
            "created_utc": str(int(NOW - age_h * 3600)), "permalink": f"/r/{sub}/comments/{pid}"}


class FakeArctic(ArcticShiftClient):
    def __init__(self, handler):
        super().__init__("test", rpm=100000, max_pages=5)
        self.handler, self.calls = handler, []

        def get(url, params, timeout):
            self.calls.append((url.split("/api")[1], dict(params)))
            status, body = handler(url.split("/api")[1], params)
            r = requests.Response()
            r.status_code, r._content = status, json.dumps(body).encode()
            r.headers["X-RateLimit-Reset"] = "0"
            return r
        self.session.get = get


def test_arctic_pipeline():
    s = config.load(Path(__file__).resolve().parent.parent / "config.toml", lookback_hours=14)
    s.raw["run"]["workers"] = 1
    busy = [p(f"b{i:03d}", "personalfinanceindia", "nothing here") for i in range(100)]

    def handler(path, q):
        sub = q.get("subreddit")
        if path == "/posts/search" and sub == "HealthInsuranceIndia":
            return 200, {"data": [p("p1", sub, "Star Health or Niva Bupa?")]}
        if path == "/posts/search" and sub == "personalfinanceindia":
            # page 1 = 100 items (forces paging), page 2 repeats one + a match
            if int(q["after"]) < busy[-1]["created_utc"]:
                return 200, {"data": busy}
            return 200, {"data": [busy[-1], p("p2", sub, "HDFC ERGO vs Care Supreme")]}
        if path == "/posts/search" and sub == "InsuranceGyaan":
            return 404, {"error": "not found"}
        if path == "/posts/search" and sub == "mumbai":
            return 200, {"data": [p("p3", sub, "Best health insurance for parents?")]}
        if path == "/comments/search" and sub == "personalfinanceindia":
            return 200, {"data": [c("19sydlp9zzwgw", "p9", sub, "Try Ditto Insurance")]}
        if path == "/comments/search" and q.get("link_id") == "t3_p3":
            return 200, {"data": [c("k1", "p3", "mumbai", "Go with Niva Bupa"),
                                  c("k2", "p3", "mumbai", "old one Niva Bupa", age_h=30)]}
        return 200, {"data": []}

    client = FakeArctic(handler)
    res = Scraper(s, client).run()
    rows = {r[0]: r for r in res.rows}

    assert set(rows) == {"p1", "p2", "p3", "p9_19sydlp9zzwgw", "p3_k1"}, rows.keys()
    assert rows["p9_19sydlp9zzwgw"][5] == \
        "https://www.reddit.com/r/personalfinanceindia/comments/p9/comment/19sydlp9zzwgw/"
    assert rows["p9_19sydlp9zzwgw"][6] == "Ditto Insurance"
    assert rows["p1"][8] == "" and rows["p1"][9] == ""        # placeholder score left blank
    assert any("InsuranceGyaan" in w for w in client.warnings)
    assert not any(path == "/search" for path, _ in client.calls)   # no global search
    assert all(q.get("sort") == "asc" for path, q in client.calls if "subreddit" in q)
    assert all(int(q["after"]) >= int(NOW - 14 * 3600) - 1 for _, q in client.calls if "after" in q)


def test_discovered_subs_and_gates():
    s = config.load(Path(__file__).resolve().parent.parent / "config.toml", lookback_hours=14)
    s.raw["run"]["workers"] = 1
    s.raw["subreddits"]["discovered"] = ["personalfinance", "IndiaFinance"]

    def handler(path, q):
        sub = q.get("subreddit")
        if path == "/posts/search" and sub == "personalfinance":       # discovered, US sub
            return 200, {"data": [p("d1", sub, "Is a high deductible plan worth it?"),   # jargon only
                                  p("d2", sub, "Moving to India, is Niva Bupa good?")]}  # brand
        if path == "/posts/search" and sub == "IndiaFinance":
            return 200, {"data": [p("d3", sub, "Ditto helped me pick a plan")]}
        if path == "/posts/search" and sub == "india":                  # regional
            return 200, {"data": [p("r1", sub, "My 80C savings plan"),                # jargon only
                                  p("r2", sub, "Is term insurance worth it?")]}       # umbrella
        if path == "/posts/search" and sub == "HealthInsuranceIndia":   # insurance: any term
            return 200, {"data": [p("i1", sub, "What is a deductible?")]}
        return 200, {"data": []}

    client = FakeArctic(handler)
    ids = {r[0] for r in Scraper(s, client).run().rows}
    assert ids == {"d2", "d3", "r2", "i1"}, ids
    asked = {q.get("subreddit") for _, q in client.calls}
    assert {"personalfinance", "IndiaFinance"} <= asked
