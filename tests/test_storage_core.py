from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

import storage_core.api as api
from storage_core import add_file, init_storage, list_public, restore_file, unlock_storage, verify_storage


PASSWORD = "correct horse battery staple"


@pytest.fixture(autouse=True)
def bypass_interactive_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "_require_auth", lambda storage_root, master_key, action: None)


@pytest.fixture()
def vault(tmp_path: Path) -> tuple[Path, bytes]:
    storage_root = tmp_path / "vault"
    init_storage(storage_root, master_password=PASSWORD)
    master_key = unlock_storage(storage_root, PASSWORD)
    return storage_root, master_key


def test_add_restore_roundtrip(vault: tuple[Path, bytes], tmp_path: Path) -> None:
    storage_root, master_key = vault
    source = tmp_path / "note.txt"
    source.write_bytes(b"hello pop\n")

    add_file(storage_root, master_key, source, doc_name="note.txt")

    restored = tmp_path / "restored.txt"
    restore_file(storage_root, master_key, "note.txt", restored)

    assert restored.read_bytes() == b"hello pop\n"


def test_multiple_versions(vault: tuple[Path, bytes], tmp_path: Path) -> None:
    storage_root, master_key = vault
    source = tmp_path / "note.txt"

    source.write_bytes(b"version one\n")
    add_file(storage_root, master_key, source, doc_name="note.txt")
    source.write_bytes(b"version two\n")
    add_file(storage_root, master_key, source, doc_name="note.txt")

    catalog = list_public(storage_root)
    docs = catalog["docs"]
    assert len(docs) == 1
    doc_info = next(iter(docs.values()))
    assert doc_info["versions"] == [1, 2]

    restored_v1 = tmp_path / "restored-v1.txt"
    restored_v2 = tmp_path / "restored-v2.txt"
    restore_file(storage_root, master_key, "note.txt", restored_v1, version=1)
    restore_file(storage_root, master_key, "note.txt", restored_v2, version=2)

    assert restored_v1.read_bytes() == b"version one\n"
    assert restored_v2.read_bytes() == b"version two\n"


def test_wrong_password_fails(tmp_path: Path) -> None:
    storage_root = tmp_path / "vault"
    init_storage(storage_root, master_password="password-a")

    with pytest.raises(InvalidTag):
        unlock_storage(storage_root, "password-b")


def test_corrupted_object_detected(vault: tuple[Path, bytes], tmp_path: Path) -> None:
    storage_root, master_key = vault
    source = tmp_path / "note.txt"
    source.write_bytes(b"content that will be corrupted\n")

    info = add_file(storage_root, master_key, source, doc_name="note.txt")
    object_path = storage_root / "objects" / info["content_enc_hash"]
    assert object_path.exists()

    for parity_path in (storage_root / "ecc").glob("*"):
        parity_path.unlink()

    with object_path.open("ab") as f:
        f.write(b"corruption")

    result = verify_storage(storage_root, master_key, deep=False)

    assert result["summary"]["CORRUPTED"] == 1
    assert result["results"][0]["status"] == "CORRUPTED"
    assert result["results"][0]["reasons"]


def test_secure_mode_removes_original_after_store(vault: tuple[Path, bytes], tmp_path: Path) -> None:
    storage_root, master_key = vault
    source = tmp_path / "secret.txt"
    source.write_bytes(b"disposable secure content\n")

    add_file(storage_root, master_key, source, doc_name="secret.txt", mode="secure")

    assert not source.exists()

    restored = tmp_path / "restored-secret.txt"
    restore_file(storage_root, master_key, "secret.txt", restored)
    assert restored.read_bytes() == b"disposable secure content\n"
