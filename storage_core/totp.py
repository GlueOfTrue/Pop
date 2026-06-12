from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .paths import get_totp_path
from .util import atomic_write_json, canonical_json_bytes

TOTP_VERSION = 1
AAD = b"gs-backup-totp-v1"
KEY_BYTES = 32
SALT_BYTES = 16
NONCE_BYTES = 12
DEFAULT_DIGITS = 6
DEFAULT_PERIOD = 30
DEFAULT_ALGORITHM = "SHA1"
DEFAULT_ISSUER = "gs-backup"


@dataclass(frozen=True)
class TotpConfig:
    secret_b32: str
    issuer: str
    label: str
    digits: int
    period: int
    algorithm: str


def _normalize_secret(secret: str) -> str:
    raw = secret.strip().replace(" ", "").upper()
    if not raw:
        raise ValueError("TOTP secret is empty")
    padded = raw + "=" * ((8 - (len(raw) % 8)) % 8)
    try:
        base64.b32decode(padded, casefold=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("TOTP secret is not valid Base32") from exc
    return raw


def _decode_secret(secret_b32: str) -> bytes:
    padded = secret_b32 + "=" * ((8 - (len(secret_b32) % 8)) % 8)
    return base64.b32decode(padded, casefold=True)


def generate_totp_secret() -> str:
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _derive_kek(master_key: bytes, salt: bytes) -> bytes:
    hkdf = HKDF(algorithm=hashes.SHA256(), length=KEY_BYTES, salt=salt, info=b"gs-backup:totp")
    return hkdf.derive(master_key)


def is_totp_configured(storage_root) -> bool:
    return get_totp_path(storage_root).exists()


def save_totp_config(
    storage_root,
    master_key: bytes,
    secret_b32: str,
    label: str,
    issuer: str = DEFAULT_ISSUER,
    digits: int = DEFAULT_DIGITS,
    period: int = DEFAULT_PERIOD,
    algorithm: str = DEFAULT_ALGORITHM,
) -> TotpConfig:
    secret_b32 = _normalize_secret(secret_b32)
    if not label:
        raise ValueError("TOTP label is required")
    if not issuer:
        raise ValueError("TOTP issuer is required")
    if digits < 6 or digits > 10:
        raise ValueError("TOTP digits must be between 6 and 10")
    if period < 10 or period > 120:
        raise ValueError("TOTP period must be between 10 and 120 seconds")
    algorithm = algorithm.upper()
    if algorithm not in {"SHA1", "SHA256", "SHA512"}:
        raise ValueError("TOTP algorithm must be SHA1, SHA256, or SHA512")

    cfg = TotpConfig(
        secret_b32=secret_b32,
        issuer=issuer,
        label=label,
        digits=digits,
        period=period,
        algorithm=algorithm,
    )

    salt = secrets.token_bytes(SALT_BYTES)
    kek = _derive_kek(master_key, salt)
    nonce = secrets.token_bytes(NONCE_BYTES)
    aesgcm = AESGCM(kek)
    plaintext = canonical_json_bytes(cfg.__dict__)
    ciphertext = aesgcm.encrypt(nonce, plaintext, AAD)

    payload = {
        "version": TOTP_VERSION,
        "kdf": {
            "name": "HKDF-SHA256",
            "salt_b64": base64.b64encode(salt).decode("ascii"),
        },
        "wrap": {
            "cipher": "AES-256-GCM",
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        },
    }

    path = get_totp_path(storage_root)
    atomic_write_json(path, payload)

    return cfg


def load_totp_config(storage_root, master_key: bytes) -> TotpConfig:
    path = get_totp_path(storage_root)
    if not path.exists():
        raise FileNotFoundError(f"TOTP config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    kdf = payload.get("kdf", {})
    salt = base64.b64decode(kdf.get("salt_b64", ""))
    wrap = payload.get("wrap", {})
    nonce = base64.b64decode(wrap.get("nonce_b64", ""))
    ciphertext = base64.b64decode(wrap.get("ciphertext_b64", ""))

    kek = _derive_kek(master_key, salt)
    aesgcm = AESGCM(kek)
    plaintext = aesgcm.decrypt(nonce, ciphertext, AAD)
    data = json.loads(plaintext.decode("utf-8"))
    return TotpConfig(
        secret_b32=data["secret_b32"],
        issuer=data["issuer"],
        label=data["label"],
        digits=int(data["digits"]),
        period=int(data["period"]),
        algorithm=data["algorithm"],
    )


def clear_totp_config(storage_root) -> None:
    path = get_totp_path(storage_root)
    if path.exists():
        path.unlink()


def build_totp_uri(cfg: TotpConfig) -> str:
    label = f"{cfg.issuer}:{cfg.label}" if cfg.issuer else cfg.label
    params = {
        "secret": cfg.secret_b32,
        "issuer": cfg.issuer,
        "digits": cfg.digits,
        "period": cfg.period,
        "algorithm": cfg.algorithm,
    }
    return f"otpauth://totp/{quote(label)}?{urlencode(params)}"


def _totp_code(cfg: TotpConfig, timestamp: Optional[int] = None) -> str:
    if timestamp is None:
        timestamp = int(time.time())
    counter = int(timestamp // cfg.period)
    key = _decode_secret(cfg.secret_b32)
    msg = struct.pack(">Q", counter)
    algo = cfg.algorithm.upper()
    if algo == "SHA1":
        digest = hashlib.sha1
    elif algo == "SHA256":
        digest = hashlib.sha256
    elif algo == "SHA512":
        digest = hashlib.sha512
    else:
        raise ValueError("unsupported TOTP algorithm")
    hmac_digest = hmac.new(key, msg, digest).digest()
    offset = hmac_digest[-1] & 0x0F
    part = hmac_digest[offset : offset + 4]
    code_int = struct.unpack(">I", part)[0] & 0x7FFFFFFF
    return str(code_int % (10 ** cfg.digits)).zfill(cfg.digits)


def verify_totp(code: str, cfg: TotpConfig, skew: int = 0) -> bool:
    raw = code.strip().replace(" ", "")
    if not raw.isdigit():
        return False
    if len(raw) != cfg.digits:
        return False
    now = int(time.time())
    for offset in range(-skew, skew + 1):
        ts = now + offset * cfg.period
        if hmac.compare_digest(_totp_code(cfg, ts), raw):
            return True
    return False
