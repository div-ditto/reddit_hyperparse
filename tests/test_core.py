import time
from pathlib import Path

from hyperparse import config
from hyperparse.matching import Matcher
from hyperparse.reddit_client import RedditClient
from hyperparse.scoring import Scorer

CFG = config.load(Path(__file__).resolve().parent.parent / "config.toml").raw


def test_match_brands_and_jargon():
    m = Matcher(CFG)
    got = m.match("Star Health vs HDFC ERGO - which has better claim settlement ratio?")
    assert got == ["Star Health", "HDFC ERGO", "claim settlement ratio"]


def test_word_boundaries():
    m = Matcher(CFG)
    assert m.match("I love GMCs") == []          # not "GMC"
    assert m.match("my GMC cover") == ["GMC"]


def test_ditto_dedupe():
    m = Matcher(CFG)
    assert m.match("Talked to Ditto Insurance today") == ["Ditto Insurance"]
    assert m.match("ditto advisors were nice") == ["Ditto"]


def test_filters():
    m = Matcher(CFG)
    assert m.is_motor("my car insurance with ICICI Lombard")
    assert not m.is_motor("cardiac cover")
    assert m.sub_excluded("AusFinance") and m.sub_excluded("IndianBikes")
    assert not m.sub_excluded("personalfinanceindia")


def test_score_matches_apps_script():
    s = Scorer(CFG)
    now = time.time()
    total, bd = s.score(now, "personalfinanceindia", "Which plan is best? Ditto or Policybazaar",
                        ["Ditto", "Policybazaar"], "post", now)
    # F30 + B25 + I(4+8+8 -> 15) + S20 + M7
    assert bd == "F30 B25 I15 S20 M7" and total == 97


def test_atom_parse():
    xml = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
    <entry><author><name>/u/abc</name></author><category term="HealthInsuranceIndia"/>
    <content type="html">&lt;p&gt;Niva Bupa claim&lt;/p&gt;</content><id>t3_1abcde</id>
    <link href="https://www.reddit.com/r/HealthInsuranceIndia/comments/1abcde/title/"/>
    <published>2026-11-21T10:00:00+00:00</published><title>Help</title></entry>
    <entry><author><name>/u/xyz</name></author><content type="html">ok</content><id>t1_kkk111</id>
    <link href="https://www.reddit.com/r/india/comments/1abcde/title/kkk111/"/>
    <updated>2026-11-21T11:00:00+00:00</updated><title>/u/xyz on Help</title></entry></feed>"""
    items, after = RedditClient._parse_atom(xml)
    assert [(i.kind, i.id, i.post_id, i.subreddit) for i in items] == [
        ("t3", "1abcde", "1abcde", "HealthInsuranceIndia"), ("t1", "kkk111", "1abcde", "india")]
    assert items[0].text == "Niva Bupa claim" and after is None
