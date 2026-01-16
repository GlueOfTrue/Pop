from __future__ import annotations

import json
import platform
from pathlib import Path

from .index import empty_catalog
from .paths import (
    CATALOG_DIRNAME,
    CONFIG_FILENAME,
    OBJECTS_DIRNAME,
    ECC_DIRNAME,
    RECORDS_DIRNAME,
    get_catalog_path,
    get_records_dir,
)


def init_storage(storage_root: Path, verbose: bool = False) -> None:
    config_path = storage_root / CONFIG_FILENAME
    catalog_path = get_catalog_path(storage_root)
    records_dir = get_records_dir(storage_root)
    objects_dir = storage_root / OBJECTS_DIRNAME
    ecc_dir = storage_root / ECC_DIRNAME

    if not storage_root.exists():
        if verbose:
            print(f"[init] Creating storage at: {storage_root}")
        storage_root.mkdir(parents=True, exist_ok=True)
    else:
        if verbose:
            print(f"[init] Storage directory already exists: {storage_root}")

    if not config_path.exists():
        config = {
            "version": 2,
            "platform": platform.system(),
            "crypto": {
                "scheme": "AES-256-GCM",
                "kdf": "HKDF-SHA256",
                "compression": "zlib",
            },
            "ui": {
                "lang": "ru",
            },
        }
        with config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=True)
        if verbose:
            print(f"[init] Created config: {config_path}")
    elif verbose:
        print(f"[init] Config already exists: {config_path}")

    (storage_root / CATALOG_DIRNAME).mkdir(parents=True, exist_ok=True)
    if not catalog_path.exists():
        with catalog_path.open("w", encoding="utf-8") as f:
            json.dump(empty_catalog(), f, indent=2, ensure_ascii=True)
        if verbose:
            print(f"[init] Created catalog: {catalog_path}")
    elif verbose:
        print(f"[init] Catalog already exists: {catalog_path}")

    records_dir.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"[init] Records dir: {records_dir}")

    objects_dir.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"[init] Objects dir: {objects_dir}")

    ecc_dir.mkdir(parents=True, exist_ok=True)
    if verbose:
        print(f"[init] ECC dir: {ecc_dir}")
