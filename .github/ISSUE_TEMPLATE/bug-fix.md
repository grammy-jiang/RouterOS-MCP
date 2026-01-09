---
name: Bug Fix
about: Template for bug fixes (can be assigned to Copilot agent)
title: '[BUG] '
labels: ['bug']
assignees: []
---

## Bug Description

<!-- Clear description of the unexpected behavior -->

## Current Behavior

<!-- What actually happens -->

## Expected Behavior

<!-- What should happen -->

## Steps to Reproduce

1. Step one
2. Step two
3. Step three
4. Observe error

## Environment

- Python version: 
- OS: 
- RouterOS version (if applicable): 
- Relevant configuration:

## Error Messages / Logs

```
<!-- Paste relevant error messages or log output here -->
<!-- IMPORTANT: Remove any secrets, credentials, or sensitive data -->
```

## Root Cause (if known)

<!-- What is causing this bug? Link to specific files/lines if known -->

- File: `path/to/file.py`
- Line: XX
- Issue: Description of the problem

## Proposed Solution

<!-- How should this be fixed? -->

## Files to Modify

- `path/to/buggy_file.py` - Fix the root cause
- `tests/path/to/test_file.py` - Add regression test

## Acceptance Criteria

- [ ] Bug no longer occurs (steps to reproduce pass)
- [ ] Regression test added that would fail without the fix
- [ ] No new warnings or errors introduced
- [ ] Related edge cases also tested

## How to Test

```bash
# Reproduce the bug (should fail before fix)
pytest tests/path/to/test_regression.py::test_bug_reproduction -v

# Verify all related tests pass
pytest tests/path/to/ -v
```

## Related Issues

<!-- Link to related issues, PRs, or discussions -->

- Related: #
- Caused by: #
- Blocks: #
