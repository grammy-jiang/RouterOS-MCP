"""Security module for RouterOS MCP Service.

Provides authentication, authorization, and cryptographic utilities:
- crypto: Credential encryption/decryption (Fernet)
- auth: OAuth/OIDC authentication (Phase 4)
- authz: Authorization and access control

See docs/02-security-oauth-integration-and-access-control.md for details.
"""

from routeros_mcp.security.auth import (
    AuthenticationError,
    InvalidTokenError,
    MissingClaimError,
    OIDCTokenValidator,
    User,
    extract_bearer_token,
    get_phase1_user,
)
from routeros_mcp.security.authz import (
    AuthorizationError,
    CapabilityDeniedError,
    EnvironmentMismatchError,
    TierRestrictedError,
    ToolTier,
    UserRole,
    check_device_capability,
    check_environment_match,
    check_tool_authorization,
    check_user_role,
)
from routeros_mcp.security.crypto import (
    CredentialEncryption,
    DecryptionError,
    EncryptionError,
    InvalidEncryptionKeyError,
    generate_encryption_key,
    validate_encryption_key,
)

__all__ = [
    # Authentication
    "User",
    "OIDCTokenValidator",
    "AuthenticationError",
    "InvalidTokenError",
    "MissingClaimError",
    "extract_bearer_token",
    "get_phase1_user",
    # Authorization
    "ToolTier",
    "UserRole",
    "AuthorizationError",
    "EnvironmentMismatchError",
    "CapabilityDeniedError",
    "TierRestrictedError",
    "check_environment_match",
    "check_device_capability",
    "check_tool_authorization",
    "check_user_role",
    # Cryptography
    "CredentialEncryption",
    "EncryptionError",
    "DecryptionError",
    "InvalidEncryptionKeyError",
    "generate_encryption_key",
    "validate_encryption_key",
]
