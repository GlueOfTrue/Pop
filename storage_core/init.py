from __future__ import annotations

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
from .util import atomic_write_json


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
        atomic_write_json(config_path, config)
        if verbose:
            print(f"[init] Created config: {config_path}")
    elif verbose:
        print(f"[init] Config already exists: {config_path}")

    (storage_root / CATALOG_DIRNAME).mkdir(parents=True, exist_ok=True)
    if not catalog_path.exists():
        atomic_write_json(catalog_path, empty_catalog())
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
