from __future__ import annotations

import json
from pathlib import Path

from .paths import CONFIG_FILENAME, INDEX_DIRNAME, INDEX_FILENAME, OBJECTS_DIRNAME
from .util import now_utc_iso


def init_storage(storage_root: Path, verbose: bool = False) -> None:
    config_path = storage_root / CONFIG_FILENAME
    index_dir = storage_root / INDEX_DIRNAME
    index_path = index_dir / INDEX_FILENAME
    objects_dir = storage_root / OBJECTS_DIRNAME

    if not storage_root.exists():
        if verbose:
            print(f"[init] Creating storage at: {storage_root}")
        storage_root.mkdir(parents=True, exist_ok=True)
    else:
        if verbose:
            print(f"[init] Storage directory already exists: {storage_root}")

    if not config_path.exists():
        config = {
            "version": 1,
            "created_at": now_utc_iso(),
            "platform": "macOS",
        }
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        if verbose:
            print(f"[init] Created config: {config_path}")
    elif verbose:
        print(f"[init] Config already exists: {config_path}")

    index_dir.mkdir(parents=True, exist_ok=True)
    if not index_path.exists():
        empty_index = {
            "version": 1,
            "files": {},
        }
        with index_path.open("w", encoding="utf-8") as f:
            json.dump(empty_index, f, indent=2, ensure_ascii=False)
        if verbose:
            print(f"[init] Created index: {index_path}")
    elif verbose:
        print(f"[init] Index already exists: {index_path}")

    objects_dir.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"[init] Objects dir: {objects_dir}")
