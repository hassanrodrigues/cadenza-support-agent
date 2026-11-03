"""Runtime configuration: model, reference time, store timezone and paths."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("America/Campo_Grande")
DEFAULT_MODEL = "anthropic/claude-haiku-5-5"

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data" / "raw"
RUNTIME_DIR = ROOT_DIR / "runtime"


def parse_now(value: str | None) -> datetime:
    """Parse an ISO 8601 reference time in store time; empty means the current time."""
    if not value:
        return datetime.now(STORE_TZ)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=STORE_TZ)
    return parsed.astimezone(STORE_TZ)


@dataclass(kw_only=True)
class Context:
    """Per-session agent context; explicit arguments win over environment variables."""

    model: str = field(default_factory=lambda: os.environ.get("MODEL") or DEFAULT_MODEL)
    # Fixed once per session so the system prompt stays identical across turns.
    now: datetime = field(
        default_factory=lambda: parse_now(os.environ.get("EMPORIO_NOW"))
    )
