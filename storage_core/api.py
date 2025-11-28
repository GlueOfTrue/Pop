from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from . import init as storage_init
from .index import load_index, save_index
from .objects import (
    get_objects_dir,
    store_file_object,
    verify_object,
)
from .paths import get_storage_root
from .util import DEFAULT_CHUNK_SIZE, mtime_to_iso, normalize_original_path, now_utc_iso


def _resolve_root(storage_root: Optional[Path]) -> Path:
    return storage_root if storage_root is not None else get_storage_root()


def init_storage(storage_root: Optional[Path] = None, verbose: bool = False) -> Path:
    root = _resolve_root(storage_root)
    storage_init.init_storage(root, verbose=verbose)
    return root


def add_file(storage_root: Optional[Path], file_path: Path) -> dict:
    root = _resolve_root(storage_root)
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    if not file_path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")

    abs_path = file_path.resolve()
    obj_hash, size, _, _replaced = store_file_object(root, abs_path)

    index = load_index(root)
    files = index.setdefault("files", {})
    versions = files.setdefault(str(abs_path), [])

    entry = {
        "hash": obj_hash,
        "size": size,
        "mtime": mtime_to_iso(abs_path.stat().st_mtime),
        "stored_at": now_utc_iso(),
        "rel_path": str(file_path),
        "plain_hash": None,
        "enc_hash": None,
        "encryption_scheme_version": None,
    }
    versions.append(entry)
    save_index(root, index)
    return entry


def list_files(storage_root: Optional[Path]) -> dict:
    root = _resolve_root(storage_root)
    return load_index(root)


def verify_storage(storage_root: Optional[Path],
                   target_paths: Optional[Iterable[str]] = None) -> dict:
    root = _resolve_root(storage_root)
    index = load_index(root)
    files = index.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("index format invalid: 'files' must be an object")

    targets = {normalize_original_path(p) for p in target_paths} if target_paths else set()

    summary = {"OK": 0, "MISSING": 0, "CORRUPTED": 0}
    results: List[dict] = []
    processed_any = False
    index_changed = False

    for original_path, versions in files.items():
        if targets and original_path not in targets:
            continue

        processed_any = True

        if not isinstance(versions, list) or not versions:
            summary["CORRUPTED"] += 1
            results.append({"path": original_path, "status": "CORRUPTED",
                            "reasons": ["invalid or empty versions list"]})
            continue

        missing = False
        corrupted = False
        reasons: List[str] = []
        for idx, entry in enumerate(versions, start=1):
            status, reason, actual_size, actual_hash = verify_object(root, entry)

            if status == "corrupted" and reason.startswith("size mismatch") and actual_hash == entry.get("hash"):
                if actual_size is not None:
                    entry["size"] = actual_size
                    status = "ok"
                    reason = f"fixed size metadata to {actual_size}"
                    reasons.append(f"v{idx}: {reason}")
                    index_changed = True
                    continue

            if status == "missing":
                missing = True
            elif status == "corrupted":
                corrupted = True
            if status != "ok" and reason:
                reasons.append(f"v{idx}: {reason}")

        if missing:
            status = "MISSING"
            summary["MISSING"] += 1
        elif corrupted:
            status = "CORRUPTED"
            summary["CORRUPTED"] += 1
        else:
            status = "OK"
            summary["OK"] += 1

        results.append({"path": original_path, "status": status, "reasons": reasons})

    if targets:
        missing_targets = targets - set(files.keys())
        for path in missing_targets:
            summary["MISSING"] += 1
            results.append({"path": path, "status": "MISSING", "reasons": ["not in index"]})

    if not processed_any and targets:
        summary["MISSING"] = max(summary["MISSING"], 1)

    if index_changed:
        save_index(root, index)

    return {"summary": summary, "results": results, "index_updated": index_changed}


def restore_file(storage_root: Optional[Path], source_path: str, dest_path: Path,
                 version: Optional[int] = None, force: bool = False) -> dict:
    root = _resolve_root(storage_root)
    index = load_index(root)

    files = index.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("index format invalid: 'files' must be an object")
    if not files:
        raise FileNotFoundError("storage is empty")

    original_path = normalize_original_path(source_path)
    versions = files.get(original_path)
    if not versions:
        raise FileNotFoundError(f"not found in index: {original_path}")
    if not isinstance(versions, list):
        raise ValueError(f"index entry for {original_path} is invalid")

    version_idx = version if version is not None else len(versions)
    if version_idx < 1 or version_idx > len(versions):
        raise ValueError(f"version must be between 1 and {len(versions)}")

    entry = versions[version_idx - 1]
    status, reason, _actual_size, _actual_hash = verify_object(root, entry)
    if status != "ok":
        raise RuntimeError(f"object failed verification: {reason}")

    dest = Path(dest_path).expanduser().absolute()
    if dest.exists():
        if dest.is_dir():
            raise IsADirectoryError(dest)
        if dest.is_symlink():
            raise RuntimeError(f"destination is a symlink: {dest}")
        if not dest.is_file():
            raise RuntimeError(f"destination exists and is not a regular file: {dest}")
        if not force:
            raise FileExistsError(f"destination exists: {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)

    obj_path = get_objects_dir(root) / entry["hash"]
    with obj_path.open("rb") as src, dest.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=DEFAULT_CHUNK_SIZE)

    return {"restored_from": original_path, "version": version_idx, "destination": str(dest)}


def open_file(storage_root: Optional[Path], source_path: str,
              version: Optional[int] = None, force: bool = False) -> dict:
    """
    Restore a version into a temp file and launch it with the default macOS app.
    """
    root = _resolve_root(storage_root)
    index = load_index(root)

    files = index.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("index format invalid: 'files' must be an object")
    if not files:
        raise FileNotFoundError("storage is empty")

    original_path = normalize_original_path(source_path)
    versions = files.get(original_path)
    if not versions:
        raise FileNotFoundError(f"not found in index: {original_path}")
    if not isinstance(versions, list):
        raise ValueError(f"index entry for {original_path} is invalid")

    version_idx = version if version is not None else len(versions)
    if version_idx < 1 or version_idx > len(versions):
        raise ValueError(f"version must be between 1 and {len(versions)}")

    entry = versions[version_idx - 1]
    status, reason, _actual_size, _actual_hash = verify_object(root, entry)
    if status != "ok" and not force:
        raise RuntimeError(f"object failed verification: {reason}")

    tmpdir = Path(tempfile.mkdtemp(prefix="gs-backup-open-"))
    basename = Path(original_path).name or entry["hash"]
    dest = tmpdir / basename

    obj_path = get_objects_dir(root) / entry["hash"]
    with obj_path.open("rb") as src, dest.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=DEFAULT_CHUNK_SIZE)

    try:
        proc = subprocess.run(["open", str(dest)], check=False)
        launched = proc.returncode == 0
        return {
            "path": str(dest),
            "version": version_idx,
            "launched": launched,
            "returncode": proc.returncode,
            "tempdir": str(tmpdir),
            "verification": status,
            "verification_reason": reason,
        }
    except FileNotFoundError as exc:
        raise RuntimeError("macOS 'open' command not found") from exc


def get_stats(storage_root: Optional[Path]) -> dict:
    root = _resolve_root(storage_root)
    index = load_index(root)

    files = index.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("index format invalid: 'files' must be an object")

    objects_dir = get_objects_dir(root)
    if objects_dir.is_symlink():
        raise RuntimeError(f"objects directory is a symlink: {objects_dir}")

    referenced_hashes: set[str] = set()
    versions_count = 0
    invalid_entries = 0
    for versions in files.values():
        if not isinstance(versions, list):
            invalid_entries += 1
            continue
        versions_count += len(versions)
        for entry in versions:
            h = entry.get("hash")
            if isinstance(h, str):
                referenced_hashes.add(h)

    objects_count = 0
    objects_total_size = 0
    largest_object = (None, 0)

    if objects_dir.exists() and objects_dir.is_dir():
        for obj in objects_dir.iterdir():
            if not obj.is_file():
                continue
            try:
                size = obj.stat().st_size
            except OSError:
                continue
            objects_count += 1
            objects_total_size += size
            if size > largest_object[1]:
                largest_object = (obj.name, size)
    else:
        objects_dir = None

    avg_size = objects_total_size / objects_count if objects_count else 0
    duplication = (versions_count / len(referenced_hashes)) if referenced_hashes else 0

    return {
        "source_paths": len(files),
        "versions_total": versions_count,
        "invalid_entries": invalid_entries,
        "unique_objects": len(referenced_hashes),
        "objects_on_disk": objects_count,
        "objects_dir_size": objects_total_size,
        "largest_object": largest_object,
        "avg_size": avg_size,
        "duplication_ratio": duplication,
        "objects_dir_exists": objects_dir is not None,
    }


def prune_objects(storage_root: Optional[Path]) -> dict:
    root = _resolve_root(storage_root)
    index = load_index(root)

    files = index.get("files", {})
    if not isinstance(files, dict):
        raise ValueError("index format invalid: 'files' must be an object")

    referenced_hashes: set[str] = set()
    for versions in files.values():
        if not isinstance(versions, list):
            continue
        for entry in versions:
            h = entry.get("hash")
            if isinstance(h, str):
                referenced_hashes.add(h)

    objects_dir = get_objects_dir(root)
    if not objects_dir.exists():
        return {"removed": 0, "failed": 0, "skipped_symlinks": 0}
    if objects_dir.is_symlink():
        raise RuntimeError(f"objects directory is a symlink: {objects_dir}")
    if not objects_dir.is_dir():
        raise RuntimeError(f"objects path is not a directory: {objects_dir}")

    unreferenced: List[Path] = []
    for obj in objects_dir.iterdir():
        if not obj.is_file():
            continue
        if obj.name not in referenced_hashes:
            unreferenced.append(obj)

    removed = 0
    failed = 0
    skipped_symlinks = 0
    for obj_path in unreferenced:
        if obj_path.is_symlink():
            skipped_symlinks += 1
            continue
        try:
            obj_path.unlink()
            removed += 1
        except OSError:
            failed += 1

    return {"removed": removed, "failed": failed, "skipped_symlinks": skipped_symlinks}
