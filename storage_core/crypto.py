from __future__ import annotations

import hashlib
import secrets
import zlib
from dataclasses import dataclass
from typing import BinaryIO, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .util import DEFAULT_CHUNK_SIZE

try:
    from compression import zstd as zstd_mod
except Exception:  # noqa: BLE001
    zstd_mod = None

MAGIC = b"GSB1"
FORMAT_VERSION = 2
TAG_LEN = 16
NONCE_LEN = 12
HEADER_FIXED_LEN = 9
FLAG_COMPRESSED = 0x01
COMP_ALGO_NONE = 0
COMP_ALGO_ZLIB = 1
COMP_ALGO_ZSTD = 2
ZSTD_AVAILABLE = zstd_mod is not None


@dataclass(frozen=True)
class EncryptionResult:
    plain_hash_hex: str
    plain_size: int
    enc_hash_hex: str
    enc_size: int
    compressed: bool
    compression_algo: str
    compression_level: Optional[int]
    compressed_size: int
    nonce: bytes
    tag: bytes


@dataclass(frozen=True)
class DecryptionResult:
    plain_hash_hex: str
    plain_size: int


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_version_key(master_key: bytes, doc_id: str, version: int, purpose: str) -> bytes:
    info = f"gs-backup:{doc_id}:{version}:{purpose}".encode("utf-8")
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info)
    return hkdf.derive(master_key)


def _build_header(nonce: bytes, flags: int, comp_algo: int) -> bytes:
    return MAGIC + bytes([FORMAT_VERSION, flags, len(nonce), TAG_LEN, comp_algo]) + nonce


def _read_header(in_stream: BinaryIO) -> tuple[bytes, int, int]:
    fixed = in_stream.read(HEADER_FIXED_LEN)
    if len(fixed) != HEADER_FIXED_LEN:
        raise ValueError("encrypted blob header is truncated")
    if fixed[:4] != MAGIC:
        raise ValueError("encrypted blob magic mismatch")
    version = fixed[4]
    if version not in (1, 2):
        raise ValueError(f"unsupported encrypted blob version: {version}")
    flags = fixed[5]
    nonce_len = fixed[6]
    tag_len = fixed[7]
    comp_algo = fixed[8]
    if tag_len != TAG_LEN:
        raise ValueError(f"unexpected tag length: {tag_len}")
    nonce = in_stream.read(nonce_len)
    if len(nonce) != nonce_len:
        raise ValueError("encrypted blob nonce is truncated")
    if version == 1:
        comp_algo = COMP_ALGO_ZLIB if (flags & FLAG_COMPRESSED) else COMP_ALGO_NONE
    elif not (flags & FLAG_COMPRESSED):
        if comp_algo != COMP_ALGO_NONE:
            raise ValueError("compression algo set for uncompressed payload")
        comp_algo = COMP_ALGO_NONE
    return nonce, flags, comp_algo


def encrypt_stream(
    in_stream: BinaryIO,
    out_stream: BinaryIO,
    key: bytes,
    aad: Optional[bytes],
    compression_level: Optional[int] = None,
    compression_algo: str = "zlib",
    nonce: Optional[bytes] = None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> EncryptionResult:
    if nonce is None:
        nonce = secrets.token_bytes(NONCE_LEN)
    if len(nonce) != NONCE_LEN:
        raise ValueError(f"nonce must be {NONCE_LEN} bytes")
    if compression_level is None:
        flags = 0
        comp_algo_id = COMP_ALGO_NONE
        compression_algo_used = "none"
    else:
        algo = compression_algo.lower()
        if algo == "zlib":
            comp_algo_id = COMP_ALGO_ZLIB
        elif algo == "zstd":
            if not ZSTD_AVAILABLE:
                raise ValueError("zstd compression requested but not available")
            comp_algo_id = COMP_ALGO_ZSTD
        else:
            raise ValueError(f"unsupported compression algorithm: {compression_algo}")
        flags = FLAG_COMPRESSED
        compression_algo_used = algo
    header = _build_header(nonce, flags, comp_algo_id)

    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    if aad:
        encryptor.authenticate_additional_data(aad)

    enc_hash = hashlib.sha256()
    plain_hash = hashlib.sha256()
    enc_size = 0
    plain_size = 0
    compressed_size = 0

    out_stream.write(header)
    enc_hash.update(header)
    enc_size += len(header)

    compressor = None
    if compression_level is not None:
        if comp_algo_id == COMP_ALGO_ZLIB:
            compressor = zlib.compressobj(compression_level)
        elif comp_algo_id == COMP_ALGO_ZSTD:
            compressor = zstd_mod.ZstdCompressor(level=compression_level)
        else:
            raise ValueError("compression requested but algorithm is undefined")

    while True:
        chunk = in_stream.read(chunk_size)
        if not chunk:
            break
        plain_hash.update(chunk)
        plain_size += len(chunk)

        if compressor is not None:
            comp = compressor.compress(chunk)
            if comp:
                compressed_size += len(comp)
                out = encryptor.update(comp)
                if out:
                    out_stream.write(out)
                    enc_hash.update(out)
                    enc_size += len(out)
        else:
            out = encryptor.update(chunk)
            if out:
                out_stream.write(out)
                enc_hash.update(out)
                enc_size += len(out)

    if compressor is not None:
        comp = compressor.flush()
        if comp:
            compressed_size += len(comp)
            out = encryptor.update(comp)
            if out:
                out_stream.write(out)
                enc_hash.update(out)
                enc_size += len(out)

    final = encryptor.finalize()
    if final:
        out_stream.write(final)
        enc_hash.update(final)
        enc_size += len(final)

    tag = encryptor.tag
    out_stream.write(tag)
    enc_hash.update(tag)
    enc_size += len(tag)

    return EncryptionResult(
        plain_hash_hex=plain_hash.hexdigest(),
        plain_size=plain_size,
        enc_hash_hex=enc_hash.hexdigest(),
        enc_size=enc_size,
        compressed=compression_level is not None,
        compression_algo=compression_algo_used,
        compression_level=compression_level,
        compressed_size=compressed_size,
        nonce=nonce,
        tag=tag,
    )


def decrypt_stream(
    in_stream: BinaryIO,
    out_stream: BinaryIO,
    key: bytes,
    aad: Optional[bytes],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> DecryptionResult:
    if not in_stream.seekable():
        raise ValueError("encrypted stream must be seekable")

    nonce, flags, comp_algo_id = _read_header(in_stream)
    is_compressed = bool(flags & FLAG_COMPRESSED)

    current_pos = in_stream.tell()
    in_stream.seek(0, 2)
    end_pos = in_stream.tell()
    tag_pos = end_pos - TAG_LEN
    if tag_pos < current_pos:
        raise ValueError("encrypted blob is truncated")
    in_stream.seek(tag_pos)
    tag = in_stream.read(TAG_LEN)
    if len(tag) != TAG_LEN:
        raise ValueError("encrypted blob tag is truncated")

    decryptor = Cipher(algorithms.AES(key), modes.GCM(nonce, tag)).decryptor()
    if aad:
        decryptor.authenticate_additional_data(aad)

    in_stream.seek(current_pos)
    remaining = tag_pos - current_pos

    decompressor = None
    decompressor_kind = None
    if is_compressed:
        if comp_algo_id in (COMP_ALGO_NONE, COMP_ALGO_ZLIB):
            decompressor = zlib.decompressobj()
            decompressor_kind = "zlib"
        elif comp_algo_id == COMP_ALGO_ZSTD:
            if not ZSTD_AVAILABLE:
                raise ValueError("zstd decompression requested but not available")
            decompressor = zstd_mod.ZstdDecompressor()
            decompressor_kind = "zstd"
        else:
            raise ValueError(f"unsupported compression algorithm id: {comp_algo_id}")
    plain_hash = hashlib.sha256()
    plain_size = 0

    while remaining > 0:
        to_read = min(chunk_size, remaining)
        chunk = in_stream.read(to_read)
        if not chunk:
            break
        remaining -= len(chunk)
        out = decryptor.update(chunk)
        if out:
            if decompressor is not None:
                data = decompressor.decompress(out)
            else:
                data = out
            if data:
                out_stream.write(data)
                plain_hash.update(data)
                plain_size += len(data)

    final = decryptor.finalize()
    if final:
        if decompressor is not None:
            data = decompressor.decompress(final)
        else:
            data = final
        if data:
            out_stream.write(data)
            plain_hash.update(data)
            plain_size += len(data)

    if decompressor is not None:
        if decompressor_kind == "zlib":
            data = decompressor.flush()
        else:
            try:
                data = decompressor.decompress(b"")
            except EOFError:
                data = b""
        if data:
            out_stream.write(data)
            plain_hash.update(data)
            plain_size += len(data)

    return DecryptionResult(plain_hash_hex=plain_hash.hexdigest(), plain_size=plain_size)


def derive_key_from_password(password: str) -> bytes:
    raise NotImplementedError("master password flow is not enabled yet")


def generate_recovery_key() -> str:
    raise NotImplementedError("recovery key flow is not enabled yet")


def split_key(master_key: bytes) -> dict:
    raise NotImplementedError("key split flow is not enabled yet")
