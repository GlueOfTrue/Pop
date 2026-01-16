import base64
import getpass
import hashlib
import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class EncryptionResult:
    nonce_b64: str
    ciphertext_b64: str
    ciphertext_hash_hex: str


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def derive_branch_key(master_password: str, branch_id: str) -> bytes:
    """
    Derive a 256-bit key from a master password and a branch identifier.
    The user never provides the full key directly.
    """
    salt = hashlib.sha256(branch_id.encode("utf-8")).digest()
    return hashlib.pbkdf2_hmac(
        "sha256",
        master_password.encode("utf-8"),
        salt,
        200_000,
        dklen=32,
    )


def encrypt_message(message: str, key: bytes) -> EncryptionResult:
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, message.encode("utf-8"), None)
    return EncryptionResult(
        nonce_b64=base64.b64encode(nonce).decode("utf-8"),
        ciphertext_b64=base64.b64encode(ciphertext).decode("utf-8"),
        ciphertext_hash_hex=sha256_hex(ciphertext),
    )


def main() -> None:
    message = input("Введите строку: ").strip()
    if not message:
        raise SystemExit("Пустая строка. Нечего шифровать.")

    master_password = getpass.getpass("Мастер-пароль: ")
    if not master_password:
        raise SystemExit("Мастер-пароль не задан.")

    branch_id = input("Идентификатор ветки (по умолчанию: main): ").strip() or "main"

    plaintext_hash = sha256_hex(message.encode("utf-8"))
    key = derive_branch_key(master_password, branch_id)
    result = encrypt_message(message, key)

    print("Хэш открытого текста (SHA-256):", plaintext_hash)
    print("Nonce (Base64):", result.nonce_b64)
    print("Шифротекст (Base64):", result.ciphertext_b64)
    print("Хэш шифротекста (SHA-256):", result.ciphertext_hash_hex)


if __name__ == "__main__":
    main()
