# Threat Model

Pop is an experimental local-first encrypted backup vault. This document describes the intended security boundaries for the current prototype.

## Protects Against / Reduces Risk Of

- Lost or stolen remote copy: attacker sees encrypted vault files only.
- Curious or compromised cloud storage operator: remote storage should not see plaintext file contents.
- Accidental deletion or bad overwrite: older versions can be restored if the vault still exists.
- Ransomware or corruption of working files: previous versions can help if the vault or remote mirror survives.
- Object corruption: hash verification detects it; ECC may repair limited single-block-per-stripe corruption.
- Casual local access: local auth plus optional TOTP gates protected metadata, open, restore, verify, stats, prune, and TOTP operations.

## Does Not Protect Against

- Malware running on the client while the vault is unlocked.
- Keyloggers or screen capture malware.
- Weak master passwords.
- Viewer applications leaking plaintext into caches, thumbnails, recent-file databases, autosave files, swap, or screenshots.
- Deletion of every local and remote vault copy.
- Malicious remote rollback without trusted local state or a future anti-rollback design.
- A compromised Python runtime or operating system.

## Design Implications

- Remote storage is untrusted.
- Client is trusted only while not compromised.
- Master password strength matters.
- TOTP is an interactive local authorization layer, not offline encryption security.
- Paranoid open reduces plaintext path lifetime but is not a complete anti-forensics tool.
