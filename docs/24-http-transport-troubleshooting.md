# HTTP Transport Troubleshooting Guide

## Purpose

Comprehensive troubleshooting guide for RouterOS MCP HTTP/SSE transport, covering common issues, debug logging, performance tuning, and operational best practices.

**Target Audience**: DevOps engineers, SREs, and operators running RouterOS MCP in production.

---

## Quick Diagnostic Checklist

Before diving into specific issues, run this quick diagnostic:

```bash
# 1. Check if service is running
sudo systemctl status routeros-mcp

# 2. Test health endpoint
curl http://localhost:8080/health

# 3. Check logs for errors
sudo journalctl -u routeros-mcp -n 100 --no-pager

# 4. Verify network connectivity
curl -v https://mcp.example.com/health

# 5. Test OAuth provider connectivity
curl https://your-oidc-provider.com/.well-known/openid-configuration

# 6. Check database connectivity
psql -h localhost -U mcp_user -d routeros_mcp -c "SELECT 1;"
```

---

## Common Issues and Solutions

### 1. Connection Refused

**Symptom:**
```
curl: (7) Failed to connect to mcp.example.com port 443: Connection refused
```

**Possible Causes and Solutions:**

#### Cause 1: Service Not Running

```bash
# Check service status
sudo systemctl status routeros-mcp

# If stopped, start it
sudo systemctl start routeros-mcp

# Check logs for startup errors
sudo journalctl -u routeros-mcp -f
```

#### Cause 2: Firewall Blocking Port

```bash
# Check if port is open
sudo netstat -tulpn | grep 8080

# Add firewall rule (ufw example)
sudo ufw allow 8080/tcp

# Or iptables
sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT
sudo iptables-save
```

#### Cause 3: nginx/Reverse Proxy Not Running

```bash
# Check nginx status
sudo systemctl status nginx

# Test nginx config
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

#### Cause 4: Wrong Host Binding

**Problem**: MCP server bound to 127.0.0.1 (localhost only) but accessed from external network.

```bash
# Check binding in config
grep mcp_http_host config/*.yaml

# Should be 0.0.0.0 for external access
export ROUTEROS_MCP_MCP_HTTP_HOST=0.0.0.0

# Restart service
sudo systemctl restart routeros-mcp
```

---

### 2. Authentication Failures

**Symptom:**
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32001,
    "message": "Authentication failed: Invalid token"
  }
}
```

**Possible Causes and Solutions:**

#### Cause 1: Token Expired

```bash
# Decode token to check expiry
echo "$TOKEN" | cut -d. -f2 | base64 -d | jq '.exp'

# Compare to current time
date +%s

# Solution: Request new token
curl -X POST https://your-oidc-provider.com/oauth/token \
  -d "client_id=..." -d "client_secret=..." -d "grant_type=client_credentials"
```

#### Cause 2: Wrong OIDC Configuration

```bash
# Verify OIDC settings
env | grep ROUTEROS_MCP_OIDC

# Check if provider URL is correct
curl https://your-oidc-provider.com/.well-known/openid-configuration

# Common mistakes:
# - Missing trailing slash: https://auth0.com/ vs https://auth0.com
# - Wrong tenant ID in Azure AD
# - Wrong authorization server in Okta
```

#### Cause 3: Network Cannot Reach OIDC Provider

```bash
# Test connectivity to OIDC provider
curl -v https://login.microsoftonline.com

# Check DNS resolution
nslookup login.microsoftonline.com

# Test from MCP server (not local machine)
ssh mcp-server 'curl -v https://your-oidc-provider.com'

# Check firewall/proxy rules
```

#### Cause 4: Clock Skew

**JWT validation fails if server clock is off by >30 seconds.**

```bash
# Check server time
date

# Sync with NTP
sudo ntpdate pool.ntp.org

# Or enable NTP service
sudo systemctl enable systemd-timesyncd
sudo systemctl start systemd-timesyncd
```

#### Cause 5: Invalid Signature

```bash
# Check if OIDC_SKIP_VERIFICATION is enabled (DANGEROUS)
env | grep OIDC_SKIP_VERIFICATION

# Should be false in production
export ROUTEROS_MCP_OIDC_SKIP_VERIFICATION=false

# Verify JWKS endpoint is accessible
curl https://your-oidc-provider.com/.well-known/jwks.json
```

---

### 3. Slow Response / Timeout

**Symptom:**
```
curl: (28) Operation timed out after 30000 milliseconds
```

**Possible Causes and Solutions:**

#### Cause 1: Database Connection Pool Exhausted

```bash
# Check database pool settings
env | grep DATABASE_POOL

# Increase pool size
export ROUTEROS_MCP_DATABASE_POOL_SIZE=30
export ROUTEROS_MCP_DATABASE_MAX_OVERFLOW=20

# Check active connections
psql -U mcp_user -d routeros_mcp -c "SELECT count(*) FROM pg_stat_activity;"
```

#### Cause 2: RouterOS Device Unreachable

```bash
# Check MCP logs for device connection errors
sudo journalctl -u routeros-mcp | grep "device.*timeout"

# Test connectivity to RouterOS device
ping 192.168.1.1
curl -v http://192.168.1.1/rest/system/resource

# Check device credentials
# (use MCP diagnostics tool or database query)
```

#### Cause 3: Too Many Concurrent Requests

```bash
# Check number of active connections
netstat -an | grep :8080 | grep ESTABLISHED | wc -l

# Increase worker processes (if using gunicorn/uvicorn)
# Or add more MCP instances behind load balancer

# Check CPU/memory usage
top
htop
```

#### Cause 4: nginx Timeout Too Short

```nginx
# In nginx config, increase timeouts for SSE
location /mcp {
    proxy_connect_timeout 60s;
    proxy_send_timeout 1800s;  # 30 minutes for SSE
    proxy_read_timeout 1800s;  # 30 minutes for SSE
    # ...
}
```

```bash
# Reload nginx
sudo nginx -t && sudo systemctl reload nginx
```

---

### 4. SSE Connection Drops

**Symptom:**
```
SSE connection closed unexpectedly after 5 minutes
```

**Possible Causes and Solutions:**

#### Cause 1: Load Balancer Timeout

```bash
# Check nginx/HAProxy timeout settings
# For nginx:
proxy_read_timeout 1800s;  # 30 minutes

# For HAProxy:
timeout client 1800s
timeout server 1800s
```

#### Cause 2: Client Inactivity Timeout

```bash
# Check MCP SSE settings
env | grep SSE_CLIENT_TIMEOUT

# Increase timeout (in seconds)
export ROUTEROS_MCP_SSE_CLIENT_TIMEOUT_SECONDS=3600  # 1 hour
```

#### Cause 3: No Heartbeat/Keep-Alive

**SSE requires periodic messages to keep connection alive.**

Check MCP implementation sends periodic keep-alive:
```python
# In SSE handler, send periodic comments (keep-alive)
async def event_generator():
    while True:
        yield ": keep-alive\n\n"
        await asyncio.sleep(30)  # Every 30 seconds
```

#### Cause 4: Reverse Proxy Buffering

```nginx
# Disable buffering for SSE in nginx
location /mcp {
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding off;
    # ...
}
```

---

### 5. Database Connection Errors

**Symptom:**
```
ERROR: Database connection failed: FATAL: password authentication failed
```

**Possible Causes and Solutions:**

#### Cause 1: Wrong Credentials

```bash
# Test database connection manually
psql -h localhost -U mcp_user -d routeros_mcp

# If fails, check credentials in environment
env | grep DATABASE_URL

# Update credentials
export ROUTEROS_MCP_DATABASE_URL="postgresql+asyncpg://mcp_user:correct-password@localhost:5432/routeros_mcp"
```

#### Cause 2: PostgreSQL Not Accepting Connections

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Check if listening on correct address
sudo netstat -tulpn | grep postgres

# Edit PostgreSQL config to accept connections
sudo nano /etc/postgresql/14/main/postgresql.conf
# Set: listen_addresses = '*'

# Edit pg_hba.conf to allow MCP server
sudo nano /etc/postgresql/14/main/pg_hba.conf
# Add: host routeros_mcp mcp_user 0.0.0.0/0 md5

# Restart PostgreSQL
sudo systemctl restart postgresql
```

#### Cause 3: Database Migration Not Run

```bash
# Check database schema version
psql -U mcp_user -d routeros_mcp -c "SELECT version_num FROM alembic_version;"

# Run migrations
alembic upgrade head

# Verify migration succeeded
psql -U mcp_user -d routeros_mcp -c "\dt"
```

---

### 6. SSL/TLS Certificate Errors

**Symptom:**
```
curl: (60) SSL certificate problem: unable to get local issuer certificate
```

**Possible Causes and Solutions:**

#### Cause 1: Self-Signed Certificate (Development)

```bash
# For testing only, disable SSL verification
curl -k https://mcp.example.com/health

# Proper solution: Use valid certificate or add CA to trust store
sudo cp /path/to/ca-certificate.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates
```

#### Cause 2: Certificate Expired

```bash
# Check certificate expiry
echo | openssl s_client -connect mcp.example.com:443 2>/dev/null | openssl x509 -noout -dates

# Renew Let's Encrypt certificate
sudo certbot renew

# For other CAs, obtain new certificate and redeploy
```

#### Cause 3: Certificate Name Mismatch

```bash
# Check certificate CN/SAN
echo | openssl s_client -connect mcp.example.com:443 2>/dev/null | openssl x509 -noout -text | grep -A1 "Subject Alternative Name"

# Ensure certificate is issued for correct domain
# If using IP address, certificate must include IP in SAN
```

---

### 7. High Memory Usage

**Symptom:**
```
MCP server consuming >4GB RAM, OOM killer terminating process
```

**Possible Causes and Solutions:**

#### Cause 1: Too Many SSE Connections

```bash
# Check active SSE connections
# (use metrics endpoint if enabled)
curl http://localhost:9090/metrics | grep sse_connections_active

# Limit SSE subscriptions per device
export ROUTEROS_MCP_SSE_MAX_SUBSCRIPTIONS_PER_DEVICE=50

# Reduce client timeout to clean up idle connections
export ROUTEROS_MCP_SSE_CLIENT_TIMEOUT_SECONDS=900  # 15 minutes
```

#### Cause 2: Database Connection Pool Too Large

```bash
# Reduce pool size
export ROUTEROS_MCP_DATABASE_POOL_SIZE=10
export ROUTEROS_MCP_DATABASE_MAX_OVERFLOW=5

# Restart service
sudo systemctl restart routeros-mcp
```

#### Cause 3: Memory Leak in Application

```bash
# Monitor memory over time
watch -n 5 'ps aux | grep routeros-mcp'

# If memory grows continuously, check for leaks
# Enable debug logging and analyze patterns

# Temporary mitigation: Restart service periodically
# (e.g., nightly restart)
```

---

### 8. CORS Errors (Browser Clients)

**Symptom:**
```
Access to fetch at 'https://mcp.example.com/mcp/initialize' from origin 'https://app.example.com' has been blocked by CORS policy
```

**Solution:**

```nginx
# In nginx, add CORS headers
location /mcp {
    # Allow specific origin (replace with your domain)
    add_header Access-Control-Allow-Origin https://app.example.com always;
    
    # Or allow all origins (less secure)
    # add_header Access-Control-Allow-Origin * always;
    
    add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
    add_header Access-Control-Allow-Headers "Authorization, Content-Type" always;
    add_header Access-Control-Max-Age 3600 always;
    
    # Handle preflight requests
    if ($request_method = OPTIONS) {
        return 204;
    }
    
    # ... proxy_pass config
}
```

---

### 9. Rate Limiting / 429 Too Many Requests

**Symptom:**
```json
{
  "error": {
    "code": -32003,
    "message": "Rate limit exceeded"
  }
}
```

**Solution:**

```bash
# If using nginx rate limiting:
# Edit nginx config
sudo nano /etc/nginx/sites-available/routeros-mcp

# Increase rate limit
limit_req_zone $binary_remote_addr zone=mcp_limit:10m rate=20r/s;  # 20 req/sec

# Or add burst buffer
location /mcp {
    limit_req zone=mcp_limit burst=50 nodelay;
    # ...
}

# Reload nginx
sudo nginx -t && sudo systemctl reload nginx
```

---

### 10. Service Crashes on Startup

**Symptom:**
```
systemctl status routeros-mcp
● routeros-mcp.service - RouterOS MCP Server
   Loaded: loaded
   Active: failed (Result: exit-code)
```

**Diagnostic Steps:**

```bash
# View full logs
sudo journalctl -u routeros-mcp -n 200 --no-pager

# Check for common startup errors:

# 1. Port already in use
# Error: "Address already in use"
sudo lsof -i :8080
# Solution: Kill process or change port

# 2. Missing encryption key
# Warning: "Using insecure default encryption key"
# Solution: Set ROUTEROS_MCP_ENCRYPTION_KEY

# 3. Database migration needed
# Error: "Table does not exist"
alembic upgrade head

# 4. Invalid configuration
# Error: "Configuration validation failed"
# Check config file syntax and required fields

# 5. Permission denied
# Error: "Permission denied"
# Check file permissions and user/group
sudo chown -R mcp:mcp /var/lib/routeros-mcp
```

---

## Debug Logging Setup

### Enable Debug Mode

**Environment Variable:**

```bash
export ROUTEROS_MCP_DEBUG=true
export ROUTEROS_MCP_LOG_LEVEL=DEBUG
```

**Configuration File:**

```yaml
# config/debug.yaml
debug: true
log_level: DEBUG
log_format: text  # Human-readable for debugging (use json in prod)
```

### Structured Logging

MCP uses structlog for structured logging. Logs include:
- Correlation IDs for request tracing
- User context (if authenticated)
- Device context (for RouterOS operations)
- Performance metrics (execution time)

**Example Log Output (JSON):**

```json
{
  "event": "MCP tool execution",
  "tool": "system/get-overview",
  "device_id": "dev-001",
  "user": "admin@example.com",
  "correlation_id": "req-abc123",
  "duration_ms": 250,
  "status": "success",
  "timestamp": "2024-12-16T01:00:00Z",
  "level": "info"
}
```

### View Logs in Real-Time

```bash
# Follow logs with systemd
sudo journalctl -u routeros-mcp -f

# Filter by level
sudo journalctl -u routeros-mcp -p err  # Errors only

# Filter by correlation ID
sudo journalctl -u routeros-mcp | grep "req-abc123"

# Export logs to file
sudo journalctl -u routeros-mcp --since today > mcp-logs.txt
```

### Log Aggregation (Production)

**Send logs to external system:**

```bash
# Example: rsyslog forwarding to ELK
sudo nano /etc/rsyslog.d/30-routeros-mcp.conf

# Add:
:programname, isequal, "routeros-mcp" @@elk.example.com:514

# Restart rsyslog
sudo systemctl restart rsyslog
```

---

## Performance Tuning

### Database Optimization

```bash
# Increase connection pool for high load
export ROUTEROS_MCP_DATABASE_POOL_SIZE=50
export ROUTEROS_MCP_DATABASE_MAX_OVERFLOW=20

# Enable connection pooling in PostgreSQL
# Edit postgresql.conf
max_connections = 200

# Create indexes on frequently queried columns
psql -U mcp_user -d routeros_mcp << EOF
CREATE INDEX idx_devices_name ON devices(name);
CREATE INDEX idx_audit_events_timestamp ON audit_events(timestamp);
CREATE INDEX idx_jobs_status ON jobs(status);
EOF
```

### SSE Optimization

```bash
# Batch updates to reduce event frequency
export ROUTEROS_MCP_SSE_UPDATE_BATCH_INTERVAL_SECONDS=2.0  # Batch for 2 seconds

# Limit subscriptions to prevent DoS
export ROUTEROS_MCP_SSE_MAX_SUBSCRIPTIONS_PER_DEVICE=100

# Use shorter timeout for inactive clients
export ROUTEROS_MCP_SSE_CLIENT_TIMEOUT_SECONDS=1200  # 20 minutes
```

### HTTP Server Tuning

**If using uvicorn (ASGI server):**

```bash
# Run with multiple workers
uvicorn routeros_mcp.main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --workers 4 \
  --timeout-keep-alive 1800

# Or use gunicorn with uvicorn workers
gunicorn routeros_mcp.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8080 \
  --timeout 1800
```

### nginx Tuning

```nginx
# Increase worker processes
worker_processes auto;

# Increase worker connections
events {
    worker_connections 4096;
}

# Enable HTTP/2
listen 443 ssl http2;

# Enable gzip compression
gzip on;
gzip_types application/json;

# Increase buffers for SSE
proxy_buffers 8 16k;
proxy_buffer_size 16k;
```

---

## Monitoring and Alerting

### Health Check Monitoring

```bash
# Cron job for health check
*/5 * * * * curl -f http://localhost:8080/health || systemctl restart routeros-mcp
```

### Prometheus Metrics

**If metrics enabled:**

```bash
# Scrape metrics endpoint
curl http://localhost:9090/metrics

# Key metrics to monitor:
# - mcp_http_requests_total (request count)
# - mcp_http_request_duration_seconds (latency)
# - mcp_sse_connections_active (active SSE connections)
# - mcp_database_pool_size (DB connection pool usage)
# - mcp_tool_execution_duration_seconds (tool performance)
```

**Example Prometheus Alert:**

```yaml
# prometheus-alerts.yml
groups:
  - name: mcp
    interval: 30s
    rules:
      - alert: MCPHighErrorRate
        expr: rate(mcp_http_requests_total{status="error"}[5m]) > 0.1
        for: 5m
        annotations:
          summary: "MCP error rate above 10%"
          
      - alert: MCPHighLatency
        expr: histogram_quantile(0.95, mcp_http_request_duration_seconds) > 2
        for: 5m
        annotations:
          summary: "MCP p95 latency above 2 seconds"
```

---

## Emergency Procedures

### Service Not Responding

```bash
# 1. Check if service is running
sudo systemctl status routeros-mcp

# 2. If running but not responding, restart
sudo systemctl restart routeros-mcp

# 3. If restart fails, check logs
sudo journalctl -u routeros-mcp -n 500

# 4. If database locked, restart PostgreSQL
sudo systemctl restart postgresql

# 5. Last resort: reboot server
sudo reboot
```

### Database Corruption

```bash
# 1. Stop MCP service
sudo systemctl stop routeros-mcp

# 2. Backup current database
pg_dump -U mcp_user routeros_mcp > mcp_backup_$(date +%Y%m%d).sql

# 3. Check database integrity
psql -U mcp_user -d routeros_mcp -c "VACUUM FULL ANALYZE;"

# 4. Restore from backup if needed
psql -U mcp_user -d routeros_mcp < mcp_backup_20241215.sql

# 5. Start service
sudo systemctl start routeros-mcp
```

### Certificate Expiry

```bash
# If Let's Encrypt cert expired:
sudo certbot renew --force-renewal

# Restart nginx
sudo systemctl restart nginx

# Verify renewal
echo | openssl s_client -connect mcp.example.com:443 2>/dev/null | openssl x509 -noout -dates
```

---

## Related Documentation

- [HTTP/SSE Transport Deployment Guide](20-http-sse-transport-deployment-guide.md)
- [OAuth Setup: Azure AD](21-oauth-setup-azure-ad.md)
- [OAuth Setup: Okta](22-oauth-setup-okta.md)
- [OAuth Setup: Auth0](23-oauth-setup-auth0.md)
- [MCP Protocol Integration](14-mcp-protocol-integration-and-transport-design.md)

---

## Getting Help

If you encounter issues not covered in this guide:

1. **Check GitHub Issues**: [RouterOS-MCP Issues](https://github.com/your-org/routeros-mcp/issues)
2. **Review Documentation**: All docs in `docs/` directory
3. **Enable Debug Logging**: Set `debug=true` and `log_level=DEBUG`
4. **Collect Diagnostics**: Logs, config, system info
5. **Open Issue**: Include logs, config (redact secrets), steps to reproduce
