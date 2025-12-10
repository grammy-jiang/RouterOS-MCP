# MCP Prompt Templates

This directory contains YAML prompt templates for the RouterOS MCP service. These templates define guided workflows and troubleshooting procedures that help users safely perform complex operations.

## YAML Format

Each prompt template is defined as a YAML file with the following structure:

```yaml
# Unique prompt name (used for invocation)
name: prompt-name-kebab-case

# Human-readable description
description: Brief description of what this prompt does

# Optional: Arguments that customize the prompt
arguments:
  - name: environment
    description: Target environment
    type: string
    enum: [lab, staging, prod]
    required: false
    default: lab
  
  - name: dry_run
    description: Whether to preview changes first
    type: boolean
    required: false
    default: true

# Prompt content (Jinja2 template)
messages:
  - role: user
    content: |
      # {{ title }}
      
      {{ workflow_content }}

# Optional: Template variables for rendering
template_vars:
  title: "Workflow Title"
  safety_note: "Safety considerations..."

# Optional: Metadata
metadata:
  category: workflow  # workflow, troubleshooting, onboarding
  tier: fundamental   # fundamental, advanced, professional
  environments: [lab, staging, prod]
  requires_approval: false
```

## Available Prompts

### Workflows
- `dns_ntp_rollout.yaml` - DNS/NTP configuration rollout
- `address_list_sync.yaml` - Address list synchronization
- `device_onboarding.yaml` - Device registration guide

### Troubleshooting
- `troubleshoot_dns_ntp.yaml` - DNS/NTP troubleshooting
- `troubleshoot_device.yaml` - General device diagnostics
- `comprehensive_device_review.yaml` - Full device health review
- `security_audit.yaml` - Security configuration audit

### Fleet Operations
- `fleet_health_review.yaml` - Fleet-wide health assessment

## Jinja2 Template Features

Templates support the following Jinja2 features:

- Variable substitution: `{{ variable_name }}`
- Conditionals: `{% if condition %}...{% endif %}`
- Loops: `{% for item in items %}...{% endfor %}`
- Filters: `{{ value | upper }}`

Context variables available in all templates:

- `environment` - Current environment (lab/staging/prod)
- `device_count` - Number of devices in scope (if applicable)
- `user_role` - Current user's role
- `timestamp` - Current timestamp (ISO format)

## Adding New Prompts

1. Create a new YAML file in this directory
2. Follow the format specification above
3. Test the prompt with the MCP Inspector
4. Update this README with the prompt description

## Validation

Prompt templates are validated at startup for:
- Required fields (name, description, messages)
- Argument schema correctness
- Jinja2 syntax validity
- Tool/resource reference validity (warnings only)
