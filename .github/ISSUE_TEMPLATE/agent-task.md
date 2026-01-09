---
name: Agent Task
about: Optimized issue template for GitHub Copilot coding agent
title: '[AGENT] '
labels: ['agent-task', 'good-first-agent-task']
assignees: []
---

## Problem

<!-- Clear business description: What issue needs to be solved? -->

## Context

<!-- 
- Where in the codebase does this relate to?
- What business impact does this have?
- Link to relevant design docs, ADRs, or related issues
-->

## Acceptance Criteria

<!-- Specific, measurable conditions for "done". Each should be verifiable. -->

- [ ] Criterion 1 (e.g., API returns 200 for valid input)
- [ ] Criterion 2 (e.g., Unit tests added with 95%+ coverage)
- [ ] Criterion 3 (e.g., Documentation updated in docs/)

## Files to Modify

<!-- Explicit list of files the agent should change -->

- `path/to/file1.py` - What changes are needed
- `tests/path/to/test_file1.py` - What tests to add
- `docs/relevant-doc.md` - What documentation to update

## Do Not Change

<!-- Critical: What must NOT be modified -->

- Database schema (requires migration review)
- Authentication/authorization logic (security review required)
- Production configuration files
- Existing test coverage (no test deletions)

## How to Build & Test

<!-- Specific commands to validate the changes -->

```bash
# Fast validation (run this first)
pytest tests/unit/path/to/relevant_tests.py -q

# Full validation
pytest
ruff check routeros_mcp tests
black --check routeros_mcp tests
mypy routeros_mcp
```

## Expected Test Output

<!-- What should the test results look like when done correctly? -->

```bash
# Example:
$ pytest tests/unit/domain/test_device_service.py::test_get_device_when_exists -v
tests/unit/domain/test_device_service.py::test_get_device_when_exists PASSED

# Or specific behavior:
$ curl http://localhost:8000/api/devices/test-device
{"id": "test-device", "name": "Test Device", "status": "active"}
```

## Known Edge Cases & Pitfalls

<!-- Important warnings about historical bugs or tricky behavior -->

- Edge case 1: Example issue to watch out for
- Pitfall 2: Previous bug to avoid (link to issue if available)

## Architecture & Design Context

<!-- Link to relevant design documents -->

- Related design doc: [docs/XX-relevant-design.md](../docs/XX-relevant-design.md)
- Architecture diagram: (if applicable)
- API contracts: (if applicable)

## Success Checklist

Before marking this complete, ensure:

- [ ] All acceptance criteria met
- [ ] Tests pass locally (`pytest`)
- [ ] Linting passes (`ruff check --fix routeros_mcp tests`)
- [ ] Formatting passes (`black routeros_mcp tests`)
- [ ] Type checking passes for new code (`mypy routeros_mcp`)
- [ ] No secrets or credentials in logs or code
- [ ] Documentation updated if public APIs changed
- [ ] No breaking changes to existing APIs (or clearly documented)

---

<!-- 
AGENT EXECUTION PLAN TEMPLATE (for agent to fill out before starting):

Before making changes, please:
1. Write a numbered plan of the changes you'll make
2. List any assumptions you're making
3. Identify any uncertainties that need clarification
4. Then implement the plan step-by-step
-->
