from __future__ import annotations

"""
Placeholder crypto API for future AES-GCM integration.
Implementations will stream-encrypt/decrypt using provided key material.
"""


def encrypt_stream(in_stream, out_stream, key, metadata) -> None:
    """Encrypt in_stream -> out_stream using key and metadata as AAD."""
    ...


def decrypt_stream(in_stream, out_stream, key, metadata) -> None:
    """Decrypt in_stream -> out_stream using key and metadata as AAD."""
    ...


def derive_key_from_password(password: str) -> bytes:
    """Derive a key from a user password via KDF (e.g., PBKDF2/Argon2)."""
    ...


def generate_recovery_key() -> str:
    """Generate a human-transferable recovery key."""
    ...


def split_key(master_key: bytes) -> dict:
    """Split master key into parts for recovery flows."""
    ...
