from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


POLL_INTERVAL_SECONDS = 0.5
DEFAULT_LLM_MODEL = "gpt-4.1-mini"
DEFAULT_DB_PATH = Path.home() / ".jp_data" / "jp.sqlite3"
DEFAULT_ENV_PATH = Path.home() / ".jp_data" / ".env"


def _resolve_db_path(override: Optional[str] = None) -> Path:
    if override:
        return Path(override).expanduser()
    env = os.environ.get("JP_DB_PATH")
    if env:
        return Path(env).expanduser()
    return DEFAULT_DB_PATH

_db_path: Path = _resolve_db_path()


def get_db_path() -> Path:
    return _db_path


def set_db_path(override: Optional[str] = None) -> None:
    global _db_path
    _db_path = _resolve_db_path(override)


def load_environment() -> None:
    load_dotenv(DEFAULT_ENV_PATH)


def configure_standard_streams() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
