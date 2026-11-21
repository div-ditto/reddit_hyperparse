"""Keyword matching and filters - same rules as the Apps Script."""
from __future__ import annotations

import re


class Matcher:
    def __init__(self, cfg: dict):
        kw = cfg["keywords"]
        terms = kw["global"] + kw["health_terms"] + kw["term_terms"] + kw["umbrella"] + ["Ditto"]
        seen, self.keywords = set(), []
        for t in terms:                      # keep order, drop exact repeats
            if t not in seen:
                seen.add(t)
                self.keywords.append(t)
        self._patterns = [(t, re.compile(rf"\b{re.escape(t)}\b", re.I)) for t in self.keywords]
        # Cheap pre-check: one big regex; only texts that hit it get the per-term scan.
        self._any = re.compile("|".join(rf"\b{re.escape(t)}\b" for t in self.keywords), re.I)

        f = cfg["filters"]
        self._motor = re.compile(r"\b(" + "|".join(map(re.escape, f["motor_exclude"])) + r")\b", re.I)
        self._motor_words = [m.lower() for m in f["motor_exclude"]]
        self._excluded_subs = {s.lower() for s in f["exclude_subreddits"]}

    def match(self, text: str) -> list[str]:
        if not text or not self._any.search(text):
            return []
        found = [t for t, p in self._patterns if p.search(text)]
        # "Ditto Insurance" already covers the bare "Ditto".
        if any(t != "Ditto" and "ditto" in t.lower() for t in found):
            found = [t for t in found if t != "Ditto"]
        return found

    def is_motor(self, text: str) -> bool:
        return bool(text and self._motor.search(text))

    def sub_excluded(self, sub: str) -> bool:
        s = (sub or "").lower()
        if not s:
            return False
        return s in self._excluded_subs or any(m in s for m in self._motor_words)
