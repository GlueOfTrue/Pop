# Nextcloud/WebDAV Mirror

Pop currently supports an experimental push+status bridge for Nextcloud/WebDAV. It uploads encrypted vault files and a manifest; it does not pull, delete remote files, prune remote files, restore from remote, or trust remote data for rollback decisions.

## Environment

Use a Nextcloud app password rather than your main account password.

```bash
export POP_NEXTCLOUD_URL="https://cloud.example.com"
export POP_NEXTCLOUD_USER="username"
export POP_NEXTCLOUD_PASSWORD="nextcloud-app-password"
export POP_NEXTCLOUD_PATH="Pop/demo-vault"  # optional
```

If `POP_NEXTCLOUD_PATH` is unset, Pop uses `Pop/<storage-root-name>`.

HTTPS is required by default. For local test servers only, set:

```bash
export POP_NEXTCLOUD_ALLOW_HTTP=1
```

## What Gets Uploaded

Only vault data is mirrored:

- `config.json`
- `meta/catalog.json`
- `meta/keystore.json`
- `meta/totp.json` when present
- `meta/records/**`
- `objects/**`
- `ecc/**`
- `pop-manifest.v1.json`, uploaded last

Plaintext source files, restored files, temp viewer files, and unrelated files in the storage root are not mirrored.

## Usage

Run `python3 backup.py` and use:

- `Remote status`
- `Push remote mirror`

Push requires the same local authorization gate as protected operations. Status reads the remote manifest and compares it with the local vault manifest.
