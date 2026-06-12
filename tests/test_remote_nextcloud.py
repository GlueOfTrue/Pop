from __future__ import annotations

import json
from pathlib import Path

import pytest

from storage_core import add_file, init_storage, unlock_storage
from storage_core.remote_nextcloud import (
    MANIFEST_NAME,
    NextcloudClient,
    RemoteConfig,
    RemoteConfigError,
    build_manifest,
    load_env_config,
    push_mirror,
    remote_status,
)


PASSWORD = "remote bridge password"


class FakeResponse:
    def __init__(self, status_code: int, content: bytes = b"", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text


class FakeSession:
    def __init__(self, manifest: dict | None = None, manifest_exists: bool = True) -> None:
        self.requests: list[dict] = []
        self.manifest = manifest
        self.manifest_exists = manifest_exists

    def request(self, method: str, url: str, **kwargs) -> FakeResponse:
        body = kwargs.get("data")
        if hasattr(body, "read"):
            body = body.read()
        self.requests.append({"method": method, "url": url, "body": body})

        if method == "MKCOL":
            return FakeResponse(201)
        if method == "PUT":
            return FakeResponse(201)
        if method == "HEAD":
            return FakeResponse(200 if self.manifest_exists else 404)
        if method == "PROPFIND":
            return FakeResponse(207)
        if method == "GET":
            if not self.manifest_exists:
                return FakeResponse(404)
            return FakeResponse(200, json.dumps(self.manifest or {"files": []}).encode("utf-8"))
        raise AssertionError(f"unexpected method {method}")


@pytest.fixture()
def vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, bytes]:
    monkeypatch.setattr("storage_core.api._require_auth", lambda storage_root, master_key, action: None)
    storage_root = tmp_path / "vault"
    init_storage(storage_root, master_password=PASSWORD)
    master_key = unlock_storage(storage_root, PASSWORD)
    source = tmp_path / "note.txt"
    source.write_bytes(b"remote mirror content\n")
    add_file(storage_root, master_key, source, doc_name="note.txt")
    return storage_root, master_key


def test_load_env_config_requires_https(vault: tuple[Path, bytes]) -> None:
    storage_root, _master_key = vault
    env = {
        "POP_NEXTCLOUD_URL": "http://cloud.example",
        "POP_NEXTCLOUD_USER": "alice",
        "POP_NEXTCLOUD_PASSWORD": "app-password",
    }

    with pytest.raises(RemoteConfigError, match="must use HTTPS"):
        load_env_config(storage_root, env)

    env["POP_NEXTCLOUD_ALLOW_HTTP"] = "1"
    config = load_env_config(storage_root, env)
    assert config.base_url == "http://cloud.example"


def test_client_builds_quoted_webdav_root() -> None:
    config = RemoteConfig(
        base_url="https://cloud.example/nextcloud",
        username="alice@example.com",
        password="app-password",
        remote_path="Pop Vault/main",
    )
    client = NextcloudClient(config, session=FakeSession())

    assert client.root_url == (
        "https://cloud.example/nextcloud/remote.php/dav/files/"
        "alice%40example.com/Pop%20Vault/main/"
    )


def test_manifest_contains_only_allowed_vault_paths(vault: tuple[Path, bytes]) -> None:
    storage_root, _master_key = vault
    (storage_root / "plain.txt").write_text("do not mirror plaintext root file", encoding="utf-8")

    manifest = build_manifest(storage_root)
    paths = {item["path"] for item in manifest["files"]}

    assert "plain.txt" not in paths
    assert "config.json" in paths
    assert "meta/catalog.json" in paths
    assert "meta/keystore.json" in paths
    assert any(path.startswith("meta/records/") for path in paths)
    assert any(path.startswith("objects/") for path in paths)
    assert all({"path", "size", "sha256"} <= set(item) for item in manifest["files"])


def test_push_mirror_mkcol_puts_files_and_manifest_last(vault: tuple[Path, bytes]) -> None:
    storage_root, _master_key = vault
    session = FakeSession()
    config = RemoteConfig(
        base_url="https://cloud.example",
        username="alice",
        password="app-password",
        remote_path="Pop/vault",
    )

    result = push_mirror(storage_root, config=config, session=session)
    methods = [entry["method"] for entry in session.requests]
    put_urls = [entry["url"] for entry in session.requests if entry["method"] == "PUT"]

    assert result["files_uploaded"] > 0
    assert "DELETE" not in methods
    assert "MKCOL" in methods
    assert put_urls[-1].endswith(f"/{MANIFEST_NAME}")


def test_remote_status_reports_missing_and_changed(vault: tuple[Path, bytes]) -> None:
    storage_root, _master_key = vault
    local_manifest = build_manifest(storage_root)
    remote_entries = local_manifest["files"][:-1]
    remote_entries[0] = dict(remote_entries[0], sha256="0" * 64)
    session = FakeSession(manifest={"files": remote_entries}, manifest_exists=True)
    config = RemoteConfig(
        base_url="https://cloud.example",
        username="alice",
        password="app-password",
        remote_path="Pop/vault",
    )

    status = remote_status(storage_root, config=config, session=session)
    methods = [entry["method"] for entry in session.requests]

    assert status["remote_manifest"] is True
    assert "PROPFIND" in methods
    assert "HEAD" in methods
    assert status["up_to_date"] is False
    assert status["changed"] == [local_manifest["files"][0]["path"]]
    assert status["missing"] == [local_manifest["files"][-1]["path"]]


def test_remote_status_without_manifest_marks_all_missing(vault: tuple[Path, bytes]) -> None:
    storage_root, _master_key = vault
    session = FakeSession(manifest_exists=False)
    config = RemoteConfig(
        base_url="https://cloud.example",
        username="alice",
        password="app-password",
        remote_path="Pop/vault",
    )

    status = remote_status(storage_root, config=config, session=session)

    assert status["remote_manifest"] is False
    assert status["local_files"] == len(status["missing"])
