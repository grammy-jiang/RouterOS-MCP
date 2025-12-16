# OAuth Setup Guide: Auth0

## Purpose

Step-by-step guide for configuring Auth0 as the OAuth 2.1 / OIDC provider for RouterOS MCP HTTP transport. This guide covers application setup, API configuration, custom claims, and integration with the MCP service.

**Target Audience**: Auth0 administrators and DevOps engineers deploying RouterOS MCP with Auth0 authentication.

---

## Prerequisites

- **Auth0 Account**: Active Auth0 tenant (free developer account or paid subscription)
- **Auth0 Administrator** role
- **RouterOS MCP Server**: Deployed and accessible (see [Deployment Guide](20-http-sse-transport-deployment-guide.md))
- **Public URL**: HTTPS endpoint for MCP service (e.g., `https://mcp.example.com`)

---

## Overview

**Auth0 Integration Flow:**

```
┌──────────────┐                    ┌─────────────────┐
│  MCP Client  │                    │      Auth0      │
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
       │ 4. Validate token with Auth0       │
       │                                ├────>
       │                                │ JWKS
       │                                │<────
       │                                     │
       │ 5. Return MCP response             │
       │<────────────────────────────────────┤
       │                                     │
```

---

## Step 1: Create Auth0 Application

### 1.1 Log in to Auth0 Dashboard

1. Navigate to [Auth0 Dashboard](https://manage.auth0.com)
2. Select your tenant (e.g., `dev-abc123.us.auth0.com`)
3. Sign in with administrator credentials

### 1.2 Create Application

1. Navigate to **Applications** > **Applications** from left menu
2. Click **+ Create Application**
3. **Name**: `RouterOS MCP Service`
4. **Application Type**:
   - **Machine to Machine Applications** (for API-to-API, client credentials flow - recommended)
   - **Regular Web Applications** (for web apps with user login)
   - **Single Page Applications** (for browser-based apps)
   - **Native** (for mobile/desktop apps)
5. Click **Create**

### 1.3 Configure Application Settings

**For Machine to Machine Application:**

1. After creation, you'll be prompted to **Authorize** the application
2. Select the API you want to access (see Step 2 - create API first if not exists)
3. Select **Permissions** (scopes) the app should have
4. Click **Authorize**

**General Application Settings:**

1. Navigate to **Settings** tab
2. Note the following values (you'll need them later):
   - **Domain**: `dev-abc123.us.auth0.com`
   - **Client ID**: `AbC123DeFgHiJkLmNoPqRsTuVwXyZ`
   - **Client Secret**: Click **🔑 Reveal Secret** and copy (keep secure)
3. Scroll down and configure:
   - **Application Login URI**: `https://mcp.example.com/login` (optional)
   - **Allowed Callback URLs**: `https://mcp.example.com/oauth/callback` (for authorization code flow)
   - **Allowed Logout URLs**: `https://mcp.example.com/logout` (optional)
   - **Allowed Web Origins**: `https://mcp.example.com` (for CORS, if browser-based)
4. Click **Save Changes**

---

## Step 2: Create Auth0 API

Auth0 APIs represent your backend services. Create an API for the MCP service.

### 2.1 Create API

1. Navigate to **Applications** > **APIs** from left menu
2. Click **+ Create API**
3. **Name**: `RouterOS MCP API`
4. **Identifier**: `https://mcp.example.com` (or `api://routeros-mcp`)
   - This is the **audience** value for tokens
   - Must be a valid URL (doesn't need to resolve)
   - Convention: Use your API domain or URN
5. **Signing Algorithm**: `RS256` (recommended, asymmetric)
6. Click **Create**

### 2.2 Configure API Settings

1. Navigate to **Settings** tab of your API
2. Configure:
   - **Token Expiration (Seconds)**: `3600` (1 hour, adjust as needed)
   - **Allow Skipping User Consent**: ✓ (for first-party apps, optional)
   - **Allow Offline Access**: ✓ (if using refresh tokens)
3. Click **Save**

### 2.3 Define API Permissions (Scopes)

1. Click **Permissions** tab
2. Add scopes for MCP operations:
   - **Permission (Scope)**: `read:devices`, **Description**: `Read device information`
   - **Permission (Scope)**: `write:devices`, **Description**: `Modify device configuration`
   - **Permission (Scope)**: `admin:mcp`, **Description**: `Full MCP administration`
3. Click **Add** for each scope

---

## Step 3: Authorize Machine to Machine Application

If using Machine to Machine (M2M) application:

### 3.1 Grant API Access

1. Navigate to **Applications** > **Applications**
2. Click on **RouterOS MCP Service** (your M2M application)
3. Click **APIs** tab
4. Click **Authorize** next to **RouterOS MCP API**
5. Select permissions (scopes) to grant:
   - ✓ `read:devices`
   - ✓ `write:devices`
   - ✓ `admin:mcp`
6. Click **Update**

Now the M2M application can request tokens with these scopes.

---

## Step 4: Configure Custom Claims (Optional)

Add custom claims to access tokens for role-based access control.

### 4.1 Create Auth0 Action for Token Customization

**Note**: Auth0 uses "Actions" (successor to Rules/Hooks) for token customization.

1. Navigate to **Actions** > **Library** from left menu
2. Click **+ Build Custom**
3. **Name**: `Add MCP Role Claim`
4. **Trigger**: `Login / Post Login` (for authorization code flow) or `Machine to Machine / Client Credentials` (for M2M)
5. Click **Create**

### 4.2 Add Custom Claim Code

**For User Login (Authorization Code Flow):**

```javascript
/**
* Handler that will be called during the execution of a PostLogin flow.
*
* @param {Event} event - Details about the user and the context in which they are logging in.
* @param {PostLoginAPI} api - Interface whose methods can be used to change the behavior of the login.
*/
exports.onExecutePostLogin = async (event, api) => {
  const namespace = 'https://mcp.example.com/';
  
  // Map user roles to MCP role
  let mcpRole = 'read_only';
  
  if (event.authorization && event.authorization.roles) {
    if (event.authorization.roles.includes('MCP-Admin')) {
      mcpRole = 'admin';
    } else if (event.authorization.roles.includes('MCP-OpsRW')) {
      mcpRole = 'ops_rw';
    }
  }
  
  // Add custom claim to access token
  api.accessToken.setCustomClaim(`${namespace}mcp_role`, mcpRole);
  
  // Optionally add to ID token
  api.idToken.setCustomClaim(`${namespace}mcp_role`, mcpRole);
};
```

**For Machine to Machine (Client Credentials Flow):**

```javascript
/**
* Handler that will be called during the execution of a Client Credentials exchange.
*
* @param {Event} event - Details about client credentials grant request.
* @param {CredentialsExchangeAPI} api - Interface whose methods can be used to change the behavior of client credentials grant.
*/
exports.onExecuteCredentialsExchange = async (event, api) => {
  const namespace = 'https://mcp.example.com/';
  
  // Grant admin role to specific M2M application
  if (event.client.client_id === 'AbC123DeFgHiJkLmNoPqRsTuVwXyZ') {
    api.accessToken.setCustomClaim(`${namespace}mcp_role`, 'admin');
  }
};
```

**Important**: Use namespaced claim names (URLs) to avoid conflicts with OIDC standard claims.

### 4.3 Deploy Action

1. Click **Deploy** (in Action editor)
2. Navigate to **Actions** > **Flows**
3. Select **Login** (or **Machine to Machine**) flow
4. Drag your custom Action from right panel into the flow
5. Click **Apply**

---

## Step 5: Create Auth0 Roles (Optional)

If using role-based access control with user context:

### 5.1 Create Roles

1. Navigate to **User Management** > **Roles** from left menu
2. Click **+ Create Role**
3. Create roles for each MCP tier:
   - **Name**: `MCP-ReadOnly`, **Description**: `MCP read-only access`
   - **Name**: `MCP-OpsRW`, **Description**: `MCP operators with write access`
   - **Name**: `MCP-Admin`, **Description**: `MCP administrators`
4. Click **Create**

### 5.2 Assign Permissions to Roles

1. Click on role name (e.g., `MCP-Admin`)
2. Click **Permissions** tab
3. Click **Add Permissions**
4. Select **RouterOS MCP API**
5. Check scopes to grant (e.g., ✓ `admin:mcp`, ✓ `write:devices`, ✓ `read:devices`)
6. Click **Add Permissions**

Repeat for other roles with appropriate scopes.

### 5.3 Assign Roles to Users

1. Navigate to **User Management** > **Users**
2. Click on a user
3. Click **Roles** tab
4. Click **Assign Roles**
5. Select roles to assign (e.g., `MCP-Admin`)
6. Click **Assign**

---

## Step 6: Configure RouterOS MCP Service

### 6.1 Set Environment Variables

```bash
# Enable OIDC
export ROUTEROS_MCP_OIDC_ENABLED=true

# Auth0 Configuration
export ROUTEROS_MCP_OIDC_PROVIDER_URL=https://dev-abc123.us.auth0.com
export ROUTEROS_MCP_OIDC_CLIENT_ID=AbC123DeFgHiJkLmNoPqRsTuVwXyZ
export ROUTEROS_MCP_OIDC_AUDIENCE=https://mcp.example.com

# IMPORTANT: NEVER enable this in production
export ROUTEROS_MCP_OIDC_SKIP_VERIFICATION=false
```

**Replace Placeholders:**
- `dev-abc123.us.auth0.com` → Your Auth0 domain (from Step 1.3)
- `AbC123DeFgHiJkLmNoPqRsTuVwXyZ` → Your Client ID (from Step 1.3)
- `https://mcp.example.com` → Your API identifier (from Step 2.1)

### 6.2 Alternative: Configuration File

Create `config/auth0-prod.yaml`:

```yaml
# Production configuration with Auth0
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

# Auth0 OIDC
oidc_enabled: true
oidc_provider_url: https://dev-abc123.us.auth0.com
oidc_client_id: AbC123DeFgHiJkLmNoPqRsTuVwXyZ
oidc_audience: https://mcp.example.com
oidc_skip_verification: false

# Encryption key (MUST come from environment variable)
# export ROUTEROS_MCP_ENCRYPTION_KEY=...
```

Start MCP with: `routeros-mcp --config config/auth0-prod.yaml`

---

## Step 7: Test Authentication

### 7.1 Obtain Access Token (Client Credentials Flow)

**Using curl:**

```bash
# Request token from Auth0
curl -X POST https://dev-abc123.us.auth0.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "AbC123DeFgHiJkLmNoPqRsTuVwXyZ",
    "client_secret": "your-client-secret-here",
    "audience": "https://mcp.example.com",
    "grant_type": "client_credentials"
  }'
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6...",
  "token_type": "Bearer",
  "expires_in": 86400
}
```

**Save the `access_token` value.**

### 7.2 Obtain Access Token (Authorization Code Flow - User Context)

**Step 1: Direct user to authorization URL:**

```
https://dev-abc123.us.auth0.com/authorize?
  response_type=code
  &client_id=AbC123DeFgHiJkLmNoPqRsTuVwXyZ
  &redirect_uri=https://mcp.example.com/oauth/callback
  &scope=openid%20profile%20email%20read:devices%20write:devices
  &audience=https://mcp.example.com
  &state=random-state-string
```

**Step 2: User authenticates and consents**

**Step 3: Auth0 redirects to callback with authorization code:**

```
https://mcp.example.com/oauth/callback?code=ABC123DEF456&state=random-state-string
```

**Step 4: Exchange code for token:**

```bash
curl -X POST https://dev-abc123.us.auth0.com/oauth/token \
  -H "Content-Type: application/json" \
  -d '{
    "grant_type": "authorization_code",
    "client_id": "AbC123DeFgHiJkLmNoPqRsTuVwXyZ",
    "client_secret": "your-client-secret-here",
    "code": "ABC123DEF456",
    "redirect_uri": "https://mcp.example.com/oauth/callback"
  }'
```

### 7.3 Call MCP API with Token

```bash
# Set token variable
export TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6..."

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

### 7.4 Decode and Inspect Token (Optional)

Use [jwt.io](https://jwt.io) or decode locally:

```bash
# Decode JWT (header and payload)
echo "$TOKEN" | cut -d. -f2 | base64 -d | jq .
```

**Verify Claims:**
- `iss`: `https://dev-abc123.us.auth0.com/`
- `aud`: `https://mcp.example.com`
- `exp`: Unix timestamp (not expired)
- `azp`: Client ID of requesting application
- `scope`: Granted scopes (e.g., `read:devices write:devices admin:mcp`)
- `https://mcp.example.com/mcp_role`: Custom role claim (if configured in Step 4)

---

## Troubleshooting

### Issue: "access_denied: Unauthorized"

**Cause**: Application not authorized to access API, or missing scopes.

**Solution**:
1. Verify M2M application is authorized for the API (Step 3.1)
2. Check scopes are granted in application's API permissions
3. Ensure `audience` parameter in token request matches API identifier

### Issue: "invalid_client: Client authentication failed"

**Cause**: Client ID or secret incorrect.

**Solution**:
1. Verify `client_id` matches exactly (case-sensitive)
2. Reveal and re-copy `client_secret` from Auth0 dashboard
3. Ensure client secret hasn't been rotated (check if multiple secrets exist)
4. Verify Content-Type is `application/json` (Auth0 prefers JSON)

### Issue: "invalid_grant: Grant type not allowed for the client"

**Cause**: Application type doesn't support requested grant type.

**Solution**:
1. For client_credentials: Use **Machine to Machine** application type
2. For authorization_code: Use **Regular Web Application** type
3. Check **Application Settings** > **Advanced Settings** > **Grant Types** tab

### Issue: "Token validation failed: Invalid issuer"

**Cause**: Token issuer doesn't match configured OIDC provider URL.

**Solution**:
1. Verify `oidc_provider_url` matches Auth0 domain exactly
2. Auth0 issuer includes trailing slash: `https://dev-abc123.us.auth0.com/`
3. Ensure no typos in domain name

### Issue: "Token validation failed: Invalid audience"

**Cause**: Token audience doesn't match expected value.

**Solution**:
1. Verify `oidc_audience` matches API identifier from Step 2.1
2. Check `audience` parameter in token request is correct
3. Inspect token claims to see actual `aud` value

### Issue: "Custom claims not appearing in token"

**Cause**: Action not deployed or not added to flow.

**Solution**:
1. Verify Action is deployed (green checkmark in Actions > Library)
2. Check Action is in the correct flow (Actions > Flows)
3. Test Action with Real-time Webtask Logs (Actions > Library > your Action > play button)
4. Ensure namespace is used for custom claims

---

## Security Best Practices

### Production Security Checklist

- [ ] **Use HTTPS Only**: Auth0 requires HTTPS for production redirect URIs
- [ ] **Rotate Client Secrets**: Rotate secrets every 90 days (Auth0 recommendation)
- [ ] **Enable Anomaly Detection**: Auth0 automatically detects brute-force attacks (enabled by default)
- [ ] **Configure Attack Protection**: Enable breached password detection and bot detection
- [ ] **Use Strong Token Algorithms**: RS256 (asymmetric) preferred over HS256
- [ ] **Set Short Token Lifetimes**: Balance security vs. UX (1 hour for access tokens)
- [ ] **Implement Refresh Tokens**: For long-lived sessions, use refresh tokens instead of long-lived access tokens
- [ ] **Monitor Logs**: Review Auth0 logs for suspicious activity (Monitoring > Logs)
- [ ] **Restrict CORS Origins**: Limit allowed web origins to known domains
- [ ] **Validate Tokens Server-Side**: Never trust client-side validation alone

### Client Secret Rotation

**Auth0 supports secret rotation without downtime:**

1. Navigate to **Applications** > **Your App** > **Settings**
2. Scroll to **Client Secret**
3. Click **Rotate** (Auth0 creates new secret, keeps old one active for 24 hours)
4. Copy new secret and update MCP environment
5. Deploy updated configuration
6. Old secret automatically expires after 24 hours

**Immediate Rotation (Breaking):**
1. Click **Reveal** on current secret
2. Click **Change** (immediately invalidates old secret)
3. Copy new secret and deploy to all environments quickly

---

## Advanced Configuration

### Custom Domain (Branded Authentication)

Use your own domain instead of `dev-abc123.us.auth0.com`:

1. Navigate to **Branding** > **Custom Domains**
2. Click **+ Set Up Custom Domain**
3. **Domain**: `auth.example.com`
4. Verify domain ownership (DNS TXT record)
5. Configure SSL certificate (Auth0 managed or custom)
6. Update MCP configuration:
   ```bash
   export ROUTEROS_MCP_OIDC_PROVIDER_URL=https://auth.example.com
   ```

### Organizations (Multi-Tenant)

For SaaS scenarios with separate customer organizations:

1. Navigate to **Organizations** from left menu
2. Enable Organizations feature (if not already enabled)
3. Create organizations for each customer
4. Update token request with organization:
   ```bash
   curl -X POST https://dev-abc123.us.auth0.com/oauth/token \
     -d "organization=org_abc123..." \
     # ... other params
   ```

### Refresh Tokens (Long-Lived Sessions)

For user sessions that should persist beyond access token expiry:

1. In API settings, enable **Allow Offline Access**
2. Request `offline_access` scope in authorization:
   ```
   scope=openid profile email read:devices offline_access
   ```
3. Token response includes `refresh_token`
4. Exchange refresh token for new access token:
   ```bash
   curl -X POST https://dev-abc123.us.auth0.com/oauth/token \
     -d "grant_type=refresh_token" \
     -d "client_id=..." \
     -d "refresh_token=..."
   ```

### Token Expiration Configuration

Adjust token lifetimes for different environments:

**Development:**
- Access token: 24 hours (for convenience)
- Refresh token: 7 days

**Production:**
- Access token: 1 hour (default, recommended)
- Refresh token: 30 days (with rotation)

Configure in **Applications** > **APIs** > **Settings**.

---

## Related Documentation

- [HTTP/SSE Transport Deployment Guide](20-http-sse-transport-deployment-guide.md)
- [OAuth Setup: Azure AD](21-oauth-setup-azure-ad.md)
- [OAuth Setup: Okta](22-oauth-setup-okta.md)
- [HTTP Transport Troubleshooting](24-http-transport-troubleshooting.md)
- [Security & Access Control](02-security-oauth-integration-and-access-control.md)

---

## Additional Resources

**Auth0 Documentation:**
- [Auth0 Quickstarts](https://auth0.com/docs/quickstarts)
- [OAuth 2.0 Authorization Framework](https://auth0.com/docs/authenticate/protocols/oauth)
- [Secure API Access with Client Credentials](https://auth0.com/docs/get-started/authentication-and-authorization-flow/client-credentials-flow)
- [Customize Tokens with Actions](https://auth0.com/docs/customize/actions/flows-and-triggers)
- [Auth0 Best Practices](https://auth0.com/docs/best-practices)

**Tools:**
- [Auth0 Dashboard](https://manage.auth0.com)
- [Auth0 Extensions](https://auth0.com/docs/extensions)
- [JWT Decoder](https://jwt.io)
- [Auth0 Community](https://community.auth0.com/)
