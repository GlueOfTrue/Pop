# Reviewer Notes

These notes collect implementation facts and security follow-ups that are useful when evaluating the current prototype. They are not a stable specification.

## Project Shape

Pop is a local-first encrypted backup vault. The current app entry point is `backup.py`; the storage and security-sensitive logic lives in `storage_core/`.

The storage root is selected through `GSBACKUP_STORAGE` when set. Otherwise Pop uses platform defaults from `storage_core/paths.py`. The project name is Pop, while some internal storage paths still use the inherited `gs-backup-storage` name for compatibility.

Current storage layout:

```text
<storage-root>/
  config.json
  meta/
    catalog.json
    keystore.json
    totp.json
    records/
      <doc_id>/
        v<version>.bin
  objects/
    <encrypted_object_hash>
  ecc/
    <parity_hash>
```

## Security Boundaries

- Remote storage is treated as untrusted.
- The Nextcloud/WebDAV mirror is push+status only.
- Remote data and the remote manifest are not trusted for restore, rollback, deletion, pruning, or conflict resolution.
- File contents are encrypted before storage.
- Public catalog data is intentionally visible to anyone who can read the vault.
- Protected metadata records are encrypted separately from content objects.
- Restore and open operations produce local plaintext after interactive authorization.
- Viewer applications may still leak plaintext through caches, thumbnails, recent-file databases, autosave, swap, screenshots, or indexing.

## Current Hardening Status

- Source symlinks are refused when adding files.
- Restore refuses symlink destinations and non-regular overwrite targets.
- Restore writes through an atomic temporary file in the destination parent directory.
- Plaintext temp files for external open use sanitized basenames and private file permissions.
- Sensitive vault writes use atomic helpers and private permissions where practical.
- Default prune behavior does not delete corrupted referenced versions; destructive cleanup is explicit.
- Linux local authorization refuses root execution unless `POP_ALLOW_ROOT=1` is set.
- macOS local authorization avoids embedding unescaped prompt text in generated Swift/JXA source.
- Nextcloud mirroring rejects symlinks and only uploads allowlisted vault files.

## Known Security Follow-Ups

- Add a privacy mode that stores opaque document aliases in the public catalog instead of user-visible document names.
- Make `source_path` in protected metadata optional or redactable.
- Gate networked remote status behind local authorization, or split local mirror diff from remote status.
- Move Nextcloud app passwords out of environment variables into macOS Keychain, Linux Secret Service, `pass`, or an interactive prompt fallback.
- Add remote anti-rollback state before implementing pull or restore-from-remote.
- Consider Argon2id support or stronger KDF migration for the keystore.
- Make storage verification read-only by default and move ECC repair behind an explicit repair action.
- Add signed release checksums before treating packaged app artifacts as distribution-ready.

## Safe Evaluation Checklist

- Use a temporary storage root with `GSBACKUP_STORAGE`.
- Use disposable source files for demos.
- Avoid `secure` mode unless the source file is disposable; it removes the source after storing it.
- Treat restored files and external viewer temp files as plaintext exports.
- Treat the Nextcloud mirror as a ciphertext backup copy only, not as a trusted restore source.
