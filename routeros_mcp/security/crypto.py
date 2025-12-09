"""Cryptographic utilities for secure credential storage.

This module provides encryption and decryption functions for sensitive data
using Fernet symmetric encryption (AES-128-CBC with HMAC authentication).

Key features:
- Fernet-based encryption (cryptography library)
- Fail-fast key validation at startup
- Never logs plaintext secrets
- Constant-time comparisons where appropriate

Security design:
- Encryption key stored in environment variable
- Database compromise does not reveal secrets
- Each encrypted value has unique IV (implicit in Fernet)
- HMAC authentication prevents tampering

See docs/02-security-oauth-integration-and-access-control.md for key management.
"""

import logging
from typing import Final

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Sentinel value for insecure default key (lab only)
_INSECURE_LAB_KEY: Final[str] = "INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION"


class EncryptionError(Exception):
    """Base exception for encryption/decryption errors."""

    pass


class InvalidEncryptionKeyError(EncryptionError):
    """Raised when encryption key is invalid or malformed."""

    pass


class DecryptionError(EncryptionError):
    """Raised when decryption fails (wrong key, tampered data, etc)."""

    pass


class CredentialEncryption:
    """Encrypt and decrypt device credentials using Fernet.

    This class provides a simple interface for encrypting device credentials
    (passwords, API tokens, SSH keys) before storing in the database.

    Example:
        crypto = CredentialEncryption(settings.encryption_key)

        # Encrypt before storing
        encrypted = crypto.encrypt("my-secret-password")
        credential.encrypted_secret = encrypted

        # Decrypt when needed
        plaintext = crypto.decrypt(credential.encrypted_secret)
        # Use plaintext for API call, then discard
    """

    def __init__(self, encryption_key: str, environment: str = "lab") -> None:
        """Initialize credential encryption.

        Args:
            encryption_key: Base64-encoded Fernet key (32 bytes)
            environment: Deployment environment (lab/staging/prod)

        Raises:
            InvalidEncryptionKeyError: If key is invalid or missing in prod/staging
        """
        self.environment = environment
        self._validate_and_set_key(encryption_key)

    def _validate_and_set_key(self, encryption_key: str) -> None:
        """Validate encryption key and create Fernet instance.

        Args:
            encryption_key: Base64-encoded Fernet key

        Raises:
            InvalidEncryptionKeyError: If key is invalid
        """
        # Check for insecure default key
        if encryption_key == _INSECURE_LAB_KEY:
            if self.environment in ["staging", "prod"]:
                raise InvalidEncryptionKeyError(
                    f"Insecure default encryption key not allowed in {self.environment}. "
                    "Set ROUTEROS_MCP_ENCRYPTION_KEY environment variable."
                )
            else:
                logger.warning(
                    "Using insecure default encryption key (lab only). "
                    "Generate production key with: "
                    "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
                )
                # Generate a temporary key for lab use
                encryption_key = Fernet.generate_key().decode()

        # Validate key format
        try:
            key_bytes = encryption_key.encode("utf-8")
            self._fernet = Fernet(key_bytes)
        except Exception as e:
            raise InvalidEncryptionKeyError(
                f"Invalid encryption key format. Must be base64-encoded 32-byte Fernet key. "
                f"Generate with: python -c 'from cryptography.fernet import Fernet; "
                f"print(Fernet.generate_key().decode())' Error: {e}"
            ) from e

        logger.info(f"Encryption initialized for environment: {self.environment}")

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext credential.

        Args:
            plaintext: Secret to encrypt (password, token, etc)

        Returns:
            Base64-encoded encrypted string

        Example:
            encrypted = crypto.encrypt("my-secret-password")
            # Store encrypted in database
        """
        try:
            encrypted_bytes = self._fernet.encrypt(plaintext.encode("utf-8"))
            return encrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error("Encryption failed", exc_info=False)  # Don't log secret
            raise EncryptionError(f"Failed to encrypt data: {type(e).__name__}") from e

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt encrypted credential.

        Args:
            ciphertext: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext

        Raises:
            DecryptionError: If decryption fails (wrong key, tampered data)

        Example:
            plaintext = crypto.decrypt(credential.encrypted_secret)
            # Use plaintext, then immediately discard
        """
        try:
            decrypted_bytes = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken as e:
            logger.error("Decryption failed - invalid token or wrong key", exc_info=False)
            raise DecryptionError(
                "Failed to decrypt credential. Possible causes: wrong encryption key, "
                "tampered data, or key rotation without re-encrypting."
            ) from e
        except Exception as e:
            logger.error("Decryption failed", exc_info=False)
            raise DecryptionError(f"Failed to decrypt data: {type(e).__name__}") from e

    def rotate_key(self, old_key: str, new_key: str, ciphertext: str) -> str:
        """Rotate encryption key for a credential.

        Decrypts with old key and re-encrypts with new key.

        Args:
            old_key: Previous encryption key
            new_key: New encryption key
            ciphertext: Encrypted credential

        Returns:
            Re-encrypted credential with new key

        Example:
            # During key rotation
            old_crypto = CredentialEncryption(old_key)
            new_crypto = CredentialEncryption(new_key)

            new_encrypted = new_crypto.rotate_key(
                old_key, new_key, credential.encrypted_secret
            )
            credential.encrypted_secret = new_encrypted
        """
        # Decrypt with old key
        old_crypto = CredentialEncryption(old_key, self.environment)
        plaintext = old_crypto.decrypt(ciphertext)

        # Encrypt with new key
        new_crypto = CredentialEncryption(new_key, self.environment)
        return new_crypto.encrypt(plaintext)


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        Base64-encoded 32-byte key suitable for use with CredentialEncryption

    Example:
        key = generate_encryption_key()
        print(f"Export this key: export ROUTEROS_MCP_ENCRYPTION_KEY='{key}'")
    """
    return Fernet.generate_key().decode("utf-8")


def validate_encryption_key(key: str) -> bool:
    """Validate that a string is a valid Fernet encryption key.

    Args:
        key: String to validate

    Returns:
        True if valid, False otherwise

    Example:
        if validate_encryption_key(settings.encryption_key):
            print("Key is valid")
    """
    try:
        Fernet(key.encode("utf-8"))
        return True
    except Exception:
        return False
