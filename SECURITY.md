# Security Policy

Pop is experimental and has not had a security audit. Do not store the only copy of important files in Pop yet.

## Reporting Vulnerabilities

Use GitHub issues for non-sensitive bugs.

For sensitive security issues, ask the maintainer for a private contact channel until a dedicated disclosure address exists. Avoid posting exploit details, real secrets, or private vault data in public issues.

## Current Security Boundaries

Pop is designed to reduce exposure when encrypted vault data is copied to untrusted storage. Remote storage should see ciphertext, public catalog data, and protected metadata only.

The current Nextcloud/WebDAV bridge is push+status only. Remote data and the remote manifest are not trusted for restore, rollback, deletion, pruning, or conflict resolution.

On Linux, Pop refuses local authorization while running as root unless `POP_ALLOW_ROOT=1` is set. This is a guardrail against root-owned vault files and against weakening the local-user authorization model.

Pop does not protect against malware running on the client while the vault is unlocked, keyloggers, screen capture malware, weak master passwords, a compromised Python runtime, or a compromised operating system.

Viewer applications may leak plaintext into caches, thumbnails, recent-file databases, autosave files, swap, screenshots, or other local artifacts. Paranoid open reduces the lifetime of a named plaintext path but does not prevent those leaks.

TOTP is an interactive local authorization layer. It does not protect against offline brute-force of a copied vault.

## Crypto Design Notes

- The keystore wraps a random master key with a scrypt-derived KEK and AES-GCM.
- Per-version content and metadata keys are derived from the master key with HKDF.
- Content encryption uses AES-GCM with public metadata as AAD.
- Protected metadata is encrypted separately and checked with an embedded metadata hash.
- Integrity verification checks encrypted object hashes, AEAD tags, plaintext hashes during deep verification, and optional ECC parity metadata.

Do not change cryptographic formats, KDF parameters, AAD construction, metadata hashing, or key derivation labels without tests that cover migration, backward compatibility, and failure modes.
