"""Reddit reader.

Two modes, picked automatically:
  * OAuth (REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET set): app-only token, no
    Reddit user login. Fast and reliable (~100 requests/minute).
  * Public (no keys): the same public .json feeds a browser sees, falling back
    to the .rss feeds (what the Apps Script uses). Slow on purpose.

Every request goes through one shared rate limiter and honours Reddit's
X-Ratelimit-* and Retry-After headers.
"""
from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

import requests

log = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"


class RedditBlocked(RuntimeError):
    """Reddit refused to serve a URL (blocked, rate-limited past retries, or gone)."""

    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


PUBLIC_REFUSED_HELP = (
    "Reddit is refusing anonymous (no-login) reads from this network. "
    "Add REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET (a Reddit app; see README) to use the API instead.")


@dataclass
class Item:
    kind: str            # "t3" post | "t1" comment
    id: str              # base36 id, no prefix
    post_id: str         # post id (same as id for posts)
    subreddit: str
    title: str
    text: str            # selftext for posts, body for comments
    author: str
    created_utc: float
    permalink: str       # full https URL
    score: int | None = None
    num_comments: int | None = None


class RateLimiter:
    """Spaces requests evenly; can be told to pause (Reddit headers)."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / max(rpm, 0.1)
        self._next = 0.0
        self._paused_until = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next, self._paused_until)
            self._next = slot + self.interval
        if slot > now:
            time.sleep(slot - now)
        # A pause may have been set while we slept (another thread saw a 429).
        while True:
            with self._lock:
                left = self._paused_until - time.monotonic()
            if left <= 0:
                return
            time.sleep(left)

    def pause(self, seconds: float) -> None:
        with self._lock:
            self._paused_until = max(self._paused_until, time.monotonic() + seconds)


class RedditClient:
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

    def __init__(self, user_agent: str, client_id: str | None = None,
                 client_secret: str | None = None, rpm_oauth: float = 90,
                 rpm_public: float = 20, timeout: float = 30):
        self.ua = user_agent
        self.client_id, self.client_secret = client_id, client_secret
        self.oauth = bool(client_id and client_secret)
        self.limiter = RateLimiter(rpm_oauth if self.oauth else rpm_public)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._token: str | None = None
        self._token_exp = 0.0
        self._token_lock = threading.Lock()
        self.stats = {"requests": 0, "errors": 0, "rss_fallbacks": 0}
        self._stats_lock = threading.Lock()
        # In public mode, once JSON is refused we go straight to RSS.
        self._json_blocked = False

    @property
    def mode(self) -> str:
        return "oauth" if self.oauth else "public"

    # ------------------------------------------------------------ auth
    def _bearer(self) -> str:
        with self._token_lock:
            if self._token and time.time() < self._token_exp - 60:
                return self._token
            r = self.session.post(
                self.TOKEN_URL,
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                timeout=self.timeout,
            )
            if r.status_code != 200:
                raise RuntimeError(
                    f"Reddit OAuth token request failed ({r.status_code}): {r.text[:200]}. "
                    "Check REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET.")
            data = r.json()
            self._token = data["access_token"]
            self._token_exp = time.time() + float(data.get("expires_in", 3600))
            return self._token

    # ------------------------------------------------------------ http
    def _get(self, url: str, params: dict, auth: bool) -> requests.Response:
        """GET with rate limiting and retries. Returns the final response."""
        last: requests.Response | None = None
        for attempt in range(5):
            self.limiter.wait()
            headers = {"Authorization": f"bearer {self._bearer()}"} if auth else {}
            try:
                r = self.session.get(url, params=params, headers=headers, timeout=self.timeout)
            except requests.RequestException as exc:
                log.warning("network error %s (try %d): %s", url, attempt + 1, exc)
                self._bump("errors")
                time.sleep(2 ** attempt)
                continue
            self._bump("requests")
            self._respect_headers(r)
            if r.status_code == 401 and auth:
                self._token = None            # expired token: refresh and retry
                continue
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("Retry-After") or 2 ** (attempt + 1))
                log.info("HTTP %s on %s, waiting %.0fs", r.status_code, url, wait)
                self.limiter.pause(min(wait, 120))
                last = r
                continue
            return r
        self._bump("errors")
        return last if last is not None else requests.Response()

    def _respect_headers(self, r: requests.Response) -> None:
        try:
            remaining = float(r.headers.get("x-ratelimit-remaining", "nan"))
            reset = float(r.headers.get("x-ratelimit-reset", "nan"))
        except ValueError:
            return
        if remaining == remaining and reset == reset and remaining < 2:
            log.info("rate-limit budget used up, sleeping %.0fs", reset)
            self.limiter.pause(reset + 1)

    def _bump(self, key: str) -> None:
        with self._stats_lock:
            self.stats[key] += 1

    # ------------------------------------------------------------ health check
    def probe(self, subreddit: str) -> None:
        """One cheap request; raises RedditBlocked with a plain reason if reading
        is impossible, so a run fails in seconds instead of minutes."""
        if self.oauth:
            self._bearer()
            r = self._get(f"https://oauth.reddit.com/r/{subreddit}/new", {"limit": 1}, auth=True)
            if r.status_code != 200:
                raise RedditBlocked(f"Reddit API answered HTTP {r.status_code} for r/{subreddit}.",
                                    r.status_code)
            return
        r = self._get(f"https://www.reddit.com/r/{subreddit}/new.json", {"limit": 1}, auth=False)
        if r.status_code == 200:
            return
        self._json_blocked = True
        r = self._get(f"https://www.reddit.com/r/{subreddit}/new.rss", {"limit": 1}, auth=False)
        if r.status_code != 200 or "<entry" not in r.text:
            raise RedditBlocked(f"{PUBLIC_REFUSED_HELP} (JSON and RSS both refused, last HTTP "
                                f"{r.status_code})", r.status_code)
        log.warning("public JSON refused; using RSS feeds (no scores / comment counts)")

    # ------------------------------------------------------------ listings
    def listing(self, path: str, params: dict | None = None, *,
                stop_before: float = 0.0, max_pages: int = 10) -> Iterator[Item]:
        """Page through a listing (newest first) until items get older than
        `stop_before` (unix seconds) or `max_pages` is reached."""
        params = dict(params or {})
        params.setdefault("limit", 100)
        after = None
        for _ in range(max_pages):
            if after:
                params["after"] = after
            items, after = self._page(path, params)
            oldest = None
            for it in items:
                oldest = it.created_utc if oldest is None else min(oldest, it.created_utc)
                if it.created_utc >= stop_before:
                    yield it
            if not after or not items or (oldest is not None and oldest < stop_before):
                return

    def comments(self, post_id: str, limit: int = 200) -> list[Item]:
        """All comments of one post, flattened (no 'load more' expansion)."""
        if self.oauth or not self._json_blocked:
            r = self._json(f"/comments/{post_id}", {"limit": limit, "sort": "new", "depth": 10})
            if r is not None:
                out: list[Item] = []
                if isinstance(r, list) and len(r) > 1:
                    self._walk_comments(r[1].get("data", {}).get("children", []), out)
                return out
        items, _ = self._rss(f"/comments/{post_id}", {"limit": limit, "sort": "new"})
        return [i for i in items if i.kind == "t1"]

    def _page(self, path: str, params: dict) -> tuple[list[Item], str | None]:
        if self.oauth or not self._json_blocked:
            data = self._json(path, params)
            if data is not None:
                d = data.get("data", {}) if isinstance(data, dict) else {}
                items = [self._from_json(c) for c in d.get("children", [])]
                return [i for i in items if i], d.get("after")
        return self._rss(path, params)

    def _json(self, path: str, params: dict):
        if self.oauth:
            r = self._get("https://oauth.reddit.com" + path, {**params, "raw_json": 1}, auth=True)
        else:
            r = self._get("https://www.reddit.com" + path + ".json", {**params, "raw_json": 1}, auth=False)
        if r.status_code == 200:
            try:
                return r.json()
            except ValueError:
                pass
        if r.status_code in (403, 404) and not self.oauth:
            if r.status_code == 403 and not self._json_blocked:
                log.warning("Reddit refused the public JSON feed (403); switching to RSS feeds.")
                self._json_blocked = True
            return None
        if self.oauth:
            raise RedditBlocked(f"API request {path} failed: {_why(r.status_code)}", r.status_code)
        return None

    def _rss(self, path: str, params: dict) -> tuple[list[Item], str | None]:
        self._bump("rss_fallbacks")
        r = self._get("https://www.reddit.com" + path + ".rss", params, auth=False)
        if r.status_code != 200:
            raise RedditBlocked(f"{path}: {_why(r.status_code)}", r.status_code)
        return self._parse_atom(r.text)

    # ------------------------------------------------------------ parsing
    @staticmethod
    def _from_json(child: dict) -> Item | None:
        kind, d = child.get("kind"), child.get("data", {})
        if kind == "t3":
            return Item("t3", d["id"], d["id"], d.get("subreddit", ""), d.get("title", ""),
                        d.get("selftext", ""), _u(d.get("author")), float(d.get("created_utc", 0)),
                        "https://www.reddit.com" + d.get("permalink", ""),
                        d.get("score"), d.get("num_comments"))
        if kind == "t1":
            return Item("t1", d["id"], str(d.get("link_id", "")).removeprefix("t3_"),
                        d.get("subreddit", ""), "(comment)", d.get("body", ""), _u(d.get("author")),
                        float(d.get("created_utc", 0)),
                        "https://www.reddit.com" + d.get("permalink", ""), d.get("score"), None)
        return None

    def _walk_comments(self, children: list, out: list[Item]) -> None:
        for c in children:
            if c.get("kind") != "t1":
                continue
            it = self._from_json(c)
            if it:
                out.append(it)
            replies = c.get("data", {}).get("replies")
            if isinstance(replies, dict):
                self._walk_comments(replies.get("data", {}).get("children", []), out)

    @staticmethod
    def _parse_atom(xml_text: str) -> tuple[list[Item], str | None]:
        root = ET.fromstring(xml_text)
        items: list[Item] = []
        for e in root.findall(f"{ATOM}entry"):
            full_id = (e.findtext(f"{ATOM}id") or "").strip()
            link_el = e.find(f"{ATOM}link")
            link = link_el.get("href", "") if link_el is not None else ""
            parts = link.split("/")
            # https://www.reddit.com/r/<sub>/comments/<post>/<slug>/[<comment>/]
            sub = parts[4] if len(parts) > 4 and parts[3] == "r" else ""
            post = parts[6] if len(parts) > 6 else ""
            when = e.findtext(f"{ATOM}published") or e.findtext(f"{ATOM}updated") or ""
            try:
                ts = datetime.fromisoformat(when).timestamp()
            except ValueError:
                ts = 0.0
            author = e.findtext(f"{ATOM}author/{ATOM}name") or ""
            content = _strip_html(e.findtext(f"{ATOM}content") or "")
            title = e.findtext(f"{ATOM}title") or ""
            cat = e.find(f"{ATOM}category")
            if cat is not None and cat.get("term"):
                sub = cat.get("term")
            if full_id.startswith("t1_"):
                items.append(Item("t1", full_id[3:], post, sub, "(comment)", content,
                                  author, ts, link))
            elif full_id.startswith("t3_"):
                items.append(Item("t3", full_id[3:], full_id[3:], sub, title, content,
                                  author, ts, link))
        after = None
        if len(items) >= 25:
            last = items[-1]
            after = ("t1_" if last.kind == "t1" else "t3_") + last.id
        return items, after


def _why(status: int | None) -> str:
    if status == 429:
        return "HTTP 429 - rate-limited (too many requests); lower rpm in config.toml"
    if status in (401, 403):
        return f"HTTP {status} - refused (private/banned subreddit, or reads from this network blocked)"
    if status == 404:
        return "HTTP 404 - not found or refused"
    return f"HTTP {status} - network error" if status else "no response (network error)"


def _u(name: str | None) -> str:
    return f"/u/{name}" if name else ""


def _strip_html(html: str) -> str:
    import html as _html
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", _html.unescape(text)).strip()
