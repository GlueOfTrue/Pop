# Roadmap

This roadmap is intentionally conservative. Pop is an early prototype, and clarity plus safe evaluation come before new feature breadth.

## v0.1-alpha Polish

- README, demo guide, threat model, security notes, and storage format docs.
- Pytest roundtrip tests for the storage core.
- GitHub Actions CI for tests.
- Safer atomic writes and fsync behavior where practical.
- Packaging basics for local development.

## v0.2 Remote Mirror

- Harden the initial Nextcloud/WebDAV push+status bridge.
- Pull and conflict handling.
- Remote verification of mirrored ciphertext and protected metadata.
- Remote rollback notes and initial anti-rollback design.

## v0.3 Storage Efficiency

- Chunked object format.
- Deduplication across versions.
- Retention policies.
- Version pruning policies.

## v0.4 Linux Convenience Layer

- Read-only FUSE mount for browsing stored versions.
- Optional tmpfs/RAM cache mode.
- Explicit warnings about plaintext exposure through mounted views and viewer applications.
