# MCP Server Design Procedure Guide

This guide provides a structured, end-to-end process for designing and implementing MCP servers. It synthesizes official MCP documentation, production experience, and community best practices into a systematic procedure that helps engineering teams apply the MCP specification effectively.

Large language models interact with external systems via the Model Context Protocol (MCP). This protocol is not another REST façade—it is a standardized way to expose tools, context data, and structured workflows to conversational agents. Designing an MCP server requires careful scoping, schema design, and operational safeguards to ensure reliability, security, and model efficacy.

---

## Running Example: Issue Tracker MCP Server

To make this procedure concrete, we'll design an Issue Tracker MCP server throughout. This server exposes an internal bug/issue system to AI assistants.

**Target user workflows:**

1. "Find all open P1 bugs assigned to me last week."
2. "Create a bug from this stack trace and logs."
3. "Change this issue's status to 'In Progress' and assign it to Alice."
4. "Summarize the discussion on this issue and suggest next steps."
5. "List my open issues for project `CORE`."

We'll refer back to these workflows as we progress through each step.

---

## The Phased Implementation Strategy

Given the reality that most AI clients support only Tools (ChatGPT, Mistral, many UIs) while richer clients (Claude, VS Code + Copilot) support Resources and Prompts, we adopt a phased strategy:

**Phase 1 (Portable MCP Core):** Tools + base protocol + security. Works in almost every client.

**Phase 2 (Rich MCP):** Resources + Prompts + Roots, for richer hosts.

**Phase 3 (Scale & Governance):** Registries, sampling tuning, large-scale policy.

The procedure below designs for the full spec but implements in phases.

---

## Step 0: Set the Frame—What Is MCP Doing for You?

Before implementing any endpoint, articulate the mission of your MCP server.

**MCP is the bridge between the model and your domain, not a generic API gateway.**

The constraints that shape MCP design are fundamentally different from traditional API design:

**Context windows are limited and expensive.** Models cannot process unlimited data. Unlike REST clients that paginate through thousands of results, LLMs need focused, relevant information.

**Models struggle with huge, noisy tool surfaces.** When presented with dozens of similar-sounding tools, models make poor choices. Fewer well-designed tools outperform comprehensive coverage.

**Security blast radius must be tightly controlled.** MCP servers often run with the same privileges as the host application. A poorly scoped server can expose far more than intended.

**The cardinal mistake:** If you merely mirror existing services, you will end up with a bloated and confusing tool surface, causing poor model performance. This step ensures you design for LLM ergonomics from the start.

**Self-check questions:**
- What specific user problems will this MCP server solve?
- What makes this server valuable to an LLM that a REST API wouldn't provide?
- What should this server explicitly NOT do?

---

## Step 1: Define Use-Cases and Success Criteria

Begin by answering: "What tasks do users want to accomplish, and what would success look like?"

### 1.1 Enumerate 5-10 Concrete User Workflows

For each workflow, capture:
- **Inputs:** User language, attachments, IDs, context
- **Systems touched:** Databases, APIs, external services
- **Side effects:** Create/update records, notifications, or read-only

**Issue Tracker example workflows:**

| # | Workflow | Inputs | Systems | Side Effects |
|---|----------|--------|---------|--------------|
| 1 | Find P1 bugs assigned to me | Natural language query | Issue DB | Read-only |
| 2 | Create bug from logs | Stack trace, log snippet | Issue DB | Creates issue |
| 3 | Update status and assignee | Issue ID, new values | Issue DB | Updates issue |
| 4 | Summarize issue discussion | Issue ID | Issue DB | Read-only |
| 5 | List my open issues | Project name | Issue DB | Read-only |

### 1.2 Convert to Measurable Success Criteria

Success criteria make evaluation concrete and prevent scope creep:

| Workflow | Success Criterion |
|----------|------------------|
| Find P1 bugs | >95% accuracy in filtering by priority and assignee |
| Create bug from logs | >90% choose correct project and priority without manual correction |
| Update status | Status change reflected in system within 2 seconds |
| Summarize discussion | Summary captures key points; users rate 4+/5 on usefulness |
| List my open issues | P95 latency < 1 second for typical filters |

**Why this matters:** Without success criteria, you'll optimize for the wrong things or never know if your design actually works.

---

## Step 2: Decide Server Boundaries

Apply the "single responsibility" principle to your entire server.

### 2.1 Group Workflows by Business Capability

Group by capability, not by existing microservices:

- Issue lifecycle + search → **Issue MCP server**
- Git operations → separate **Git MCP server**
- Log analysis → separate **Logs MCP server** (or integrate if tightly coupled)

### 2.2 Apply the One-Sentence Test

Can you describe the server in one sentence without saying "and also..."?

```
✅ "This server manages issue lifecycle: searching, creating, updating, and reading issues."

❌ "This server manages issues and also handles Git operations and also analyzes logs..."
```

If you fail this test, you're mixing concerns. Split into multiple servers.

### 2.3 Document the Boundary

For the Issue Tracker:
- **In scope:** Issue CRUD, search, status transitions, comments
- **Out of scope:** Git operations, CI/CD, deployment, user management

**Why this matters:** Models perform better when servers have clear, cohesive purposes. Mixed-domain servers create confusion about which tool to call.

---

## Step 3: Enumerate Capabilities and Classify Them

Break each workflow into atomic capabilities and classify each as a tool, resource, or prompt.

### 3.1 Understanding the Three Primitives

**Tool:** A model-controlled function that performs an action or query. Tools are discovered via `tools/list` and invoked via `tools/call`. They should encapsulate meaningful tasks rather than low-level API calls.

**Resource:** Read-only data or context provided by the application. Resources are discovered via `resources/list` and read via `resources/read`. They are application-driven; clients choose when to fetch them.

**Prompt:** A user-controlled template or workflow macro discovered via `prompts/list` and expanded with `prompts/get`. Prompts represent multi-step sequences that users trigger explicitly.

### 3.2 Classification Decision Framework

| If the capability... | Use... | Because... |
|---------------------|--------|------------|
| Performs an action or returns dynamic results | **Tool** | Model decides when to invoke |
| Provides static or semi-static reference data | **Resource** | Application controls context loading |
| Is a reusable multi-step workflow template | **Prompt** | User explicitly selects it |

### 3.3 Create the Capability Inventory

For each capability, determine:
1. MCP type: Tool / Resource / Prompt
2. Implementation phase: 1 / 2 / 2+
3. Phase-1 fallback for Phase-2 features

**Issue Tracker capability inventory:**

| Capability | MCP Type | Phase | Phase-1 Fallback | Rationale |
|------------|----------|-------|------------------|-----------|
| Search issues by filters | Tool | 1 | — | Dynamic results, model-controlled |
| Get single issue by ID | Tool | 1 | — | Dynamic results |
| Create new issue | Tool | 1 | — | Has side effects |
| Update issue status/assignee | Tool | 1 | — | Has side effects |
| List my open issues | Tool | 1 | — | Convenience wrapper |
| Issue full text as context | Resource | 2 | `get_issue_full_text` tool | Static reference data |
| Project schema/custom fields | Resource | 2 | `get_project_schema` tool | Static reference data |
| "Triage from logs" workflow | Prompt | 2 | Host-side prompt | Multi-step workflow |
| "Summarize discussion" workflow | Prompt | 2 | Host-side prompt | Multi-step workflow |

### 3.4 Design Phase-1 Fallbacks

For each Phase-2 feature, design a Phase-1 fallback:

**Planned Resource → Phase-1 read-only Tool:**
```python
@mcp.tool()
async def get_issue_full_text(project: str, issue_id: str) -> dict:
    """Get complete issue content (fallback for issue:// resource)."""
    content = await fetch_issue_full_text(project, issue_id)
    return {
        "content": content,
        "resource_uri": f"issue://{project}/{issue_id}",  # Migration hint
        "note": "In clients supporting Resources, use the URI directly."
    }
```

**Planned Prompt → Phase-1 host-side prompt/macro:**
Document the prompt template so users can implement it in their IDE or chat client until Phase 2.

---

## Step 4: Design Each Tool—Naming, Description, and Schema

For each tool identified in Step 3, complete the following design elements.

### 4.1 Choose a Clear Name

**Pattern:** verb + domain in snake_case

**Good examples:**
- `search_issues`
- `create_event`
- `update_issue_status`

**Avoid:**
- Generic names: `execute`, `run`, `process`
- Implementation details: `call_jira_api`
- Abbreviations: `upd_iss`, `srch`

### 4.2 Write an Intent-Based Description

The description is the most critical design element. It must explain *when* to use the tool:

```
❌ Functional (what it does):
"Retrieves issues from the database."

✅ Intent-based (when to use it):
"Search issues by project, optionally filtering by assignee, status, and priority.

Use when the user wants to:
- Find issues matching specific criteria
- Check what's assigned to them
- Explore issues in a project

Returns a list of matching issues with key metadata."
```

**Description checklist:**
- [ ] Explains the user scenario when this tool is appropriate
- [ ] Lists concrete examples of when to use it
- [ ] Clarifies what inputs are needed and optional
- [ ] Mentions side effects if any
- [ ] Distinguishes from similar tools

### 4.3 Design the Input Schema

Define a JSON Schema with necessary parameters, types, and validation:

```python
@mcp.tool()
async def search_issues(
    project: str,                                                    # Required
    assignee: str | None = None,                                    # Optional filter
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None,
    priority: Literal["P1", "P2", "P3", "P4"] | None = None,
    max_results: int = 50,                                          # Sensible default
    created_after: str | None = None,                               # ISO date format
) -> dict:
    """..."""
```

**Schema principles:**
- Required parameters first, optional with sensible defaults
- Use enums for constrained values (status, priority)
- Clear field names (`assignee` not `a`, `max_results` not `n`)
- Document units, formats, and constraints in docstrings

### 4.4 Define Structured Output

Return structured JSON containing just the data the model needs:

```python
return {
    "count": len(issues),
    "data": [
        {
            "id": issue.id,
            "title": issue.title,
            "status": issue.status,
            "priority": issue.priority,
            "assignee": issue.assignee,
            "created_at": issue.created_at.isoformat()
        }
        for issue in issues
    ],
    "has_more": total_count > len(issues),
    "suggestion": "Use get_issue to see full details for a specific issue."
}
```

**Avoid:** Dumping raw upstream API responses.

### 4.5 Design the Error Model

Differentiate between error types and provide actionable messages:

```python
# User error (invalid parameters)
return {
    "error": True,
    "type": "user_error",
    "message": "Project 'FOO' not found.",
    "suggestion": "Valid projects: CORE, WEB, API"
}

# Permission error
return {
    "error": True,
    "type": "permission",
    "message": "You don't have access to project 'SECURE'.",
    "suggestion": "Contact your administrator for access."
}

# System error
return {
    "error": True,
    "type": "system_error",
    "message": "Issue service timed out after 30s.",
    "suggestion": "Try again in a few moments."
}
```

### 4.6 Map Tools to Workflows

Verify each workflow from Step 1 can be accomplished:

| Workflow | Tools Used |
|----------|------------|
| Find P1 bugs assigned to me | `search_issues(assignee="me", priority="P1")` |
| Create bug from logs | `create_issue(...)` |
| Update status to In Progress | `get_issue(id)` → `update_issue_status(id, status="in_progress")` |
| Summarize discussion | `get_issue(id)` or `get_issue_full_text(id)` |
| List my open issues | `list_my_issues()` or `search_issues(assignee="me", status="open")` |

---

## Step 5: Design Resources—URIs, Discovery, and Chunking

Even though Resources are Phase 2, design them now to ensure smooth migration.

### 5.1 Define Clear URI Schemes

Use URI schemes that indicate domain boundaries:

```
issue://{project}/{issue_id}      # Full issue context
project://{project}/schema        # Project custom field definitions
logs://service/{date}             # Service logs for a specific date
```

Use URI templates (RFC 6570) for dynamic resources to avoid registering thousands of static entries.

### 5.2 Plan the Discovery Strategy

Decide how clients discover resources via `resources/list`:
- **Static resources:** Listed directly (e.g., schema files)
- **Dynamic resources:** URI templates that clients can expand

### 5.3 Determine Appropriate Granularity

**Chunking strategy:** Avoid exposing massive objects:

| Instead of... | Expose... |
|---------------|-----------|
| Entire project's issues | Individual issues via `issue://{project}/{id}` |
| Complete log history | Daily logs via `logs://service/{date}` |
| Full database | Per-entity resources |

### 5.4 Plan Metadata

Include metadata so clients can decide what to retrieve:

```python
@mcp.resource("issue://{project}/{issue_id}")
async def issue_resource(project: str, issue_id: str) -> Resource:
    content = await get_issue_full_text(project, issue_id)
    return Resource(
        uri=f"issue://{project}/{issue_id}",
        name=f"Issue {project}/{issue_id}",
        description="Full issue content including description, comments, and history",
        mime_type="text/plain",
        size_hint=len(content),  # Helps hosts budget context
        content=content
    )
```

---

## Step 6: Design Prompts—Workflows as Configuration

Prompts capture reusable, multi-step workflows that users trigger explicitly.

### 6.1 Identify Prompt-Worthy Workflows

Look for:
- Frequently repeated sequences
- Workflows requiring consistent phrasing
- Multi-step processes with clear entry points

From our Issue Tracker workflows:
- "Triage from logs" (workflow 2)
- "Summarize discussion" (workflow 4)

### 6.2 Specify Prompt Structure

For each prompt, define:

**Name and description:** Describe the workflow in user terms.

**Arguments:** List the parameters needed.

**Message sequence:** Provide templates for system and user messages.

```yaml
# prompts/triage_from_logs.yaml
name: triage_issue_from_logs
description: >
  Analyze logs for a service and decide whether to create a new issue
  or update an existing one. Guides the triage decision process.
arguments:
  - name: log_snippet
    description: The log content to analyze
    required: true
  - name: service
    description: The service name
    required: true
messages:
  system: |
    You are an SRE triage assistant. Your job is to:
    1. Analyze the provided logs for errors and anomalies
    2. Search for existing issues that might match
    3. Decide: create new issue OR update existing
    4. If creating, suggest project, priority, and initial description
    
    Prefer updating existing issues when logs match known patterns.
  user: |
    Service: {service}
    
    Logs:
    {log_snippet}
```

### 6.3 Store Prompts as Configuration

Keep prompts declarative and under version control:

- Store in YAML/JSON files, not hardcoded in Python
- Enable non-developers (product managers, prompt engineers) to update without redeploying
- Reference tools and resources implicitly in the message templates

### 6.4 Implement Phase-1 as Host-Side Prompts

In Phase 1, document prompt templates so users can implement them in their IDE or chat client. The template should be ready to migrate to MCP `prompts/list` and `prompts/get` in Phase 2.

---

## Step 7: Cross-Cutting Concerns—Security, Rate Limits, and Transport

Determine non-functional requirements early.

### 7.1 Security Model

**Identity and authorization:**
- Define which identity the server uses to call downstream systems
- Determine: per-user tokens vs service account
- Specify: which projects/actions per identity, read-only vs read-write

**Filesystem and scope control:**
- Implement "roots" to bound filesystem access
- Restrict high-risk tools (e.g., shell, arbitrary SQL) to require explicit user confirmation
- Filter tools and resources lists based on user permissions

**Credentials:**
- Never accept credentials as tool parameters
- Load from environment variables at startup
- For HTTP transports, OAuth 2.1 is mandatory (as of March 2025)
- Use non-predictable session identifiers
- Never echo secrets in tool results

### 7.2 Rate Limits

Set quotas per tool and per user:

```python
RATE_LIMITS = {
    "search_issues": {"calls": 100, "period_seconds": 60},
    "create_issue": {"calls": 10, "period_seconds": 60},
    "update_issue_status": {"calls": 30, "period_seconds": 60},
}
```

Implement backoff when downstream services fail.

### 7.3 Transport Selection

| If your users primarily use... | Choose... |
|-------------------------------|-----------|
| Claude Desktop, VS Code, Cursor, IDEs | STDIO |
| ChatGPT, web-based clients | HTTP/SSE (requires remote hosting) |
| Both | Implement STDIO first, add HTTP later |

**Critical STDIO rule:** Do not log to stdout when using STDIO. Log to stderr or files only.

### 7.4 Configuration Management

Externalize all configuration:
- API keys and endpoints
- Timeouts and retry settings
- Rate limits
- Allowed projects/resources

Validate configuration at startup—fail fast if required settings are missing.

```python
# config.py
class Settings(BaseSettings):
    issue_api_url: str
    issue_api_token: str
    timeout_seconds: float = 30.0
    
    def validate_startup(self):
        if not self.issue_api_url:
            raise ValueError("ISSUE_API_URL is required")
```

---

## Step 8: Implementation Plan—Scaffold Then Map Capabilities

Use official SDKs to generate a minimal server skeleton.

### 8.1 Choose Your SDK

**Python:** Use FastMCP 2.x for most servers. It provides decorators, transport runners, and testing helpers.

**TypeScript:** Use the official TypeScript SDK.

**Avoid:** Hand-rolling JSON-RPC implementations.

### 8.2 Implementation Order

Implement features in stages, testing after each addition:

```
Phase 1 Implementation Order:
┌─────────────────────────────────────────────────────────┐
│ 1. Healthcheck tool (trivial, validates setup)          │
├─────────────────────────────────────────────────────────┤
│ 2. Read-only tool (e.g., get_issue)                     │
├─────────────────────────────────────────────────────────┤
│ 3. Search/query tools (e.g., search_issues)             │
├─────────────────────────────────────────────────────────┤
│ 4. Mutating tools (e.g., create_issue, update_status)   │
├─────────────────────────────────────────────────────────┤
│ 5. Phase-1 fallback tools for Phase-2 features          │
└─────────────────────────────────────────────────────────┘

Phase 2 Implementation Order:
┌─────────────────────────────────────────────────────────┐
│ 6. Resources (resources/list, resources/read)           │
├─────────────────────────────────────────────────────────┤
│ 7. Prompts (prompts/list, prompts/get)                  │
├─────────────────────────────────────────────────────────┤
│ 8. Roots (if local filesystem access needed)            │
├─────────────────────────────────────────────────────────┤
│ 9. Deprecate/refactor Phase-1 fallback tools            │
└─────────────────────────────────────────────────────────┘
```

### 8.3 Validate After Each Addition

After each capability, run integration tests using MCP client/inspector:

```bash
# Test with MCP Inspector
uv run mcp dev mcp_issue_server/mcp/server.py

# Verify protocol lifecycle
- initialize handshake
- tools/list returns expected tools
- tools/call executes correctly
```

### 8.4 Project Structure

```
mcp-issue-server/
├── pyproject.toml
├── mcp_issue_server/
│   ├── __init__.py
│   ├── config.py              # Settings, env management
│   ├── domain/                # Pure business logic, NO MCP imports
│   │   ├── __init__.py
│   │   ├── issues.py
│   │   └── models.py
│   └── mcp/                   # MCP protocol adapters
│       ├── __init__.py
│       ├── server.py          # FastMCP bootstrap
│       ├── tools.py           # @mcp.tool definitions
│       ├── resources.py       # @mcp.resource (Phase 2)
│       └── prompts.py         # @mcp.prompt (Phase 2)
├── prompts/                   # Prompt configuration files
│   └── triage_from_logs.yaml
└── tests/
    ├── test_domain_issues.py
    ├── test_tools.py
    └── conftest.py
```

---

## Step 9: Testing Strategy—Unit, Integration, and LLM-in-the-Loop

Establish a layered testing approach.

### 9.1 Unit Tests

Test business logic functions in isolation:

```python
# tests/test_domain_issues.py
@pytest.mark.asyncio
async def test_search_issues_filters_by_status():
    results = await issue_service.search(project="CORE", status="open")
    assert all(issue.status == "open" for issue in results)

@pytest.mark.asyncio
async def test_search_issues_respects_max_results():
    results = await issue_service.search(project="CORE", max_results=5)
    assert len(results) <= 5
```

### 9.2 Protocol-Level Integration Tests

Bring up the server and send real MCP messages:

```python
# tests/test_tools.py
@pytest.fixture
async def mcp_client():
    async with Client(mcp) as client:
        yield client

@pytest.mark.asyncio
async def test_initialize_handshake(mcp_client):
    # Verify server responds to initialize
    info = await mcp_client.initialize()
    assert info.name == "IssueServer"

@pytest.mark.asyncio
async def test_tools_list_returns_expected_tools(mcp_client):
    tools = await mcp_client.list_tools()
    tool_names = {t.name for t in tools}
    assert "search_issues" in tool_names
    assert "create_issue" in tool_names

@pytest.mark.asyncio
async def test_search_issues_returns_valid_structure(mcp_client):
    result = await mcp_client.call_tool(
        "search_issues", 
        {"project": "CORE"}
    )
    assert "count" in result.data
    assert "data" in result.data
```

### 9.3 LLM-in-the-Loop Tests

Use a non-production model with fixed prompts to simulate real user interactions:

```python
@pytest.mark.asyncio
async def test_find_bugs_prompt_matches_search_tool(mcp_client):
    """Verify search_issues would be selected for 'Find my P1 bugs'."""
    tools = await mcp_client.list_tools()
    search_tool = next(t for t in tools if t.name == "search_issues")
    
    # Verify the description matches the intent
    desc_lower = search_tool.description.lower()
    assert any(word in desc_lower for word in ["find", "search", "filter"])
    
    # Verify the schema supports the needed parameters
    schema_str = str(search_tool.inputSchema)
    assert "assignee" in schema_str
    assert "priority" in schema_str
```

### 9.4 Negative/Chaos Tests

Test error handling for edge cases:

```python
@pytest.mark.asyncio
async def test_invalid_project_returns_actionable_error(mcp_client):
    result = await mcp_client.call_tool(
        "search_issues",
        {"project": "NONEXISTENT"}
    )
    assert result.data.get("error") is True
    assert "suggestion" in result.data

@pytest.mark.asyncio
async def test_handles_downstream_timeout(mcp_client):
    with mock_slow_downstream(timeout=60):
        result = await mcp_client.call_tool(
            "search_issues",
            {"project": "CORE"}
        )
        assert result.data.get("error") is True
        assert "timeout" in result.data.get("message", "").lower()
```

---

## Step 10: Observability and Iteration Loop

Deploy metrics and logging, then use insights to refine your design.

### 10.1 Logging Requirements

Log every tool call with:
- Tool name
- Inputs (sanitized—remove sensitive values)
- Duration
- Outcome (success/error)
- Error code if applicable
- JSON-RPC request ID for correlation

```python
import logging
import time

logger = logging.getLogger(__name__)

async def logged_tool_call(tool_name: str, inputs: dict, func):
    sanitized = {k: v for k, v in inputs.items() if k not in ["token", "secret"]}
    request_id = get_current_request_id()
    start = time.time()
    
    try:
        result = await func(**inputs)
        duration = time.time() - start
        logger.info(
            f"tool_call",
            extra={
                "tool": tool_name,
                "request_id": request_id,
                "status": "success",
                "duration_ms": int(duration * 1000),
                "input_keys": list(sanitized.keys()),
            }
        )
        return result
    except Exception as e:
        duration = time.time() - start
        logger.error(
            f"tool_call_error",
            extra={
                "tool": tool_name,
                "request_id": request_id,
                "status": "error",
                "duration_ms": int(duration * 1000),
                "error_type": type(e).__name__,
            }
        )
        raise
```

### 10.2 Metrics to Track

Per tool:
- Call count
- Error rate and error types
- P50/P95/P99 latency
- Payload sizes (input and output)
- Token consumption (if measurable)

### 10.3 Session Traces

Record how the model selects tools and what results are returned. This helps identify:
- Tools that are never selected (candidate for removal or description improvement)
- Tools that are frequently misused (adjust schema or description)
- Workflows that take too many calls (consolidate tools)

### 10.4 Iteration Process

Schedule regular reviews (weekly or monthly):

| Observation | Action |
|-------------|--------|
| Tool never used | Remove or improve description |
| Tool frequently errors | Fix bugs or improve validation |
| Tool called with wrong parameters | Improve description or schema |
| Users accomplish workflow in 5+ calls | Consolidate into fewer tools |
| Users request capability not available | Add to backlog, assign phase |

### 10.5 Tool Taxonomy for Scale

When tool counts grow, organize them into taxonomies so routing layers can select relevant subsets. Security auditing should verify that roots and capabilities remain within intended boundaries.

---

## Step 11: Quick Checklist

Use this checklist during implementation:

### Design Phase

- [ ] Listed 5-10 workflows with inputs, systems, and side effects
- [ ] Defined measurable success criteria per workflow
- [ ] Verified server has single responsibility (one-sentence test)
- [ ] Classified each capability as tool, resource, or prompt
- [ ] Assigned implementation phase (1/2/2+) to each capability
- [ ] Designed Phase-1 fallbacks for Phase-2 features
- [ ] For each tool: clear name, intent-based description, typed schema, structured output
- [ ] Defined resource URI schemes, templates, and chunking strategy
- [ ] Designed prompts with parameters and message templates (stored as config)
- [ ] Documented security model, rate limits, and transport choice
- [ ] Externalized all configuration

### Implementation Phase

- [ ] Scaffolded server using official SDK
- [ ] Implemented in order: healthcheck → read → search → write → resources → prompts
- [ ] Tested after each capability addition
- [ ] No logging to stdout (stderr only for STDIO transport)
- [ ] Configuration validated at startup

### Testing Phase

- [ ] Unit tests for domain logic
- [ ] Protocol-level integration tests (initialize, tools/list, tools/call)
- [ ] LLM-in-the-loop tests for tool selection
- [ ] Negative tests for timeouts, permissions, downstream failures

### Operations Phase

- [ ] Metrics instrumented per tool
- [ ] Structured logging with correlation IDs
- [ ] Scheduled regular reviews for tool refinement
- [ ] Security audit for roots and capability boundaries

---

## Summary: The Design Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 0: Set the Frame                                          │
│  • Articulate MCP server mission (not a REST gateway)           │
│  • Understand constraints: context limits, tool surface, security│
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Define Use-Cases & Success Criteria                    │
│  • List 5-10 workflows with inputs, systems, side effects       │
│  • Define measurable success criteria per workflow              │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: Decide Server Boundaries                               │
│  • Group by business capability, not microservices              │
│  • Apply one-sentence test: no "and also..."                    │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Enumerate & Classify Capabilities                      │
│  • Assign MCP type: Tool / Resource / Prompt                    │
│  • Assign phase: 1 / 2 / 2+                                     │
│  • Design Phase-1 fallbacks for Phase-2 features                │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4: Design Tools                                           │
│  • Naming: verb_noun in snake_case                              │
│  • Intent-based descriptions (when, not just what)              │
│  • Strong-typed input schemas with sensible defaults            │
│  • Structured outputs with next-step guidance                   │
│  • Error model: user/permission/system with actionable messages │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: Design Resources                                       │
│  • Define URI schemes with domain boundaries                    │
│  • Plan chunking: avoid massive objects                         │
│  • Include metadata (title, MIME type, size hints)              │
│  • Create Phase-1 fallback tools with resource_uri hints        │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 6: Design Prompts                                         │
│  • Identify multi-step workflows requiring consistency          │
│  • Define name, arguments, message templates                    │
│  • Store as YAML/JSON configuration under version control       │
│  • Implement Phase-1 as host-side prompts                       │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 7: Cross-Cutting Concerns                                 │
│  • Security: identity, roots, credential management             │
│  • Rate limits: per-tool and per-user quotas                    │
│  • Transport: STDIO vs HTTP based on client needs               │
│  • Configuration: externalize everything, validate at startup   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 8: Implementation Plan                                    │
│  • Use official SDK (FastMCP for Python)                        │
│  • Order: healthcheck → read → search → write → resources       │
│  • Test after each capability addition                          │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 9: Testing Strategy                                       │
│  • Unit tests for domain logic                                  │
│  • Protocol integration tests via MCP client                    │
│  • LLM-in-the-loop tests (prompt → tool selection)              │
│  • Negative tests for error handling                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 10: Observability & Iteration                             │
│  • Log every call: tool, duration, outcome, request ID          │
│  • Track metrics: call count, error rate, latency               │
│  • Record session traces for tool selection analysis            │
│  • Regular reviews: prune unused, refine misused tools          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Conclusion

This procedure emphasizes single-responsibility server design, careful mapping of domain tasks into tools, resources, and prompts, and rigorous schema and operational practices. Following these steps will help ensure that your MCP servers are secure, efficient, and tailored to the needs of LLM-driven applications.

The key principles are:

1. **Step 0 is foundational:** MCP is not REST. Design for LLM ergonomics.
2. **Workflows drive design:** Start from user tasks, not API endpoints.
3. **Single responsibility:** One bounded context per server.
4. **Intent-based descriptions:** Explain *when* to use each tool.
5. **Phased implementation:** Tools first, then Resources/Prompts.
6. **Incremental validation:** Test after every capability addition.
7. **Continuous iteration:** Use observability to refine the tool surface.

By applying this systematic approach, engineering teams can build MCP servers that are secure, efficient, and genuinely useful for LLM-driven applications.
