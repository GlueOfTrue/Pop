# Demo Guide

This demo uses a temporary storage root so it does not touch your real Pop or `gs-backup-storage` data.

Warning: `secure` mode deletes the source file after storing it. Use only disposable files during demos.

## 1. Prepare an Isolated Vault

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GSBACKUP_STORAGE="$(mktemp -d)"
export POP_DEMO_DIR="$(mktemp -d)"
printf "first version\n" > "$POP_DEMO_DIR/note.txt"
```

Expected outcome: `GSBACKUP_STORAGE` points at an empty temporary directory, and `note.txt` is a disposable sample file.

## 2. Start the App

```bash
python3 backup.py
```

Expected outcome: Pop starts the console interface. On first run it asks you to set and repeat a master password. The default language is currently Russian; use menu item `13` if you want to switch to English.

## 3. Initialize Storage

Enter a demo master password twice.

Expected outcome: Pop creates:

- `config.json`
- `meta/catalog.json`
- `meta/keystore.json`
- `meta/records/`
- `objects/`
- `ecc/`

## 4. Add the Sample File In Backup Mode

Choose `Add file`, then enter:

- Path: the value of `$POP_DEMO_DIR/note.txt`
- Document name: `note.txt`
- Mode: `backup`

Expected outcome: Pop stores `note.txt` as version 1 and leaves the source file in place.

## 5. Modify the Sample File

In another terminal:

```bash
printf "second version\n" > "$POP_DEMO_DIR/note.txt"
```

Expected outcome: the working file now has different bytes.

## 6. Add Version 2

Choose `Add file` again and use the same path and document name:

- Path: the value of `$POP_DEMO_DIR/note.txt`
- Document name: `note.txt`
- Mode: `backup`

Expected outcome: Pop stores `note.txt` as version 2 under the same document entry.

## 7. List Public Documents And Versions

Choose `List documents`.

Expected outcome: the public catalog shows `note.txt` with two versions. This view does not decrypt protected metadata.

## 8. Show Protected Metadata

Choose `Show metadata`, select `note.txt`, and leave version blank for the latest version or enter `1` for version 1.

Expected outcome: Pop asks for local authorization. On macOS it tries LocalAuthentication/Touch ID first and falls back to sudo. On Linux/POSIX it uses sudo validation. If TOTP is configured, it also asks for a TOTP code.

After authorization, Pop prints protected metadata such as source path, plaintext hash, encrypted object hash, sizes, compression metadata, and ECC metadata.

## 9. Restore Version 1

Choose `Restore file`, select `note.txt`, enter version `1`, and set the destination to:

```text
$POP_DEMO_DIR/restored-v1.txt
```

If your shell does not expand variables inside the app prompt, paste the full absolute path instead.

Expected outcome: Pop restores version 1 to the separate path. You can confirm it from another terminal:

```bash
cat "$POP_DEMO_DIR/restored-v1.txt"
```

The output should be:

```text
first version
```

## 10. Verify Storage

Choose `Verify storage`. For a quick demo, answer `N` when asked for deep verification. For a stronger check, answer `y`.

Expected outcome: Pop asks for local authorization and then reports all versions as OK.

## 11. Configure TOTP If Desired

Choose `Configure/rotate TOTP`.

You can leave the secret blank to let Pop generate one. Pop prints the Base32 secret and an `otpauth://` URI. If the optional `qrcode` package is available, it also renders an ASCII QR code.

Expected outcome: future protected operations ask for local authorization and then a TOTP code.

Important: TOTP is an interactive local authorization gate. It is not part of offline encryption security for a copied vault.

## 12. Enable Paranoid View And Open A File

Choose `Paranoid view` to toggle it on, then choose `Open file` and select `note.txt`.

Expected outcome: Pop decrypts the selected version to a temporary plaintext file, launches an external viewer, tries to detect that the viewer opened the file, then unlinks the plaintext path when possible.

This reduces the lifetime of a named plaintext file. It does not prevent leaks through viewer caches, thumbnails, indexing, swap, screenshots, recent-file lists, or autosave.

## 13. Try Secure Mode With A Disposable File

Create a separate disposable file:

```bash
printf "delete me after storing\n" > "$POP_DEMO_DIR/secure-note.txt"
```

Choose `Add file` with:

- Path: the full path to `secure-note.txt`
- Document name: `secure-note.txt`
- Mode: `secure`

Expected outcome: Pop stores the file and then deletes the source path. Restore it to a separate path to confirm the stored copy works.
