# HTTP/SSE Transport Deployment Guide

## Purpose

This guide provides production deployment patterns for RouterOS MCP service using HTTP/SSE transport with OAuth 2.1 authentication. It covers infrastructure requirements, environment configuration, SSL/TLS setup, load balancing, horizontal scaling, and production best practices.

**Target Audience**: DevOps engineers, SREs, and infrastructure operators deploying RouterOS MCP in staging/production environments.

---

## System Requirements

### Hardware Requirements

**Minimum (Single Instance):**
- **CPU**: 2 vCPUs (x86_64 or ARM64)
- **RAM**: 2 GB
- **Disk**: 10 GB (SSD recommended for database performance)
- **Network**: 100 Mbps, stable connectivity to RouterOS devices

**Recommended (Production):**
- **CPU**: 4 vCPUs
- **RAM**: 4-8 GB (depends on concurrent connections and device count)
- **Disk**: 20 GB SSD
- **Network**: 1 Gbps, low latency to RouterOS devices

**Scaling Considerations:**
- Each concurrent SSE connection uses ~1-2 MB RAM
- Database size grows ~100 KB per device + ~1 KB per audit event
- Plan for 10-20% CPU headroom for health checks and background jobs

### Software Requirements

**Required:**
- **Python**: 3.11+ (3.13 recommended)
- **Database**: SQLite 3.40+ (dev/staging) or PostgreSQL 14+ (production)
- **SSL/TLS**: Valid certificate (Let's Encrypt or commercial CA)
- **Reverse Proxy**: nginx 1.20+ or HAProxy 2.4+ (optional but recommended)

**Optional but Recommended:**
- **Process Manager**: systemd (Linux), supervisor, or Docker
- **Monitoring**: Prometheus + Grafana for metrics
- **Log Aggregation**: ELK Stack, Loki, or CloudWatch
- **Secrets Manager**: HashiCorp Vault, AWS Secrets Manager, or Azure Key Vault

### Port Requirements

**Inbound:**
- `8080/tcp` - HTTP/SSE transport (default, configurable)
- `443/tcp` - HTTPS (if terminating SSL at MCP server)

**Outbound:**
- `80/tcp`, `443/tcp` - OIDC provider (OAuth token validation)
- `8728/tcp`, `8729/tcp` - RouterOS API/SSH (device management)

---

## Pre-Deployment Checklist

Before deploying to production, verify:

- [ ] **Database**: PostgreSQL instance provisioned and accessible
- [ ] **OAuth Provider**: OIDC application registered (see OAuth setup guides)
- [ ] **SSL Certificate**: Valid certificate obtained and deployed
- [ ] **DNS**: Hostname resolves to server IP (e.g., `mcp.example.com`)
- [ ] **Firewall**: Required ports open (8080, 443, outbound OIDC)
- [ ] **Environment Variables**: All required variables set (see below)
- [ ] **Encryption Key**: Strong 32-byte key generated and stored securely
- [ ] **Health Check Endpoint**: `/health` accessible for load balancer probes
- [ ] **Audit Logging**: Log destination configured and tested
- [ ] **Backup Strategy**: Database backup policy defined

---

## Environment Variable Configuration

### Core Application Settings

```bash
# Deployment environment (lab/staging/prod)
export ROUTEROS_MCP_ENVIRONMENT=prod

# Debug mode (MUST be false in production)
export ROUTEROS_MCP_DEBUG=false

# Logging
export ROUTEROS_MCP_LOG_LEVEL=INFO
export ROUTEROS_MCP_LOG_FORMAT=json

# MCP Transport
export ROUTEROS_MCP_MCP_TRANSPORT=http
export ROUTEROS_MCP_MCP_HTTP_HOST=0.0.0.0  # Bind to all interfaces
export ROUTEROS_MCP_MCP_HTTP_PORT=8080
export ROUTEROS_MCP_MCP_HTTP_BASE_PATH=/mcp
```

### Database Configuration

**For PostgreSQL (Production):**

```bash
export ROUTEROS_MCP_DATABASE_URL="postgresql+asyncpg://user:password@db.example.com:5432/routeros_mcp"
export ROUTEROS_MCP_DATABASE_POOL_SIZE=20
export ROUTEROS_MCP_DATABASE_MAX_OVERFLOW=10
export ROUTEROS_MCP_DATABASE_ECHO=false  # No SQL logging in prod
```

**For SQLite (Development/Staging):**

```bash
export ROUTEROS_MCP_DATABASE_URL="sqlite+aiosqlite:///./data/routeros_mcp.db"
export ROUTEROS_MCP_DATABASE_POOL_SIZE=5
```

### OIDC Authentication

**Required in Production:**

```bash
# Enable OIDC (MUST be true for HTTP transport in prod)
export ROUTEROS_MCP_OIDC_ENABLED=true

# OIDC Provider (see OAuth setup guides for provider-specific values)
export ROUTEROS_MCP_OIDC_PROVIDER_URL=https://login.microsoftonline.com/{tenant-id}/v2.0
export ROUTEROS_MCP_OIDC_CLIENT_ID=your-client-id-here
export ROUTEROS_MCP_OIDC_AUDIENCE=api://routeros-mcp

# IMPORTANT: NEVER set this to true in production
export ROUTEROS_MCP_OIDC_SKIP_VERIFICATION=false
```

### Encryption and Secrets

**Critical: Generate a Strong Encryption Key**

```bash
# Generate 32-byte random key (run once, store securely)
python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"

# Set as environment variable (use secrets manager in production)
export ROUTEROS_MCP_ENCRYPTION_KEY=your-base64-encoded-32-byte-key
```

**⚠️ WARNING**: The encryption key protects RouterOS device credentials in the database. If lost, all stored credentials become unrecoverable. Store in:
- AWS Secrets Manager / Azure Key Vault / HashiCorp Vault (preferred)
- Encrypted configuration management (Ansible Vault, SOPS)
- Environment variable from secure secret store (never in git!)

### SSE Configuration

```bash
# SSE subscription limits (prevent DoS)
export ROUTEROS_MCP_SSE_MAX_SUBSCRIPTIONS_PER_DEVICE=100
export ROUTEROS_MCP_SSE_CLIENT_TIMEOUT_SECONDS=1800  # 30 minutes
export ROUTEROS_MCP_SSE_UPDATE_BATCH_INTERVAL_SECONDS=1.0
```

### Health Checks and Observability

```bash
# Health check intervals
export ROUTEROS_MCP_HEALTH_CHECK_INTERVAL_SECONDS=60
export ROUTEROS_MCP_HEALTH_CHECK_JITTER_SECONDS=10

# Metrics (if using Prometheus)
export ROUTEROS_MCP_METRICS_ENABLED=true
export ROUTEROS_MCP_METRICS_PORT=9090
```

---

## SSL/TLS Certificate Setup

### Option 1: Let's Encrypt (Recommended for Internet-Facing Deployments)

**Using Certbot with nginx:**

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d mcp.example.com

# Auto-renewal (certbot sets up systemd timer)
sudo systemctl status certbot.timer
```

**Using Certbot Standalone (No nginx):**

```bash
# Stop MCP server temporarily
sudo systemctl stop routeros-mcp-http

# Obtain certificate
sudo certbot certonly --standalone -d mcp.example.com

# Certificates stored in /etc/letsencrypt/live/mcp.example.com/
# - fullchain.pem (certificate + chain)
# - privkey.pem (private key)

# Start MCP server
sudo systemctl start routeros-mcp-http
```

**Configure MCP to Use Let's Encrypt Certificates:**

```bash
# Option A: Terminate SSL at reverse proxy (recommended)
# nginx or HAProxy handles HTTPS, forwards HTTP to MCP on localhost

# Option B: Terminate SSL at MCP server (requires additional dependencies)
# Not currently implemented in Phase 2 - use reverse proxy instead
```

### Option 2: Self-Signed Certificates (Development/Internal Only)

**⚠️ WARNING**: Self-signed certificates are NOT suitable for production. Use only for:
- Internal networks with corporate CA
- Development/testing environments
- Proof-of-concept deployments

**Generate Self-Signed Certificate:**

```bash
# Generate private key and certificate
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=mcp.example.com"

# Set permissions
chmod 600 key.pem
chmod 644 cert.pem
```

**Use with nginx:**

```nginx
server {
    listen 443 ssl;
    server_name mcp.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Disable if self-signed (dev only)
    ssl_verify_client off;

    location /mcp {
        proxy_pass http://127.0.0.1:8080;
        # ... proxy settings
    }
}
```

### Option 3: Commercial CA Certificate

**For Enterprise Deployments:**

1. Purchase certificate from trusted CA (DigiCert, GlobalSign, Sectigo)
2. Generate CSR (Certificate Signing Request)
3. Submit to CA and obtain signed certificate
4. Install certificate and intermediate chain on reverse proxy

**Example nginx Configuration:**

```nginx
ssl_certificate /etc/ssl/certs/mcp.example.com.crt;
ssl_certificate_key /etc/ssl/private/mcp.example.com.key;
ssl_trusted_certificate /etc/ssl/certs/ca-chain.crt;
```

---

## Load Balancer Configuration

### nginx as Reverse Proxy

**Recommended Configuration:**

```nginx
# /etc/nginx/sites-available/routeros-mcp
upstream mcp_backend {
    # Multiple instances for horizontal scaling
    server 127.0.0.1:8080 max_fails=3 fail_timeout=30s;
    server 127.0.0.1:8081 max_fails=3 fail_timeout=30s backup;
    
    # Keep connections alive
    keepalive 32;
}

server {
    listen 80;
    server_name mcp.example.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name mcp.example.com;

    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/mcp.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mcp.example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options DENY always;
    add_header X-Content-Type-Options nosniff always;

    # Health check endpoint
    location /health {
        proxy_pass http://mcp_backend/health;
        proxy_http_version 1.1;
        access_log off;
    }

    # MCP endpoints
    location /mcp {
        proxy_pass http://mcp_backend;
        proxy_http_version 1.1;
        
        # Required for SSE (Server-Sent Events)
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        
        # Timeouts for long-lived SSE connections
        proxy_connect_timeout 60s;
        proxy_send_timeout 1800s;  # 30 minutes
        proxy_read_timeout 1800s;  # 30 minutes
        
        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # CORS (if browser-based clients)
        add_header Access-Control-Allow-Origin * always;
        add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
    }

    # Client max body size
    client_max_body_size 10M;
}
```

**Enable and Test:**

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/routeros-mcp /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### HAProxy Configuration

**Alternative to nginx:**

```haproxy
# /etc/haproxy/haproxy.cfg
global
    log /dev/log local0
    maxconn 4096
    ssl-default-bind-ciphers HIGH:!aNULL:!MD5
    ssl-default-bind-options ssl-min-ver TLSv1.2

defaults
    log     global
    mode    http
    option  httplog
    option  dontlognull
    timeout connect 5000ms
    timeout client  1800000ms  # 30 minutes for SSE
    timeout server  1800000ms

frontend mcp_https
    bind *:443 ssl crt /etc/ssl/private/mcp.example.com.pem
    
    # Security headers
    http-response set-header Strict-Transport-Security "max-age=31536000"
    
    # Route to backend
    default_backend mcp_servers

backend mcp_servers
    balance roundrobin
    option httpclose
    
    # Health check
    option httpchk GET /health
    http-check expect status 200
    
    # Servers
    server mcp1 127.0.0.1:8080 check inter 10s fall 3 rise 2
    server mcp2 127.0.0.1:8081 check inter 10s fall 3 rise 2 backup
```

---

## Horizontal Scaling

### Multi-Instance Deployment

**Requirements for Horizontal Scaling:**

1. **Shared Database**: All instances must use same PostgreSQL database
2. **Stateless Application**: MCP server is stateless (all state in DB)
3. **SSE Session Affinity**: Sticky sessions for SSE subscriptions (optional)
4. **Health Monitoring**: Load balancer must check each instance

### Example: 3-Node Deployment

**Architecture:**

```
                      ┌─────────────┐
                      │ nginx / HAProxy │
                      │   (Port 443)    │
                      └────────┬────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
          ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
          │  MCP #1   │  │  MCP #2   │  │  MCP #3   │
          │ Port 8080 │  │ Port 8081 │  │ Port 8082 │
          └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
                │              │              │
                └──────────────┼──────────────┘
                               │
                      ┌────────▼────────┐
                      │   PostgreSQL    │
                      │  (Shared State) │
                      └─────────────────┘
```

**systemd Service Template:**

```ini
# /etc/systemd/system/routeros-mcp@.service
[Unit]
Description=RouterOS MCP Server Instance %i
After=network.target postgresql.service

[Service]
Type=exec
User=mcp
Group=mcp
Environment="ROUTEROS_MCP_MCP_HTTP_PORT=808%i"
EnvironmentFile=/etc/routeros-mcp/config.env
ExecStart=/usr/local/bin/routeros-mcp --config /etc/routeros-mcp/prod.yaml
Restart=on-failure
RestartSec=10s

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

**Start Multiple Instances:**

```bash
# Start 3 instances on ports 8080, 8081, 8082
sudo systemctl enable --now routeros-mcp@0
sudo systemctl enable --now routeros-mcp@1
sudo systemctl enable --now routeros-mcp@2

# Check status
sudo systemctl status routeros-mcp@*
```

### Database Connection Pooling

**PostgreSQL Configuration:**

```bash
# Per-instance pool size
export ROUTEROS_MCP_DATABASE_POOL_SIZE=10
export ROUTEROS_MCP_DATABASE_MAX_OVERFLOW=5

# Total connections: (pool_size + max_overflow) × num_instances
# Example: (10 + 5) × 3 instances = 45 connections
# PostgreSQL max_connections should be 45 + headroom (60-80)
```

**PostgreSQL Server Settings:**

```sql
-- /etc/postgresql/14/main/postgresql.conf
max_connections = 100
shared_buffers = 256MB
effective_cache_size = 1GB
```

### SSE Subscription Handling

**Challenge**: SSE connections are stateful (long-lived HTTP connections)

**Solution 1: Sticky Sessions (Recommended)**

```nginx
# nginx with IP hash for sticky sessions
upstream mcp_backend {
    ip_hash;  # Same client IP always routes to same backend
    server 127.0.0.1:8080;
    server 127.0.0.1:8081;
    server 127.0.0.1:8082;
}
```

**Solution 2: Redis Pub/Sub (Future Enhancement)**

For true stateless SSE, use Redis Pub/Sub to broadcast updates to all instances. This requires code changes (Phase 3+).

---

## Production Deployment Example

### Complete Deployment on Ubuntu 22.04

**Step 1: Install Dependencies**

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python 3.11+
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Install PostgreSQL
sudo apt-get install -y postgresql postgresql-contrib

# Install nginx
sudo apt-get install -y nginx

# Install certbot
sudo apt-get install -y certbot python3-certbot-nginx
```

**Step 2: Create MCP User and Directories**

```bash
# Create service user
sudo useradd -r -s /bin/false -m -d /var/lib/routeros-mcp mcp

# Create directories
sudo mkdir -p /etc/routeros-mcp
sudo mkdir -p /var/lib/routeros-mcp
sudo mkdir -p /var/log/routeros-mcp

# Set permissions
sudo chown -R mcp:mcp /var/lib/routeros-mcp
sudo chown -R mcp:mcp /var/log/routeros-mcp
```

**Step 3: Install RouterOS MCP**

```bash
# Clone or download release
cd /opt
sudo git clone https://github.com/your-org/routeros-mcp.git
cd routeros-mcp

# Create virtual environment
sudo -u mcp python3.11 -m venv /var/lib/routeros-mcp/venv

# Install application
sudo -u mcp /var/lib/routeros-mcp/venv/bin/pip install -e .
```

**Step 4: Configure Database**

```bash
# Create PostgreSQL user and database
sudo -u postgres psql << EOF
CREATE USER mcp_user WITH PASSWORD 'secure-password-here';
CREATE DATABASE routeros_mcp OWNER mcp_user;
GRANT ALL PRIVILEGES ON DATABASE routeros_mcp TO mcp_user;
EOF

# Run migrations
sudo -u mcp /var/lib/routeros-mcp/venv/bin/alembic upgrade head
```

**Step 5: Configure Environment**

```bash
# Create config file
sudo tee /etc/routeros-mcp/config.env << EOF
ROUTEROS_MCP_ENVIRONMENT=prod
ROUTEROS_MCP_DEBUG=false
ROUTEROS_MCP_LOG_LEVEL=INFO
ROUTEROS_MCP_LOG_FORMAT=json
ROUTEROS_MCP_MCP_TRANSPORT=http
ROUTEROS_MCP_MCP_HTTP_HOST=127.0.0.1
ROUTEROS_MCP_MCP_HTTP_PORT=8080
ROUTEROS_MCP_DATABASE_URL=postgresql+asyncpg://mcp_user:secure-password-here@localhost:5432/routeros_mcp
ROUTEROS_MCP_OIDC_ENABLED=true
ROUTEROS_MCP_OIDC_PROVIDER_URL=https://your-provider.com
ROUTEROS_MCP_OIDC_CLIENT_ID=your-client-id
ROUTEROS_MCP_OIDC_AUDIENCE=api://routeros-mcp
ROUTEROS_MCP_ENCRYPTION_KEY=$(python3 -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")
EOF

# Secure config file
sudo chmod 600 /etc/routeros-mcp/config.env
sudo chown mcp:mcp /etc/routeros-mcp/config.env
```

**Step 6: Configure systemd Service**

```bash
# Create service file
sudo tee /etc/systemd/system/routeros-mcp.service << 'EOF'
[Unit]
Description=RouterOS MCP Server (HTTP/SSE)
After=network.target postgresql.service

[Service]
Type=exec
User=mcp
Group=mcp
WorkingDirectory=/opt/routeros-mcp
EnvironmentFile=/etc/routeros-mcp/config.env
ExecStart=/var/lib/routeros-mcp/venv/bin/routeros-mcp --config /etc/routeros-mcp/prod.yaml
StandardOutput=journal
StandardError=journal
Restart=on-failure
RestartSec=10s

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/routeros-mcp /var/log/routeros-mcp

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable routeros-mcp
sudo systemctl start routeros-mcp

# Check status
sudo systemctl status routeros-mcp
```

**Step 7: Configure nginx with SSL**

```bash
# Obtain Let's Encrypt certificate
sudo certbot --nginx -d mcp.example.com

# nginx config created in previous section
sudo nano /etc/nginx/sites-available/routeros-mcp

# Enable site
sudo ln -s /etc/nginx/sites-available/routeros-mcp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

**Step 8: Verify Deployment**

```bash
# Test health endpoint
curl https://mcp.example.com/health

# Expected: {"status": "healthy", "timestamp": "..."}

# Test authentication (requires OAuth token)
curl -H "Authorization: Bearer $TOKEN" https://mcp.example.com/mcp/initialize
```

---

## Security Best Practices

### Production Hardening Checklist

- [ ] **TLS 1.2+ Only**: Disable older SSL/TLS versions
- [ ] **Strong Ciphers**: Use modern cipher suites (AES-GCM, ChaCha20)
- [ ] **HSTS Enabled**: Strict-Transport-Security header set
- [ ] **OIDC Verification**: NEVER set `oidc_skip_verification=true` in production
- [ ] **Database Encryption**: Enable PostgreSQL SSL connections
- [ ] **Encryption Key**: Store in secrets manager, never in git
- [ ] **Firewall Rules**: Restrict inbound to HTTPS only
- [ ] **Rate Limiting**: Implement at reverse proxy (nginx limit_req)
- [ ] **Audit Logging**: Enable and monitor audit events
- [ ] **Regular Updates**: Apply security patches promptly

### Example nginx Rate Limiting

```nginx
# Limit requests to prevent DoS
limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=10r/s;

server {
    # ...
    location /mcp {
        limit_req zone=mcp_limit burst=20 nodelay;
        # ... proxy_pass config
    }
}
```

---

## Monitoring and Health Checks

### Health Check Endpoint

**Endpoint**: `GET /health`

**Response (Healthy):**

```json
{
  "status": "healthy",
  "timestamp": "2024-12-16T01:00:00Z",
  "version": "1.0.0",
  "database": "connected",
  "oidc": "configured"
}
```

**Response (Unhealthy):**

```json
{
  "status": "unhealthy",
  "timestamp": "2024-12-16T01:00:00Z",
  "errors": ["Database connection failed"]
}
```

### Load Balancer Health Check Configuration

**nginx:**

```nginx
location /health {
    proxy_pass http://mcp_backend/health;
    proxy_http_version 1.1;
    access_log off;
}
```

**HAProxy:**

```haproxy
option httpchk GET /health
http-check expect status 200
```

### Prometheus Metrics (Optional)

If metrics are enabled, the server exposes Prometheus metrics on configured port:

```bash
# Query metrics
curl http://localhost:9090/metrics
```

**Key Metrics:**
- `mcp_http_requests_total` - Total HTTP requests
- `mcp_sse_connections_active` - Active SSE connections
- `mcp_tool_execution_duration_seconds` - Tool execution latency
- `mcp_database_connection_pool_size` - DB connection pool usage

---

## Backup and Disaster Recovery

### Database Backup

**PostgreSQL Automated Backup:**

```bash
# Daily backup script
cat > /usr/local/bin/backup-mcp-db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR=/var/backups/routeros-mcp
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

pg_dump -U mcp_user -h localhost routeros_mcp | gzip > $BACKUP_DIR/mcp_backup_$DATE.sql.gz

# Retain 30 days
find $BACKUP_DIR -name "mcp_backup_*.sql.gz" -mtime +30 -delete
EOF

chmod +x /usr/local/bin/backup-mcp-db.sh

# Schedule with cron
echo "0 2 * * * /usr/local/bin/backup-mcp-db.sh" | sudo crontab -
```

### Configuration Backup

```bash
# Backup config (exclude secrets)
tar czf /var/backups/mcp-config-$(date +%Y%m%d).tar.gz \
    /etc/routeros-mcp/*.yaml \
    /etc/nginx/sites-available/routeros-mcp
```

### Disaster Recovery Steps

1. **Restore Database**: `gunzip < backup.sql.gz | psql -U mcp_user routeros_mcp`
2. **Restore Config**: Extract from backup tarball
3. **Regenerate Encryption Key**: If lost, device credentials must be re-entered
4. **Restart Services**: `sudo systemctl restart routeros-mcp nginx`

---

## Related Documentation

- [OAuth Setup: Azure AD](21-oauth-setup-azure-ad.md)
- [OAuth Setup: Okta](22-oauth-setup-okta.md)
- [OAuth Setup: Auth0](23-oauth-setup-auth0.md)
- [HTTP Transport Troubleshooting](24-http-transport-troubleshooting.md)
- [MCP Protocol Integration](14-mcp-protocol-integration-and-transport-design.md)
- [Security & Access Control](02-security-oauth-integration-and-access-control.md)

---

## Next Steps

After completing deployment:

1. **Configure OAuth Provider** – See provider-specific guides (docs 21-23)
2. **Test End-to-End** – Run `examples/curl_example.sh` and `examples/http_client.py`
3. **Monitor Health** – Set up Prometheus/Grafana dashboards
4. **Review Security** – Run security audit checklist
5. **Document Runbook** – Customize for your environment
