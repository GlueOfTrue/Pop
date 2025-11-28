from __future__ import annotations

import json
from pathlib import Path

from .paths import INDEX_DIRNAME, INDEX_FILENAME


def load_index(storage_root: Path) -> dict:
    index_path = storage_root / INDEX_DIRNAME / INDEX_FILENAME
    if not index_path.exists():
        raise RuntimeError(f"Index file not found: {index_path}. Run init first.")
    with index_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_index(storage_root: Path, index: dict) -> None:
    index_path = storage_root / INDEX_DIRNAME / INDEX_FILENAME
    tmp_path = index_path.with_suffix(".tmp")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    tmp_path.replace(index_path)
