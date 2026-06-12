# Codex task: polish Pop into a presentable early OSS project

Repository: `GlueOfTrue/Pop`
Primary goal: make the repository understandable, credible, and easy to evaluate before an external OSS/Claude for OSS-style application.

This is not a rewrite. Preserve the existing working storage core. The task is to polish, document, test, and package the current prototype so a new reviewer can understand it in 3-5 minutes and run a basic demo safely.

## Project identity

Pop is an early-stage local-first encrypted backup vault.

Core idea:

- Store files as encrypted versioned backups.
- Keep file contents encrypted locally before any future cloud mirroring.
- Separate public catalog data from protected metadata.
- Provide restore, verification, and controlled local viewing flows.
- Support local interactive authorization via macOS Touch ID/LocalAuthentication or Linux sudo.
- Support optional TOTP as a second interactive authorization gate.
- Eventually mirror encrypted vault data to untrusted remote storage such as Nextcloud/WebDAV.
- Eventually add a Linux read-only FUSE layer, but do not make FUSE part of the first polish milestone.

One-line README positioning:

> Pop is an experimental local-first encrypted backup vault with file versioning, integrity verification, Touch ID/TOTP authorization, paranoid file viewing, and planned Nextcloud/WebDAV mirroring.

Short product distinction:

> Nextcloud sync is convenient, but sync is not backup. Pop stores encrypted versioned backups locally and is designed to mirror only ciphertext and protected metadata to untrusted storage.

## Current implementation facts to preserve

Use these as the source of truth before editing:

- Entry point: `backup.py`.
- Core package: `storage_core/`.
- Storage root is selected through `GSBACKUP_STORAGE` or platform defaults in `storage_core/paths.py`.
- Default app name is currently `gs-backup-storage`. Do not rename paths or formats in this pass unless doing a careful compatibility migration.
- Storage layout includes:
  - `config.json`
  - `meta/catalog.json`
  - `meta/keystore.json`
  - `meta/totp.json`
  - `meta/records/<doc_id>/v<version>.bin`
  - `objects/<encrypted_object_hash>`
  - `ecc/<parity_hash>`
- Keystore currently uses random master key, scrypt-derived KEK, AES-GCM wrapping.
- Content encryption currently uses AES-GCM stream format with header, compression-before-encryption, SHA-256 hashes, and AAD tied to public metadata.
- Per-version content/meta keys are derived with HKDF from the master key using doc id, version, and purpose.
- TOTP config is encrypted using a key derived from the master key and is verified interactively after local auth when enabled.
- macOS local auth uses Swift LocalAuthentication first, then JXA LocalAuthentication, then sudo fallback.
- Linux/POSIX local auth uses sudo validation.
- `open_file(..., paranoid=True)` tries to open a temporary plaintext copy, detect viewer PIDs, then unlink the plaintext path and clean tempdir where possible.
- ECC is XOR parity per stripe and can repair one corrupted block per stripe if parity and block hashes are valid.

## Non-goals for this Codex pass

Do not implement a full encrypted filesystem.
Do not implement writable FUSE.
Do not redesign the cryptographic format unless a test proves a serious bug.
Do not replace the existing storage core with a new architecture.
Do not promise production-grade security in documentation.
Do not claim the project protects against malware running on an already unlocked client.
Do not claim paranoid open prevents viewer caches, thumbnails, swap, screenshots, or recent-file leaks.
Do not claim TOTP protects against offline brute-force of a copied vault. TOTP is only an interactive local authorization gate.

## Desired outcome

After this pass, the repository should have:

1. A strong README that explains what Pop is, why it exists, what already works, how to run a demo, and what is planned.
2. A clear threat model.
3. A demo guide.
4. A documented storage format overview.
5. A security limitations document.
6. Basic pytest tests covering the most important working behavior.
7. Optional CI if feasible within time.
8. No misleading demo crypto file in the root.
9. Commit history that looks intentional.

## High-priority tasks

### 1. Add or rewrite `README.md`

Create a concise but useful README with these sections:

- `# Pop`
- Status badge placeholder if CI is added.
- One-paragraph description.
- `Why Pop?`
- `What works today`
- `Security model in one minute`
- `Quick start`
- `Demo scenario`
- `Current limitations`
- `Roadmap`
- `Design inspirations`
- `License`

Use sober language. Do not oversell.

Feature list should mention:

- encrypted local vault
- versioned documents
- public catalog + encrypted protected metadata
- AES-GCM content encryption
- scrypt-protected keystore
- per-version HKDF keys
- integrity verification
- restore and open flows
- paranoid open mode
- optional TOTP
- macOS Touch ID/LocalAuthentication hook
- Linux sudo auth
- experimental ECC repair
- planned Nextcloud/WebDAV mirror
- planned read-only Linux FUSE browsing

Quick start should be practical:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export GSBACKUP_STORAGE="$(mktemp -d)"
python3 backup.py
```

If there is no `requirements.txt`, create one.

README must clearly say:

- Experimental.
- Do not use as the only copy of important data yet.
- Review the threat model before using.

### 2. Add `docs/demo.md`

Write a step-by-step manual demo that a reviewer can follow.

Demo should use a temporary storage path via `GSBACKUP_STORAGE` to avoid touching the user's real files.

Cover:

1. Create a sample file.
2. Start the app.
3. Initialize storage with a master password.
4. Add file in backup mode.
5. Modify sample file.
6. Add the same document again to create version 2.
7. List public documents and versions.
8. Show metadata after local auth.
9. Restore version 1 to a separate path.
10. Verify storage.
11. Configure TOTP if desired.
12. Enable paranoid view and open a file.

Add expected outcomes for each step.

Important: include a warning that `secure` mode deletes the source file after storing it, so the demo should use disposable files only.

### 3. Add `docs/threat-model.md`

Create a direct threat model with three sections:

#### Protects against / reduces risk of

- Lost or stolen remote copy: attacker sees encrypted vault files only.
- Curious or compromised cloud storage operator: remote should not see plaintext file contents.
- Accidental deletion or bad overwrite: older versions can be restored if vault still exists.
- Ransomware or corruption of working files: previous versions can help if vault/remote mirror survives.
- Object corruption: hash verification detects it; ECC may repair limited single-block-per-stripe corruption.
- Casual local access: local auth + optional TOTP gates protected metadata/open/restore operations.

#### Does not protect against

- Malware running on the client while the vault is unlocked.
- Keyloggers or screen capture malware.
- Weak master passwords.
- Viewer applications leaking plaintext into caches, thumbnails, recent-file databases, autosave files, swap, or screenshots.
- Deletion of every local and remote vault copy.
- Malicious remote rollback without trusted local state or future anti-rollback design.
- A compromised Python runtime or operating system.

#### Design implications

- Remote storage is untrusted.
- Client is trusted only while not compromised.
- Master password strength matters.
- TOTP is an interactive local authorization layer, not offline encryption security.
- Paranoid open reduces plaintext path lifetime but is not a complete anti-forensics tool.

### 4. Add `docs/storage-format.md`

Document current storage layout and formats at a high level.

Include:

- Storage root selection using `GSBACKUP_STORAGE` and platform defaults.
- Directory tree.
- Public catalog purpose.
- Keystore purpose.
- Record purpose.
- Object purpose.
- ECC purpose.
- Key hierarchy:
  - password -> scrypt KEK -> unwrap random master key
  - master key -> HKDF per-version content/meta keys
  - master key -> HKDF TOTP config wrapping key
- Content object format:
  - magic/version/flags/nonce/tag/compression metadata
  - ciphertext
  - GCM tag
- Metadata record:
  - encrypted protected metadata
  - AAD = public metadata bytes
  - metadata hash checked after decryption
- Integrity model:
  - plaintext hash
  - encrypted object hash
  - AEAD tag
  - public metadata hash embedded in protected metadata
  - ECC parity for selected object sizes

Keep it descriptive, not overly formal.

### 5. Add `docs/paranoid-view.md`

Explain paranoid view honestly.

Must say:

- It decrypts to a temporary file for an external viewer.
- In paranoid mode it tries to detect that the viewer opened the file, then unlinks the plaintext path.
- On POSIX systems an opened file may remain accessible to the process even after unlink.
- This reduces the lifetime of a named plaintext file.
- It does not stop the viewer, OS, thumbnailer, indexer, swap, screenshots, recent-file list, or autosave from leaking plaintext.
- Use only on trusted machines.

### 6. Add `SECURITY.md`

Include:

- Project is experimental.
- No security audit yet.
- Do not store the only copy of important files.
- How to report vulnerabilities: use GitHub issues for non-sensitive bugs; for sensitive issues, ask maintainer for private contact until a dedicated disclosure channel exists.
- Security boundaries copied from threat model.
- Crypto design notes and warnings against changing crypto without tests.

### 7. Add `ROADMAP.md`

Divide roadmap:

#### v0.1-alpha polish

- README/docs/demo/security docs
- pytest roundtrip tests
- CI
- safer atomic writes/fsync improvements
- packaging basics

#### v0.2 remote mirror

- Nextcloud/WebDAV push/pull/status
- remote verify
- conflict handling
- remote rollback notes

#### v0.3 storage efficiency

- chunked object format
- dedup across versions
- retention policies
- version pruning policies

#### v0.4 Linux convenience layer

- read-only FUSE mount
- tmpfs/RAM cache option
- explicit warning about plaintext exposure

### 8. Handle `crypto_standalone.py`

This file is dangerous for first impressions because it looks like a root-level crypto implementation and uses a simplified password derivation model.

Do one of the following:

Preferred:

- Move it to `examples/crypto_demo.py`.
- Add a top-level warning docstring:

```python
"""
Educational AES-GCM demo only.
Not used by Pop's storage core.
Real vault keys are managed by storage_core.keystore.
"""
```

Alternative:

- Delete it if it is unused and not referenced.

Do not leave it in the repository root without a warning.

### 9. Add basic tests

Use pytest.

Create tests that use temporary storage roots and disposable files only.

Minimum tests:

1. `test_add_restore_roundtrip`
   - init storage with master password
   - add a file
   - restore it to a new path
   - assert restored bytes match original

2. `test_multiple_versions`
   - add same document name twice with different contents
   - assert public catalog has two versions
   - restore v1 and v2 separately
   - assert bytes match expected versions

3. `test_wrong_password_fails`
   - init keystore with password A
   - attempt unlock with password B
   - assert failure

4. `test_corrupted_object_detected`
   - add file
   - corrupt the encrypted object on disk
   - run verify
   - assert corrupted or repair behavior is detected clearly

5. `test_secure_mode_removes_original_after_store`
   - create disposable source file
   - add with mode `secure`
   - assert original path no longer exists
   - assert restore works

Important test constraints:

- Avoid tests that require Touch ID, sudo, curses, opening external viewers, or real TOTP prompts.
- Monkeypatch or bypass local auth for core API tests where needed.
- Use `tmp_path` and pass explicit `storage_root` where possible.
- Do not write to the real user storage path in tests.

### 10. Add packaging basics

If time allows, add one of these:

Option A: `requirements.txt`

Required likely dependencies:

```text
cryptography
qrcode
pytest
```

Optional zstd dependency should be documented if used.

Option B: `pyproject.toml`

Only do this if it is quick and does not break running `backup.py` directly.

### 11. Add GitHub Actions CI

If tests are added, create `.github/workflows/tests.yml`:

- Ubuntu latest
- Python 3.11/3.12 if 3.14 is not available in CI
- install requirements
- run pytest

Do not make CI depend on macOS Touch ID or sudo auth flows.

## Code hardening tasks if time remains

These are secondary. Do not let them block docs/tests.

### Atomic writes

Review `storage_core/index.py`, `storage_core/init.py`, `storage_core/keystore.py`, and `storage_core/totp.py` for JSON writes.

Where safe, improve atomic write behavior:

- write temp file in same directory
- flush
- fsync file
- replace
- fsync parent directory on POSIX if practical

Do this carefully and add helper function if useful.

### Safer docs around local auth

Do not change `auth_mac.py` unless necessary. Document it instead:

- Swift LocalAuthentication first
- JXA LocalAuthentication fallback
- sudo fallback

If changing, preserve behavior and add comments. Avoid adding heavy dependencies.

### Naming

The code still uses `gs-backup-storage` internally. Do not rename storage paths/formats in this pass. In docs, explain that Pop is the project name and `gs-backup-storage` is the current internal app/storage name inherited from the prototype.

## Suggested commit sequence

Use small readable commits:

1. `docs: add README and project positioning`
2. `docs: add threat model and storage format notes`
3. `docs: document demo flow and paranoid view`
4. `chore: move standalone crypto demo out of root`
5. `test: add storage core roundtrip tests`
6. `ci: run pytest on GitHub Actions`

If making one commit only, use:

`docs,test: polish Pop for early OSS review`

## Definition of done

A reviewer should be able to open the repository and answer these questions quickly:

- What is Pop?
- Why is it not just Nextcloud sync?
- What works today?
- How do I run a safe demo?
- What are the security limits?
- What files are safe to sync to an untrusted cloud later?
- What is planned next?
- Are there basic tests?

Do not finish with only internal refactors. Public clarity is the priority.

