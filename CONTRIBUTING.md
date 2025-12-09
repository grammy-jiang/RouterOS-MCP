# Contributing to RouterOS MCP Service

Thank you for your interest in contributing to the RouterOS MCP Service! This guide will help you set up your development environment and understand our development workflow.

## Prerequisites

- Python 3.11 or later
- Git
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Development Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/grammy-jiang/RouterOS-MCP.git
cd RouterOS-MCP
```

### 2. Create a Virtual Environment

Using `uv` (recommended):

```bash
uv venv .venv
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

Using standard Python:

```bash
python -m venv .venv
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

### 3. Install Dependencies

Using `uv`:

```bash
uv pip install -e .[dev]
```

Using pip:

```bash
pip install -e .[dev]
```

This installs the package in editable mode with all development dependencies.

## Development Workflow

### Running the CLI

Test the CLI with the example lab configuration:

```bash
routeros-mcp --config config/lab.yaml
```

Or with command-line overrides:

```bash
routeros-mcp --debug --log-level DEBUG
```

### Running Tests

Run all tests:

```bash
pytest
```

Run tests with coverage:

```bash
pytest --cov=routeros_mcp --cov-report=html
```

Run specific test file:

```bash
pytest tests/unit/test_config.py
```

Run tests with verbose output:

```bash
pytest -v
```

### Code Quality Checks

#### Type Checking with mypy

```bash
mypy routeros_mcp
```

#### Linting with ruff

Check for issues:

```bash
ruff check routeros_mcp
```

Auto-fix issues:

```bash
ruff check --fix routeros_mcp
```

#### Code Formatting with black

Check formatting:

```bash
black --check routeros_mcp
```

Format code:

```bash
black routeros_mcp
```

#### Run All Quality Checks

```bash
# Run in sequence
ruff check routeros_mcp
black --check routeros_mcp
mypy routeros_mcp
pytest
```

## Code Standards

### Python Style

- Follow PEP 8 naming conventions
- Use type hints for all functions and methods
- Write docstrings for all public modules, classes, and functions
- Maximum line length: 100 characters
- Use `snake_case` for functions and variables
- Use `CamelCase` for classes
- Use `UPPER_SNAKE_CASE` for constants

### Testing

- Write tests for all new features and bug fixes
- Aim for at least 85% overall test coverage
- Core modules (domain, security, configuration) should have 100% coverage
- Use descriptive test names: `test_<what>_<when>_<expected>`
- Use pytest fixtures for common test setup

### Commit Messages

Follow conventional commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Example:

```
feat(config): add support for TOML configuration files

Implement TOML file loading in load_settings_from_file function.
Add tests for TOML file parsing.

Closes #123
```

## Project Structure

```
RouterOS-MCP/
├── routeros_mcp/          # Main package
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── cli.py             # CLI interface
│   ├── main.py            # Main entry point
│   ├── mcp/               # MCP protocol implementation
│   ├── domain/            # Business logic
│   ├── infra/             # Infrastructure (DB, RouterOS clients)
│   ├── security/          # Authentication and authorization
│   ├── api/               # HTTP API
│   ├── mcp_tools/         # MCP tool implementations
│   ├── mcp_resources/     # MCP resource providers
│   └── mcp_prompts/       # MCP prompt templates
├── tests/                 # Test suite
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── e2e/               # End-to-end tests
├── docs/                  # Design documentation
├── config/                # Example configurations
├── pyproject.toml         # Project metadata and dependencies
└── README.md              # Project overview
```

## Documentation

All design decisions are documented in the `docs/` directory. When making significant changes:

1. Review relevant design documents
2. Update documentation if behavior changes
3. Add new design documents for major features

## Questions or Issues?

- Check existing issues: https://github.com/grammy-jiang/RouterOS-MCP/issues
- Open a new issue for bugs or feature requests
- Discuss in pull request comments

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
