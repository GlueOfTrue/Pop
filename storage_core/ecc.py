from __future__ import annotations

import hashlib
import math
import os
import tempfile
from pathlib import Path
from typing import List

from .objects import sha256_file


def _xor_into(parity: bytearray, block: bytes) -> None:
    view = memoryview(parity)
    for i, b in enumerate(block):
        view[i] ^= b


def compute_ecc(
    obj_path: Path,
    ecc_dir: Path,
    block_size: int,
    stripe_blocks: int,
) -> dict:
    if block_size <= 0 or stripe_blocks <= 0:
        raise ValueError("block_size and stripe_blocks must be positive")
    if not obj_path.exists():
        raise FileNotFoundError(obj_path)

    ecc_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=ecc_dir, prefix=".tmp-")
    tmp_path = Path(tmp_name)

    block_hashes: List[str] = []
    parity_hash = hashlib.sha256()
    parity_size = 0

    parity = bytearray(block_size)
    blocks_in_stripe = 0
    total_blocks = 0

    try:
        with os.fdopen(fd, "wb") as dst, obj_path.open("rb") as src:
            while True:
                block = src.read(block_size)
                if not block:
                    break
                block_hashes.append(hashlib.sha256(block).hexdigest())
                _xor_into(parity, block)
                blocks_in_stripe += 1
                total_blocks += 1
                if blocks_in_stripe == stripe_blocks:
                    dst.write(parity)
                    parity_hash.update(parity)
                    parity_size += block_size
                    parity = bytearray(block_size)
                    blocks_in_stripe = 0
            if blocks_in_stripe:
                dst.write(parity)
                parity_hash.update(parity)
                parity_size += block_size
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise

    parity_hash_hex = parity_hash.hexdigest()
    parity_path = ecc_dir / parity_hash_hex

    if parity_path.exists():
        try:
            existing_hash = sha256_file(parity_path)
            existing_size = parity_path.stat().st_size
        except OSError:
            existing_hash = None
            existing_size = None
        if existing_hash == parity_hash_hex and existing_size == parity_size:
            tmp_path.unlink(missing_ok=True)
        else:
            tmp_path.replace(parity_path)
    else:
        tmp_path.replace(parity_path)

    return {
        "parity_hash": parity_hash_hex,
        "parity_size": parity_size,
        "block_hashes": block_hashes,
        "total_blocks": total_blocks,
    }


def attempt_repair(
    obj_path: Path,
    parity_path: Path,
    expected_hash: str,
    parity_hash: str,
    block_hashes: List[str],
    block_size: int,
    stripe_blocks: int,
    total_size: int,
) -> dict:
    if not obj_path.exists():
        return {"repaired": False, "reason": "object not found"}
    if not parity_path.exists():
        return {"repaired": False, "reason": "parity not found"}
    if block_size <= 0 or stripe_blocks <= 0:
        return {"repaired": False, "reason": "invalid ecc parameters"}

    total_blocks = len(block_hashes)
    expected_blocks = math.ceil(total_size / block_size) if total_size > 0 else 0
    if total_blocks != expected_blocks:
        return {"repaired": False, "reason": "block hashes count mismatch"}

    stripe_count = math.ceil(total_blocks / stripe_blocks) if total_blocks else 0
    expected_parity_size = stripe_count * block_size
    if parity_path.stat().st_size != expected_parity_size:
        return {"repaired": False, "reason": "parity size mismatch"}

    repairs = 0
    parity_hasher = hashlib.sha256()

    with obj_path.open("r+b") as obj, parity_path.open("rb") as par:
        for stripe in range(stripe_count):
            stripe_start = stripe * stripe_blocks
            blocks = []
            mismatches = []
            for i in range(stripe_blocks):
                idx = stripe_start + i
                if idx >= total_blocks:
                    break
                block = obj.read(block_size)
                blocks.append(block)
                if hashlib.sha256(block).hexdigest() != block_hashes[idx]:
                    mismatches.append(i)

            parity = par.read(block_size)
            if len(parity) != block_size:
                return {"repaired": False, "reason": "parity truncated"}
            parity_hasher.update(parity)

            if len(mismatches) == 1:
                missing = mismatches[0]
                recovered = bytearray(parity)
                for j, block in enumerate(blocks):
                    if j == missing:
                        continue
                    _xor_into(recovered, block)
                global_idx = stripe_start + missing
                block_len = block_size
                if global_idx == total_blocks - 1:
                    block_len = total_size - block_size * (total_blocks - 1)
                next_pos = obj.tell()
                obj.seek(global_idx * block_size)
                obj.write(bytes(recovered[:block_len]))
                obj.seek(next_pos)
                repairs += 1
            elif len(mismatches) > 1:
                return {"repaired": False, "reason": "multiple corrupted blocks in stripe"}

    if parity_hasher.hexdigest() != parity_hash:
        return {"repaired": False, "reason": "parity hash mismatch"}

    actual_hash = sha256_file(obj_path)
    if actual_hash != expected_hash:
        return {"repaired": False, "reason": "object hash mismatch after repair"}

    if repairs == 0:
        return {"repaired": False, "reason": "no repairable corruption found"}

    return {"repaired": True, "fixed_blocks": repairs}
