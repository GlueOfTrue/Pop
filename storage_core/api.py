from __future__ import annotations

import io
import json
import os
import platform
import secrets
import shutil
import subprocess
import tempfile
import time
from getpass import getpass
from pathlib import Path
from typing import List, Optional

from . import init as storage_init
from .auth import require_local_auth
from .crypto import ZSTD_AVAILABLE, decrypt_stream, derive_version_key, encrypt_stream, sha256_hex
from .ecc import attempt_repair, compute_ecc
from .index import load_catalog, save_catalog
from .keystore import get_or_init_master_key, keystore_exists, unlock_keystore
from .objects import get_objects_dir, store_encrypted_object, verify_object_hash
from .paths import get_ecc_dir, get_record_path, get_storage_root
from .remote_nextcloud import push_mirror as nextcloud_push_mirror
from .remote_nextcloud import remote_status as nextcloud_remote_status
from .totp import (
    build_totp_uri,
    clear_totp_config,
    generate_totp_secret,
    is_totp_configured,
    load_totp_config,
    save_totp_config,
    verify_totp,
)
from .util import (
    atomic_write_binary,
    canonical_json_bytes,
    ensure_private_dir,
    normalize_original_path,
    safe_temp_basename,
    set_private_permissions,
    now_utc_iso,
)

FAST_ZLIB_LEVEL = 1
FAST_ZSTD_LEVEL = 3
STRONG_ZSTD_LEVEL = 19
LSOF_PATH = shutil.which("lsof")
ECC_MAX_BYTES = 1024 * 1024 * 1024
ECC_BLOCK_SIZE = 64 * 1024
ECC_STRIPE_BLOCKS = 8


def _resolve_root(storage_root: Optional[Path]) -> Path:
    return storage_root if storage_root is not None else get_storage_root()


def _public_meta(doc_id: str, name: str, version: int) -> dict:
    return {"doc_id": doc_id, "name": name, "version": version}


def _public_meta_bytes(doc_id: str, name: str, version: int) -> bytes:
    return canonical_json_bytes(_public_meta(doc_id, name, version))


def _require_auth(storage_root: Path, master_key: bytes, action: str) -> None:
    if not require_local_auth(action):
        raise PermissionError("authentication failed or canceled")
    if is_totp_configured(storage_root):
        cfg = load_totp_config(storage_root, master_key)
        code = getpass("TOTP code: ")
        if not verify_totp(code, cfg, skew=0):
            raise PermissionError("invalid TOTP code")


def _select_fast_compression() -> tuple[str, int]:
    if ZSTD_AVAILABLE:
        return "zstd", FAST_ZSTD_LEVEL
    return "zlib", FAST_ZLIB_LEVEL


def _maybe_build_ecc(storage_root: Path, obj_path: Path, enc_size: Optional[int]) -> Optional[dict]:
    if enc_size is None or enc_size > ECC_MAX_BYTES:
        return None
    ecc_info = compute_ecc(
        obj_path,
        get_ecc_dir(storage_root),
        block_size=ECC_BLOCK_SIZE,
        stripe_blocks=ECC_STRIPE_BLOCKS,
    )
    return {
        "enabled": True,
        "version": 1,
        "scheme": "xor-parity",
        "block_size": ECC_BLOCK_SIZE,
        "stripe_blocks": ECC_STRIPE_BLOCKS,
        "parity": {
            "hash": ecc_info["parity_hash"],
            "size": ecc_info["parity_size"],
        },
        "block_hashes": ecc_info["block_hashes"],
        "total_blocks": ecc_info["total_blocks"],
    }


def _attempt_ecc_repair(
    storage_root: Path,
    meta: dict,
    enc_hash: str,
    enc_size: Optional[int],
) -> dict:
    if not enc_hash:
        return {"attempted": False, "repaired": False, "reason": "missing encrypted hash"}
    ecc = meta.get("ecc")
    if not isinstance(ecc, dict) or not ecc.get("enabled"):
        return {"attempted": False, "repaired": False, "reason": "ecc not enabled"}
    if enc_size is None:
        return {"attempted": False, "repaired": False, "reason": "missing encrypted size"}
    block_hashes = ecc.get("block_hashes")
    if not isinstance(block_hashes, list):
        return {"attempted": False, "repaired": False, "reason": "missing block hashes"}
    parity = ecc.get("parity", {})
    if not isinstance(parity, dict):
        return {"attempted": False, "repaired": False, "reason": "missing parity metadata"}
    parity_hash = parity.get("hash")
    if not parity_hash:
        return {"attempted": False, "repaired": False, "reason": "missing parity hash"}

    block_size = ecc.get("block_size", ECC_BLOCK_SIZE)
    stripe_blocks = ecc.get("stripe_blocks", ECC_STRIPE_BLOCKS)
    try:
        block_size = int(block_size)
        stripe_blocks = int(stripe_blocks)
    except (TypeError, ValueError):
        return {"attempted": False, "repaired": False, "reason": "invalid ecc parameters"}

    obj_path = get_objects_dir(storage_root) / enc_hash
    parity_path = get_ecc_dir(storage_root) / parity_hash
    result = attempt_repair(
        obj_path=obj_path,
        parity_path=parity_path,
        expected_hash=enc_hash,
        parity_hash=parity_hash,
        block_hashes=block_hashes,
        block_size=block_size,
        stripe_blocks=stripe_blocks,
        total_size=enc_size,
    )
    result["attempted"] = True
    return result


def init_storage(storage_root: Optional[Path] = None, master_password: Optional[str] = None,
                 verbose: bool = False) -> Path:
    root = _resolve_root(storage_root)
    storage_init.init_storage(root, verbose=verbose)
    if master_password is None:
        if not keystore_exists(root):
            raise ValueError("master password required to initialize keystore")
        return root
    get_or_init_master_key(root, master_password)
    return root


def unlock_storage(storage_root: Optional[Path], master_password: str) -> bytes:
    root = _resolve_root(storage_root)
    return unlock_keystore(root, master_password)


def totp_is_configured(storage_root: Optional[Path]) -> bool:
    root = _resolve_root(storage_root)
    return is_totp_configured(root)


def get_totp_info(storage_root: Optional[Path], master_key: bytes) -> dict:
    root = _resolve_root(storage_root)
    _require_auth(root, master_key, "read TOTP config")
    cfg = load_totp_config(root, master_key)
    return {
        "issuer": cfg.issuer,
        "label": cfg.label,
        "digits": cfg.digits,
        "period": cfg.period,
        "algorithm": cfg.algorithm,
    }


def configure_totp(
    storage_root: Optional[Path],
    master_key: bytes,
    secret_b32: Optional[str],
    label: Optional[str],
    issuer: Optional[str] = None,
    digits: Optional[int] = None,
    period: Optional[int] = None,
    algorithm: Optional[str] = None,
) -> dict:
    root = _resolve_root(storage_root)
    _require_auth(root, master_key, "configure TOTP")

    generated = False
    if secret_b32 is None or not secret_b32.strip():
        secret_b32 = generate_totp_secret()
        generated = True

    label = (label or "gs-backup").strip()

    kwargs: dict = {}
    if issuer is not None and issuer.strip():
        kwargs["issuer"] = issuer.strip()
    if digits is not None:
        kwargs["digits"] = int(digits)
    if period is not None:
        kwargs["period"] = int(period)
    if algorithm is not None and algorithm.strip():
        kwargs["algorithm"] = algorithm.strip().upper()

    cfg = save_totp_config(root, master_key, secret_b32, label, **kwargs)
    uri = build_totp_uri(cfg)
    return {
        "configured": True,
        "generated": generated,
        "secret_b32": cfg.secret_b32,
        "issuer": cfg.issuer,
        "label": cfg.label,
        "digits": cfg.digits,
        "period": cfg.period,
        "algorithm": cfg.algorithm,
        "otpauth_uri": uri,
    }


def clear_totp(storage_root: Optional[Path], master_key: bytes) -> None:
    root = _resolve_root(storage_root)
    _require_auth(root, master_key, "disable TOTP")
    clear_totp_config(root)


def list_public(storage_root: Optional[Path]) -> dict:
    root = _resolve_root(storage_root)
    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")
    result = {}
    for doc_id, doc in docs.items():
        if not isinstance(doc, dict):
            continue
        name = doc.get("name")
        versions = doc.get("versions", [])
        if not isinstance(versions, list):
            continue
        result[doc_id] = {"name": name, "versions": list(versions)}
    return {"docs": result}


def add_file(
    storage_root: Optional[Path],
    master_key: bytes,
    file_path: Path,
    doc_name: Optional[str] = None,
    mode: str = "backup",
) -> dict:
    if mode not in ("backup", "secure"):
        raise ValueError("mode must be 'backup' or 'secure'")

    root = _resolve_root(storage_root)
    file_path = Path(file_path)
    if file_path.is_symlink():
        raise RuntimeError(f"source path is a symlink: {file_path}")
    if not file_path.exists():
        raise FileNotFoundError(file_path)
    if not file_path.is_file():
        raise ValueError(f"path is not a file: {file_path}")

    abs_path = file_path.resolve()
    doc_name = doc_name or file_path.name

    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")

    doc_id = None
    for existing_id, doc in docs.items():
        if isinstance(doc, dict) and doc.get("name") == doc_name:
            doc_id = existing_id
            break

    if doc_id is None:
        doc_id = secrets.token_hex(16)
        docs[doc_id] = {"name": doc_name, "versions": []}

    versions = docs[doc_id].get("versions", [])
    if not isinstance(versions, list):
        raise ValueError("catalog format invalid: 'versions' must be a list")
    version = len(versions) + 1

    pub_bytes = _public_meta_bytes(doc_id, doc_name, version)
    pub_hash = sha256_hex(pub_bytes)

    content_key = derive_version_key(master_key, doc_id, version, "content")
    meta_key = derive_version_key(master_key, doc_id, version, "meta")

    compression_algo, compression_level = _select_fast_compression()
    enc_result, obj_path, _replaced = store_encrypted_object(
        root,
        abs_path,
        key=content_key,
        aad=pub_bytes,
        compression_level=compression_level,
        compression_algo=compression_algo,
    )

    ecc = _maybe_build_ecc(root, obj_path, enc_result.enc_size)

    meta_core = {
        "doc_id": doc_id,
        "version": version,
        "source_path": normalize_original_path(abs_path),
        "mode": mode,
        "created_at": now_utc_iso(),
        "public_hash": pub_hash,
        "content": {
            "plain_hash": enc_result.plain_hash_hex,
            "plain_size": enc_result.plain_size,
            "enc_hash": enc_result.enc_hash_hex,
            "enc_size": enc_result.enc_size,
            "compressed": enc_result.compressed,
            "compressed_size": enc_result.compressed_size,
            "compression": {
                "algo": enc_result.compression_algo,
                "level": enc_result.compression_level,
            },
        },
    }
    if ecc is not None:
        meta_core["ecc"] = ecc
    meta_plain_hash = sha256_hex(canonical_json_bytes(meta_core))
    meta = dict(meta_core)
    meta["meta_plain_hash"] = meta_plain_hash

    record_path = get_record_path(root, doc_id, version)
    def write_record(record_file: io.BufferedWriter) -> None:
        encrypt_stream(
            io.BytesIO(canonical_json_bytes(meta)),
            record_file,
            key=meta_key,
            aad=pub_bytes,
            compression_level=None,
        )
    atomic_write_binary(record_path, write_record, overwrite=False)

    versions.append(version)
    catalog["docs"] = docs
    save_catalog(root, catalog)

    if mode == "secure":
        abs_path.unlink(missing_ok=False)

    return {
        "doc_id": doc_id,
        "name": doc_name,
        "version": version,
        "public_hash": pub_hash,
        "content_enc_hash": enc_result.enc_hash_hex,
    }


def _load_record(
    storage_root: Path,
    master_key: bytes,
    doc_id: str,
    name: str,
    version: int,
) -> dict:
    pub_bytes = _public_meta_bytes(doc_id, name, version)
    meta_key = derive_version_key(master_key, doc_id, version, "meta")
    record_path = get_record_path(storage_root, doc_id, version)
    if not record_path.exists():
        raise FileNotFoundError(f"record not found: {record_path}")

    out = io.BytesIO()
    with record_path.open("rb") as record_file:
        decrypt_stream(record_file, out, key=meta_key, aad=pub_bytes)
    meta = json.loads(out.getvalue().decode("utf-8"))

    stored_hash = meta.get("meta_plain_hash")
    core = dict(meta)
    core.pop("meta_plain_hash", None)
    if sha256_hex(canonical_json_bytes(core)) != stored_hash:
        raise ValueError("metadata hash mismatch")

    if meta.get("public_hash") != sha256_hex(pub_bytes):
        raise ValueError("public metadata hash mismatch")

    return meta


def get_metadata(
    storage_root: Optional[Path],
    master_key: bytes,
    doc_name: str,
    version: Optional[int] = None,
) -> dict:
    root = _resolve_root(storage_root)
    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")

    doc_id = None
    doc = None
    for existing_id, entry in docs.items():
        if isinstance(entry, dict) and entry.get("name") == doc_name:
            doc_id = existing_id
            doc = entry
            break
    if doc_id is None or doc is None:
        raise FileNotFoundError(f"document not found: {doc_name}")

    versions = doc.get("versions", [])
    if not isinstance(versions, list) or not versions:
        raise RuntimeError("document has no versions")

    version_idx = version if version is not None else versions[-1]
    if version_idx not in versions:
        raise ValueError(f"version not found: {version_idx}")

    _require_auth(root, master_key, "access hidden metadata")
    return _load_record(root, master_key, doc_id, doc_name, version_idx)


def verify_storage(
    storage_root: Optional[Path],
    master_key: bytes,
    deep: bool = False,
) -> dict:
    root = _resolve_root(storage_root)
    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")

    _require_auth(root, master_key, "verify storage")
    results: List[dict] = []
    summary = {"OK": 0, "CORRUPTED": 0, "MISSING": 0}

    for doc_id, doc in docs.items():
        if not isinstance(doc, dict):
            continue
        name = doc.get("name", doc_id)
        versions = doc.get("versions", [])
        if not isinstance(versions, list) or not versions:
            continue

        for version in versions:
            try:
                meta = _load_record(root, master_key, doc_id, name, version)
                content = meta.get("content", {})
                enc_hash = content.get("enc_hash")
                enc_size = content.get("enc_size")
                status, reason, _size, _hash = verify_object_hash(
                    root,
                    enc_hash,
                    expected_size=enc_size,
                )
                repaired = False
                reasons: List[str] = []
                if status != "ok":
                    reasons.append(reason)
                    if status == "corrupted":
                        ecc_result = _attempt_ecc_repair(root, meta, enc_hash, enc_size)
                        if ecc_result.get("attempted"):
                            if ecc_result.get("repaired"):
                                status, reason, _size, _hash = verify_object_hash(
                                    root,
                                    enc_hash,
                                    expected_size=enc_size,
                                )
                                if status == "ok":
                                    repaired = True
                                else:
                                    reasons.append(reason)
                            else:
                                reasons.append(f"ecc: {ecc_result.get('reason')}")
                    if status != "ok":
                        summary[status.upper()] += 1
                        results.append({
                            "doc": name,
                            "version": version,
                            "status": status.upper(),
                            "reasons": reasons,
                        })
                        continue
                if deep:
                    _ = _decrypt_content_to_sink(root, master_key, doc_id, name, version, meta)
                summary["OK"] += 1
                results.append({
                    "doc": name,
                    "version": version,
                    "status": "OK",
                    "reasons": ["repaired via ecc"] if repaired else [],
                })
            except FileNotFoundError as exc:
                summary["MISSING"] += 1
                results.append({
                    "doc": name,
                    "version": version,
                    "status": "MISSING",
                    "reasons": [str(exc)],
                })
            except Exception as exc:  # noqa: BLE001
                summary["CORRUPTED"] += 1
                results.append({
                    "doc": name,
                    "version": version,
                    "status": "CORRUPTED",
                    "reasons": [str(exc)],
                })

    return {"summary": summary, "results": results}


def _decrypt_content_to_sink(
    storage_root: Path,
    master_key: bytes,
    doc_id: str,
    name: str,
    version: int,
    meta: dict,
    out_stream: Optional[io.BufferedWriter] = None,
) -> dict:
    content = meta.get("content", {})
    enc_hash = content.get("enc_hash")
    enc_size = content.get("enc_size")
    if not enc_hash:
        raise ValueError("metadata missing content.enc_hash")

    status, reason, _size, _hash = verify_object_hash(
        storage_root,
        enc_hash,
        expected_size=enc_size,
    )
    if status != "ok":
        if status == "corrupted":
            ecc_result = _attempt_ecc_repair(storage_root, meta, enc_hash, enc_size)
            if ecc_result.get("repaired"):
                status, reason, _size, _hash = verify_object_hash(
                    storage_root,
                    enc_hash,
                    expected_size=enc_size,
                )
        if status != "ok":
            if status == "missing":
                raise FileNotFoundError(
                    f"object not found: {get_objects_dir(storage_root) / enc_hash}"
                )
            raise ValueError(f"encrypted object corrupted: {reason}")

    obj_path = get_objects_dir(storage_root) / enc_hash

    pub_bytes = _public_meta_bytes(doc_id, name, version)
    content_key = derive_version_key(master_key, doc_id, version, "content")

    if out_stream is None:
        out_stream = io.BytesIO()

    with obj_path.open("rb") as src:
        result = decrypt_stream(src, out_stream, key=content_key, aad=pub_bytes)

    expected_hash = content.get("plain_hash")
    expected_size = content.get("plain_size")
    if expected_hash and result.plain_hash_hex != expected_hash:
        raise ValueError("content hash mismatch")
    if expected_size is not None and result.plain_size != expected_size:
        raise ValueError("content size mismatch")

    return {"plain_hash": result.plain_hash_hex, "plain_size": result.plain_size}


def _wait_for_file_open(path: Path, timeout: float = 5.0, interval: float = 0.2) -> bool:
    if not LSOF_PATH or not Path(LSOF_PATH).exists():
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc = subprocess.run(
            [LSOF_PATH, "-t", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return True
        if proc.returncode not in (0, 1):
            break
        time.sleep(interval)
    return False


def _wait_for_file_open_pids(
    path: Path, timeout: float = 5.0, interval: float = 0.2
) -> list[int]:
    if not LSOF_PATH or not Path(LSOF_PATH).exists():
        return []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc = subprocess.run(
            [LSOF_PATH, "-t", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            pids = [int(line) for line in proc.stdout.splitlines() if line.strip().isdigit()]
            if pids:
                return pids
        elif proc.returncode not in (0, 1):
            break
        time.sleep(interval)
    return []


def _pid_start_time(pid: int) -> Optional[str]:
    proc = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    value = proc.stdout.strip()
    return value if value else None


def _wait_for_file_close(path: Path, interval: float = 0.5) -> bool:
    if not LSOF_PATH or not Path(LSOF_PATH).exists():
        return False
    while True:
        proc = subprocess.run(
            [LSOF_PATH, "-t", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 1 or not proc.stdout.strip():
            return True
        if proc.returncode not in (0, 1):
            return False
        time.sleep(interval)


def restore_file(
    storage_root: Optional[Path],
    master_key: bytes,
    doc_name: str,
    dest_path: Optional[Path],
    version: Optional[int] = None,
    force: bool = False,
) -> dict:
    root = _resolve_root(storage_root)
    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")

    doc_id = None
    doc = None
    for existing_id, entry in docs.items():
        if isinstance(entry, dict) and entry.get("name") == doc_name:
            doc_id = existing_id
            doc = entry
            break
    if doc_id is None or doc is None:
        raise FileNotFoundError(f"document not found: {doc_name}")

    versions = doc.get("versions", [])
    if not isinstance(versions, list) or not versions:
        raise RuntimeError("document has no versions")

    version_idx = version if version is not None else versions[-1]
    if version_idx not in versions:
        raise ValueError(f"version not found: {version_idx}")

    _require_auth(root, master_key, "restore file")
    meta = _load_record(root, master_key, doc_id, doc_name, version_idx)

    if dest_path is None:
        dest_path = meta.get("source_path")
        if not dest_path:
            raise ValueError("metadata missing source_path for restore")

    dest = Path(dest_path).expanduser().absolute()
    if dest.is_symlink():
        raise RuntimeError(f"destination is a symlink: {dest}")
    if dest.parent.exists() and dest.parent.is_symlink():
        raise RuntimeError(f"destination parent is a symlink: {dest.parent}")
    if dest.exists():
        if dest.is_dir():
            raise IsADirectoryError(dest)
        if not dest.is_file():
            raise RuntimeError(f"destination exists and is not a regular file: {dest}")
        if not force:
            raise FileExistsError(f"destination exists: {dest}")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)

    def write_restore(out: io.BufferedWriter) -> None:
        _decrypt_content_to_sink(root, master_key, doc_id, doc_name, version_idx, meta, out_stream=out)
    atomic_write_binary(dest, write_restore, overwrite=force, private_parent=False)

    return {"doc": doc_name, "version": version_idx, "destination": str(dest)}


def open_file(
    storage_root: Optional[Path],
    master_key: bytes,
    doc_name: str,
    version: Optional[int] = None,
    force: bool = False,
    paranoid: bool = False,
) -> dict:
    root = _resolve_root(storage_root)
    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")

    doc_id = None
    doc = None
    for existing_id, entry in docs.items():
        if isinstance(entry, dict) and entry.get("name") == doc_name:
            doc_id = existing_id
            doc = entry
            break
    if doc_id is None or doc is None:
        raise FileNotFoundError(f"document not found: {doc_name}")

    versions = doc.get("versions", [])
    if not isinstance(versions, list) or not versions:
        raise RuntimeError("document has no versions")

    version_idx = version if version is not None else versions[-1]
    if version_idx not in versions:
        raise ValueError(f"version not found: {version_idx}")

    _require_auth(root, master_key, "open file")
    meta = _load_record(root, master_key, doc_id, doc_name, version_idx)

    tmpdir = Path(tempfile.mkdtemp(prefix="gs-backup-open-"))
    ensure_private_dir(tmpdir)
    basename = safe_temp_basename(doc_name, fallback=f"{doc_id}-{version_idx}")
    dest = tmpdir / basename

    fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        set_private_permissions(dest)
        _decrypt_content_to_sink(root, master_key, doc_id, doc_name, version_idx, meta, out_stream=out)

    try:
        system = platform.system()
        if system == "Darwin":
            open_args = ["open", str(dest)] if paranoid else ["open", "-W", str(dest)]
        elif system == "Linux":
            opener = shutil.which("xdg-open") or shutil.which("gio")
            if not opener:
                raise RuntimeError("no opener found (xdg-open/gio)")
            open_args = ["gio", "open", str(dest)] if Path(opener).name == "gio" else [opener, str(dest)]
        else:
            raise RuntimeError(f"unsupported platform: {system}")
        proc = subprocess.run(open_args, check=False)
        launched = proc.returncode == 0
    except FileNotFoundError as exc:
        raise RuntimeError("viewer command not found") from exc

    cleaned = False
    unlinked = False
    opened = False
    viewer_pids: list[dict] = []
    system = platform.system()
    if paranoid and launched:
        pid_list = _wait_for_file_open_pids(dest)
        opened = bool(pid_list)
        viewer_pids = [{"pid": pid, "start": _pid_start_time(pid)} for pid in pid_list]
        if opened:
            try:
                dest.unlink()
                unlinked = True
            except OSError:
                unlinked = False
        if unlinked:
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
                cleaned = True
            except OSError:
                cleaned = False
    elif paranoid:
        try:
            dest.unlink()
            unlinked = True
        except OSError:
            unlinked = False
    elif system == "Linux":
        pid_list = _wait_for_file_open_pids(dest)
        opened = bool(pid_list)
        viewer_pids = [{"pid": pid, "start": _pid_start_time(pid)} for pid in pid_list]
        if opened:
            closed = _wait_for_file_close(dest)
            if closed:
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                    cleaned = True
                except OSError:
                    cleaned = False
                viewer_pids = []
    else:
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
            cleaned = True
        except OSError:
            cleaned = False

    if not launched and not force:
        raise RuntimeError(f"failed to launch viewer (exit {proc.returncode})")

    return {
        "doc": doc_name,
        "version": version_idx,
        "path": str(dest),
        "launched": launched,
        "returncode": proc.returncode,
        "tempdir": str(tmpdir),
        "cleaned": cleaned,
        "unlinked": unlinked,
        "opened": opened,
        "viewer_pids": viewer_pids,
    }


def get_stats(storage_root: Optional[Path], master_key: bytes) -> dict:
    root = _resolve_root(storage_root)
    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")

    _require_auth(root, master_key, "read storage stats")

    doc_count = 0
    version_count = 0
    referenced_hashes = set()
    referenced_parity = set()

    for doc_id, doc in docs.items():
        if not isinstance(doc, dict):
            continue
        name = doc.get("name", doc_id)
        versions = doc.get("versions", [])
        if not isinstance(versions, list) or not versions:
            continue
        doc_count += 1
        for version in versions:
            meta = _load_record(root, master_key, doc_id, name, version)
            content = meta.get("content", {})
            enc_hash = content.get("enc_hash")
            if enc_hash:
                referenced_hashes.add(enc_hash)
            ecc = meta.get("ecc")
            if isinstance(ecc, dict) and ecc.get("enabled"):
                parity = ecc.get("parity", {})
                if isinstance(parity, dict):
                    parity_hash = parity.get("hash")
                    if parity_hash:
                        referenced_parity.add(parity_hash)
            version_count += 1

    objects_dir = get_objects_dir(root)
    objects = []
    if objects_dir.exists():
        for obj in objects_dir.iterdir():
            if obj.is_file() and not obj.is_symlink():
                objects.append(obj)

    total_size = sum(p.stat().st_size for p in objects)
    ecc_dir = get_ecc_dir(root)
    ecc_objects = []
    if ecc_dir.exists():
        for obj in ecc_dir.iterdir():
            if obj.is_file() and not obj.is_symlink():
                ecc_objects.append(obj)
    ecc_total_size = sum(p.stat().st_size for p in ecc_objects)
    return {
        "documents": doc_count,
        "versions_total": version_count,
        "unique_objects": len(referenced_hashes),
        "objects_on_disk": len(objects),
        "objects_dir_size": total_size,
        "ecc_unique": len(referenced_parity),
        "ecc_objects_on_disk": len(ecc_objects),
        "ecc_dir_size": ecc_total_size,
    }


def prune_objects(storage_root: Optional[Path], master_key: bytes, aggressive: bool = False) -> dict:
    root = _resolve_root(storage_root)
    catalog = load_catalog(root)
    docs = catalog.get("docs", {})
    if not isinstance(docs, dict):
        raise ValueError("catalog format invalid: 'docs' must be an object")

    _require_auth(root, master_key, "prune storage")

    referenced_hashes = set()
    referenced_parity = set()
    removed_versions = 0
    removed_records = 0
    removed_docs = 0
    removed_record_dirs = 0
    repaired_versions = 0
    kept_problem_versions = 0
    corrupted_versions = 0
    uncertain_references = False

    for doc_id, doc in list(docs.items()):
        if not isinstance(doc, dict):
            continue
        name = doc.get("name", doc_id)
        versions = doc.get("versions", [])
        if not isinstance(versions, list):
            continue

        kept_versions: List[int] = []
        for version in versions:
            record_path = get_record_path(root, doc_id, version)
            try:
                meta = _load_record(root, master_key, doc_id, name, version)
            except FileNotFoundError:
                if aggressive:
                    removed_versions += 1
                    if record_path.exists():
                        try:
                            record_path.unlink()
                            removed_records += 1
                        except OSError:
                            pass
                else:
                    kept_problem_versions += 1
                    uncertain_references = True
                    kept_versions.append(version)
                continue
            except Exception:
                if aggressive:
                    removed_versions += 1
                    if record_path.exists():
                        try:
                            record_path.unlink()
                            removed_records += 1
                        except OSError:
                            pass
                else:
                    kept_problem_versions += 1
                    uncertain_references = True
                    kept_versions.append(version)
                continue

            content = meta.get("content", {})
            enc_hash = content.get("enc_hash")
            enc_size = content.get("enc_size")
            if not enc_hash:
                if aggressive:
                    removed_versions += 1
                    try:
                        record_path.unlink()
                        removed_records += 1
                    except OSError:
                        pass
                else:
                    kept_problem_versions += 1
                    uncertain_references = True
                    kept_versions.append(version)
                continue

            referenced_hashes.add(enc_hash)
            ecc = meta.get("ecc")
            if isinstance(ecc, dict) and ecc.get("enabled"):
                parity = ecc.get("parity", {})
                if isinstance(parity, dict):
                    parity_hash = parity.get("hash")
                    if parity_hash:
                        referenced_parity.add(parity_hash)

            status, _reason, _size, _hash = verify_object_hash(
                root,
                enc_hash,
                expected_size=enc_size,
            )
            if status != "ok":
                if status == "corrupted":
                    ecc_result = _attempt_ecc_repair(root, meta, enc_hash, enc_size)
                    if ecc_result.get("repaired"):
                        status, _reason, _size, _hash = verify_object_hash(
                            root,
                            enc_hash,
                            expected_size=enc_size,
                        )
                        if status == "ok":
                            repaired_versions += 1
                if status != "ok":
                    corrupted_versions += 1
                    if aggressive:
                        removed_versions += 1
                        try:
                            record_path.unlink()
                            removed_records += 1
                        except OSError:
                            pass
                    else:
                        kept_problem_versions += 1
                        kept_versions.append(version)
                    continue

            kept_versions.append(version)

        if kept_versions:
            doc["versions"] = kept_versions
        else:
            removed_docs += 1
            docs.pop(doc_id, None)
            record_dir = get_record_path(root, doc_id, 1).parent
            try:
                record_dir.rmdir()
                removed_record_dirs += 1
            except OSError:
                pass

    if removed_versions or removed_docs:
        catalog["docs"] = docs
        save_catalog(root, catalog)

    objects_dir = get_objects_dir(root)
    removed = 0
    failed = 0
    skipped_symlinks = 0
    if objects_dir.exists():
        for obj in objects_dir.iterdir():
            if obj.is_symlink():
                skipped_symlinks += 1
                continue
            if obj.is_file() and obj.name not in referenced_hashes and not uncertain_references:
                try:
                    obj.unlink()
                    removed += 1
                except OSError:
                    failed += 1

    ecc_dir = get_ecc_dir(root)
    ecc_removed = 0
    ecc_failed = 0
    ecc_skipped_symlinks = 0
    if ecc_dir.exists():
        for obj in ecc_dir.iterdir():
            if obj.is_symlink():
                ecc_skipped_symlinks += 1
                continue
            if obj.is_file() and obj.name not in referenced_parity and not uncertain_references:
                try:
                    obj.unlink()
                    ecc_removed += 1
                except OSError:
                    ecc_failed += 1

    return {
        "removed": removed,
        "failed": failed,
        "skipped_symlinks": skipped_symlinks,
        "versions_removed": removed_versions,
        "records_removed": removed_records,
        "docs_removed": removed_docs,
        "record_dirs_removed": removed_record_dirs,
        "versions_repaired": repaired_versions,
        "versions_kept_problem": kept_problem_versions,
        "versions_corrupted": corrupted_versions,
        "prune_blocked_by_uncertain_references": uncertain_references,
        "ecc_removed": ecc_removed,
        "ecc_failed": ecc_failed,
        "ecc_skipped_symlinks": ecc_skipped_symlinks,
    }


def remote_status(storage_root: Optional[Path]) -> dict:
    root = _resolve_root(storage_root)
    return nextcloud_remote_status(root)


def push_remote_mirror(storage_root: Optional[Path], master_key: bytes) -> dict:
    root = _resolve_root(storage_root)
    _require_auth(root, master_key, "push remote mirror")
    return nextcloud_push_mirror(root)
