from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Tuple

from .paths import OBJECTS_DIRNAME
from .util import DEFAULT_CHUNK_SIZE


def get_objects_dir(storage_root: Path) -> Path:
    return storage_root / OBJECTS_DIRNAME


def sha256_file(path: Path, chunk_size: int = DEFAULT_CHUNK_SIZE) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def store_file_object(storage_root: Path, src: Path,
                      chunk_size: int = DEFAULT_CHUNK_SIZE) -> Tuple[str, int, Path, bool]:
    """
    Stream file into objects dir, compute hash and size, ensure consistency.
    Returns (hash, size, dest_path, replaced_flag).
    """
    objects_dir = get_objects_dir(storage_root)
    objects_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=objects_dir, prefix=".tmp-")
    tmp_path = Path(tmp_name)
    h = hashlib.sha256()
    size = 0
    try:
        with os.fdopen(fd, "wb") as f_dst, src.open("rb") as f_src:
            while True:
                chunk = f_src.read(chunk_size)
                if not chunk:
                    break
                f_dst.write(chunk)
                size += len(chunk)
                h.update(chunk)
            f_dst.flush()
            os.fsync(f_dst.fileno())
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    obj_hash = h.hexdigest()
    dest = objects_dir / obj_hash

    if dest.exists():
        try:
            existing_hash = sha256_file(dest, chunk_size=chunk_size)
            existing_size = dest.stat().st_size
        except OSError:
            existing_hash = None
            existing_size = None

        if existing_hash == obj_hash and existing_size == size:
            tmp_path.unlink(missing_ok=True)
            return obj_hash, size, dest, False
        tmp_path.replace(dest)
        return obj_hash, size, dest, True

    tmp_path.replace(dest)
    return obj_hash, size, dest, True


def verify_object(storage_root: Path, entry: dict,
                  chunk_size: int = DEFAULT_CHUNK_SIZE) -> Tuple[str, str, int | None, str | None]:
    obj_hash = entry.get("hash")
    if not obj_hash:
        return "corrupted", "missing hash in entry", None, None

    obj_path = get_objects_dir(storage_root) / obj_hash
    if not obj_path.exists():
        return "missing", f"object not found: {obj_path}", None, None
    if obj_path.is_symlink():
        return "corrupted", f"object path is a symlink: {obj_path}", None, None
    if not obj_path.is_file():
        return "corrupted", f"object path is not a file: {obj_path}", None, None

    try:
        obj_stat = obj_path.stat()
    except OSError as exc:
        return "corrupted", f"cannot stat object {obj_path}: {exc}", None, None

    expected_size = entry.get("size")
    size_mismatch = expected_size is not None and obj_stat.st_size != expected_size

    try:
        actual_hash = sha256_file(obj_path, chunk_size=chunk_size)
    except OSError as exc:
        return "corrupted", f"cannot read object {obj_path}: {exc}", obj_stat.st_size, None

    if actual_hash != obj_hash:
        return "corrupted", f"hash mismatch: expected {obj_hash}, got {actual_hash}", obj_stat.st_size, actual_hash

    if size_mismatch:
        return "corrupted", f"size mismatch: expected {expected_size}, got {obj_stat.st_size}", obj_stat.st_size, actual_hash

    return "ok", "", obj_stat.st_size, actual_hash
