# OAuth Setup Guide: Okta

## Purpose

Step-by-step guide for configuring Okta as the OAuth 2.1 / OIDC provider for RouterOS MCP HTTP transport. This guide covers application setup, authorization server configuration, token customization, and integration with the MCP service.

**Target Audience**: Okta administrators and DevOps engineers deploying RouterOS MCP with Okta authentication.

---

## Prerequisites

- **Okta Account**: Active Okta organization (free developer account or paid subscription)
- **Okta Administrator** or **Application Administrator** role
- **RouterOS MCP Server**: Deployed and accessible (see [Deployment Guide](20-http-sse-transport-deployment-guide.md))
- **Public URL**: HTTPS endpoint for MCP service (e.g., `https://mcp.example.com`)

---

## Overview

**Okta Integration Flow:**

```
┌──────────────┐                    ┌─────────────────┐
│  MCP Client  │                    │      Okta       │
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
       │ 4. Validate token with Okta        │
       │                                ├────>
       │                                │ JWKS
       │                                │<────
       │                                     │
       │ 5. Return MCP response             │
       │<────────────────────────────────────┤
       │                                     │
```

---

## Step 1: Create Okta Application

### 1.1 Log in to Okta Admin Console

1. Navigate to your Okta organization: `https://your-org.okta.com/admin`
2. Sign in with administrator credentials

### 1.2 Create Application Integration

1. Navigate to **Applications** > **Applications** from left menu
2. Click **Create App Integration**
3. Select sign-in method:
   - **OIDC - OpenID Connect** (recommended for OAuth 2.1)
4. Select application type:
   - **Web Application** (for server-side apps with client secret)
   - **Native Application** (for mobile/desktop apps)
   - **Service (Machine-to-Machine)** (for API-to-API, client credentials flow)
5. Click **Next**

### 1.3 Configure Application Settings

**For Service (Machine-to-Machine) - Recommended:**

- **App integration name**: `RouterOS MCP Service`
- **Grant type**: ✓ `Client Credentials`
- **Controlled access**: 
  - `Allow everyone in your organization to access` (default)
  - Or restrict to specific groups

Click **Save**.

**For Web Application (User Context):**

- **App integration name**: `RouterOS MCP Service`
- **Grant type**: 
  - ✓ `Authorization Code`
  - ✓ `Refresh Token` (optional, for long-lived sessions)
- **Sign-in redirect URIs**: `https://mcp.example.com/oauth/callback`
- **Sign-out redirect URIs**: `https://mcp.example.com/logout` (optional)
- **Controlled access**: `Allow everyone in your organization to access`

Click **Save**.

### 1.4 Note Application Credentials

After creation, note the following values:

- **Client ID**: `0oa1b2c3d4e5f6g7h8i9`
- **Client secret**: Click **Copy to clipboard** (keep secure)
- **Okta domain**: `https://your-org.okta.com`

---

## Step 2: Configure Authorization Server

Okta uses authorization servers to issue tokens. By default, Okta provides:
- **Org Authorization Server**: For Okta API access
- **Default Authorization Server**: For custom applications (recommended for MCP)

### 2.1 Navigate to Authorization Server

1. Go to **Security** > **API** from left menu
2. Select **Authorization Servers** tab
3. Click on **default** authorization server (or create a custom one)

### 2.2 Note Authorization Server Details

- **Issuer URI**: `https://your-org.okta.com/oauth2/default`
- **Metadata URI**: `https://your-org.okta.com/oauth2/default/.well-known/oauth-authorization-server`

**This issuer URI is your OIDC provider URL for MCP configuration.**

### 2.3 Configure Access Policies (Optional)

To restrict which clients can request tokens:

1. Click **Access Policies** tab in authorization server
2. Click **Add Policy**
3. **Name**: `MCP Service Policy`
4. **Description**: `Policy for RouterOS MCP service access`
5. **Assign to**: Select your MCP application
6. Click **Create Policy**

### 2.4 Add Policy Rule

1. Click **Add Rule** in the new policy
2. **Rule Name**: `MCP Service Rule`
3. **Grant type is**: ✓ `Client Credentials` (or `Authorization Code` if using user context)
4. **User is**: `Any user assigned the app`
5. **Scopes requested**: `Any scopes`
6. **Access token lifetime**: `1 hour` (default, adjust as needed)
7. Click **Create Rule**

---

## Step 3: Configure Custom Claims (Optional)

Add custom claims to access tokens for role-based access control.

### 3.1 Add Custom Scope

1. In authorization server, click **Scopes** tab
2. Click **Add Scope**
3. **Name**: `mcp:access`
4. **Description**: `Access to RouterOS MCP service`
5. **Default scope**: ✓ (checked)
6. Click **Create**

### 3.2 Add Custom Claim for User Role

1. Click **Claims** tab in authorization server
2. Click **Add Claim**
3. **Name**: `mcp_role`
4. **Include in token type**: `Access Token`
5. **Value type**: `Expression`
6. **Value**: 
   ```javascript
   // Example: Map Okta groups to MCP roles
   String role = "read_only";
   if (user.isMemberOf("MCP-Admin")) {
     role = "admin";
   } else if (user.isMemberOf("MCP-OpsRW")) {
     role = "ops_rw";
   }
   role
   ```
7. **Include in**: `Any scope`
8. Click **Create**

### 3.3 Add Groups Claim (Alternative)

To include user groups in token:

1. Click **Add Claim**
2. **Name**: `groups`
3. **Include in token type**: `Access Token`
4. **Value type**: `Groups`
5. **Filter**: `Matches regex` → `.*` (all groups) or `^MCP-.*` (only MCP groups)
6. **Include in**: `Any scope`
7. Click **Create**

---

## Step 4: Create Okta Groups for Roles (Optional)

If using group-based role mapping:

### 4.1 Create Groups

1. Navigate to **Directory** > **Groups**
2. Click **Add Group**
3. Create groups for each MCP role:
   - **Name**: `MCP-ReadOnly`, **Description**: `MCP read-only users`
   - **Name**: `MCP-OpsRW`, **Description**: `MCP operators with write access`
   - **Name**: `MCP-Admin`, **Description**: `MCP administrators`
4. Click **Save**

### 4.2 Assign Users to Groups

1. Click on group name
2. Click **Manage People**
3. Search and add users
4. Click **Save**

### 4.3 Assign Groups to Application

1. Navigate to **Applications** > **Applications**
2. Click on **RouterOS MCP Service**
3. Click **Assignments** tab
4. Click **Assign** > **Assign to Groups**
5. Select `MCP-ReadOnly`, `MCP-OpsRW`, `MCP-Admin`
6. Click **Assign** > **Done**

---

## Step 5: Configure RouterOS MCP Service

### 5.1 Set Environment Variables

```bash
# Enable OIDC
export ROUTEROS_MCP_OIDC_ENABLED=true

# Okta Configuration
export ROUTEROS_MCP_OIDC_PROVIDER_URL=https://your-org.okta.com/oauth2/default
export ROUTEROS_MCP_OIDC_CLIENT_ID=0oa1b2c3d4e5f6g7h8i9
export ROUTEROS_MCP_OIDC_AUDIENCE=api://default  # Or custom audience

# IMPORTANT: NEVER enable this in production
export ROUTEROS_MCP_OIDC_SKIP_VERIFICATION=false
```

**Replace Placeholders:**
- `your-org` → Your Okta organization subdomain (e.g., `dev-12345`)
- `0oa1b2c3d4e5f6g7h8i9` → Your application Client ID (from Step 1.4)
- `/oauth2/default` → Your authorization server path (from Step 2.2)

### 5.2 Alternative: Configuration File

Create `config/okta-prod.yaml`:

```yaml
# Production configuration with Okta
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

# Okta OIDC
oidc_enabled: true
oidc_provider_url: https://dev-12345.okta.com/oauth2/default
oidc_client_id: 0oa1b2c3d4e5f6g7h8i9
oidc_audience: api://default
oidc_skip_verification: false

# Encryption key (MUST come from environment variable)
# export ROUTEROS_MCP_ENCRYPTION_KEY=...
```

Start MCP with: `routeros-mcp --config config/okta-prod.yaml`

---

## Step 6: Test Authentication

### 6.1 Obtain Access Token (Client Credentials Flow)

**Using curl:**

```bash
# Request token from Okta
curl -X POST https://your-org.okta.com/oauth2/default/v1/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=0oa1b2c3d4e5f6g7h8i9" \
  -d "client_secret=your-client-secret-here" \
  -d "grant_type=client_credentials" \
  -d "scope=mcp:access"
```

**Response:**

```json
{
  "token_type": "Bearer",
  "expires_in": 3600,
  "access_token": "eyJraWQiOiJxMnduZ...",
  "scope": "mcp:access"
}
```

**Save the `access_token` value.**

### 6.2 Obtain Access Token (Authorization Code Flow - User Context)

**Step 1: Direct user to authorization URL:**

```
https://your-org.okta.com/oauth2/default/v1/authorize?
  client_id=0oa1b2c3d4e5f6g7h8i9
  &response_type=code
  &scope=openid%20profile%20email%20mcp:access
  &redirect_uri=https://mcp.example.com/oauth/callback
  &state=random-state-string
```

**Step 2: User authenticates and consents**

**Step 3: Okta redirects to callback with authorization code:**

```
https://mcp.example.com/oauth/callback?code=ABC123DEF456&state=random-state-string
```

**Step 4: Exchange code for token:**

```bash
curl -X POST https://your-org.okta.com/oauth2/default/v1/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_id=0oa1b2c3d4e5f6g7h8i9" \
  -d "client_secret=your-client-secret-here" \
  -d "grant_type=authorization_code" \
  -d "code=ABC123DEF456" \
  -d "redirect_uri=https://mcp.example.com/oauth/callback"
```

### 6.3 Call MCP API with Token

```bash
# Set token variable
export TOKEN="eyJraWQiOiJxMnduZ..."

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

### 6.4 Decode and Inspect Token (Optional)

Use [jwt.io](https://jwt.io) or decode locally:

```bash
# Decode JWT (header and payload)
echo "$TOKEN" | cut -d. -f2 | base64 -d | jq .
```

**Verify Claims:**
- `iss`: `https://your-org.okta.com/oauth2/default`
- `aud`: `api://default` (or custom audience)
- `exp`: Unix timestamp (not expired)
- `cid`: Client ID of requesting application
- `scp`: Granted scopes (e.g., `["mcp:access"]`)
- `mcp_role`: Custom role claim (if configured in Step 3.2)
- `groups`: User groups (if configured in Step 3.3)

---

## Step 7: Configure Role Mapping (Optional)

### 7.1 Group-Based Role Mapping

In MCP configuration, map Okta group IDs to roles:

```yaml
# config/okta-prod.yaml
authz_group_mappings:
  # Okta group IDs → MCP roles
  "00g1a2b3c4d5e6f7g8": "read_only"   # MCP-ReadOnly
  "00g2b3c4d5e6f7g8h9": "ops_rw"      # MCP-OpsRW
  "00g3c4d5e6f7g8h9i0": "admin"       # MCP-Admin
```

**Find Group ID:**
1. Navigate to **Directory** > **Groups**
2. Click on group name
3. Copy **Group ID** from URL or details page

### 7.2 Claim-Based Role Mapping

If using custom `mcp_role` claim (from Step 3.2):

```python
# MCP server extracts role from token claim
user_role = token_claims.get("mcp_role", "read_only")
```

No additional configuration needed - role is directly in token.

---

## Troubleshooting

### Issue: "invalid_client: Invalid value for 'client_id' parameter"

**Cause**: Client ID incorrect or application doesn't exist.

**Solution**:
1. Verify `oidc_client_id` matches Client ID from Okta application
2. Ensure application is active (not deactivated)
3. Check Okta domain in `oidc_provider_url`

### Issue: "invalid_scope: The authorization server resource could not find scope"

**Cause**: Requested scope not defined in authorization server.

**Solution**:
1. Add scope to authorization server (Step 3.1)
2. Or remove scope from token request (use default scopes only)
3. Verify scope name matches exactly (case-sensitive)

### Issue: "invalid_client: Client authentication failed"

**Cause**: Client secret incorrect, expired, or not provided.

**Solution**:
1. Copy client secret again from Okta application (General tab)
2. Ensure secret is passed correctly in token request (check for extra spaces)
3. Verify request uses `Content-Type: application/x-www-form-urlencoded`

### Issue: "Token validation failed: Invalid issuer"

**Cause**: Token issuer doesn't match configured OIDC provider URL.

**Solution**:
1. Verify `oidc_provider_url` includes correct authorization server path
2. Check if using org server (`https://your-org.okta.com`) vs. default (`https://your-org.okta.com/oauth2/default`)
3. Ensure no trailing slash in provider URL

### Issue: "Token validation failed: Invalid signature"

**Cause**: MCP server cannot verify token signature.

**Solution**:
1. Check network connectivity to Okta (port 443)
2. Verify `oidc_provider_url` is correct
3. Ensure system clock is accurate (within 30 seconds)
4. Test JWKS endpoint: `curl https://your-org.okta.com/oauth2/default/v1/keys`

### Issue: "Access token lifetime too short"

**Cause**: Default token lifetime is 1 hour, may be too short for long operations.

**Solution**:
1. Edit access policy rule in authorization server
2. Increase **Access token lifetime** (max: 24 hours)
3. Or implement token refresh logic in client

---

## Security Best Practices

### Production Security Checklist

- [ ] **Use HTTPS Only**: Okta requires HTTPS for production redirect URIs
- [ ] **Rotate Client Secrets**: Regularly rotate secrets (quarterly recommended)
- [ ] **Least Privilege Scopes**: Grant minimum required scopes
- [ ] **Restrict Access Policies**: Limit which apps/users can request tokens
- [ ] **Enable MFA**: Require multi-factor authentication for admin users
- [ ] **Monitor Token Usage**: Review Okta system logs for suspicious activity
- [ ] **Set Token Lifetimes**: Use shortest practical token lifetime
- [ ] **Validate Issuer**: Ensure `iss` claim matches expected Okta domain
- [ ] **Validate Audience**: Ensure `aud` claim matches your API identifier
- [ ] **Use Custom Authorization Server**: Don't use org authorization server for custom apps

### Client Secret Rotation

**Okta allows multiple active client secrets:**

1. Generate new client secret in Okta (keep old secret active)
2. Update MCP production environment with new secret
3. Deploy and verify MCP service works with new secret
4. Deactivate old secret in Okta (after 24-48 hours)

**Steps:**
1. Navigate to **Applications** > **Your MCP App** > **General**
2. Scroll to **Client Credentials**
3. Click **Add Secret** (don't delete old one yet)
4. Copy new secret and deploy to MCP
5. After verification, click **Deactivate** on old secret

---

## Advanced Configuration

### Custom Authorization Server

For production, create a dedicated authorization server instead of using "default":

1. Navigate to **Security** > **API** > **Authorization Servers**
2. Click **Add Authorization Server**
3. **Name**: `MCP Authorization Server`
4. **Audience**: `https://mcp.example.com`
5. **Description**: `OAuth server for RouterOS MCP service`
6. Click **Save**

Update MCP configuration:
```bash
export ROUTEROS_MCP_OIDC_PROVIDER_URL=https://your-org.okta.com/oauth2/aus1b2c3d4e5f6g7h8i9
export ROUTEROS_MCP_OIDC_AUDIENCE=https://mcp.example.com
```

### Token Inline Hook (Advanced)

Modify tokens dynamically before issuance:

1. Navigate to **Workflow** > **Inline Hooks**
2. Click **Add Inline Hook** > **Token**
3. Configure webhook to modify claims (requires external service)

**Use case**: Dynamic role assignment based on external system.

### Rate Limiting

Prevent token abuse by configuring rate limits:

1. Navigate to **Security** > **General**
2. Configure **Rate Limiting** for:
   - Authentication (login attempts)
   - Token requests (client credentials)
   - API calls (introspection, JWKS)

---

## Related Documentation

- [HTTP/SSE Transport Deployment Guide](20-http-sse-transport-deployment-guide.md)
- [OAuth Setup: Azure AD](21-oauth-setup-azure-ad.md)
- [OAuth Setup: Auth0](23-oauth-setup-auth0.md)
- [HTTP Transport Troubleshooting](24-http-transport-troubleshooting.md)
- [Security & Access Control](02-security-oauth-integration-and-access-control.md)

---

## Additional Resources

**Okta Documentation:**
- [Okta OAuth 2.0 Guide](https://developer.okta.com/docs/guides/implement-oauth-for-okta/main/)
- [Authorization Servers](https://developer.okta.com/docs/concepts/auth-servers/)
- [Custom Claims](https://developer.okta.com/docs/guides/customize-tokens-returned-from-okta/main/)
- [Okta API Reference](https://developer.okta.com/docs/reference/)

**Tools:**
- [Okta Developer Console](https://developer.okta.com/)
- [Okta Token Previewer](https://token.preview.okta.com/)
- [JWT Decoder](https://jwt.io)
