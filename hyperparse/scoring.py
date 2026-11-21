"""Priority score - a port of computePriority_ in the Apps Script.

Breakdown string: F<freshness> B<brand> I<intent> S<subreddit> M<specificity>
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

_COMPARE = re.compile(r"\bvs\b|\bor\b|compare|comparison|better|difference between")
_BUY = re.compile(r"\bbuy\b|\bbest\b|recommend|suggest|which plan|which policy|should i|"
                  r"looking for|planning|worth")
_HELP = re.compile(r"\bhelp\b|advice|advise|confused|guidance|suggestion")


class Scorer:
    def __init__(self, cfg: dict):
        self.p = p = cfg["priority"]
        kw = cfg["keywords"]
        self.ditto = {"ditto", "ditto insurance"}
        self.platforms = {s.lower() for s in p["competitor_platforms"]}
        self.generic = {s.lower() for s in kw["health_terms"] + kw["term_terms"] + kw["umbrella"]}
        self.high = {s.lower() for s in p["sub_authority_high"]}
        self.core = {s.lower() for s in p["sub_authority_core"]}
        self.niche = {s.lower() for s in p["sub_authority_niche"]}

    def score(self, created_utc: float, subreddit: str, title: str,
              matched: list[str], source_type: str, now: float) -> tuple[int, str]:
        p = self.p
        age_h = max(0.0, (now - created_utc) / 3600)
        fresh = p["freshness_max"] * math.exp(-age_h / p["freshness_tau_hours"])

        terms = [t.lower() for t in matched]
        brand = 0
        if any(t in self.ditto for t in terms):
            brand = max(brand, p["brand_ditto"])
        if any(t in self.platforms for t in terms):
            brand = max(brand, p["brand_competitor_platform"])
        if any(t not in self.ditto and t not in self.platforms and t not in self.generic for t in terms):
            brand = max(brand, p["brand_insurer_plan"])
        if any(t in self.generic for t in terms):
            brand = max(brand, p["brand_generic"])

        intent = 0
        t = (title or "").lower()
        if source_type != "comment" and t:
            if "?" in t:
                intent += p["intent_question"]
            if _COMPARE.search(t):
                intent += p["intent_comparison"]
            if _BUY.search(t):
                intent += p["intent_buying"]
            if _HELP.search(t):
                intent += p["intent_help"]
            intent = min(intent, p["intent_max"])

        s = (subreddit or "").lower()
        sub = (p["sub_high"] if s in self.high else p["sub_core"] if s in self.core
               else p["sub_niche"] if s in self.niche else p["sub_default"])

        n = len({x for x in terms if x not in self.generic})
        multi = p["spec_3plus"] if n >= 3 else p["spec_2"] if n == 2 else p["spec_1"] if n == 1 else 0

        total = _jsround(fresh + brand + intent + sub + multi)
        return total, f"F{_jsround(fresh)} B{brand} I{intent} S{sub} M{multi}"


def _jsround(x: float) -> int:
    """JavaScript Math.round (halves go up), so scores equal the sheet's."""
    return math.floor(x + 0.5)


def to_ist(ts: float) -> str:
    return datetime.fromtimestamp(ts, IST).strftime("%Y-%m-%d %H:%M:%S")
