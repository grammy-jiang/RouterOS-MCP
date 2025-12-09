# Contributing to RouterOS MCP

Thank you for your interest in contributing to the RouterOS MCP service! This document provides guidelines and instructions for setting up your development environment and contributing to the project.

## Development Environment Setup

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 14+ (optional, SQLite is used by default for development)
- Git
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### Setting Up Your Development Environment

1. **Clone the repository**:

   ```bash
   git clone https://github.com/grammy-jiang/RouterOS-MCP.git
   cd RouterOS-MCP
   ```

2. **Create a virtual environment**:

   Using `uv` (recommended):
   ```bash
   uv venv .venv
   source .venv/bin/activate  # On Unix/macOS
   # or
   .venv\Scripts\activate  # On Windows
   ```

   Using standard `venv`:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Unix/macOS
   # or
   .venv\Scripts\activate  # On Windows
   ```

3. **Install dependencies**:

   Using `uv`:
   ```bash
   uv pip install -e .[dev]
   ```

   Using pip:
   ```bash
   pip install -e .[dev]
   ```

4. **Verify installation**:

   ```bash
   routeros-mcp --version
   pytest --version
   ruff --version
   mypy --version
   ```

### Configuration

1. **Create a local configuration file** (optional):

   ```bash
   cp config/lab.yaml config/local.yaml
   # Edit config/local.yaml with your local settings
   ```

2. **Set environment variables** (optional):

   ```bash
   cp .env.example .env
   # Edit .env with your local settings
   ```

## Running the Service

### CLI Usage

Run the service with default settings:

```bash
routeros-mcp
```

Run with a specific config file:

```bash
routeros-mcp --config config/lab.yaml
```

Run with debug logging:

```bash
routeros-mcp --debug --log-level DEBUG
```

### Testing Configuration

Test that your configuration loads successfully:

```bash
python -c "from routeros_mcp.config import Settings; s = Settings(); print(s.to_dict())"
```

## Development Workflow

### Code Style and Quality

This project uses the following tools for code quality:

- **Ruff**: Fast Python linter (replaces flake8, isort, and more)
- **Black**: Code formatter
- **mypy**: Static type checker

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
pytest tests/test_config.py
```

Run tests matching a pattern:

```bash
pytest -k "test_config"
```

### Linting and Formatting

Check code with ruff:

```bash
ruff check routeros_mcp tests
```

Auto-fix issues with ruff:

```bash
ruff check --fix routeros_mcp tests
```

Format code with black:

```bash
black routeros_mcp tests
```

Check formatting without changes:

```bash
black --check routeros_mcp tests
```

### Type Checking

Run mypy type checker:

```bash
mypy routeros_mcp
```

### Running All Quality Checks

Using tox (recommended for CI/local validation):

```bash
# Run all test environments
tox

# Run specific environment
tox -e lint   # Linting
tox -e type   # Type checking
tox -e cov    # Tests with coverage
```

## Project Structure

```
RouterOS-MCP/
├── config/                  # Configuration file examples
│   ├── lab.yaml            # Lab environment config
│   └── prod.yaml           # Production environment config
├── docs/                    # Design documentation
├── routeros_mcp/           # Main package
│   ├── __init__.py
│   ├── cli.py              # CLI entry point
│   ├── config.py           # Configuration system
│   ├── api/                # FastAPI HTTP API
│   ├── domain/             # Business logic
│   ├── infra/              # Infrastructure (DB, RouterOS clients, etc.)
│   ├── mcp/                # MCP protocol implementation
│   ├── mcp_tools/          # MCP tool implementations
│   ├── mcp_resources/      # MCP resource providers
│   ├── mcp_prompts/        # MCP prompt templates
│   └── security/           # Authentication and authorization
├── tests/                   # Test suite
│   ├── __init__.py
│   └── test_config.py
├── .env.example            # Example environment variables
├── .gitignore
├── pyproject.toml          # Project configuration and dependencies
└── README.md
```

## Coding Standards

### Python Version

- **Minimum**: Python 3.11
- **Target**: Python 3.11+
- Use modern Python features (type hints, async/await, etc.)

### Type Hints

- All functions and methods must have type hints
- Use `from typing import ...` for generic types
- Avoid `Any` unless absolutely necessary

### Async/Await

- All I/O operations must be async
- Use `async`/`await` throughout
- Prefer `httpx` over `requests`
- Use `asyncpg` for PostgreSQL

### Documentation

- All modules must have docstrings
- All public functions and classes must have docstrings
- Use Google-style docstrings:

  ```python
  def my_function(arg1: str, arg2: int) -> bool:
      """Short description.

      Longer description if needed.

      Args:
          arg1: Description of arg1
          arg2: Description of arg2

      Returns:
          Description of return value

      Raises:
          ValueError: Description of when this is raised
      """
      pass
  ```

### Testing

- Aim for 85%+ overall test coverage
- Core modules should have 100% coverage
- Write unit tests for all new functionality
- Use pytest fixtures for common setup
- Mark async tests with `@pytest.mark.asyncio`

### Error Handling

- Use specific exception types
- Avoid bare `except:` clauses
- Log errors with context
- Provide actionable error messages

### Security

- Never commit secrets or credentials
- Mask sensitive data in logs
- Validate all external input
- Follow principle of least privilege

## Making Changes

### Before You Start

1. Check existing issues and pull requests
2. Create an issue to discuss major changes
3. Ensure you have the latest code:
   ```bash
   git pull origin main
   ```

### Development Process

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**:
   - Write code following the coding standards
   - Add tests for new functionality
   - Update documentation as needed

3. **Run quality checks**:
   ```bash
   # Run all checks
   tox

   # Or run individually
   ruff check routeros_mcp tests
   black routeros_mcp tests
   mypy routeros_mcp
   pytest --cov=routeros_mcp
   ```

4. **Commit your changes**:
   ```bash
   git add .
   git commit -m "Brief description of changes"
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a pull request**:
   - Provide a clear description of changes
   - Reference any related issues
   - Ensure CI checks pass

### Commit Message Guidelines

- Use present tense: "Add feature" not "Added feature"
- Be concise but descriptive
- Reference issues when applicable: "Fix #123: Add validation"

## Getting Help

- **Documentation**: See the `docs/` directory for design specifications
- **Issues**: Open a GitHub issue for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions and ideas

## Code of Conduct

- Be respectful and constructive
- Welcome newcomers
- Focus on what is best for the project
- Show empathy towards other community members

## License

By contributing to RouterOS MCP, you agree that your contributions will be licensed under the MIT License.

## Additional Resources

- [Design Documentation](docs/)
- [MCP Best Practices](docs/best_practice/)
- [Python Coding Standards](docs/13-python-coding-standards-and-conventions.md)
- [Testing Strategy](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md)
