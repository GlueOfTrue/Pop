from __future__ import annotations

import base64
import json
import secrets
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .paths import get_keystore_path

KDF_NAME = "scrypt"
KDF_N = 2**15
KDF_R = 8
KDF_P = 1
KEY_BYTES = 32
NONCE_BYTES = 12
AAD = b"gs-backup-master-key-v1"


def _derive_kek(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_BYTES, n=n, r=r, p=p)
    return kdf.derive(password.encode("utf-8"))


def keystore_exists(storage_root: Path) -> bool:
    return get_keystore_path(storage_root).exists()


def init_keystore(storage_root: Path, password: str) -> bytes:
    if not password:
        raise ValueError("master password is required")
    path = get_keystore_path(storage_root)
    if path.exists():
        raise RuntimeError(f"keystore already exists: {path}")

    salt = secrets.token_bytes(16)
    master_key = secrets.token_bytes(KEY_BYTES)
    kek = _derive_kek(password, salt, KDF_N, KDF_R, KDF_P)
    aesgcm = AESGCM(kek)
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, master_key, AAD)

    payload = {
        "version": 1,
        "kdf": {
            "name": KDF_NAME,
            "n": KDF_N,
            "r": KDF_R,
            "p": KDF_P,
            "salt_b64": base64.b64encode(salt).decode("ascii"),
        },
        "wrap": {
            "cipher": "AES-256-GCM",
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=True)

    return master_key


def unlock_keystore(storage_root: Path, password: str) -> bytes:
    if not password:
        raise ValueError("master password is required")
    path = get_keystore_path(storage_root)
    if not path.exists():
        raise RuntimeError(f"keystore not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    kdf = payload.get("kdf", {})
    if kdf.get("name") != KDF_NAME:
        raise ValueError("unsupported KDF in keystore")
    salt = base64.b64decode(kdf.get("salt_b64", ""))
    n = int(kdf.get("n", KDF_N))
    r = int(kdf.get("r", KDF_R))
    p = int(kdf.get("p", KDF_P))

    wrap = payload.get("wrap", {})
    nonce = base64.b64decode(wrap.get("nonce_b64", ""))
    ciphertext = base64.b64decode(wrap.get("ciphertext_b64", ""))

    kek = _derive_kek(password, salt, n, r, p)
    aesgcm = AESGCM(kek)
    return aesgcm.decrypt(nonce, ciphertext, AAD)


def get_or_init_master_key(storage_root: Path, password: str) -> bytes:
    if keystore_exists(storage_root):
        return unlock_keystore(storage_root, password)
    return init_keystore(storage_root, password)
