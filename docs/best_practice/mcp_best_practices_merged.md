# MCP Protocol: Best Practices and Implementation Guidance

This document synthesizes recommended patterns for structuring MCP servers, drawing from official MCP documentation, production experience from organizations like Block (60+ servers) and PagerDuty, The New Stack's production best practices, and community wisdom. It provides both protocol-level design guidance and implementation best practices, organized to help architects and engineers build secure, scalable, and maintainable MCP servers.

---

## Part A: Protocol-Level Design

### A1. Understanding MCP's Role: What It Is and Isn't

Before designing any endpoint, articulate the mission of your MCP server. MCP is the bridge between the model and your domain—it is not a generic API gateway or another REST façade. MCP is a standardized way to expose tools, context data, and structured workflows to conversational agents via JSON-RPC 2.0.

The key constraints that shape MCP design are fundamentally different from traditional API design:

**Context windows are limited and expensive.** Models cannot process unlimited data, and every token has a cost. Unlike REST clients that can paginate through thousands of results, LLMs need focused, relevant information.

**Models struggle with huge, noisy tool surfaces.** When presented with dozens of similar-sounding tools, models make poor choices. Block's experience with 60+ MCP servers confirms that fewer well-designed tools dramatically outperform comprehensive coverage.

**Security blast radius must be tightly controlled.** MCP servers often run with the same privileges as the host application. A poorly scoped server can expose far more than intended.

**The cardinal mistake:** If you merely mirror existing services, you will end up with a bloated and confusing tool surface, causing poor model performance. Design for LLM ergonomics, not human API consumers.

### A2. Server Scope and Single Responsibility

Each MCP server should model a specific domain. Don't build a monolithic server that wraps every microservice; instead, treat each server as a bounded context.

**The one-sentence test:** Can you describe your server's purpose in one sentence without saying "and also..."? If not, you're mixing concerns and should split into multiple servers.

**Good examples:**
- "This server manages issue lifecycle: searching, creating, updating, and reading issues."
- "This server provides filesystem operations within a bounded directory tree."
- "This server handles calendar events and availability queries."

**Bad examples:**
- "This server manages issues and also handles Git operations and also analyzes logs..."

Cohesive, uniquely named tools with JSON Schema'd inputs and outputs make it easier for clients and models to disambiguate actions. Group workflows by business capability rather than existing microservices.

### A3. The Three Primitives: Tools, Resources, and Prompts

MCP provides three fundamental primitives with distinct control models. Understanding when to use each is critical for effective server design.

#### A3.1 Tools: Model-Controlled Actions

Tools are executable functions that allow models to interact with external systems autonomously. The model discovers them through `tools/list` and invokes them via `tools/call`.

**Characteristics:**
- Model-controlled: The LLM decides when to invoke based on conversation context
- Used for operations with side effects or non-trivial computation
- Each tool should be uniquely identified with a JSON Schema
- Should be idempotent and return deterministic results for the same input
- Clients may retry requests or parallelize them

**When to use tools:**
- Querying databases or external APIs
- Creating, updating, or deleting records
- Executing calculations or transformations
- Any operation that performs an action

**Example tools for Issue Tracker:**
- `search_issues` – Find issues matching criteria
- `create_issue` – Create a new issue
- `update_issue_status` – Change issue state
- `get_issue` – Retrieve issue details

#### A3.2 Resources: Application-Controlled Context

Resources expose read-only data for context. The MCP documentation explains that resources allow servers to expose data that can be read by clients and used as context for LLM interactions.

**Characteristics:**
- Application-controlled: The client (not the model) decides when and what to fetch
- Represent persistent data: files, database records, API responses, schemas
- Each resource has a unique URI
- No side effects—ideal for retrieving context without executing operations
- Use RFC 6570 URI templates for dynamic sets of data

**When to use resources:**
- File contents that models need as reference
- Database schemas or API documentation
- Configuration data or project metadata
- Large context documents for analysis

**Example resources for Issue Tracker:**
- `issue://{project}/{id}` – Full issue content including comments
- `project://{project}/schema` – Custom field definitions
- `logs://service/{date}` – Service logs for a specific date

#### A3.3 Prompts: User-Controlled Templates

Prompts are reusable instruction templates that users trigger explicitly. The server exposes prompts via `prompts/list`, but clients (and ultimately users) explicitly choose when to invoke them.

**Characteristics:**
- User-controlled: Never invoked automatically by the model
- Standardize workflows and enforce consistent instructions
- Can reference tools and resources
- Versionable and centrally managed
- Retrieved via `prompts/get` with arguments

**When to use prompts:**
- Multi-step workflows requiring consistent phrasing
- Slash-command style interfaces
- Guided processes like triage or code review
- Any workflow the user should explicitly select

**Example prompts for Issue Tracker:**
- `triage_issue_from_logs` – Analyze logs and create/update appropriate issue
- `summarize_issue_thread` – Summarize discussion and recommend next steps

#### A3.4 Decision Framework: Which Primitive to Choose

| If the capability... | Use... | Because... |
|---------------------|--------|------------|
| Performs an action or returns dynamic results | **Tool** | Model decides when to invoke |
| Provides static or semi-static reference data | **Resource** | Application controls context loading |
| Is a reusable multi-step workflow template | **Prompt** | User explicitly selects it |

**Critical warning:** Do not expose thousands of operations as tools. The model must parse all of them, leading to poor selection. Instead, list options as resources and let the client choose, or consolidate related operations into fewer well-designed tools.

### A4. Endpoint Design: Naming, Schemas, and Boundaries

#### A4.1 Tool Naming Conventions

Name tools after user tasks, not implementation details:

- **Pattern:** `verb_noun` in snake_case
- **Examples:** `search_issues`, `create_event`, `update_status`
- **Avoid:** Generic names like `execute`, `run`, `process`
- **Avoid:** Implementation details like `call_jira_api`

#### A4.2 Intent-Based Descriptions

The most critical aspect of tool design is the description. It must explain *when* to use the tool, not just *what* it does:

```
❌ Functional (what it does):
"Retrieves issues from the database."

✅ Intent-based (when to use it):
"Search issues by project, optionally filtering by assignee, status, and priority.
Use when the user wants to find issues matching specific criteria, check what's
assigned to them, or explore issues in a project. Returns a list with key metadata."
```

Descriptions should:
- Explicitly state when to call the tool
- Describe what it returns
- Reference only one domain
- Clearly mention side effects

#### A4.3 Input Schema Design

Use JSON Schema with strong typing, enums, and pattern constraints:

```python
@mcp.tool()
async def search_issues(
    project: str,                                                    # Required
    assignee: str | None = None,                                    # Optional filter
    status: Literal["open", "in_progress", "resolved", "closed"] | None = None,
    priority: Literal["P1", "P2", "P3", "P4"] | None = None,
    max_results: int = 50,                                          # Sensible default
) -> dict:
    """..."""
```

**Principles:**
- Required parameters first, optional with defaults
- Use enums for constrained values
- Clear field names (`assignee` not `a`)
- Document units, formats, and constraints

#### A4.4 Output Design

Return structured JSON containing just the data the model needs:

- Avoid raw upstream responses
- Include metadata that helps the model decide next steps
- Keep responses token-conscious
- For large outputs, return handles/URIs rather than inlining megabytes of data

```python
# ✅ Good: Structured, focused output
return {
    "count": len(issues),
    "data": [{"id": i.id, "title": i.title, "status": i.status} for i in issues],
    "has_more": total > len(issues),
    "suggestion": "Use get_issue for full details on a specific issue."
}

# ❌ Bad: Raw upstream dump
return upstream_api_response.json()
```

#### A4.5 Resource URI Design

Use clear URI schemes that indicate domain boundaries:

- `file:///path/to/file`
- `git://repo/branch/path`
- `logs://service/env/date`
- `issue://{project}/{id}`

Define resource templates (RFC 6570) for dynamic datasets to avoid registering thousands of static resources. Include metadata (title, description, MIME type, size hints) so clients can decide what to retrieve.

### A5. Transport, Lifecycle, and Protocol Behaviour

MCP runs over JSON-RPC 2.0 and supports multiple transports:

**STDIO:** Maximum compatibility for local tools, Claude Desktop, VS Code, Cursor, most IDEs. Use this as your primary transport.

**Streamable HTTP:** For networked scalability, streaming results, or when clients cannot run local processes. Required for ChatGPT (which cannot connect to localhost).

**Key protocol behaviours:**

- Tools should be **stateless and idempotent**: Clients may retry requests or parallelize them
- Implement **cancellation and timeouts** to prevent long-running calls from consuming resources
- Support the **standard lifecycle**: `initialize`, `tools/list`, `resources/list`, `tools/call`

**Critical STDIO rule:** Only protocol messages should go to stdout. Send all logs to stderr or files to avoid corrupting the JSON-RPC stream. This is the most common cause of silent failures.

### A6. Security, Roots, and Isolation

Security must be a first-class concern. The MCP specification mandates specific protections.

**Authentication and Authorization:**
- OAuth 2.1 is mandatory for HTTP-based transports (as of March 2025)
- Session identifiers must be non-predictable
- Token passthrough is explicitly forbidden
- Restrict tools and resources lists based on user permissions

**Filesystem and Scope Control:**
- Use "roots" to bound filesystem access and limit each server's blast radius
- Tools executing shell or file operations require explicit user confirmation
- Never echo secrets in tool results or elicitation messages

**Rate Limiting:**
- Set quotas per tool (e.g., `create_issue` max 10/min/user)
- Implement backoff when downstream services fail
- Track and surface rate limits to clients

**Error Handling:**
- Classify errors: user errors (invalid parameters), system errors (downstream failures), permission errors
- Error messages should tell the model what to do next
- Implement circuit breakers to avoid cascading failures

### A7. Multi-Server Orchestration

The power of MCP emerges when multiple servers coordinate. Each server remains domain-focused, while the host application orchestrates cross-server workflows.

**Example: Planning a company offsite**
- Conference server: Books venues and catering
- Travel server: Handles flights and hotels
- Calendar/email server: Sends invitations and manages schedules

Each server exposes its own tools, resources, and prompts. The model (or host application) combines them to accomplish complex workflows that span multiple domains.

**Design principle:** Keep servers domain-focused. Don't bundle unrelated capabilities to "save containers." Different domain servers should be separate deployable units.

### A8. Versioning and Capability Negotiation

Version your server and its surface area:

- Advertise supported capabilities (tools, resources, prompts, elicitation, structured output) during initialization so clients can adapt
- Use semantic versioning for server and tool changes
- Maintain backward compatibility when possible
- Document breaking changes clearly

### A9. Instrumentation and Observability

Treat MCP servers like any production microservice:

- Emit structured logs with correlation IDs (JSON-RPC request ID)
- Record latency, success/failure, and payload sizes per tool
- Track token costs and context window usage
- Surface rate limits to clients
- Expose health checks and metrics per tool

**Metrics to track:**
- Call count per tool
- Error rate and error types
- P50/P95/P99 latency
- Payload sizes (input and output)
- Token consumption

---

## Part B: Implementation Best Practices

### B1. Use Official SDKs

Avoid hand-rolling the protocol. Use official SDKs (Python FastMCP, TypeScript SDK) that implement the JSON-RPC lifecycle and transports.

**Python recommendation:** Use FastMCP 2.x for most servers. It provides decorators (`@mcp.tool`, `@mcp.resource`, `@mcp.prompt`), HTTP/stdio runners, composition, and testing helpers. Drop to the official SDK only when you need custom clients or very fine-grained control.

```python
from fastmcp import FastMCP

mcp = FastMCP("IssueServer")

@mcp.tool()
async def search_issues(project: str, status: str | None = None) -> dict:
    """Search issues by project, optionally filtering by status.
    
    Use when the user wants to find issues in a project or check
    what's currently open/in-progress.
    """
    results = await issue_service.search(project, status)
    return {"count": len(results), "data": results}
```

### B2. Project Structure and Layering

Separate business logic from MCP protocol adapters:

```
mcp-issue-server/
├── pyproject.toml
├── mcp_issue_server/
│   ├── __init__.py
│   ├── config.py              # Settings, env management
│   ├── domain/                # Pure business logic, NO MCP imports
│   │   ├── __init__.py
│   │   ├── issues.py          # Issue operations
│   │   └── models.py          # Domain models (Pydantic/dataclass)
│   └── mcp/                   # MCP protocol adapters
│       ├── __init__.py
│       ├── server.py          # FastMCP bootstrap
│       ├── tools.py           # @mcp.tool definitions
│       ├── resources.py       # @mcp.resource (Phase 2)
│       └── prompts.py         # @mcp.prompt (Phase 2)
└── tests/
    ├── test_domain_issues.py  # Unit tests (pure logic)
    ├── test_tools.py          # Tool integration tests
    └── conftest.py            # Pytest fixtures
```

**Principles:**
- `domain/` contains pure business logic with no MCP dependencies
- `mcp/` contains thin adapters: MCP calls → domain functions
- `config.py` centralizes configuration (env vars, secrets, endpoints)

### B3. Logging and Transport Discipline

For STDIO transports:
- Only protocol messages go to stdout
- Logs go to stderr or files
- Use structured logging with JSON-RPC request ID for traceability

```python
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # CRITICAL: Never stdout for STDIO transport
)
```

For Streamable HTTP:
- Stream incremental chunks for long operations
- Advertise total counts when possible
- Support cancellation for long-running requests

### B4. Tool Implementation Patterns

Design tools around user tasks, not raw API endpoints:

```python
@mcp.tool()
async def search_issues(
    project: str,
    assignee: str | None = None,
    status: str | None = None,
    max_results: int = 50
) -> dict:
    """
    Search issues by project with optional filters.
    
    Use when the user wants to:
    - Find issues matching specific criteria
    - Check what's assigned to them
    - Explore issues in a project
    
    Returns a list of issues with key metadata.
    """
    # Validate inputs
    if max_results > 100:
        return {
            "error": True,
            "message": "max_results cannot exceed 100",
            "suggestion": "Use pagination or narrow your search criteria."
        }
    
    # Call domain logic (separated from MCP layer)
    issues = await issue_service.search(
        project=project,
        assignee=assignee,
        status=status,
        limit=max_results
    )
    
    return {
        "count": len(issues),
        "data": [issue.to_summary_dict() for issue in issues],
        "has_more": issue_service.total_count > len(issues)
    }
```

**Key principles:**
- Idempotent design and deterministic outputs
- Prefer basic types, enums, and clear field names
- Return structured JSON, not raw upstream responses
- Avoid loosely related optional parameters; break large operations into multiple tools

### B5. Resource Implementation Patterns

Use well-structured URI schemes and templates:

```python
@mcp.resource("issue://{project}/{issue_id}")
async def issue_resource(project: str, issue_id: str) -> str:
    """
    Full issue content including description, comments, and history.
    Use as context for analysis, summarization, or understanding discussions.
    """
    return await issue_service.get_full_text(project, issue_id)

@mcp.resource("project://{project}/schema")
async def project_schema_resource(project: str) -> str:
    """
    Project's custom field definitions and workflow states.
    Use as context when creating or updating issues.
    """
    return await project_service.get_schema(project)
```

**Chunking strategy:** Avoid exposing massive objects. Split logs, tables, or file systems into manageable, logically grouped resources:
- Per file, not entire directory trees
- Per day of logs, not complete history
- Per entity, not entire databases

Specify MIME types to allow clients to handle content correctly.

### B6. Prompts as Configuration

Keep prompts declarative—define name, description, arguments, and message templates in configuration files rather than code:

```yaml
# prompts/triage_from_logs.yaml
name: triage_issue_from_logs
description: Analyze logs for a service and decide whether to create a new issue or update an existing one.
arguments:
  - name: log_snippet
    description: The log content to analyze
    required: true
  - name: service
    description: The service name
    required: true
messages:
  system: |
    You are an SRE triage assistant.
    Prefer updating existing issues when logs match known patterns.
  user: |
    Service: {service}
    
    Logs:
    {log_snippet}
```

Store prompts under version control so non-developers (product managers, prompt engineers) can update them without redeploying the server.

```python
@mcp.prompt()
def triage_issue_from_logs(log_snippet: str, service: str) -> Prompt:
    """Analyze logs and decide whether to create or update an issue."""
    config = load_prompt_config("triage_from_logs.yaml")
    return Prompt(
        system=config["messages"]["system"],
        user=config["messages"]["user"].format(
            service=service,
            log_snippet=log_snippet
        )
    )
```

### B7. Error Handling and Failure Modes

Return structured errors with codes, messages, and actionable guidance:

```python
# Error classification
class ErrorType:
    USER_ERROR = "user_error"           # Invalid parameters
    PERMISSION_ERROR = "permission"     # Access denied
    SYSTEM_ERROR = "system_error"       # Downstream failure
    NOT_FOUND = "not_found"             # Resource doesn't exist

async def handle_tool_call(func, **kwargs):
    try:
        return await func(**kwargs)
    except ValidationError as e:
        return {
            "error": True,
            "type": ErrorType.USER_ERROR,
            "message": str(e),
            "suggestion": "Check the parameter format and try again."
        }
    except PermissionDenied as e:
        return {
            "error": True,
            "type": ErrorType.PERMISSION_ERROR,
            "message": f"Access denied: {e}",
            "suggestion": "Verify your permissions for this resource."
        }
    except DownstreamTimeout as e:
        return {
            "error": True,
            "type": ErrorType.SYSTEM_ERROR,
            "message": f"Downstream service timed out: {e}",
            "suggestion": "Try again in a few moments."
        }
```

**Implement resilience patterns:**
- Circuit breakers to prevent cascading failures
- Timeouts on all external calls
- Retry with exponential backoff for transient failures

### B8. Performance, Pagination, and Context Efficiency

**Pagination:** Keep responses small and predictable. Never return unbounded result sets.

```python
@mcp.tool()
async def search_issues(project: str, page: int = 1, page_size: int = 20) -> dict:
    """Search issues with pagination."""
    results, total = await issue_service.search_paginated(
        project, page, page_size
    )
    return {
        "data": results,
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": page * page_size < total
    }
```

**Caching:** Cache frequently requested read-only data and expensive external calls.

**Large outputs:** Return handles or URIs rather than inlining megabytes of data:

```python
# ❌ Bad: Inlining large content
return {"content": massive_file_content}  # Could be megabytes

# ✅ Good: Return a reference
return {
    "resource_uri": f"file://{file_path}",
    "size_bytes": file_size,
    "suggestion": "Fetch the resource URI if you need the full content."
}
```

**Token budget management:** One server returned 360,000 characters—the agent became "thoroughly stumped." Set hard limits (e.g., 400KB) and return errors with recovery guidance when exceeded.

### B9. Testing Strategy

Apply multi-layer testing:

**Unit tests:** Test business logic functions in isolation:

```python
@pytest.mark.asyncio
async def test_search_issues_filters_by_status():
    results = await issue_service.search(project="CORE", status="open")
    assert all(issue.status == "open" for issue in results)
```

**Protocol integration tests:** Bring up the server and send real MCP messages:

```python
@pytest.mark.asyncio
async def test_tools_list_returns_expected_tools(mcp_client):
    tools = await mcp_client.list_tools()
    tool_names = {t.name for t in tools}
    assert "search_issues" in tool_names
    assert "create_issue" in tool_names
```

**LLM-in-the-loop tests:** Use a non-production model with fixed prompts to verify tool selection:

```python
@pytest.mark.asyncio
async def test_find_bugs_prompt_selects_search_tool():
    """Verify search_issues would be selected for 'Find my P1 bugs'."""
    tools = await mcp_client.list_tools()
    search_tool = next(t for t in tools if t.name == "search_issues")
    
    # Verify description matches the intent
    assert "find" in search_tool.description.lower()
    assert "assignee" in str(search_tool.inputSchema)
```

**Negative/chaos tests:** Test timeouts, permission denials, and downstream failures:

```python
@pytest.mark.asyncio
async def test_handles_downstream_timeout_gracefully(mcp_client):
    # Simulate slow downstream
    with mock_slow_downstream(timeout=30):
        result = await mcp_client.call_tool("search_issues", {"project": "CORE"})
        assert result.data.get("error") is True
        assert "timeout" in result.data.get("message", "").lower()
```

### B10. Deployment and Configuration Management

**Externalize configuration:** Transport settings, upstream API endpoints, rate limits, and timeouts should not be hard-coded:

```python
# config.py
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    issue_api_url: str
    issue_api_token: str
    rate_limit_per_minute: int = 100
    timeout_seconds: float = 30.0
    allowed_projects: list[str] = []
    
    class Config:
        env_file = ".env"
    
    def validate_startup(self):
        if not self.issue_api_url:
            raise ValueError("ISSUE_API_URL is required")
        if not self.issue_api_token:
            raise ValueError("ISSUE_API_TOKEN is required")
```

**Containerization:**
- Publish minimal runtime images
- Include a README with tool catalog, schemas, and security notes
- Keep different domain servers in separate deployable units

**Package distribution:**

```toml
# pyproject.toml
[project]
name = "mcp-issue-server"
version = "0.1.0"

[project.scripts]
mcp-issue-server = "mcp_issue_server.mcp.server:main"
```

---

## Part C: Client Ecosystem and Market Reality

Understanding which clients support which features helps prioritize implementation.

### C1. Client Support Tiers

**Tier 1: Full-stack MCP clients** (almost entire spec)
- VS Code + GitHub Copilot, Claude Code, advanced agent frameworks
- Support: Tools ✅, Resources ✅, Prompts ✅, Roots ✅, advanced options

**Tier 2: Rich MCP clients** (Tools + Resources + Prompts)
- Claude.ai/Claude Desktop, Continue, Microsoft Copilot Studio
- Can fully exploit Resources and Prompts

**Tier 3: Tools-only clients** (the majority)
- ChatGPT, Mistral Le Chat, many multi-model chat UIs
- Treat MCP primarily as a tool-extension protocol

**Tier 4: Experimental/SDK-level**
- Gemini API, some CLIs
- Often Tools-only, sometimes labeled "experimental"

### C2. Implementation Strategy Based on Client Support

**Phase 1 (Portable MCP Core):** Tools + base protocol + security. Works in almost every client.

**Phase 2 (Rich MCP):** Resources + Prompts + Roots, for richer hosts.

**Phase 3 (Scale & Governance):** Registries, sampling tuning, large-scale policy.

**Phase-1 fallback pattern:** For each Phase-2 Resource, provide a Phase-1 Tool that returns the same content with a `resource_uri` hint:

```python
@mcp.tool()
async def get_issue_full_text(project: str, issue_id: str) -> dict:
    """Get complete issue content (Phase-1 fallback for issue:// resource)."""
    content = await issue_service.get_full_text(project, issue_id)
    return {
        "content": content,
        "resource_uri": f"issue://{project}/{issue_id}",
        "note": "In clients supporting Resources, use the URI directly."
    }
```

### C3. Transport Compatibility

| Client | STDIO | SSE | HTTP | Remote Required |
|--------|-------|-----|------|-----------------|
| Claude Desktop | ✅ | ✅ | ⚠️ | No |
| VS Code/Copilot | ✅ | ✅ | ✅ | No |
| Cursor | ✅ | ✅ | ✅ | No |
| ChatGPT | ❌ | ✅ | ✅ | **Yes** |
| Windsurf | ✅ | ✅ | ✅ | No |

**Recommendation:** Start with STDIO for maximum compatibility, add HTTP when needed for ChatGPT or enterprise remote access.

---

## Part D: Feature Priority Matrix

| Feature | Spec Role | Client Support | Business Value | Phase |
|---------|-----------|----------------|----------------|-------|
| **Tools** | Model-controlled actions | Universal | Core functionality | P0 – Phase 1 |
| **Base protocol** | JSON-RPC lifecycle | Universal | Foundation | P0 – Phase 1 |
| **Security & auth** | Protection | Your responsibility | Risk control | P0 – Phase 1 |
| **Structured errors** | Recovery guidance | Universal | Agent reliability | P0 – Phase 1 |
| **Resources** | Application-controlled context | Rich/IDE clients | RAG, context reuse | P1 – Phase 2 |
| **Prompts** | User-controlled templates | Rich/IDE/desktop | Workflow standardization | P1 – Phase 2 |
| **Roots** | Filesystem scope | Desktop/IDE | Local FS access | P1 – Phase 2 |
| **HTTP transport** | Remote access | ChatGPT, enterprise | Broader reach | P1 – Phase 2 |
| **Versioning** | Capability negotiation | All clients | Evolution | P2 |
| **Multi-server orchestration** | Cross-domain workflows | Host-dependent | Complex workflows | P2 |
| **Discovery/Registry** | Server discovery | Emerging | Large org governance | P3 |
| **Sampling/Elicitation** | Advanced orchestration | Limited | Complex setups | P3 |

---

## Part E: Common Pitfalls and Solutions

**Mirroring REST APIs:** Creates bloated, confusing tool surfaces. Design for user workflows instead.

**Exposing thousands of tools:** Models struggle to select correctly. Consolidate into 20-25 well-designed tools, use resources for reference data.

**Vague descriptions:** "Gets data" doesn't help the model. Explain *when* to use each tool.

**Dumping raw responses:** Even 200K context limits get overwhelmed. Return focused summaries.

**Silent failures:** Empty error responses cause agents to abandon strategies. Return actionable errors.

**Logging to stdout:** Corrupts JSON-RPC in STDIO transport. Log to stderr only.

**Missing timeouts:** Long-running calls hang conversations. Implement circuit breakers.

**Hardcoded configuration:** Makes deployment inflexible. Externalize everything.

**Monolithic servers:** Mixing domains confuses models. One bounded context per server.

---

## Conclusion

MCP has become the universal protocol for connecting language-model agents with enterprise systems. By thoughtfully designing servers around bounded domains, choosing the correct primitive for each operation, and adhering to the practices above, teams can build secure, scalable, and maintainable MCP servers.

The key principles are:

1. **MCP is not REST:** Design for LLM ergonomics, not human API consumers
2. **Single responsibility:** One bounded context per server
3. **Choose primitives wisely:** Tools for actions, Resources for context, Prompts for workflows
4. **Intent-based descriptions:** Explain *when* to use each tool
5. **Actionable errors:** Help the model recover from failures
6. **Security first:** Rate limits, roots, OAuth for HTTP
7. **Phased implementation:** Tools first for universal support, then Resources/Prompts
8. **Observability:** Instrument like any production service

These practices are not mere suggestions—they are necessary disciplines for production-grade AI integration.
