import pytest
import requests

from hyperparse import sinks


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


def test_push_chunks_and_counts(monkeypatch):
    sent = []

    def fake_post(url, json, timeout, allow_redirects):
        sent.append(json)
        assert json["key"] == "k"
        return Resp({"ok": True, "added": len(json["rows"]) - 1, "skipped": 1})

    monkeypatch.setattr(requests, "post", fake_post)
    sink = sinks.SheetSink("https://x/exec", "k")
    sink.CHUNK = 2
    rows = [[f"id{i}", "2026-11-21 10:00:00"] + [""] * 8 + [50, "F1"] for i in range(5)]
    assert sink.push(rows) == (2, 3)
    assert [len(p["rows"]) for p in sent] == [2, 2, 1]


def test_html_login_page_is_explained(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(ValueError("html"), 200))
    with pytest.raises(sinks.SheetError, match="Who has access"):
        sinks.SheetSink("https://x/exec", "k").known_ids()


def test_bad_key(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp({"ok": False, "error": "Wrong security key."}))
    with pytest.raises(sinks.SheetError, match="Wrong security key"):
        sinks.SheetSink("https://x/exec", "bad").ping()
