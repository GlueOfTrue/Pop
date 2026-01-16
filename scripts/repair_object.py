#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import sys
import getpass
from pathlib import Path

from storage_core.crypto import (
    FLAG_COMPRESSED,
    HEADER_FIXED_LEN,
    MAGIC,
    NONCE_LEN,
    decrypt_stream,
    derive_version_key,
    encrypt_stream,
    sha256_hex,
)
from storage_core.index import load_catalog
from storage_core.keystore import unlock_keystore
from storage_core.paths import get_record_path, get_storage_root
from storage_core.util import canonical_json_bytes


def _read_nonce_and_flags(path: Path) -> tuple[bytes, int]:
    with path.open("rb") as f:
        fixed = f.read(HEADER_FIXED_LEN)
        if len(fixed) != HEADER_FIXED_LEN:
            raise ValueError("encrypted object header is truncated")
        if fixed[:4] != MAGIC:
            raise ValueError("encrypted object magic mismatch")
        nonce_len = fixed[6]
        if nonce_len != NONCE_LEN:
            raise ValueError(f"unexpected nonce length: {nonce_len}")
        flags = fixed[5]
        nonce = f.read(nonce_len)
        if len(nonce) != nonce_len:
            raise ValueError("encrypted object nonce is truncated")
    return nonce, flags


def _load_metadata(root: Path, doc_id: str, name: str, version: int, master_key: bytes) -> dict:
    pub_bytes = canonical_json_bytes({"doc_id": doc_id, "name": name, "version": version})
    meta_key = derive_version_key(master_key, doc_id, version, "meta")
    record_path = get_record_path(root, doc_id, version)
    if not record_path.exists():
        raise FileNotFoundError(f"record not found: {record_path}")
    out = io.BytesIO()
    with record_path.open("rb") as record_file:
        decrypt_stream(record_file, out, key=meta_key, aad=pub_bytes)
    meta = json.loads(out.getvalue().decode("utf-8"))
    core = dict(meta)
    stored_hash = core.pop("meta_plain_hash", None)
    if stored_hash and sha256_hex(canonical_json_bytes(core)) != stored_hash:
        raise ValueError("metadata hash mismatch")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair an encrypted object from plaintext.")
    parser.add_argument("name", help="Document name (as shown in public catalog)")
    parser.add_argument("--version", type=int, help="Version number (default: latest)")
    parser.add_argument("--source", help="Path to plaintext file (default: metadata source_path)")
    args = parser.parse_args()

    root = get_storage_root()
    if not root.exists():
        raise SystemExit(f"Storage not found: {root}")

    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise SystemExit("Catalog is invalid: 'docs' must be an object")

    doc_id = None
    doc_entry = None
    for existing_id, entry in docs.items():
        if isinstance(entry, dict) and entry.get("name") == args.name:
            doc_id = existing_id
            doc_entry = entry
            break
    if doc_id is None or doc_entry is None:
        raise SystemExit(f"Document not found: {args.name}")

    versions = doc_entry.get("versions", [])
    if not isinstance(versions, list) or not versions:
        raise SystemExit("Document has no versions")
    version = args.version if args.version is not None else versions[-1]
    if version not in versions:
        raise SystemExit(f"Version not found: {version}")

    password = getpass.getpass("Master password: ")
    if not password:
        raise SystemExit("Master password required")

    master_key = unlock_keystore(root, password)
    meta = _load_metadata(root, doc_id, args.name, version, master_key)

    content = meta.get("content", {})
    enc_hash = content.get("enc_hash")
    if not enc_hash:
        raise SystemExit("Metadata missing content.enc_hash")

    obj_path = root / "objects" / enc_hash
    if not obj_path.exists():
        raise SystemExit(f"Object not found: {obj_path}")

    nonce, flags = _read_nonce_and_flags(obj_path)
    compressed = bool(flags & FLAG_COMPRESSED)
    compression_level = None
    if compressed:
        compression = content.get("compression", {})
        compression_level = compression.get("level")
        if compression_level is None:
            raise SystemExit("Metadata missing compression level")

    source_path = Path(args.source) if args.source else Path(meta.get("source_path", ""))
    if not source_path.exists():
        raise SystemExit(f"Source file not found: {source_path}")

    pub_bytes = canonical_json_bytes({"doc_id": doc_id, "name": args.name, "version": version})
    content_key = derive_version_key(master_key, doc_id, version, "content")

    tmp_path = obj_path.with_suffix(".repair")
    with source_path.open("rb") as src, tmp_path.open("wb") as dst:
        result = encrypt_stream(
            src,
            dst,
            key=content_key,
            aad=pub_bytes,
            compression_level=compression_level,
            nonce=nonce,
        )

    if result.enc_hash_hex != enc_hash:
        tmp_path.unlink(missing_ok=True)
        raise SystemExit(
            "Re-encryption mismatch. Source file may differ from stored version."
        )

    tmp_path.replace(obj_path)
    print(f"Repaired object: {obj_path}")
    print(f"Version: {version}  Document: {args.name}")


if __name__ == "__main__":
    main()
