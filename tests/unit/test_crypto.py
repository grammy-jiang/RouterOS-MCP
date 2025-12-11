"""Tests for credential encryption module."""

import pytest
from cryptography.fernet import Fernet

from routeros_mcp.security.crypto import (
    CredentialEncryption,
    DecryptionError,
    EncryptionError,
    InvalidEncryptionKeyError,
    decrypt_string,
    encrypt_string,
    generate_encryption_key,
    validate_encryption_key,
)


class TestCredentialEncryption:
    """Tests for CredentialEncryption class."""

    def test_successful_encryption_decryption_roundtrip(self) -> None:
        """Test successful encryption and decryption."""
        key = generate_encryption_key()
        crypto = CredentialEncryption(key, environment="lab")

        plaintext = "my-secret-password"
        encrypted = crypto.encrypt(plaintext)
        decrypted = crypto.decrypt(encrypted)

        assert decrypted == plaintext
        assert encrypted != plaintext

    def test_different_keys_produce_different_ciphertexts(self) -> None:
        """Test that different keys produce different ciphertexts."""
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()
        crypto1 = CredentialEncryption(key1, environment="lab")
        crypto2 = CredentialEncryption(key2, environment="lab")

        plaintext = "test-password"
        encrypted1 = crypto1.encrypt(plaintext)
        encrypted2 = crypto2.encrypt(plaintext)

        assert encrypted1 != encrypted2

    def test_insecure_lab_key_in_lab_environment(self) -> None:
        """Test that insecure lab key is allowed in lab environment."""
        crypto = CredentialEncryption(
            "INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION", environment="lab"
        )

        # Should work without raising error
        plaintext = "test"
        encrypted = crypto.encrypt(plaintext)
        decrypted = crypto.decrypt(encrypted)
        assert decrypted == plaintext

    def test_insecure_lab_key_in_staging_raises_error(self) -> None:
        """Test that insecure lab key is rejected in staging environment."""
        with pytest.raises(InvalidEncryptionKeyError, match="Insecure default encryption key"):
            CredentialEncryption("INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION", environment="staging")

    def test_insecure_lab_key_in_prod_raises_error(self) -> None:
        """Test that insecure lab key is rejected in prod environment."""
        with pytest.raises(InvalidEncryptionKeyError, match="Insecure default encryption key"):
            CredentialEncryption("INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION", environment="prod")

    def test_invalid_key_format_raises_error(self) -> None:
        """Test that invalid key format is detected."""
        with pytest.raises(InvalidEncryptionKeyError, match="Invalid encryption key format"):
            CredentialEncryption("not-a-valid-fernet-key", environment="lab")

    def test_decryption_with_wrong_key_raises_error(self) -> None:
        """Test that decryption with wrong key raises DecryptionError."""
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()
        crypto1 = CredentialEncryption(key1, environment="lab")
        crypto2 = CredentialEncryption(key2, environment="lab")

        encrypted = crypto1.encrypt("test")

        with pytest.raises(DecryptionError, match="Failed to decrypt credential"):
            crypto2.decrypt(encrypted)

    def test_decryption_with_tampered_ciphertext_raises_error(self) -> None:
        """Test that tampered ciphertext raises DecryptionError."""
        key = generate_encryption_key()
        crypto = CredentialEncryption(key, environment="lab")

        encrypted = crypto.encrypt("test")
        tampered = encrypted[:-5] + "xxxxx"

        with pytest.raises(DecryptionError):
            crypto.decrypt(tampered)

    def test_encrypt_unicode_text(self) -> None:
        """Test encryption of unicode text."""
        key = generate_encryption_key()
        crypto = CredentialEncryption(key, environment="lab")

        plaintext = "パスワード123 🔒"
        encrypted = crypto.encrypt(plaintext)
        decrypted = crypto.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_empty_string(self) -> None:
        """Test encryption of empty string."""
        key = generate_encryption_key()
        crypto = CredentialEncryption(key, environment="lab")

        plaintext = ""
        encrypted = crypto.encrypt(plaintext)
        decrypted = crypto.decrypt(encrypted)

        assert decrypted == plaintext

    def test_key_rotation(self) -> None:
        """Test key rotation functionality."""
        old_key = generate_encryption_key()
        new_key = generate_encryption_key()
        old_crypto = CredentialEncryption(old_key, environment="lab")
        new_crypto = CredentialEncryption(new_key, environment="lab")

        plaintext = "test-password"
        old_encrypted = old_crypto.encrypt(plaintext)

        # Rotate key
        new_encrypted = new_crypto.rotate_key(old_key, new_key, old_encrypted)

        # Should decrypt with new key
        decrypted = new_crypto.decrypt(new_encrypted)
        assert decrypted == plaintext

        # Should NOT decrypt with old key
        with pytest.raises(DecryptionError):
            old_crypto.decrypt(new_encrypted)

    def test_encrypt_error_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Encryption errors should be wrapped in EncryptionError without leaking secrets."""
        key = generate_encryption_key()
        crypto = CredentialEncryption(key, environment="lab")

        monkeypatch.setattr(
            crypto._fernet, "encrypt", lambda _: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        with pytest.raises(EncryptionError, match="RuntimeError"):
            crypto.encrypt("secret")

    def test_decrypt_unexpected_error_wrapped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unexpected decrypt errors should raise DecryptionError with error type."""
        key = generate_encryption_key()
        crypto = CredentialEncryption(key, environment="lab")

        monkeypatch.setattr(
            crypto._fernet, "decrypt", lambda _: (_ for _ in ()).throw(RuntimeError("boom"))
        )

        with pytest.raises(DecryptionError, match="RuntimeError"):
            crypto.decrypt("invalid")

    def test_helper_encrypt_decrypt_string_functions(self) -> None:
        """Helper functions should round-trip correctly."""
        key = generate_encryption_key()
        ciphertext = encrypt_string("helper-secret", key)
        assert decrypt_string(ciphertext, key) == "helper-secret"

    def test_validate_encryption_key_handles_type_error(self) -> None:
        """validate_encryption_key should return False for non-string values."""
        assert validate_encryption_key(None) is False


class TestGenerateEncryptionKey:
    """Tests for generate_encryption_key function."""

    def test_generates_valid_fernet_key(self) -> None:
        """Test that generated key is valid Fernet key."""
        key = generate_encryption_key()

        # Should be able to create Fernet instance
        fernet = Fernet(key.encode())
        assert fernet is not None

    def test_generates_different_keys(self) -> None:
        """Test that multiple calls generate different keys."""
        key1 = generate_encryption_key()
        key2 = generate_encryption_key()

        assert key1 != key2


class TestValidateEncryptionKey:
    """Tests for validate_encryption_key function."""

    def test_valid_key_returns_true(self) -> None:
        """Test that valid key returns True."""
        key = generate_encryption_key()
        assert validate_encryption_key(key) is True

    def test_invalid_key_returns_false(self) -> None:
        """Test that invalid key returns False."""
        assert validate_encryption_key("not-a-valid-key") is False

    def test_empty_string_returns_false(self) -> None:
        """Test that empty string returns False."""
        assert validate_encryption_key("") is False

    def test_non_utf8_string_returns_false(self) -> None:
        """Test that non-UTF-8 string returns False."""
        # This is a bit tricky since Python 3 strings are always valid UTF-8
        # But we can test the error handling path
        assert validate_encryption_key("short") is False

    def test_non_base64_string_returns_false(self) -> None:
        """Test that non-base64 string returns False."""
        assert validate_encryption_key("this-is-not-base64!@#$") is False
