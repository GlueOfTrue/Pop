from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Union

DEFAULT_CHUNK_SIZE = 1024 * 1024


def isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def now_utc_iso() -> str:
    return isoformat_utc(datetime.now(timezone.utc))


def mtime_to_iso(mtime: float) -> str:
    return isoformat_utc(datetime.fromtimestamp(mtime, tz=timezone.utc))


def normalize_original_path(path: Union[str, Path]) -> str:
    return str(Path(path).expanduser().resolve())
