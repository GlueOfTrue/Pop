from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

import storage_core.api as api
from storage_core import (
    add_file,
    init_storage,
    list_public,
    open_file,
    prune_objects,
    restore_file,
    unlock_storage,
    verify_storage,
)


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


def test_add_file_rejects_source_symlink(vault: tuple[Path, bytes], tmp_path: Path) -> None:
    storage_root, master_key = vault
    source = tmp_path / "source.txt"
    source.write_bytes(b"real content\n")
    link = tmp_path / "source-link.txt"
    os.symlink(source, link)

    with pytest.raises(RuntimeError, match="source path is a symlink"):
        add_file(storage_root, master_key, link, doc_name="link.txt")


def test_open_file_sanitizes_temp_basename(
    vault: tuple[Path, bytes],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root, master_key = vault
    source = tmp_path / "source.txt"
    source.write_bytes(b"temporary view\n")
    malicious_name = "../bad/name\\with\x01control.txt"
    add_file(storage_root, master_key, source, doc_name=malicious_name)

    monkeypatch.setattr(api.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(api.subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess(args, 1))

    info = open_file(storage_root, master_key, malicious_name, paranoid=True, force=True)

    temp_path = Path(info["path"])
    assert temp_path.name == ".._bad_name_with_control.txt".strip(" .")
    assert temp_path.parent.name.startswith("gs-backup-open-")
    assert not Path(info["path"]).exists()


def test_restore_refuses_symlink_destination(vault: tuple[Path, bytes], tmp_path: Path) -> None:
    storage_root, master_key = vault
    source = tmp_path / "source.txt"
    source.write_bytes(b"restore content\n")
    add_file(storage_root, master_key, source, doc_name="restore.txt")

    target = tmp_path / "target.txt"
    target.write_bytes(b"do not overwrite\n")
    link = tmp_path / "restore-link.txt"
    os.symlink(target, link)

    with pytest.raises(RuntimeError, match="destination is a symlink"):
        restore_file(storage_root, master_key, "restore.txt", link, force=True)

    assert target.read_bytes() == b"do not overwrite\n"


def test_prune_keeps_corrupted_referenced_version_by_default(
    vault: tuple[Path, bytes],
    tmp_path: Path,
) -> None:
    storage_root, master_key = vault
    source = tmp_path / "source.txt"
    source.write_bytes(b"content that will be corrupted but kept\n")
    info = add_file(storage_root, master_key, source, doc_name="kept.txt")

    object_path = storage_root / "objects" / info["content_enc_hash"]
    with object_path.open("ab") as f:
        f.write(b"corruption")

    result = prune_objects(storage_root, master_key)
    catalog = list_public(storage_root)

    assert result["versions_removed"] == 0
    assert result["versions_kept_problem"] == 1
    assert result["versions_corrupted"] == 1
    assert object_path.exists()
    assert next(iter(catalog["docs"].values()))["versions"] == [1]
