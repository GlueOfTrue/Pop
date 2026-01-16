from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

from .paths import get_catalog_path


def empty_catalog() -> dict:
    return {
        "version": 2,
        "docs": {},
    }


def load_catalog(storage_root: Path) -> dict:
    catalog_path = get_catalog_path(storage_root)
    if not catalog_path.exists():
        raise RuntimeError(f"Catalog file not found: {catalog_path}. Run init first.")
    with catalog_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_catalog(storage_root: Path, catalog: dict) -> None:
    catalog_path = get_catalog_path(storage_root)
    tmp_path = catalog_path.with_suffix(".tmp")
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=True)
    tmp_path.replace(catalog_path)


def get_doc_by_name(catalog: dict, name: str) -> Optional[Tuple[str, dict]]:
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        return None
    for doc_id, doc in docs.items():
        if isinstance(doc, dict) and doc.get("name") == name:
            return doc_id, doc
    return None


def add_doc(catalog: dict, doc_id: str, name: str) -> None:
    docs = catalog.setdefault("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")
    if doc_id in docs:
        raise ValueError(f"document id already exists: {doc_id}")
    docs[doc_id] = {"name": name, "versions": []}


def add_version(catalog: dict, doc_id: str) -> int:
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict) or doc_id not in docs:
        raise ValueError(f"document not found: {doc_id}")
    doc = docs[doc_id]
    versions = doc.setdefault("versions", [])
    if not isinstance(versions, list):
        raise ValueError("catalog format invalid: 'versions' must be a list")
    next_version = len(versions) + 1
    versions.append(next_version)
    return next_version
