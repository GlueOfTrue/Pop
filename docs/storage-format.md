# Storage Format Overview

This is a descriptive overview of the current prototype format. It is not a formal stable specification yet.

## Storage Root

The storage root is selected with the `GSBACKUP_STORAGE` environment variable when it is set. Otherwise Pop uses platform defaults from `storage_core/paths.py`.

Pop is the project name, but the current internal app/storage name is still `gs-backup-storage`. This compatibility detail is intentionally preserved for now.

On macOS, the default path is:

```text
~/Library/Application Support/gs-backup-storage
```

On Linux, Pop first reuses the legacy macOS-like path if it already exists. Otherwise it uses:

```text
$XDG_DATA_HOME/gs-backup-storage
```

or:

```text
~/.local/share/gs-backup-storage
```

## Directory Tree

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

## Public Catalog

`meta/catalog.json` is intentionally public metadata. It maps document IDs to document names and version numbers. It does not contain plaintext file contents or protected per-version metadata.

The public document metadata is canonicalized and used as AEAD additional authenticated data for related encrypted records and content objects.

## Keystore

`meta/keystore.json` stores parameters for unwrapping the random vault master key:

```text
master password -> scrypt KEK -> AES-GCM unwrap -> random master key
```

The keystore stores the scrypt salt and parameters plus the AES-GCM nonce and wrapped master key ciphertext. The master key itself is not stored in plaintext.

## Metadata Records

Each `meta/records/<doc_id>/v<version>.bin` file contains encrypted protected metadata for one document version.

The metadata key is derived from the master key:

```text
master key -> HKDF(doc_id, version, "meta") -> metadata key
```

The protected metadata includes source path, storage mode, creation time, public metadata hash, plaintext hash, plaintext size, encrypted object hash, encrypted size, compression details, and optional ECC metadata.

The record uses AEAD additional authenticated data equal to the canonical public metadata bytes. After decrypting, Pop recomputes and checks `meta_plain_hash`; it also verifies the embedded public metadata hash.

## Objects

`objects/<encrypted_object_hash>` stores encrypted file content. The object name is the SHA-256 hash of the encrypted object bytes.

The content key is derived from the master key:

```text
master key -> HKDF(doc_id, version, "content") -> content key
```

Content is compressed before encryption. The default path uses zlib unless the optional zstd module imported by `storage_core.crypto` is available.

## Content Object Format

Encrypted content objects use a small stream header followed by ciphertext and a GCM tag:

```text
magic/version/flags/nonce_length/tag_length/compression_algo/nonce
ciphertext
gcm_tag
```

Current magic is `GSB1`. Version 2 records compression metadata in the header. AES-GCM authenticates the ciphertext plus the public metadata AAD.

## TOTP Config

`meta/totp.json` is present only when TOTP is configured. It stores encrypted TOTP settings.

The TOTP config wrapping key is derived from the master key:

```text
master key -> HKDF("gs-backup:totp", random salt) -> TOTP config key
```

TOTP is an interactive local authorization gate. It is not part of offline encryption security for a copied vault.

## ECC

`ecc/<parity_hash>` stores XOR parity data for encrypted objects that are small enough for the current ECC policy. The current scheme is per-stripe XOR parity with block hashes. It may repair one corrupted block per stripe when the parity object and remaining blocks are valid.

ECC is experimental. It helps detect and sometimes repair object corruption, but it is not a replacement for multiple real backups.

## Integrity Model

Pop combines several integrity checks:

- Plaintext SHA-256 hash stored in protected metadata.
- Encrypted object SHA-256 hash used as the object filename.
- AES-GCM authentication tag over encrypted content and public metadata AAD.
- Public metadata hash embedded in protected metadata.
- Protected metadata hash checked after metadata decryption.
- ECC parity and block hashes for selected object sizes.

Verification first checks object hashes and sizes. Deep verification also decrypts content and checks plaintext hash and size.
