# Pop

[![Tests](https://github.com/GlueOfTrue/Pop/actions/workflows/tests.yml/badge.svg)](https://github.com/GlueOfTrue/Pop/actions/workflows/tests.yml)

Pop is an experimental local-first encrypted backup vault with file versioning, integrity verification, Touch ID/TOTP authorization, paranoid file viewing, and an early Nextcloud/WebDAV push mirror.

Pop is not production-ready. Do not use it as the only copy of important data yet, and review the threat model before using it with anything sensitive.

## Why Pop?

Nextcloud sync is convenient, but sync is not backup. Sync can copy accidental deletion, bad overwrites, or ransomware damage very efficiently. Pop stores encrypted versioned backups locally and is designed to mirror only ciphertext and protected metadata to untrusted storage later.

The current prototype keeps the working storage core small: files are encrypted before storage, versions are retained, public catalog data is separated from protected metadata, and restore/open operations require an interactive local authorization step.

## What Works Today

- Encrypted local vault selected with `GSBACKUP_STORAGE` or platform defaults.
- Versioned documents with restore by version.
- Public catalog plus encrypted protected metadata records.
- AES-GCM content encryption with compression before encryption.
- Scrypt-protected keystore that wraps a random master key.
- Per-version HKDF keys for content and metadata.
- Integrity verification for records and encrypted objects.
- Restore and external open flows.
- Paranoid open mode that shortens the lifetime of a named plaintext temp file.
- Optional TOTP gate after local authorization.
- macOS Touch ID/LocalAuthentication hook with sudo fallback.
- Linux/POSIX sudo authorization.
- Experimental XOR parity ECC repair for one corrupted block per stripe.
- Initial Nextcloud/WebDAV push+status mirror for encrypted vault data.
- Planned read-only Linux FUSE browsing.

## Security Model In One Minute

Pop assumes remote storage is untrusted and should only receive encrypted vault data. The client machine is trusted while it is not compromised. The master password protects the random vault master key through scrypt and AES-GCM key wrapping. File contents and protected metadata use keys derived from the master key with HKDF for each document version.

Local auth and optional TOTP are interactive gates for protected operations such as metadata access, restore, verify, and open. They do not replace encryption, and TOTP does not protect against offline brute-force of a copied vault. Paranoid open reduces the lifetime of a named plaintext file, but it is not an anti-forensics guarantee.

See [docs/threat-model.md](docs/threat-model.md) and [SECURITY.md](SECURITY.md) before using Pop with real data.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GSBACKUP_STORAGE="$(mktemp -d)"
python3 backup.py
```

On first run, set and repeat a master password. The default interface language is currently Russian; use menu item `13` to switch to English.

The project name is Pop. Some internal paths and prompts still use the inherited prototype app name `gs-backup-storage`; this pass intentionally preserves those storage paths and formats.

## Demo Scenario

For a safe manual walkthrough, use a temporary vault:

1. Create a disposable sample file.
2. Start `python3 backup.py`.
3. Initialize the vault with a master password.
4. Add the file in `backup` mode.
5. Modify the sample file and add it again with the same document name.
6. List public documents and confirm two versions.
7. Restore version 1 to a separate output path.
8. Run storage verification.

The full reviewer demo is in [docs/demo.md](docs/demo.md). Be careful with `secure` mode: it deletes the source file after storing it.

For the experimental Nextcloud/WebDAV push mirror, see [docs/nextcloud.md](docs/nextcloud.md).

## Current Limitations

- Experimental prototype with no security audit.
- Not suitable as the only copy of important files.
- Remote mirror is push+status only; there is no pull, remote delete, conflict handling, or rollback protection yet.
- No retention policy or version pruning policy yet.
- No full encrypted filesystem and no writable FUSE layer.
- Paranoid open cannot stop viewer caches, thumbnails, swap, screenshots, recent-file lists, or autosave leaks.
- Malicious remote rollback is not solved without trusted local state or a future anti-rollback design.
- A compromised OS, Python runtime, or unlocked client can read plaintext during normal operations.

## Roadmap

See [ROADMAP.md](ROADMAP.md). The near-term goal is a v0.1-alpha polish pass: documentation, safe demo, tests, CI, hardening, packaging basics, and a conservative Nextcloud/WebDAV push mirror. Later milestones cover pull/conflict handling, storage efficiency, and a read-only Linux FUSE browsing layer.

## Design Inspirations

Pop takes inspiration from versioned backup tools, local-first storage, content-addressed object stores, and encrypted vault designs. It is not trying to replace mature tools such as BorgBackup, restic, age, VeraCrypt, or Nextcloud; the current goal is to explore a small local-first encrypted backup core that can later mirror ciphertext to untrusted cloud storage.

## License

No license file is present yet. Choose and add a license before treating the repository as reusable open source or accepting external contributions.
