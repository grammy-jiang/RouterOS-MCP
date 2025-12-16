# OAuth Setup Guide: Azure AD (Microsoft Entra ID)

## Purpose

Step-by-step guide for configuring Azure Active Directory (Microsoft Entra ID) as the OAuth 2.1 / OIDC provider for RouterOS MCP HTTP transport. This guide covers app registration, API permissions, token configuration, and integration with the MCP service.

**Target Audience**: Azure administrators and DevOps engineers deploying RouterOS MCP with Azure AD authentication.

---

## Prerequisites

- **Azure AD Tenant**: Active Azure AD tenant with admin access
- **Global Administrator** or **Application Administrator** role
- **RouterOS MCP Server**: Deployed and accessible (see [Deployment Guide](20-http-sse-transport-deployment-guide.md))
- **Public URL**: HTTPS endpoint for MCP service (e.g., `https://mcp.example.com`)

---

## Overview

**Azure AD Integration Flow:**

```
┌──────────────┐                    ┌─────────────────┐
│  MCP Client  │                    │   Azure AD      │
│ (User/App)   │                    │ (OAuth Provider)│
└──────┬───────┘                    └────────┬────────┘
       │                                     │
       │ 1. Request access token            │
       │ (client_credentials or auth_code)  │
       ├────────────────────────────────────>│
       │                                     │
       │ 2. Return JWT access token         │
       │<────────────────────────────────────┤
       │                                     │
       │ 3. Call MCP API with Bearer token  │
       ├────────────────────────────────────>│
       │                                ┌────▼─────┐
       │                                │   MCP    │
       │                                │  Server  │
       │                                └────┬─────┘
       │                                     │
       │ 4. Validate token with Azure AD    │
       │                                ├────>
       │                                │ JWKS
       │                                │<────
       │                                     │
       │ 5. Return MCP response             │
       │<────────────────────────────────────┤
       │                                     │
```

---

## Step 1: Register Application in Azure AD

### 1.1 Navigate to Azure Portal

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** (or **Microsoft Entra ID**)
3. Select **App registrations** from left menu
4. Click **+ New registration**

### 1.2 Configure Application Registration

**Basic Settings:**

- **Name**: `RouterOS MCP Service`
- **Supported account types**: 
  - `Accounts in this organizational directory only (Single tenant)` – Recommended for internal use
  - `Accounts in any organizational directory (Multi-tenant)` – For SaaS scenarios
- **Redirect URI**: 
  - Platform: `Web`
  - URI: `https://mcp.example.com/oauth/callback` (if using OAuth authorization code flow)
  - Leave blank for machine-to-machine (client credentials flow)

Click **Register**.

### 1.3 Note Application Details

After registration, note the following values (you'll need them later):

- **Application (client) ID**: `12345678-1234-1234-1234-123456789abc`
- **Directory (tenant) ID**: `87654321-4321-4321-4321-987654321def`
- **Object ID**: (not needed for MCP configuration)

---

## Step 2: Configure API Permissions

### 2.1 Expose an API (Create Application ID URI)

1. In your app registration, navigate to **Expose an API**
2. Click **+ Add a scope**
3. For **Application ID URI**, click **Set** and accept default: `api://12345678-1234-1234-1234-123456789abc`
4. Click **Save and continue**

### 2.2 Add API Scope

Create a scope for MCP access:

- **Scope name**: `MCP.Access`
- **Who can consent**: `Admins and users` (or `Admins only` for stricter control)
- **Admin consent display name**: `Access RouterOS MCP Service`
- **Admin consent description**: `Allows the application to access RouterOS MCP service on behalf of the signed-in user`
- **User consent display name**: `Access RouterOS MCP`
- **User consent description**: `Allow this application to manage RouterOS devices on your behalf`
- **State**: `Enabled`

Click **Add scope**.

### 2.3 Configure API Permissions (For Client Apps)

If you have client applications that will access MCP:

1. Navigate to **API permissions**
2. Click **+ Add a permission**
3. Select **My APIs** tab
4. Choose **RouterOS MCP Service**
5. Select **Delegated permissions** (for user context) or **Application permissions** (for service-to-service)
6. Check `MCP.Access`
7. Click **Add permissions**
8. Click **✓ Grant admin consent for [Tenant Name]** (requires admin role)

---

## Step 3: Create Client Secret (For Service-to-Service)

### 3.1 Generate Client Secret

1. Navigate to **Certificates & secrets**
2. Click **+ New client secret**
3. **Description**: `MCP Production Secret`
4. **Expires**: 
   - `6 months` – Recommended for production (requires rotation)
   - `12 months` – Acceptable
   - `24 months` – Maximum (not recommended, harder to rotate)
5. Click **Add**

### 3.2 Copy Secret Value

**⚠️ CRITICAL**: Copy the secret **Value** (not the Secret ID) immediately. You cannot view it again.

```
Example: your-secret-value-here-abc123def456
```

Store securely in:
- Azure Key Vault
- HashiCorp Vault
- Environment variable from secure secret store
- **NEVER** commit to git or store in plaintext

---

## Step 4: Configure Token Claims (Optional)

### 4.1 Add Optional Claims

To include user roles or groups in tokens:

1. Navigate to **Token configuration**
2. Click **+ Add optional claim**
3. **Token type**: `Access`
4. Select claims:
   - `email` – User email address
   - `family_name` – User last name
   - `given_name` – User first name
   - `upn` – User principal name
5. Click **Add**
6. Check **Turn on the Microsoft Graph email, profile permission** if prompted

### 4.2 Add Groups Claim (For Role-Based Access)

If using Azure AD groups for MCP roles:

1. In **Token configuration**, click **+ Add groups claim**
2. Select **Security groups** (or **All groups**)
3. For **Customize token properties**, select:
   - ID: `Group ID`
   - Access: `Group ID`
   - SAML: `sAMAccountName` (if applicable)
4. Click **Add**

Now access tokens will include `groups` claim with group object IDs.

---

## Step 5: Configure RouterOS MCP Service

### 5.1 Set Environment Variables

**For Single-Tenant Azure AD:**

```bash
# Enable OIDC
export ROUTEROS_MCP_OIDC_ENABLED=true

# Azure AD Configuration
export ROUTEROS_MCP_OIDC_PROVIDER_URL=https://login.microsoftonline.com/{tenant-id}/v2.0
export ROUTEROS_MCP_OIDC_CLIENT_ID=12345678-1234-1234-1234-123456789abc
export ROUTEROS_MCP_OIDC_AUDIENCE=api://12345678-1234-1234-1234-123456789abc

# IMPORTANT: NEVER enable this in production
export ROUTEROS_MCP_OIDC_SKIP_VERIFICATION=false
```

**Replace Placeholders:**
- `{tenant-id}` → Your Azure AD tenant ID (from Step 1.3)
- `12345678-...` → Your application (client) ID (from Step 1.3)

**Token endpoint note:** Azure AD's OAuth 2.0 token endpoint lives at `/oauth2/v2.0/token`. Example clients in this repo automatically derive that endpoint from a provider URL ending in `/v2.0`, so you do **not** need to embed `/oauth2/v2.0` in `ROUTEROS_MCP_OIDC_PROVIDER_URL`.

### 5.2 Alternative: Configuration File

Create `config/azure-prod.yaml`:

```yaml
# Production configuration with Azure AD
environment: prod
debug: false
log_level: INFO
log_format: json

# MCP HTTP Transport
mcp_transport: http
mcp_http_host: 0.0.0.0
mcp_http_port: 8080
mcp_http_base_path: /mcp

# Database
database_url: postgresql+asyncpg://user:pass@db.example.com/routeros_mcp
database_pool_size: 20

# Azure AD OIDC
oidc_enabled: true
oidc_provider_url: https://login.microsoftonline.com/87654321-4321-4321-4321-987654321def/v2.0
oidc_client_id: 12345678-1234-1234-1234-123456789abc
oidc_audience: api://12345678-1234-1234-1234-123456789abc
oidc_skip_verification: false

# Encryption key (MUST come from environment variable)
# export ROUTEROS_MCP_ENCRYPTION_KEY=...
```

Start MCP with: `routeros-mcp --config config/azure-prod.yaml`

---

## Step 6: Test Authentication

### 6.1 Obtain Access Token (Client Credentials Flow)

**Using curl:**

```bash
# Request token from Azure AD
curl -X POST https://login.microsoftonline.com/{tenant-id}/oauth2/v2.0/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=12345678-1234-1234-1234-123456789abc" \
  -d "client_secret=your-secret-value-here" \
  -d "scope=api://12345678-1234-1234-1234-123456789abc/.default" \
  -d "grant_type=client_credentials"
```

**Response:**

```json
{
  "token_type": "Bearer",
  "expires_in": 3599,
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6..."
}
```

**Save the `access_token` value.**

### 6.2 Call MCP API with Token

```bash
# Set token variable
export TOKEN="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsIng1dCI6..."

# Test health endpoint (no auth required)
curl https://mcp.example.com/health

# Test MCP initialize (requires auth)
curl -X POST https://mcp.example.com/mcp/initialize \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "test-client",
        "version": "1.0.0"
      }
    }
  }'
```

**Expected Response:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": {
      "tools": {},
      "resources": {},
      "prompts": {}
    },
    "serverInfo": {
      "name": "routeros-mcp",
      "version": "1.0.0"
    }
  }
}
```

### 6.3 Decode and Inspect Token (Optional)

Use [jwt.io](https://jwt.io) or decode locally:

```bash
# Decode JWT (header and payload)
echo "$TOKEN" | cut -d. -f2 | base64 -d | jq .
```

**Verify Claims:**
- `iss`: `https://login.microsoftonline.com/{tenant-id}/v2.0`
- `aud`: `api://12345678-1234-1234-1234-123456789abc`
- `exp`: Unix timestamp (not expired)
- `appid` or `azp`: Client ID of requesting application

---

## Step 7: Configure User Roles (Optional)

### 7.1 Create Azure AD Groups

If using group-based role mapping:

1. Navigate to **Azure Active Directory** > **Groups**
2. Click **+ New group**
3. Create groups for each MCP role:
   - **Group name**: `MCP-ReadOnly`, `MCP-OpsRW`, `MCP-Admin`
   - **Group type**: `Security`
4. Add users to groups as needed

### 7.2 Map Groups to MCP Roles

In MCP configuration, map Azure AD group IDs to roles:

```yaml
# config/azure-prod.yaml
authz_group_mappings:
  # Azure AD group object IDs → MCP roles
  "11111111-1111-1111-1111-111111111111": "read_only"   # MCP-ReadOnly
  "22222222-2222-2222-2222-222222222222": "ops_rw"      # MCP-OpsRW
  "33333333-3333-3333-3333-333333333333": "admin"       # MCP-Admin
```

**Find Group Object ID:**
1. Navigate to **Azure AD** > **Groups**
2. Click on group name
3. Copy **Object ID** from Overview page

---

## Troubleshooting

### Issue: "AADSTS50001: The application is not found in the tenant"

**Cause**: Application ID incorrect or not registered in tenant.

**Solution**:
1. Verify `oidc_client_id` matches Application (client) ID from Azure Portal
2. Ensure application is registered in correct tenant
3. Check tenant ID in `oidc_provider_url`

### Issue: "AADSTS70011: Invalid scope"

**Cause**: Requested scope not defined in application.

**Solution**:
1. Verify scope in token request matches **Expose an API** configuration
2. Use `.default` scope for client credentials: `api://{client-id}/.default`
3. Grant admin consent if using delegated permissions

### Issue: "AADSTS7000215: Invalid client secret"

**Cause**: Client secret expired, incorrect, or not copied fully.

**Solution**:
1. Generate new client secret in Azure Portal
2. Copy entire secret value (not Secret ID)
3. Update `client_secret` in token request
4. Ensure no extra spaces or line breaks in secret value

### Issue: "Token validation failed: Invalid signature"

**Cause**: MCP server cannot verify token signature.

**Solution**:
1. Check network connectivity to `login.microsoftonline.com` (port 443)
2. Verify `oidc_provider_url` includes correct tenant ID
3. Ensure system clock is accurate (within 30 seconds)
4. Check firewall rules allow outbound HTTPS

### Issue: "Token expired"

**Cause**: Access token has expired (default: 1 hour).

**Solution**:
1. Request new access token
2. Implement token refresh logic in client application
3. Cache tokens and refresh before expiry

---

## Security Best Practices

### Production Security Checklist

- [ ] **Use HTTPS Only**: Azure AD requires HTTPS for production redirect URIs
- [ ] **Rotate Secrets**: Set expiration ≤ 6 months, rotate before expiry
- [ ] **Least Privilege**: Grant minimum required API permissions
- [ ] **Admin Consent**: Require admin consent for sensitive scopes
- [ ] **Multi-Factor Authentication**: Enforce MFA for admin users
- [ ] **Conditional Access**: Use Azure AD Conditional Access policies
- [ ] **Monitor Sign-Ins**: Enable Azure AD sign-in logs and alerts
- [ ] **Restrict Token Lifetime**: Configure shorter token lifetimes if needed
- [ ] **Validate Issuer**: Ensure `iss` claim matches expected Azure AD tenant
- [ ] **Validate Audience**: Ensure `aud` claim matches your Application ID URI

### Secret Rotation Procedure

**Before Secret Expires:**

1. Generate new secret in Azure Portal (keep old secret active)
2. Update MCP production environment with new secret
3. Deploy and verify MCP service works with new secret
4. Delete old secret in Azure Portal (after 24-48 hours)

**Automation:**

Use Azure Key Vault and managed identities to avoid manual secret management:

```bash
# Use Azure Managed Identity to access Key Vault (no secrets in config)
export AZURE_KEY_VAULT_NAME=my-keyvault
export ROUTEROS_MCP_OIDC_CLIENT_SECRET_FROM_KEYVAULT=true
```

---

## Advanced Configuration

### Multi-Tenant Applications

For SaaS scenarios supporting multiple Azure AD tenants:

```bash
# Use "common" or "organizations" instead of tenant ID
export ROUTEROS_MCP_OIDC_PROVIDER_URL=https://login.microsoftonline.com/organizations/v2.0
export ROUTEROS_MCP_OIDC_CLIENT_ID=12345678-1234-1234-1234-123456789abc
export ROUTEROS_MCP_OIDC_AUDIENCE=api://12345678-1234-1234-1234-123456789abc

# Validate issuer includes any tenant ID
export ROUTEROS_MCP_OIDC_VALIDATE_ISSUER_TENANT=false
```

### On-Behalf-Of (OBO) Flow

For scenarios where MCP acts on behalf of user to call downstream APIs:

```python
# Not yet implemented in Phase 2 - requires additional OAuth flows
# Future: Exchange user token for downstream service token
```

### Certificate-Based Authentication

Instead of client secrets, use X.509 certificates:

1. Generate certificate: `openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365`
2. Upload public certificate to Azure AD (App registration > Certificates & secrets)
3. Use certificate for token requests (requires `msal` library enhancement)

---

## Related Documentation

- [HTTP/SSE Transport Deployment Guide](20-http-sse-transport-deployment-guide.md)
- [OAuth Setup: Okta](22-oauth-setup-okta.md)
- [OAuth Setup: Auth0](23-oauth-setup-auth0.md)
- [HTTP Transport Troubleshooting](24-http-transport-troubleshooting.md)
- [Security & Access Control](02-security-oauth-integration-and-access-control.md)

---

## Additional Resources

**Azure AD Documentation:**
- [Azure AD App Registration](https://learn.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- [OAuth 2.0 Client Credentials Flow](https://learn.microsoft.com/en-us/azure/active-directory/develop/v2-oauth2-client-creds-grant-flow)
- [Azure AD Token Reference](https://learn.microsoft.com/en-us/azure/active-directory/develop/access-tokens)
- [Azure AD Best Practices](https://learn.microsoft.com/en-us/azure/active-directory/develop/identity-platform-integration-checklist)

**Tools:**
- [Azure AD Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer)
- [JWT Decoder](https://jwt.io)
- [Microsoft Authentication Library (MSAL)](https://learn.microsoft.com/en-us/azure/active-directory/develop/msal-overview)
