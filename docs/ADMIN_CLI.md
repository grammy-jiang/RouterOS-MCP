# RouterOS MCP Admin CLI

Human-facing CLI tool for device onboarding and plan management in RouterOS MCP.

## Overview

The admin CLI provides operators with a user-friendly interface to:
- **Device Management**: Onboard RouterOS devices with encrypted credentials
- **Capability Configuration**: Set environment tags and capability flags
- **Plan Review**: Review, approve, or reject configuration change plans
- **Connectivity Testing**: Test REST and SSH connectivity to devices

This complements the MCP tools which are AI-facing.

## Installation

The admin CLI is installed automatically with the package:

```bash
pip install -e .
```

Two entry points are available:
- `routeros-mcp-admin` - Installed command
- `python -m routeros_mcp.cli.admin` - Module execution

## Quick Start

### Device Onboarding

Add a new device with interactive prompts:

```bash
routeros-mcp-admin --config config/lab.yaml device add \
    --id dev-lab-01 \
    --name "Router Lab 01" \
    --ip 192.168.1.1 \
    --username admin
```

Non-interactive mode (for scripts):

```bash
routeros-mcp-admin --config config/lab.yaml device add \
    --id dev-lab-01 \
    --name "Router Lab 01" \
    --ip 192.168.1.1 \
    --username admin \
    --password secret \
    --allow-professional-workflows \
    --non-interactive
```

### List Devices

Table format (default):

```bash
routeros-mcp-admin --config config/lab.yaml device list
```

JSON format:

```bash
routeros-mcp-admin --config config/lab.yaml device list --format json
```

Filter by environment:

```bash
routeros-mcp-admin --config config/lab.yaml device list --environment lab --status healthy
```

### Update Device

Update device capabilities:

```bash
routeros-mcp-admin --config config/lab.yaml device update dev-lab-01 \
    --allow-professional-workflows true \
    --allow-firewall-writes true
```

Update environment and tags:

```bash
routeros-mcp-admin --config config/lab.yaml device update dev-lab-01 \
    --environment staging \
    --tags '{"site": "datacenter", "role": "edge"}'
```

### Test Device Connectivity

Test REST and SSH connectivity:

```bash
routeros-mcp-admin --config config/lab.yaml device test dev-lab-01
```

Shows device information if reachable:
- Version
- Identity
- Model
- Serial number

### Plan Management

List plans:

```bash
routeros-mcp-admin --config config/lab.yaml plan list
```

Filter plans:

```bash
routeros-mcp-admin --config config/lab.yaml plan list \
    --status pending \
    --created-by test-user \
    --limit 100
```

Show plan details:

```bash
routeros-mcp-admin --config config/lab.yaml plan show plan-12345
```

Approve a plan (interactive):

```bash
routeros-mcp-admin --config config/lab.yaml plan approve plan-12345
```

Approve a plan (non-interactive):

```bash
routeros-mcp-admin --config config/lab.yaml plan approve plan-12345 --non-interactive
```

Reject a plan:

```bash
routeros-mcp-admin --config config/lab.yaml plan reject plan-12345 \
    --reason "Invalid DNS configuration"
```

## Command Reference

### Global Options

- `--config, -c PATH`: Path to configuration file (YAML or TOML)

### Device Commands

#### `device add`

Add a new RouterOS device with encrypted credentials.

**Required options:**
- `--id TEXT`: Unique device ID
- `--name TEXT`: Human-friendly device name
- `--ip TEXT`: Management IP address
- `--username TEXT`: REST API username

**Optional options:**
- `--password TEXT`: REST API password (prompts if not provided)
- `--port INTEGER`: Management port (default: 443)
- `--environment [lab|staging|prod]`: Environment tag
- `--tags TEXT`: JSON object with device tags
- `--allow-advanced-writes`: Allow advanced write operations
- `--allow-professional-workflows`: Allow professional workflows
- `--allow-firewall-writes`: Allow firewall write operations
- `--allow-routing-writes`: Allow routing write operations
- `--allow-wireless-writes`: Allow wireless write operations
- `--allow-dhcp-writes`: Allow DHCP write operations
- `--allow-bridge-writes`: Allow bridge write operations
- `--non-interactive`: Non-interactive mode (no prompts)

**Examples:**

```bash
# Interactive mode (prompts for password and confirmation)
routeros-mcp-admin --config config/lab.yaml device add \
    --id dev-lab-01 \
    --name "Router Lab 01" \
    --ip 192.168.1.1 \
    --username admin

# Non-interactive with all flags
routeros-mcp-admin --config config/lab.yaml device add \
    --id dev-lab-01 \
    --name "Router Lab 01" \
    --ip 192.168.1.1 \
    --username admin \
    --password secret \
    --environment lab \
    --tags '{"site": "home", "role": "core"}' \
    --allow-professional-workflows \
    --non-interactive
```

#### `device list`

List all registered devices.

**Options:**
- `--environment [lab|staging|prod]`: Filter by environment
- `--status TEXT`: Filter by status
- `--format [table|json]`: Output format (default: table)

**Examples:**

```bash
# List all devices (table format)
routeros-mcp-admin --config config/lab.yaml device list

# List lab devices in JSON format
routeros-mcp-admin --config config/lab.yaml device list \
    --environment lab \
    --format json

# List healthy devices
routeros-mcp-admin --config config/lab.yaml device list --status healthy
```

#### `device update`

Update device configuration.

**Arguments:**
- `DEVICE_ID`: Device identifier

**Options:**
- `--name TEXT`: Update device name
- `--environment [lab|staging|prod]`: Update environment
- `--tags TEXT`: Update tags (JSON object)
- `--allow-professional-workflows [true|false]`: Enable/disable professional workflows
- `--allow-firewall-writes [true|false]`: Enable/disable firewall writes
- `--allow-routing-writes [true|false]`: Enable/disable routing writes
- `--allow-wireless-writes [true|false]`: Enable/disable wireless writes
- `--allow-dhcp-writes [true|false]`: Enable/disable DHCP writes
- `--allow-bridge-writes [true|false]`: Enable/disable bridge writes

**Examples:**

```bash
# Enable capabilities
routeros-mcp-admin --config config/lab.yaml device update dev-lab-01 \
    --allow-professional-workflows true \
    --allow-firewall-writes true

# Update environment and name
routeros-mcp-admin --config config/lab.yaml device update dev-lab-01 \
    --environment staging \
    --name "Router Staging 01"

# Update tags
routeros-mcp-admin --config config/lab.yaml device update dev-lab-01 \
    --tags '{"site": "datacenter", "rack": "A1"}'
```

#### `device test`

Test connectivity to a device (REST + SSH).

**Arguments:**
- `DEVICE_ID`: Device identifier

**Examples:**

```bash
routeros-mcp-admin --config config/lab.yaml device test dev-lab-01
```

### Plan Commands

#### `plan list`

List configuration change plans.

**Options:**
- `--status TEXT`: Filter by status (pending, approved, executing, completed, failed, cancelled)
- `--created-by TEXT`: Filter by creator
- `--limit INTEGER`: Maximum number of results (default: 50)
- `--format [table|json]`: Output format (default: table)

**Examples:**

```bash
# List all plans
routeros-mcp-admin --config config/lab.yaml plan list

# List pending plans
routeros-mcp-admin --config config/lab.yaml plan list --status pending

# List plans by creator in JSON
routeros-mcp-admin --config config/lab.yaml plan list \
    --created-by test-user \
    --format json
```

#### `plan show`

Show detailed plan information.

**Arguments:**
- `PLAN_ID`: Plan identifier

**Options:**
- `--format [text|json]`: Output format (default: text)

**Examples:**

```bash
# Show plan in text format
routeros-mcp-admin --config config/lab.yaml plan show plan-12345

# Show plan in JSON format
routeros-mcp-admin --config config/lab.yaml plan show plan-12345 --format json
```

#### `plan approve`

Approve a plan (admin-only operation).

**Arguments:**
- `PLAN_ID`: Plan identifier

**Options:**
- `--non-interactive`: Non-interactive mode (no prompts)

**Examples:**

```bash
# Interactive approval (shows plan details and asks for confirmation)
routeros-mcp-admin --config config/lab.yaml plan approve plan-12345

# Non-interactive approval
routeros-mcp-admin --config config/lab.yaml plan approve plan-12345 --non-interactive
```

Returns approval token and expiration time for use with MCP tools.

#### `plan reject`

Reject a plan with reason.

**Arguments:**
- `PLAN_ID`: Plan identifier

**Options:**
- `--reason TEXT`: Reason for rejection (required)

**Examples:**

```bash
routeros-mcp-admin --config config/lab.yaml plan reject plan-12345 \
    --reason "Invalid DNS configuration"
```

## Output Formats

### Table Format

Pretty-printed tables with colorized output using Rich library:

```
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━┓
┃ ID         ┃ Name         ┃ IP:Port        ┃ Environment ┃ Status  ┃ Prof. WF ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━┩
│ dev-lab-01 │ Router Lab 1 │ 192.168.1.1:443│ lab         │ healthy │ ✓        │
└────────────┴──────────────┴────────────────┴─────────────┴─────────┴──────────┘
```

### JSON Format

Machine-readable JSON for scripting:

```json
[
  {
    "id": "dev-lab-01",
    "name": "Router Lab 1",
    "ip": "192.168.1.1",
    "port": 443,
    "environment": "lab",
    "status": "healthy",
    "professional_workflows": true
  }
]
```

## Interactive Features

### Password Prompts

When `--password` is not provided in device add commands:

```bash
$ routeros-mcp-admin --config config/lab.yaml device add \
    --id dev-lab-01 --name "Router" --ip 192.168.1.1 --username admin
Password: ********
```

### Confirmation Prompts

Interactive mode asks for confirmation on sensitive operations:

```bash
Device Configuration Summary:
  ID: dev-lab-01
  Name: Router Lab 01
  IP: 192.168.1.1:443
  ...

Proceed with device registration? [y/N]: y
```

### Progress Bars

Long-running operations show progress indicators:

```
⠹ Registering device...
✓ Device registered: dev-lab-01
✓ Credentials stored (encrypted)

Success! Device 'dev-lab-01' is ready to use.
```

## Security Considerations

### Credential Encryption

All device credentials are stored encrypted at rest. Ensure an encryption key is configured:

```bash
export ROUTEROS_MCP_ENCRYPTION_KEY="your-32-byte-base64-key"
```

In lab environments, a fallback key is used (shows warnings).

### Non-Interactive Mode

For automated scripts and CI/CD:
- Use `--non-interactive` flag
- Provide `--password` via environment variable or secure secret store
- Review automation logs for security audit trail

### Plan Approval

Approval tokens are cryptographically signed (HMAC-SHA256) and expire after 15 minutes.

## Migration from scripts/add_device.py

The old `scripts/add_device.py` is deprecated. Migrate to the new CLI:

**Old:**
```bash
python scripts/add_device.py --config config/lab.yaml \
    --id dev-lab-01 --name "Router" --ip 192.168.1.1 \
    --username admin --password secret
```

**New:**
```bash
routeros-mcp-admin --config config/lab.yaml device add \
    --id dev-lab-01 --name "Router" --ip 192.168.1.1 \
    --username admin --password secret --non-interactive
```

The old script prints a deprecation warning and will be removed in a future release.

## Testing

Run CLI tests:

```bash
pytest tests/unit/cli/test_admin.py -v
```

All 24 CLI tests should pass, covering:
- Device add with various options
- Device list with filters
- Device update
- Device test (connectivity)
- Plan list with filters
- Plan show
- Plan approve/reject
- Help messages
- Error handling

## Development

### Adding New Commands

1. Add command function to `routeros_mcp/cli/admin.py`
2. Use `@device.command()` or `@plan.command()` decorator
3. Add Click options with `@click.option()`
4. Use Rich Console for output formatting
5. Add unit tests in `tests/unit/cli/test_admin.py`

### Code Structure

```
routeros_mcp/cli/
├── __init__.py      # Package init, re-exports base CLI
├── base.py          # Base CLI (argument parsing for MCP server)
└── admin.py         # Admin CLI (device/plan management)

tests/unit/cli/
├── __init__.py
└── test_admin.py    # Admin CLI tests (24 tests)
```

## Troubleshooting

### Import Errors

If you see import errors after installation:

```bash
pip install -e .[dev]
```

### Database Connection Issues

Ensure config file has valid database URL:

```yaml
database_url: sqlite+aiosqlite:///./routeros_mcp.db
```

### Encryption Key Warnings

Set encryption key to silence warnings:

```bash
export ROUTEROS_MCP_ENCRYPTION_KEY="your-key-here"
```

## See Also

- Design doc: `docs/09-operations-deployment-self-update-and-runbook.md` (lines 715-725)
- Device onboarding flow: `docs/09-operations-deployment-self-update-and-runbook.md` (lines 50-120)
- MCP tools documentation: `docs/04-mcp-tools-interface-and-json-schema-specification.md`
