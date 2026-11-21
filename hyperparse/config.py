from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    raw: dict
    lookback_hours: float
    reddit_client_id: str | None = None
    reddit_client_secret: str | None = None
    user_agent: str = "python:reddit_hyperparse:v1.0 (insurance mention monitor)"
    sheet_url: str | None = None
    sheet_key: str | None = None
    output_dir: Path = field(default_factory=lambda: Path("output"))

    def __getitem__(self, key: str):
        return self.raw[key]


def load_dotenv(path: Path) -> None:
    """Tiny .env reader so local runs need no extra package."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def load(config_path: str | Path = "config.toml", lookback_hours: float | None = None) -> Settings:
    config_path = Path(config_path)
    load_dotenv(config_path.parent / ".env")
    raw = tomllib.loads(config_path.read_text(encoding="utf-8"))
    env = os.environ.get
    lb = lookback_hours or float(env("LOOKBACK_HOURS") or raw["run"]["lookback_hours"])
    return Settings(
        raw=raw,
        lookback_hours=lb,
        reddit_client_id=env("REDDIT_CLIENT_ID") or None,
        reddit_client_secret=env("REDDIT_CLIENT_SECRET") or None,
        user_agent=env("REDDIT_USER_AGENT") or Settings.user_agent,
        sheet_url=env("SHEET_WEBAPP_URL") or None,
        sheet_key=env("SHEET_KEY") or None,
        output_dir=Path(env("OUTPUT_DIR") or raw["run"].get("output_dir", "output")),
    )
