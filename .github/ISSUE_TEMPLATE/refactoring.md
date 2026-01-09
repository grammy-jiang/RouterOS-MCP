---
name: Refactoring Task
about: Code improvement without changing functionality (agent-friendly)
title: '[REFACTOR] '
labels: ['refactor', 'agent-refactor']
assignees: []
---

## Goal

<!-- What is the objective of this refactoring? -->

## Current State

<!-- What does the code look like now? What's the problem? -->

## Desired State

<!-- What should the code look like after refactoring? -->

## Motivation

<!-- Why is this refactoring needed? -->

- [ ] Improve code readability
- [ ] Reduce duplication
- [ ] Improve performance
- [ ] Better align with design patterns
- [ ] Prepare for future features
- [ ] Other: 

## Scope

### Files to Refactor

- `path/to/file1.py` - What changes
- `path/to/file2.py` - What changes

### Files to Update (tests, docs)

- `tests/path/to/test_file1.py` - Update tests if needed
- `docs/relevant-doc.md` - Update if public APIs change

### Do Not Change

- Public API contracts (unless explicitly planned)
- Database schema
- Configuration file formats
- Behavior visible to MCP clients

## Acceptance Criteria

- [ ] All existing tests still pass
- [ ] No functionality changes (behavior identical)
- [ ] Code coverage remains the same or improves
- [ ] Linting/type checking passes
- [ ] Performance is same or better

## Testing Strategy

```bash
# Run existing tests to ensure no regression
pytest tests/path/to/relevant/ -v

# Run full test suite
pytest

# Verify linting
ruff check routeros_mcp tests
black --check routeros_mcp tests
mypy routeros_mcp
```

## Success Metrics

<!-- How will we measure success? -->

- [ ] Cyclomatic complexity reduced (if applicable)
- [ ] Code duplication eliminated
- [ ] Type coverage improved
- [ ] Module coupling reduced
- [ ] Test execution time (should be same or faster)

## Rollback Plan

<!-- How can we revert if something goes wrong? -->

- Revert commit (no schema changes, pure code refactoring)

## Related Design Docs

<!-- Link to architecture decisions or design docs -->

- [docs/XX-relevant-design.md](../docs/XX-relevant-design.md)
