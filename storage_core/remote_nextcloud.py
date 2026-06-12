from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urlparse

try:
    import requests
except Exception:  # noqa: BLE001
    requests = None

from .objects import sha256_file
from .paths import (
    CATALOG_DIRNAME,
    CATALOG_FILENAME,
    CONFIG_FILENAME,
    ECC_DIRNAME,
    KEYSTORE_FILENAME,
    OBJECTS_DIRNAME,
    TOTP_FILENAME,
)
from .util import canonical_json_bytes, now_utc_iso

REMOTE_URL_ENV = "POP_NEXTCLOUD_URL"
REMOTE_USER_ENV = "POP_NEXTCLOUD_USER"
REMOTE_PASSWORD_ENV = "POP_NEXTCLOUD_PASSWORD"
REMOTE_PATH_ENV = "POP_NEXTCLOUD_PATH"
REMOTE_ALLOW_HTTP_ENV = "POP_NEXTCLOUD_ALLOW_HTTP"
MANIFEST_NAME = "pop-manifest.v1.json"
REQUEST_TIMEOUT = 30


class RemoteConfigError(ValueError):
    pass


class RemoteHTTPError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteConfig:
    base_url: str
    username: str
    password: str
    remote_path: str
    allow_http: bool = False


@dataclass(frozen=True)
class MirrorFile:
    relative_path: str
    path: Path
    size: int
    sha256: str

    def as_manifest_entry(self) -> dict:
        return {
            "path": self.relative_path,
            "size": self.size,
            "sha256": self.sha256,
        }


def load_env_config(storage_root: Path, environ: dict[str, str] | None = None) -> RemoteConfig:
    env = environ if environ is not None else os.environ
    missing = [
        name
        for name in (REMOTE_URL_ENV, REMOTE_USER_ENV, REMOTE_PASSWORD_ENV)
        if not env.get(name)
    ]
    if missing:
        raise RemoteConfigError(f"missing environment variables: {', '.join(missing)}")

    base_url = env[REMOTE_URL_ENV].rstrip("/")
    parsed = urlparse(base_url)
    allow_http = env.get(REMOTE_ALLOW_HTTP_ENV) == "1"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RemoteConfigError(f"{REMOTE_URL_ENV} must be an absolute http(s) URL")
    if parsed.scheme != "https" and not allow_http:
        raise RemoteConfigError(
            f"{REMOTE_URL_ENV} must use HTTPS unless {REMOTE_ALLOW_HTTP_ENV}=1 is set"
        )

    remote_path = env.get(REMOTE_PATH_ENV) or f"Pop/{storage_root.name or 'vault'}"
    remote_path = remote_path.strip("/")
    if not remote_path:
        raise RemoteConfigError(f"{REMOTE_PATH_ENV} must not be empty")

    return RemoteConfig(
        base_url=base_url,
        username=env[REMOTE_USER_ENV],
        password=env[REMOTE_PASSWORD_ENV],
        remote_path=remote_path,
        allow_http=allow_http,
    )


def _split_remote_path(path: str) -> list[str]:
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise RemoteConfigError("remote path must not contain '.' or '..' segments")
    return parts


def _quote_segments(segments: Iterable[str]) -> str:
    return "/".join(quote(segment, safe="") for segment in segments)


def _iter_allowed_files(storage_root: Path) -> Iterable[Path]:
    fixed = [
        storage_root / CONFIG_FILENAME,
        storage_root / CATALOG_DIRNAME / CATALOG_FILENAME,
        storage_root / CATALOG_DIRNAME / KEYSTORE_FILENAME,
        storage_root / CATALOG_DIRNAME / TOTP_FILENAME,
    ]
    for path in fixed:
        if path.exists():
            yield path

    for rel_dir in (
        Path(CATALOG_DIRNAME) / "records",
        Path(OBJECTS_DIRNAME),
        Path(ECC_DIRNAME),
    ):
        base = storage_root / rel_dir
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_symlink():
                raise RuntimeError(f"refusing to mirror symlink: {path}")
            if path.is_file():
                yield path


def collect_mirror_files(storage_root: Path) -> list[MirrorFile]:
    root = storage_root.resolve()
    files: list[MirrorFile] = []
    for path in _iter_allowed_files(root):
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise RuntimeError(f"refusing to mirror path outside storage root: {path}") from exc
        st = resolved.stat()
        files.append(MirrorFile(relative, resolved, st.st_size, sha256_file(resolved)))
    return sorted(files, key=lambda item: item.relative_path)


def build_manifest(storage_root: Path) -> dict:
    return build_manifest_from_files(collect_mirror_files(storage_root))


def build_manifest_from_files(files: list[MirrorFile]) -> dict:
    return {
        "version": 1,
        "generated_at": now_utc_iso(),
        "format": "pop-nextcloud-mirror-v1",
        "files": [item.as_manifest_entry() for item in files],
    }


def manifest_bytes(manifest: dict) -> bytes:
    return canonical_json_bytes(manifest) + b"\n"


class NextcloudClient:
    def __init__(self, config: RemoteConfig, session=None, timeout: int = REQUEST_TIMEOUT) -> None:
        if requests is None and session is None:
            raise RemoteConfigError("requests is required for Nextcloud/WebDAV support")
        self.config = config
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout
        remote_segments = _split_remote_path(config.remote_path)
        self._remote_segments = remote_segments
        self._files_base = (
            f"{config.base_url}/remote.php/dav/files/{quote(config.username, safe='')}/"
        )
        self.root_url = self._url_for_segments(remote_segments, collection=True)

    def _url_for_segments(self, segments: Iterable[str], *, collection: bool = False) -> str:
        suffix = _quote_segments(segments)
        url = self._files_base + suffix
        if collection and not url.endswith("/"):
            url += "/"
        return url

    def _url_for_relative(self, relative_path: str, *, collection: bool = False) -> str:
        rel_segments = _split_remote_path(relative_path)
        return self._url_for_segments([*self._remote_segments, *rel_segments], collection=collection)

    def _request(self, method: str, url: str, **kwargs):
        response = self.session.request(
            method,
            url,
            auth=(self.config.username, self.config.password),
            timeout=self.timeout,
            **kwargs,
        )
        return response

    @staticmethod
    def _raise_unexpected(response, expected: set[int], action: str) -> None:
        if response.status_code not in expected:
            raise RemoteHTTPError(f"{action} failed with HTTP {response.status_code}: {response.text[:200]}")

    def ensure_collection(self, relative_dir: str = "") -> None:
        segments = list(self._remote_segments)
        if relative_dir:
            segments.extend(_split_remote_path(relative_dir))
        for idx in range(1, len(segments) + 1):
            url = self._url_for_segments(segments[:idx], collection=True)
            response = self._request("MKCOL", url)
            self._raise_unexpected(response, {201, 405}, f"MKCOL {url}")

    def put_file(self, local_path: Path, relative_path: str) -> None:
        parent = Path(relative_path).parent.as_posix()
        if parent != ".":
            self.ensure_collection(parent)
        with local_path.open("rb") as src:
            response = self._request("PUT", self._url_for_relative(relative_path), data=src)
        self._raise_unexpected(response, {200, 201, 204}, f"PUT {relative_path}")

    def put_bytes(self, payload: bytes, relative_path: str) -> None:
        parent = Path(relative_path).parent.as_posix()
        if parent != ".":
            self.ensure_collection(parent)
        response = self._request("PUT", self._url_for_relative(relative_path), data=payload)
        self._raise_unexpected(response, {200, 201, 204}, f"PUT {relative_path}")

    def head(self, relative_path: str) -> bool:
        response = self._request("HEAD", self._url_for_relative(relative_path))
        if response.status_code == 404:
            return False
        self._raise_unexpected(response, {200, 204}, f"HEAD {relative_path}")
        return True

    def propfind(self, relative_path: str = "", depth: int = 0) -> bool:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>'
        )
        response = self._request(
            "PROPFIND",
            self._url_for_relative(relative_path, collection=True),
            data=body.encode("utf-8"),
            headers={"Depth": str(depth), "Content-Type": "application/xml"},
        )
        if response.status_code == 404:
            return False
        self._raise_unexpected(response, {207}, f"PROPFIND {relative_path or '/'}")
        return True

    def get_json(self, relative_path: str) -> dict | None:
        response = self._request("GET", self._url_for_relative(relative_path))
        if response.status_code == 404:
            return None
        self._raise_unexpected(response, {200}, f"GET {relative_path}")
        return json.loads(response.content.decode("utf-8"))


def push_mirror(storage_root: Path, config: RemoteConfig | None = None, session=None) -> dict:
    root = storage_root.resolve()
    cfg = config or load_env_config(root)
    client = NextcloudClient(cfg, session=session)
    files = collect_mirror_files(root)

    client.ensure_collection("")
    uploaded = 0
    for item in files:
        client.put_file(item.path, item.relative_path)
        uploaded += 1

    manifest = build_manifest_from_files(files)
    client.put_bytes(manifest_bytes(manifest), MANIFEST_NAME)
    return {
        "remote_root": client.root_url,
        "files_uploaded": uploaded,
        "manifest": MANIFEST_NAME,
    }


def remote_status(storage_root: Path, config: RemoteConfig | None = None, session=None) -> dict:
    root = storage_root.resolve()
    cfg = config or load_env_config(root)
    client = NextcloudClient(cfg, session=session)
    local_files = {item.relative_path: item.as_manifest_entry() for item in collect_mirror_files(root)}

    remote_collection = client.propfind("")
    if not remote_collection or not client.head(MANIFEST_NAME):
        return {
            "remote_root": client.root_url,
            "remote_collection": remote_collection,
            "remote_manifest": False,
            "local_files": len(local_files),
            "missing": sorted(local_files),
            "changed": [],
            "extra_remote_manifest": [],
            "up_to_date": False,
        }

    remote_manifest = client.get_json(MANIFEST_NAME) or {}
    remote_files = {
        item.get("path"): item
        for item in remote_manifest.get("files", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }

    missing = []
    changed = []
    for rel, local in local_files.items():
        remote = remote_files.get(rel)
        if remote is None:
            missing.append(rel)
            continue
        if remote.get("size") != local["size"] or remote.get("sha256") != local["sha256"]:
            changed.append(rel)

    extra = sorted(rel for rel in remote_files if rel not in local_files)
    return {
        "remote_root": client.root_url,
        "remote_collection": remote_collection,
        "remote_manifest": True,
        "local_files": len(local_files),
        "missing": sorted(missing),
        "changed": sorted(changed),
        "extra_remote_manifest": extra,
        "up_to_date": not missing and not changed,
    }
