---
name: Add Tests
about: Add missing test coverage (ideal for test-engineer-tdd agent)
title: '[TEST] '
labels: ['test', 'agent-tests-only']
assignees: []
---

## Goal

Add test coverage for `[module/component name]`

## Current Coverage

<!-- Output from coverage report -->

```bash
# Run coverage for the target module
pytest tests/unit/path/to/module --cov=routeros_mcp.path.to.module --cov-report=term-missing

# Current coverage: XX%
# Target coverage: YY%
```

## Target Modules

<!-- Which files need test coverage? -->

- `routeros_mcp/path/to/module.py` - Currently XX% covered, target YY%
- `routeros_mcp/path/to/another.py` - Currently XX% covered, target YY%

## Test Types Needed

- [ ] Unit tests - Test individual functions/methods
- [ ] Integration tests - Test interaction between components
- [ ] Contract tests - Test interface boundaries
- [ ] Edge case tests - Test error handling, edge cases

## Specific Scenarios to Cover

<!-- List specific test cases needed -->

1. **Happy path**: Normal operation with valid input
2. **Error handling**: Invalid input, missing data, network errors
3. **Edge cases**: Boundary conditions, empty inputs, maximum values
4. **Concurrent access**: Race conditions if applicable
5. **Regression tests**: Known bugs that should not recur

## Files to Create/Modify

- `tests/unit/path/to/test_module.py` - Create new test file
- `tests/conftest.py` - Add fixtures if needed (check existing first)

## Do Not Change

- **Never modify source code** (test-only task)
- **Never delete or comment out failing tests** (fix them or ask for clarification)
- Existing test utilities (use them, don't duplicate)

## Testing Framework & Patterns

Use existing patterns from this project:

```python
# Example test structure (see tests/unit/ for patterns)
import pytest
from unittest.mock import AsyncMock, MagicMock

class TestDeviceService:
    """Test suite for DeviceService."""
    
    async def test_get_device_when_exists_returns_device(
        self, db_session, test_device
    ):
        """Test that get_device returns device when it exists."""
        # Arrange
        service = DeviceService(db_session)
        
        # Act
        result = await service.get_device(test_device.device_id)
        
        # Assert
        assert result.device_id == test_device.device_id
        assert result.name == test_device.name
```

## Acceptance Criteria

- [ ] Target coverage percentage achieved (YY%+)
- [ ] All new tests pass
- [ ] Tests follow naming convention: `test_<what>_when_<condition>_then_<expected>`
- [ ] Tests use existing fixtures from `conftest.py`
- [ ] Tests are deterministic (no flaky tests)
- [ ] Tests run fast (<10s for unit tests)
- [ ] All external I/O is mocked (no network calls, no file system)

## How to Run Tests

```bash
# Run new tests
pytest tests/unit/path/to/test_module.py -v

# Check coverage
pytest tests/unit/path/to/test_module.py --cov=routeros_mcp.path.to.module --cov-report=term-missing

# Run full test suite to ensure no breakage
pytest
```

## Mocking Strategy

<!-- Which external dependencies need mocking? -->

- HTTP clients (`httpx.AsyncClient`) - Use `responses` library or AsyncMock
- SSH clients (`asyncssh`) - Use AsyncMock
- Database - Use test fixtures with in-memory SQLite
- Time-dependent code - Use `freezegun` or mock `datetime`

## References

- Existing test patterns: `tests/unit/mcp_tools_test_utils.py`
- Fixture library: `tests/unit/conftest.py`
- Coverage targets: 85%+ overall, 95%+ for core modules
