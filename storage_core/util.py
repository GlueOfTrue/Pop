from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Callable, Union

DEFAULT_CHUNK_SIZE = 1024 * 1024
PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def isoformat_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def now_utc_iso() -> str:
    return isoformat_utc(datetime.now(timezone.utc))


def mtime_to_iso(mtime: float) -> str:
    return isoformat_utc(datetime.fromtimestamp(mtime, tz=timezone.utc))


def normalize_original_path(path: Union[str, Path]) -> str:
    return str(Path(path).expanduser().resolve())


def canonical_json_bytes(data: object) -> bytes:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def set_private_permissions(path: Path, *, is_dir: bool = False) -> None:
    if os.name != "posix":
        return
    try:
        path.chmod(PRIVATE_DIR_MODE if is_dir else PRIVATE_FILE_MODE)
    except OSError:
        return


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    set_private_permissions(path, is_dir=True)


def fsync_parent_dir(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        fd = os.open(path.parent, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_json(
    path: Path,
    data: object,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = True,
) -> None:
    ensure_private_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            set_private_permissions(tmp_path)
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(path)
        set_private_permissions(path)
        fsync_parent_dir(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def atomic_write_binary(
    path: Path,
    writer: Callable[[BinaryIO], None],
    *,
    overwrite: bool = True,
    private: bool = True,
    private_parent: bool = True,
) -> None:
    if private_parent:
        ensure_private_dir(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as f:
            if private:
                set_private_permissions(tmp_path)
            writer(f)
            f.flush()
            os.fsync(f.fileno())

        if path.is_symlink():
            raise RuntimeError(f"destination is a symlink: {path}")
        if path.exists():
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode):
                raise RuntimeError(f"destination exists and is not a regular file: {path}")
            if not overwrite:
                raise FileExistsError(f"destination exists: {path}")

        tmp_path.replace(path)
        if private:
            set_private_permissions(path)
        fsync_parent_dir(path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


_UNSAFE_FILENAME_CHARS = re.compile(r"[\x00-\x1f\x7f/\\:]+")


def safe_temp_basename(name: str | None, fallback: str = "document") -> str:
    raw = str(name or "").strip()
    if not raw:
        raw = fallback
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", raw)
    cleaned = cleaned.strip(" .")
    if cleaned in {"", ".", ".."}:
        cleaned = fallback
    return cleaned[:160]
