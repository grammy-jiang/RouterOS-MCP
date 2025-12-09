# Testing, Validation, Sandbox Strategy & Safety Nets

## Purpose

Outline the test-driven development strategy, testing layers, sandbox environments, and safety mechanisms to ensure correct and safe behavior of RouterOS operations. This document defines how we build confidence in changes before they reach production through rigorous testing practices.

**Test-Driven Development (TDD) is the primary development methodology for this project.** All features, bug fixes, and changes should follow TDD principles to ensure correctness, maintainability, and regression prevention.

---

## Test-Driven Development (TDD) Principles

### Why TDD for RouterOS MCP

**TDD is critical for this project because:**

1. **Safety**: RouterOS operations can affect production networks - bugs can cause outages
2. **Complexity**: Multi-device workflows, async operations, and state management are error-prone
3. **Confidence**: Tests provide confidence that changes won't break existing functionality
4. **Documentation**: Tests serve as executable documentation of expected behavior
5. **Refactoring**: Comprehensive tests enable safe refactoring and optimization
6. **Security**: Authorization logic must be proven correct through tests

### The TDD Cycle (Red-Green-Refactor)

**TDD follows a strict development cycle:**

```
1. RED: Write a failing test
   ├─ Define expected behavior
   ├─ Write test before implementation
   └─ Run test - it must fail

2. GREEN: Write minimal code to pass
   ├─ Implement just enough to pass the test
   ├─ Don't add extra features
   └─ Run test - it must pass

3. REFACTOR: Improve code quality
   ├─ Clean up implementation
   ├─ Eliminate duplication
   ├─ Improve naming and structure
   └─ Run test - it must still pass

4. REPEAT: Move to next feature
```

**Example TDD Workflow:**

```python
# Step 1: RED - Write failing test
def test_device_registration_validates_environment():
    """Device registration should reject invalid environment values."""
    device_service = DeviceService()

    with pytest.raises(ValidationError, match="environment must be one of"):
        await device_service.register_device(
            name="test-device",
            management_address="192.168.1.1:443",
            environment="invalid",  # Invalid environment
            credentials={"username": "admin", "password": "test"}
        )

# Step 2: GREEN - Implement minimal code
class DeviceService:
    VALID_ENVIRONMENTS = ["lab", "staging", "prod"]

    async def register_device(self, name: str, management_address: str,
                            environment: str, credentials: dict) -> Device:
        if environment not in self.VALID_ENVIRONMENTS:
            raise ValidationError(
                f"environment must be one of {self.VALID_ENVIRONMENTS}"
            )
        # ... rest of implementation

# Step 3: REFACTOR - Improve code
class Environment(str, Enum):
    """Valid deployment environments."""
    LAB = "lab"
    STAGING = "staging"
    PROD = "prod"

class DeviceService:
    async def register_device(self, name: str, management_address: str,
                            environment: Environment, credentials: dict) -> Device:
        # Validation now handled by Pydantic/type system
        # ... implementation
```

### TDD Best Practices for this Project

**1. Test-First Development**

```python
# ❌ WRONG: Implementation-first
def system_get_overview(device_id: str) -> dict:
    # Write implementation first
    device = get_device(device_id)
    return fetch_system_resource(device)

# ✅ CORRECT: Test-first
# FIRST: Write test
@pytest.mark.asyncio
async def test_system_get_overview_returns_complete_metrics():
    """System overview should return all required metrics."""
    service = SystemService(mock_routeros_client)

    result = await service.get_overview("dev-001")

    assert result["routeros_version"] is not None
    assert result["cpu_usage_percent"] >= 0
    assert result["memory_total_bytes"] > 0
    assert result["uptime_seconds"] >= 0

# THEN: Implement to pass test
async def get_overview(device_id: str) -> dict:
    # Implementation follows test expectations
    ...
```

**2. Test Behavior, Not Implementation**

```python
# ❌ WRONG: Testing implementation details
async def test_device_service_calls_rest_client_get_method():
    """Don't test that specific methods are called."""
    mock_client = Mock()
    service = DeviceService(mock_client)

    await service.get_device("dev-001")

    # This is brittle - breaks if we change internal implementation
    mock_client.get.assert_called_once()

# ✅ CORRECT: Testing behavior
async def test_get_device_returns_device_with_correct_id():
    """Test what the method does, not how."""
    service = DeviceService(mock_client_that_returns_device_data)

    device = await service.get_device("dev-001")

    # Test observable behavior
    assert device.id == "dev-001"
    assert device.status in ["healthy", "degraded", "unreachable"]
```

**3. One Assert Per Test (Guideline)**

```python
# ❌ AVOID: Multiple unrelated assertions
async def test_device_operations():
    device = await device_service.register_device(...)
    assert device.id is not None  # Testing registration

    updated = await device_service.update_status(device.id, "degraded")
    assert updated.status == "degraded"  # Testing update

    deleted = await device_service.delete_device(device.id)
    assert deleted is True  # Testing deletion

# ✅ BETTER: Focused tests
async def test_register_device_generates_id():
    device = await device_service.register_device(...)
    assert device.id is not None

async def test_update_device_status_changes_status():
    device = await create_test_device()
    updated = await device_service.update_status(device.id, "degraded")
    assert updated.status == "degraded"

async def test_delete_device_removes_device():
    device = await create_test_device()
    await device_service.delete_device(device.id)
    with pytest.raises(DeviceNotFoundError):
        await device_service.get_device(device.id)
```

**4. Test Edge Cases and Error Paths**

```python
# ✅ Test normal path
async def test_health_check_succeeds_for_reachable_device():
    health = await health_service.check_device("dev-001")
    assert health.status == "healthy"

# ✅ Test error path
async def test_health_check_marks_unreachable_device_as_error():
    mock_client.side_effect = DeviceUnreachableError()

    health = await health_service.check_device("dev-001")
    assert health.status == "error"

# ✅ Test edge case
async def test_health_check_handles_timeout():
    mock_client.side_effect = TimeoutError()

    health = await health_service.check_device("dev-001")
    assert health.status == "error"
    assert "timeout" in health.error_message.lower()

# ✅ Test boundary condition
async def test_health_check_cpu_at_critical_threshold():
    mock_client.return_value = {"cpu-load": 95}  # Exactly at threshold

    health = await health_service.check_device("dev-001")
    assert health.status == "critical"
```

**5. Use Descriptive Test Names**

```python
# ❌ WRONG: Vague test names
def test_device_1():
    ...

def test_validation():
    ...

# ✅ CORRECT: Descriptive names following pattern:
# test_<function>_<scenario>_<expected_result>

def test_register_device_with_invalid_environment_raises_validation_error():
    ...

def test_get_device_when_device_not_found_raises_not_found_error():
    ...

def test_update_identity_when_device_unreachable_returns_error_status():
    ...
```

### TDD for Different Code Layers

**Unit Tests (Domain Logic)**

```python
# Domain logic - pure functions, no external dependencies
def test_assess_health_returns_critical_when_cpu_exceeds_threshold():
    """Health assessment should mark device critical at 95% CPU."""
    resource = SystemResource(
        cpu_usage_percent=96.0,
        memory_usage_percent=50.0,
        uptime_seconds=3600
    )
    thresholds = HealthThresholds(CPU_CRITICAL_PERCENT=95.0)

    status = assess_health(resource, thresholds)

    assert status == HealthStatus.CRITICAL
```

**Integration Tests (Service Layer)**

```python
# Integration tests - multiple components working together
@pytest.mark.asyncio
async def test_device_registration_creates_device_and_credentials():
    """Registering a device should create both device and credential records."""
    # Arrange
    device_service = DeviceService(
        device_repo=InMemoryDeviceRepository(),
        credential_repo=InMemoryCredentialRepository(),
        encryption_service=EncryptionService(test_key)
    )

    # Act
    device = await device_service.register_device(
        name="test-device",
        management_address="192.168.1.1:443",
        environment=Environment.LAB,
        credentials={"username": "admin", "password": "testpass"}
    )

    # Assert
    assert device.id is not None
    credential = await credential_repo.get_active_credential(device.id)
    assert credential is not None
    assert credential.username == "admin"
    assert credential.encrypted_secret != "testpass"  # Encrypted
```

**End-to-End Tests (MCP Tools)**

```python
# E2E tests - full stack from MCP tool to mocked RouterOS
@pytest.mark.asyncio
async def test_system_get_overview_tool_returns_complete_response():
    """MCP tool should return properly formatted system overview."""
    # Arrange
    mcp_server = create_test_mcp_server()
    mock_routeros = MockRouterOSClient()
    mock_routeros.set_response("/rest/system/resource", {
        "uptime": "1d2h3m",
        "version": "7.10.1 (stable)",
        "cpu-load": 15,
        "free-memory": 268435456,
        "total-memory": 536870912
    })

    # Act
    response = await mcp_server.call_tool(
        "system/get-overview",
        {"device_id": "dev-001"}
    )

    # Assert
    assert response["isError"] is False
    assert "_meta" in response
    meta = response["_meta"]
    assert meta["routeros_version"] == "7.10.1 (stable)"
    assert meta["cpu"]["usage_percent"] == 15.0
    assert meta["memory"]["usage_percent"] == 50.0
```

### Test Organization and Structure

**Test Directory Structure:**

```
tests/
├── unit/                       # Unit tests (pure logic, no I/O)
│   ├── domain/
│   │   ├── test_health_assessment.py
│   │   ├── test_plan_generation.py
│   │   └── test_validation.py
│   ├── security/
│   │   ├── test_authorization.py
│   │   └── test_encryption.py
│   └── utils/
│       └── test_normalization.py
├── integration/                # Integration tests (multiple components)
│   ├── test_device_service.py
│   ├── test_health_service.py
│   ├── test_plan_service.py
│   └── test_routeros_client.py
├── e2e/                       # End-to-end tests (full stack)
│   ├── test_mcp_tools.py
│   ├── test_mcp_resources.py
│   └── test_workflows.py
├── fixtures/                  # Shared test fixtures
│   ├── device_fixtures.py
│   ├── routeros_fixtures.py
│   └── mcp_fixtures.py
└── conftest.py                # Pytest configuration
```

### Test Fixtures and Factories

**Use pytest fixtures for reusable setup:**

```python
# conftest.py
import pytest
from routeros_mcp.domain.models import Device, Environment

@pytest.fixture
def test_device() -> Device:
    """Create a test device for use in tests."""
    return Device(
        id="dev-test-001",
        name="test-router",
        management_address="192.168.1.1:443",
        environment=Environment.LAB,
        status="healthy",
        allow_advanced_writes=True,
        allow_professional_workflows=False
    )

@pytest.fixture
async def device_service(tmp_path):
    """Create device service with in-memory repositories."""
    db_path = tmp_path / "test.db"
    session_manager = await create_test_session_manager(f"sqlite:///{db_path}")

    service = DeviceService(
        session_manager=session_manager,
        encryption_service=TestEncryptionService()
    )

    yield service

    await session_manager.close()

# Usage in tests
async def test_get_device_returns_correct_device(device_service, test_device):
    await device_service.register_device_from_model(test_device)

    retrieved = await device_service.get_device(test_device.id)

    assert retrieved.id == test_device.id
    assert retrieved.name == test_device.name
```

### Mocking Best Practices

**Mock external dependencies, not internal logic:**

```python
# ✅ CORRECT: Mock RouterOS client (external dependency)
@pytest.fixture
def mock_routeros_client():
    client = Mock(spec=RouterOSRestClient)
    client.get.return_value = {
        "uptime": "1d",
        "version": "7.10.1",
        "cpu-load": 10
    }
    return client

async def test_system_service_with_mock(mock_routeros_client):
    service = SystemService(mock_routeros_client)
    overview = await service.get_overview("dev-001")
    assert overview["routeros_version"] == "7.10.1"

# ❌ WRONG: Mocking internal domain logic
def test_health_service_with_mocked_assessment():
    mock_assess = Mock(return_value=HealthStatus.HEALTHY)
    service = HealthService(assess_health=mock_assess)  # Don't do this
    ...
```

### TDD Workflow Example

**Complete TDD workflow for a new feature:**

```python
# Feature: Add ability to update device tags

# STEP 1: Write failing test
@pytest.mark.asyncio
async def test_update_device_tags_replaces_existing_tags():
    """Updating device tags should completely replace existing tags."""
    # Arrange
    device = await device_service.register_device(
        name="test-router",
        management_address="192.168.1.1:443",
        environment=Environment.LAB,
        credentials={"username": "admin", "password": "test"},
        tags={"site": "main", "role": "edge"}
    )

    # Act
    updated = await device_service.update_tags(
        device.id,
        tags={"site": "backup", "priority": "high"}
    )

    # Assert
    assert updated.tags == {"site": "backup", "priority": "high"}
    assert "role" not in updated.tags  # Old tag removed

# RUN TEST: Fails (method doesn't exist)

# STEP 2: Implement minimal code
class DeviceService:
    async def update_tags(self, device_id: str, tags: dict[str, str]) -> Device:
        device = await self.device_repo.get(device_id)
        device.tags = tags
        await self.device_repo.update(device)
        return device

# RUN TEST: Passes

# STEP 3: Refactor
class DeviceService:
    async def update_tags(
        self,
        device_id: str,
        tags: dict[str, str],
        merge: bool = False
    ) -> Device:
        """Update device tags.

        Args:
            device_id: Device identifier
            tags: New tags (replaces existing by default)
            merge: If True, merge with existing tags instead of replacing

        Returns:
            Updated device
        """
        device = await self.device_repo.get(device_id)

        if merge:
            device.tags = {**device.tags, **tags}
        else:
            device.tags = tags

        await self.device_repo.update(device)
        await self.audit_service.log(
            action="DEVICE_TAGS_UPDATED",
            device_id=device_id,
            metadata={"new_tags": tags, "merge": merge}
        )

        return device

# STEP 4: Add more tests for edge cases
@pytest.mark.asyncio
async def test_update_device_tags_with_merge_combines_tags():
    device = await create_test_device(tags={"site": "main"})

    updated = await device_service.update_tags(
        device.id,
        tags={"role": "edge"},
        merge=True
    )

    assert updated.tags == {"site": "main", "role": "edge"}

@pytest.mark.asyncio
async def test_update_device_tags_for_nonexistent_device_raises_error():
    with pytest.raises(DeviceNotFoundError):
        await device_service.update_tags("invalid-id", {})
```

---

## Testing Layers

### Unit Tests

**Purpose**: Test pure business logic in isolation

**Scope:**
- Input validation
- Domain model behavior
- Authorization decisions (based on roles, scopes, environment, capability flags)
- Plan generation logic (without calling RouterOS)
- Data transformation and normalization
- Pure functions and utility methods

**Characteristics:**
- Fast execution (milliseconds)
- No external dependencies (no DB, no network, no file I/O)
- Use mocks/stubs for dependencies
- Test single responsibility
- 100% coverage expected for core domain logic

**Example:**

```python
# Unit test for pure domain logic
def test_normalize_routeros_uptime_string():
    """Uptime string parsing should handle RouterOS format."""
    assert parse_uptime("1w2d3h4m5s") == 788645  # seconds
    assert parse_uptime("30m") == 1800
    assert parse_uptime("0s") == 0

def test_calculate_memory_usage_percentage():
    """Memory usage calculation should be accurate."""
    total = 536870912  # 512MB
    free = 268435456   # 256MB

    usage_pct = calculate_memory_usage_percent(total, free)

    assert usage_pct == 50.0
```

### Integration Tests

**Purpose**: Test how components work together

**Scope:**
- Domain services and RouterOS integration using mocked clients
- Database operations with test database
- Error mapping (RouterOS → MCP error codes)
- Idempotency semantics (`changed` flags)
- Multi-component workflows

**Characteristics:**
- Slower than unit tests (seconds)
- May use in-memory/test databases
- Use mocked external APIs (RouterOS, OAuth)
- Test realistic scenarios
- 85%+ coverage expected

**Example:**

```python
# Integration test with database
@pytest.mark.asyncio
async def test_health_check_creates_database_record(db_session):
    """Health check should persist results to database."""
    health_service = HealthService(
        routeros_client=mock_client,
        health_repo=HealthCheckRepository(db_session)
    )

    await health_service.check_device("dev-001")

    # Verify database record created
    records = await db_session.execute(
        select(HealthCheck).where(HealthCheck.device_id == "dev-001")
    )
    health_record = records.scalar_one()
    assert health_record.status in ["healthy", "warning", "critical", "error"]
```

### Device Lab Tests

**Purpose**: Test against real RouterOS devices

**Scope:**
- Use small number of real RouterOS devices in `lab` environment
- End-to-end flows: MCP → RouterOS and back
- Validate tools against real RouterOS behavior and quirks
- Test version compatibility
- Verify actual configuration changes (safe environment)

**Characteristics:**
- Slowest tests (seconds to minutes)
- Require lab RouterOS devices
- May modify device state (safe to do in lab)
- Run less frequently (pre-merge, nightly)
- Test realistic device behavior

**Example:**

```python
# Lab device test
@pytest.mark.lab
@pytest.mark.asyncio
async def test_dns_update_on_real_device(lab_device):
    """Test DNS update against real RouterOS device."""
    # Capture current state
    original_dns = await dns_service.get_status(lab_device.id)

    try:
        # Apply change
        result = await dns_service.update_servers(
            lab_device.id,
            dns_servers=["1.1.1.1", "1.0.0.1"]
        )

        assert result["changed"] is True

        # Verify change
        updated_dns = await dns_service.get_status(lab_device.id)
        assert updated_dns["dns_servers"] == ["1.1.1.1", "1.0.0.1"]

    finally:
        # Rollback to original state
        await dns_service.update_servers(
            lab_device.id,
            dns_servers=original_dns["dns_servers"]
        )
```

### End-to-End Tests (MCP Protocol)

**Purpose**: Test complete MCP workflows

**Scope:**
- Full MCP protocol flows (initialize, tools/list, tools/call)
- OAuth authentication (in test IdP environment)
- MCP client → MCP server → Domain → RouterOS
- Resource subscriptions and notifications (Phase 2)
- Prompt templates and workflows (Phase 2)
- MCP transport modes (stdio, HTTP/SSE)
- JSON-RPC 2.0 protocol compliance
- MCP schema validation

**Characteristics:**
- Test MCP compliance
- Verify JSON-RPC 2.0 messages
- Test authorization at MCP layer
- Cover Phase 0-2 features initially, expand as phases implement
- Use MCP Inspector for manual E2E testing
- Test both stdio and HTTP/SSE transports

**Example - Basic MCP Workflow:**

```python
# E2E MCP test
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mcp_tool_call_full_workflow(mcp_client):
    """Test complete MCP tool invocation workflow."""
    # Initialize MCP session
    init_response = await mcp_client.initialize(
        protocol_version="2024-11-05",
        capabilities={"tools": {}},
        client_info={"name": "test-client", "version": "1.0.0"}
    )

    # Verify server response
    assert init_response["jsonrpc"] == "2.0"
    assert "result" in init_response
    assert init_response["result"]["protocolVersion"] == "2024-11-05"
    assert init_response["result"]["serverInfo"]["name"] == "routeros-mcp"
    assert "capabilities" in init_response["result"]
    assert "tools" in init_response["result"]["capabilities"]

    # List tools
    tools_response = await mcp_client.call_method("tools/list")
    assert "result" in tools_response
    assert "tools" in tools_response["result"]

    tool_names = [t["name"] for t in tools_response["result"]["tools"]]
    assert "system.get_overview" in tool_names

    # Validate tool schemas
    for tool in tools_response["result"]["tools"]:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        # Validate JSON Schema is well-formed
        from jsonschema import Draft7Validator
        Draft7Validator.check_schema(tool["inputSchema"])

    # Call tool
    call_response = await mcp_client.call_method(
        "tools/call",
        {
            "name": "system.get_overview",
            "arguments": {"device_id": "dev-lab-01"}
        }
    )

    # Verify response structure
    assert call_response["jsonrpc"] == "2.0"
    assert "result" in call_response
    result = call_response["result"]
    assert "content" in result
    assert len(result["content"]) > 0
    assert result["content"][0]["type"] == "text"

    # Verify metadata
    assert "_meta" in result
    assert "estimated_tokens" in result["_meta"]
    assert "routeros_version" in result["_meta"]
```

**MCP Protocol Compliance Tests:**

```python
# Test JSON-RPC 2.0 compliance
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mcp_jsonrpc_compliance(mcp_client):
    """Verify MCP server follows JSON-RPC 2.0 specification."""

    # Test 1: Valid request returns valid response
    response = await mcp_client.call_method("tools/list")
    assert response["jsonrpc"] == "2.0"
    assert "result" in response or "error" in response
    assert "id" in response

    # Test 2: Malformed JSON returns error
    try:
        await mcp_client.send_raw('{"invalid": "json"')
    except Exception as e:
        # Should get parse error
        assert "parse error" in str(e).lower()

    # Test 3: Unknown method returns error
    response = await mcp_client.call_method("unknown/method")
    assert "error" in response
    assert response["error"]["code"] == -32601  # Method not found

    # Test 4: Invalid params return error
    response = await mcp_client.call_method(
        "tools/call",
        {"invalid": "params"}  # Missing required "name" field
    )
    assert "error" in response
    assert response["error"]["code"] == -32602  # Invalid params

# Test MCP initialization sequence
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mcp_initialization_sequence(mcp_client):
    """Test MCP initialization handshake."""

    # Test 1: Initialize must be called first
    # Calling tools/list before initialize should fail
    try:
        await mcp_client.call_method("tools/list")
        assert False, "Should require initialization first"
    except Exception:
        pass  # Expected

    # Test 2: Initialize with valid params
    init_response = await mcp_client.initialize(
        protocol_version="2024-11-05",
        capabilities={"tools": {}},
        client_info={"name": "test-client", "version": "1.0.0"}
    )

    assert init_response["result"]["protocolVersion"] == "2024-11-05"
    assert "serverInfo" in init_response["result"]
    assert init_response["result"]["serverInfo"]["name"] == "routeros-mcp"
    assert init_response["result"]["serverInfo"]["version"]  # Has version

    # Test 3: Re-initialization should be idempotent
    init_response2 = await mcp_client.initialize(
        protocol_version="2024-11-05",
        capabilities={"tools": {}},
        client_info={"name": "test-client", "version": "1.0.0"}
    )
    assert init_response2["result"] == init_response["result"]

    # Test 4: After initialization, tools/list should work
    tools_response = await mcp_client.call_method("tools/list")
    assert "result" in tools_response

# Test MCP capability negotiation
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mcp_capability_negotiation(mcp_client):
    """Test MCP capability negotiation between client and server."""

    # Test 1: Client requests only tools capability
    init_response = await mcp_client.initialize(
        protocol_version="2024-11-05",
        capabilities={"tools": {}},
        client_info={"name": "tools-only-client", "version": "1.0.0"}
    )

    server_caps = init_response["result"]["capabilities"]
    assert "tools" in server_caps

    # Test 2: Client requests tools + resources (Phase 2)
    init_response = await mcp_client.initialize(
        protocol_version="2024-11-05",
        capabilities={"tools": {}, "resources": {"subscribe": True}},
        client_info={"name": "full-client", "version": "1.0.0"}
    )

    server_caps = init_response["result"]["capabilities"]
    assert "tools" in server_caps

    # Resources may or may not be supported depending on phase
    if "resources" in server_caps:
        assert "subscribe" in server_caps["resources"]

# Test MCP tool schema validation
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mcp_tool_schema_validation(mcp_client):
    """Verify all MCP tool schemas are valid JSON Schema."""
    await mcp_client.initialize()

    tools_response = await mcp_client.call_method("tools/list")
    tools = tools_response["result"]["tools"]

    from jsonschema import Draft7Validator, ValidationError

    for tool in tools:
        # Verify required fields
        assert "name" in tool, f"Tool missing 'name' field: {tool}"
        assert "description" in tool, f"Tool {tool.get('name')} missing 'description'"
        assert "inputSchema" in tool, f"Tool {tool['name']} missing 'inputSchema'"

        # Verify schema is valid JSON Schema
        try:
            Draft7Validator.check_schema(tool["inputSchema"])
        except ValidationError as e:
            pytest.fail(f"Tool {tool['name']} has invalid JSON Schema: {e}")

        # Verify schema has required properties
        schema = tool["inputSchema"]
        assert schema.get("type") == "object", f"Tool {tool['name']} schema must be object type"
        assert "properties" in schema, f"Tool {tool['name']} schema must have properties"

        # Verify tier metadata
        if "_meta" in tool:
            assert "tier" in tool["_meta"], f"Tool {tool['name']} missing tier in _meta"
            assert tool["_meta"]["tier"] in ["free", "basic", "professional"]

# Test MCP transport modes
@pytest.mark.e2e
@pytest.mark.parametrize("transport", ["stdio", "http"])
async def test_mcp_transport_modes(transport):
    """Test MCP server works with both stdio and HTTP transports."""

    if transport == "stdio":
        client = MCPClient(
            transport="stdio",
            command=["python", "-m", "routeros_mcp.server"],
            env={"MCP_TRANSPORT_MODE": "stdio"}
        )
    else:  # http
        client = MCPClient(
            transport="http",
            base_url="http://localhost:8080/mcp"
        )

    await client.initialize()

    # Both transports should support same operations
    tools_response = await client.call_method("tools/list")
    assert "result" in tools_response
    assert len(tools_response["result"]["tools"]) > 0

    # Call a tool
    call_response = await client.call_method(
        "tools/call",
        {"name": "system.get_overview", "arguments": {"device_id": "dev-lab-01"}}
    )
    assert "result" in call_response

    await client.close()

# Test MCP error responses
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mcp_error_responses(mcp_client):
    """Test MCP error response format."""
    await mcp_client.initialize()

    # Test 1: Tool not found
    response = await mcp_client.call_method(
        "tools/call",
        {"name": "nonexistent.tool", "arguments": {}}
    )
    assert "error" in response
    error = response["error"]
    assert error["code"] == -32602  # Invalid params or tool not found
    assert "message" in error

    # Test 2: Invalid arguments
    response = await mcp_client.call_method(
        "tools/call",
        {"name": "system.get_overview", "arguments": {}}  # Missing device_id
    )
    assert "error" in response
    error = response["error"]
    assert error["code"] in [-32602, -32603]  # Invalid params or internal error
    assert "device_id" in error["message"].lower()

    # Test 3: Device not found
    response = await mcp_client.call_method(
        "tools/call",
        {"name": "system.get_overview", "arguments": {"device_id": "invalid-device"}}
    )
    assert "error" in response
    error = response["error"]
    assert "message" in error
    assert "not found" in error["message"].lower()

# Test token budget estimation
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_token_budget_estimation(mcp_client):
    """Test that tool responses include estimated token counts."""
    await mcp_client.initialize()

    # Call a tool that returns data
    response = await mcp_client.call_method(
        "tools/call",
        {"name": "system.get_overview", "arguments": {"device_id": "dev-lab-01"}}
    )

    result = response["result"]

    # Verify estimated_tokens is present
    assert "_meta" in result
    assert "estimated_tokens" in result["_meta"]

    # Token count should be reasonable
    token_count = result["_meta"]["estimated_tokens"]
    assert isinstance(token_count, int)
    assert token_count > 0, "Token count should be positive"
    assert token_count < 100000, "Token count seems unreasonably high"

    # For small responses, token count should be < 5000 (warning threshold)
    # Larger responses may exceed this
    if len(str(result["content"])) < 2000:  # Small response
        assert token_count < 5000, "Small response should have low token count"

# Test MCP client compatibility matrix
@pytest.mark.e2e
@pytest.mark.parametrize("protocol_version", ["2024-11-05"])
async def test_protocol_version_compatibility(protocol_version, mcp_client):
    """Test compatibility with different MCP protocol versions."""

    init_response = await mcp_client.initialize(
        protocol_version=protocol_version,
        capabilities={"tools": {}},
        client_info={"name": "test-client", "version": "1.0.0"}
    )

    # Server should accept this protocol version
    assert "result" in init_response
    assert init_response["result"]["protocolVersion"] == protocol_version
```

**MCP-Specific Test Fixtures:**

```python
# conftest.py - MCP test fixtures

import pytest
from routeros_mcp.mcp.client import MCPClient
from routeros_mcp.mcp.server import MCPServer

@pytest.fixture
async def mcp_client():
    """Create MCP client for E2E testing."""
    client = MCPClient(
        transport="stdio",
        command=["python", "-m", "routeros_mcp.server"],
        env={
            "MCP_ENV": "test",
            "DATABASE_URL": "sqlite:///:memory:",
            "MCP_TRANSPORT_MODE": "stdio"
        }
    )

    yield client

    await client.close()

@pytest.fixture
async def mock_mcp_server():
    """Create mock MCP server for testing."""
    server = MCPServer(
        routeros_client=MockRouterOSClient(),
        device_service=MockDeviceService(),
        auth_service=MockAuthService()
    )

    await server.start()

    yield server

    await server.stop()

@pytest.fixture
def mock_tool_schema():
    """Provide valid MCP tool schema for testing."""
    return {
        "name": "test.example_tool",
        "description": "Example tool for testing",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "Device identifier"
                },
                "parameter": {
                    "type": "string",
                    "description": "Example parameter"
                }
            },
            "required": ["device_id"]
        },
        "_meta": {
            "tier": "free",
            "estimated_tokens": 500
        }
    }
```

---

## Coverage Expectations and Standards

### Coverage Targets

**Overall Coverage: ≥85% (Baseline)**

Automated test runs (local and CI) must enforce minimum coverage threshold using `pytest-cov`.

**Core Module Coverage: 100%**

The following modules must have 100% coverage of reachable code paths:

- `routeros_mcp/domain/` - All domain logic
- `routeros_mcp/security/` - Authorization, authentication, encryption
- `routeros_mcp/infra/routeros/` - RouterOS client integration
- `routeros_mcp/domain/plan_service.py` - Plan/apply orchestration
- `routeros_mcp/mcp_tools/` - All MCP tool implementations

**Coverage Configuration:**

```toml
# pyproject.toml
[tool.coverage.run]
source = ["routeros_mcp"]
omit = [
    "*/tests/*",
    "*/migrations/*",
    "*/__init__.py",
]

[tool.coverage.report]
fail_under = 85
show_missing = true
skip_covered = false

[[tool.coverage.report.modules]]
name = "routeros_mcp.domain"
fail_under = 100

[[tool.coverage.report.modules]]
name = "routeros_mcp.security"
fail_under = 100

[[tool.coverage.report.modules]]
name = "routeros_mcp.infra.routeros"
fail_under = 100
```

### Coverage Enforcement in CI

```bash
# CI pipeline coverage check
pytest --cov=routeros_mcp --cov-report=term-missing --cov-fail-under=85

# Generate HTML coverage report
pytest --cov=routeros_mcp --cov-report=html

# Fail if core modules below 100%
pytest --cov=routeros_mcp \
    --cov-report=term \
    --cov-fail-under=85 \
    --cov-config=pyproject.toml
```

### Mocking Rules

**What to Mock:**

✅ External services (RouterOS REST API, SSH, OAuth IdP)
✅ Database connections (use in-memory or test DB)
✅ Network I/O
✅ File system operations
✅ Time-dependent operations (use freezegun)

**What NOT to Mock:**

❌ Domain logic (test the real implementation)
❌ Simple data transformations
❌ Validation logic
❌ Internal service methods

**Mock Organization:**

```
tests/
├── mocks/
│   ├── routeros_mock.py      # Mock RouterOS client
│   ├── oauth_mock.py          # Mock OAuth responses
│   └── mcp_mock.py            # Mock MCP client
└── fixtures/
    ├── device_fixtures.py     # Device test data
    └── response_fixtures.py   # RouterOS response fixtures
```

**Example Mock:**

```python
# tests/mocks/routeros_mock.py
class MockRouterOSClient:
    """Mock RouterOS REST client for testing."""

    def __init__(self):
        self.responses = {}
        self.call_history = []

    def set_response(self, endpoint: str, response: dict):
        """Set mock response for endpoint."""
        self.responses[endpoint] = response

    async def get(self, endpoint: str) -> dict:
        """Mock GET request."""
        self.call_history.append(("GET", endpoint))

        if endpoint in self.responses:
            return self.responses[endpoint]

        raise DeviceUnreachableError(f"No mock response for {endpoint}")

    def assert_called(self, method: str, endpoint: str):
        """Assert that endpoint was called."""
        assert (method, endpoint) in self.call_history
```

---

## Test Environments and Lab Devices

### Environment Taxonomy

**`lab` Environment:**
- Fully sandboxed RouterOS devices
- Safe for testing high-risk operations
- May be virtualized (CHR) or physical hardware
- Dedicated to MCP testing
- Allows all tool tiers (fundamental, advanced, professional)
- State changes expected and acceptable

**`staging` Environment:**
- Mirrors production topology
- Close to production configuration
- Higher-risk than lab but lower than prod
- Used for final validation before production
- Limited write operations (requires approval)

**`prod` Environment:**
- Production devices
- Minimal direct testing
- Canary rollout only
- All writes require admin approval
- Rollback plan mandatory

### Lab RouterOS Instances

**Setup:**

```yaml
# Lab device configuration
lab_devices:
  - name: lab-router-01
    model: CHR (Cloud Hosted Router)
    routeros_version: 7.15
    management_ip: 192.168.100.10
    purpose: DNS/NTP testing
    tags: [lab, dns-test]

  - name: lab-router-02
    model: RB5009
    routeros_version: 7.14
    management_ip: 192.168.100.11
    purpose: Interface/IP testing
    tags: [lab, interface-test]

  - name: lab-router-03
    model: hEX S
    routeros_version: 7.15
    management_ip: 192.168.100.12
    purpose: Firewall/routing testing
    tags: [lab, firewall-test]
```

**Lab Test Fixtures:**

```python
# conftest.py
@pytest.fixture(scope="session")
def lab_devices():
    """Provide lab device registry for tests."""
    return [
        {
            "id": "dev-lab-01",
            "name": "lab-router-01",
            "management_address": "192.168.100.10:443",
            "environment": "lab"
        },
        # ... more lab devices
    ]

@pytest.mark.lab
@pytest.fixture
async def lab_device(lab_devices):
    """Select first available lab device for test."""
    device_id = lab_devices[0]["id"]

    # Verify device is reachable
    try:
        await check_device_connectivity(device_id)
        yield lab_devices[0]
    except DeviceUnreachableError:
        pytest.skip(f"Lab device {device_id} is not reachable")
```

### Simulated Devices and Mocks

**Mock RouterOS Server for CI:**

```python
# tests/mock_routeros_server.py
from aiohttp import web

class MockRouterOSServer:
    """Simulated RouterOS REST API server for testing."""

    async def handle_system_resource(self, request):
        return web.json_response({
            "uptime": "1w2d3h",
            "version": "7.15 (stable)",
            "cpu-load": 10,
            "free-memory": 268435456,
            "total-memory": 536870912,
            "board-name": "CHR"
        })

    async def handle_interface_list(self, request):
        return web.json_response([
            {
                ".id": "*1",
                "name": "ether1",
                "type": "ether",
                "running": True,
                "disabled": False
            }
        ])

    def create_app(self):
        app = web.Application()
        app.router.add_get("/rest/system/resource", self.handle_system_resource)
        app.router.add_get("/rest/interface", self.handle_interface_list)
        return app

# Usage in tests
@pytest.fixture
async def mock_routeros_server():
    server = MockRouterOSServer()
    app = server.create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()

    yield "http://localhost:8080"

    await runner.cleanup()
```

---

## Sandbox Strategy and Write-Locked Environments

### Feature Flags for Capability Control

```python
# Feature flag configuration
class FeatureFlags:
    """Feature flags for progressive rollout."""

    # Phase 1 features
    FUNDAMENTAL_TOOLS_ENABLED = True  # Always on

    # Phase 2 features
    ADVANCED_WRITES_ENABLED_LAB = True
    ADVANCED_WRITES_ENABLED_STAGING = False  # Off by default
    ADVANCED_WRITES_ENABLED_PROD = False

    # Phase 4 features
    PROFESSIONAL_WORKFLOWS_ENABLED_LAB = True
    PROFESSIONAL_WORKFLOWS_ENABLED_STAGING = False
    PROFESSIONAL_WORKFLOWS_ENABLED_PROD = False

    @classmethod
    def is_enabled(cls, feature: str, environment: str) -> bool:
        """Check if feature is enabled for environment."""
        flag_name = f"{feature}_ENABLED_{environment.upper()}"
        return getattr(cls, flag_name, False)
```

### Environment-Specific Tool Restrictions

```python
# Tool access control by environment
async def check_tool_access(device: Device, tool_name: str, tool_tier: str):
    """Verify tool can be invoked on device."""

    # Check environment-based restrictions
    if device.environment == "prod":
        if tool_tier == "professional":
            # Professional tools disabled in prod by default
            if not FeatureFlags.is_enabled("PROFESSIONAL_WORKFLOWS", "prod"):
                raise AuthorizationError(
                    f"Professional tier disabled in production"
                )

        if tool_tier == "advanced":
            # Advanced tools require explicit device flag in prod
            if not device.allow_advanced_writes:
                raise AuthorizationError(
                    f"Device {device.id} does not allow advanced writes"
                )

    # Lab environment allows all tiers
    if device.environment == "lab":
        return  # Allow

    # Staging requires device flags for advanced/professional
    if device.environment == "staging":
        if tool_tier in ["advanced", "professional"]:
            if not device.allow_advanced_writes:
                raise AuthorizationError(
                    f"Device {device.id} does not allow {tool_tier} tier"
                )
```

---

## Safety Nets for Write Operations

### Dry-Run and Plan-Only Mode

**All write tools must support dry-run:**

```python
async def update_dns_servers(
    device_id: str,
    dns_servers: list[str],
    dry_run: bool = False
) -> dict:
    """Update DNS servers with optional dry-run."""

    # Fetch current state
    current = await dns_service.get_status(device_id)

    # Compute changes
    will_change = current["dns_servers"] != dns_servers

    if dry_run:
        # Return preview without applying
        return {
            "changed": will_change,
            "dry_run": True,
            "preview": {
                "current_dns_servers": current["dns_servers"],
                "new_dns_servers": dns_servers
            }
        }

    # Apply changes
    if will_change:
        await routeros_client.patch(
            "/rest/ip/dns",
            {"servers": ",".join(dns_servers)}
        )

    return {
        "changed": will_change,
        "dns_servers": dns_servers
    }
```

### Preview Diffs for Plan/Apply

**Plan response should show clear before/after:**

```python
{
    "plan_id": "plan-001",
    "description": "DNS/NTP rollout to lab devices",
    "devices": [
        {
            "device_id": "dev-lab-01",
            "device_name": "lab-router-01",
            "changes": [
                {
                    "type": "dns_servers",
                    "before": ["8.8.8.8", "8.8.4.4"],
                    "after": ["1.1.1.1", "1.0.0.1"],
                    "risk_level": "low"
                },
                {
                    "type": "ntp_servers",
                    "before": ["pool.ntp.org"],
                    "after": ["time.cloudflare.com"],
                    "risk_level": "low"
                }
            ],
            "overall_risk": "low",
            "precondition_checks": {
                "device_reachable": true,
                "allow_advanced_writes": true,
                "health_status": "healthy"
            }
        }
    ],
    "total_devices": 1,
    "total_changes": 2,
    "risk_summary": {
        "low": 2,
        "medium": 0,
        "high": 0
    }
}
```

### Safe-Mode Rollbacks

**Automatic rollback on health check failure:**

```python
async def apply_plan_with_rollback(plan_id: str) -> dict:
    """Apply plan with automatic rollback on failure."""

    plan = await plan_service.get_plan(plan_id)
    snapshots = {}

    try:
        # Capture pre-change snapshots
        for device_id in plan.device_ids:
            snapshot = await snapshot_service.create_snapshot(
                device_id=device_id,
                snapshot_type="pre_change",
                trigger=f"plan_{plan_id}"
            )
            snapshots[device_id] = snapshot

        # Apply changes
        results = await plan_service.apply_plan(plan_id)

        # Health check post-change
        for device_id in plan.device_ids:
            health = await health_service.check_device(device_id)

            if health.status in ["critical", "error"]:
                # Automatic rollback
                logger.error(
                    f"Health check failed after apply, rolling back",
                    device_id=device_id,
                    health_status=health.status
                )

                await rollback_service.rollback_to_snapshot(
                    device_id=device_id,
                    snapshot_id=snapshots[device_id].id
                )

                raise HealthCheckFailureError(
                    f"Device {device_id} health check failed, rolled back"
                )

        return {"status": "success", "results": results}

    except Exception as e:
        # Rollback all devices on any failure
        for device_id, snapshot in snapshots.items():
            await rollback_service.rollback_to_snapshot(
                device_id=device_id,
                snapshot_id=snapshot.id
            )
        raise
```

---

## Canary and Gradual Rollout Strategies

### Phased Feature Rollout

**Stage 1: Lab Only**

```python
# Enable feature in lab
if settings.environment == "lab":
    mcp.register_tool(new_experimental_tool)
```

**Stage 2: Staging Canary**

```python
# Enable for tagged devices in staging
if settings.environment == "staging":
    canary_devices = await device_service.list_devices(
        environment="staging",
        tag="canary"
    )
    if device_id in [d.id for d in canary_devices]:
        # Allow new tool
        ...
```

**Stage 3: Production Canary**

```python
# Gradual production rollout
prod_canary_percentage = 5  # Start with 5% of devices

if settings.environment == "prod":
    # Deterministic selection based on device ID hash
    if hash(device_id) % 100 < prod_canary_percentage:
        # Allow new tool for canary devices
        ...
```

### Metrics and Alerts During Rollout

**Monitor key metrics:**

```python
# Prometheus metrics for rollout
tool_invocation_counter = Counter(
    "routeros_mcp_tool_invocations_total",
    "Total tool invocations",
    ["tool_name", "environment", "status"]
)

tool_latency_histogram = Histogram(
    "routeros_mcp_tool_latency_seconds",
    "Tool invocation latency",
    ["tool_name", "environment"]
)

tool_error_rate_gauge = Gauge(
    "routeros_mcp_tool_error_rate",
    "Tool error rate",
    ["tool_name", "environment"]
)

# Alert if error rate exceeds threshold
if error_rate > 0.10:  # 10% error rate
    alert_service.trigger_alert(
        severity="critical",
        message=f"Tool {tool_name} error rate exceeded 10%",
        disable_feature=True  # Automatic feature flag disable
    )
```

---

## Regression Testing

### RouterOS Version Compatibility Matrix

```markdown
| MCP Version | RouterOS 7.10 | RouterOS 7.11 | RouterOS 7.12 | RouterOS 7.13 | RouterOS 7.14 | RouterOS 7.15 |
|-------------|---------------|---------------|---------------|---------------|---------------|---------------|
| 1.0.0       | ✅ Tested     | ✅ Tested     | ✅ Tested     | ✅ Tested     | ✅ Tested     | ⚠️ Not tested |
| 1.1.0       | ✅ Tested     | ✅ Tested     | ✅ Tested     | ✅ Tested     | ✅ Tested     | ✅ Tested     |
```

### RouterOS Upgrade Testing Workflow

```python
@pytest.mark.routeros_version("7.15")
@pytest.mark.lab
async def test_all_tools_against_routeros_7_15(lab_device):
    """Regression test all tools against RouterOS 7.15."""

    # Verify RouterOS version
    overview = await system_service.get_overview(lab_device.id)
    assert overview["routeros_version"].startswith("7.15")

    # Test all fundamental tools
    await test_system_tools(lab_device.id)
    await test_interface_tools(lab_device.id)
    await test_ip_tools(lab_device.id)
    await test_dns_tools(lab_device.id)
    await test_ntp_tools(lab_device.id)

    # Test advanced tools if allowed
    if lab_device.allow_advanced_writes:
        await test_advanced_tools(lab_device.id)
```

---

## Smoke Tests and Periodic Health Checks

### Post-Deployment Smoke Tests

```python
# smoke_tests.py
async def run_smoke_tests(environment: str) -> dict:
    """Run smoke tests after deployment."""

    results = {
        "environment": environment,
        "timestamp": datetime.utcnow().isoformat(),
        "tests": []
    }

    # Test 1: List devices
    try:
        devices = await device_service.list_devices(environment=environment)
        results["tests"].append({
            "name": "device.list_devices",
            "status": "pass",
            "device_count": len(devices)
        })
    except Exception as e:
        results["tests"].append({
            "name": "device.list_devices",
            "status": "fail",
            "error": str(e)
        })

    # Test 2: Check first device connectivity
    if devices:
        device_id = devices[0].id
        try:
            await device_service.check_connectivity(device_id)
            results["tests"].append({
                "name": "device.check_connectivity",
                "status": "pass",
                "device_id": device_id
            })
        except Exception as e:
            results["tests"].append({
                "name": "device.check_connectivity",
                "status": "fail",
                "device_id": device_id,
                "error": str(e)
            })

    # Test 3: System overview
    if devices:
        device_id = devices[0].id
        try:
            overview = await system_service.get_overview(device_id)
            results["tests"].append({
                "name": "system.get_overview",
                "status": "pass",
                "device_id": device_id
            })
        except Exception as e:
            results["tests"].append({
                "name": "system.get_overview",
                "status": "fail",
                "device_id": device_id,
                "error": str(e)
            })

    # Determine overall status
    failures = [t for t in results["tests"] if t["status"] == "fail"]
    results["overall_status"] = "fail" if failures else "pass"
    results["failure_count"] = len(failures)

    return results
```

### Periodic Health Monitoring

```python
# health_monitor.py
async def monitor_fleet_health():
    """Periodic health monitoring (runs every 60 seconds)."""

    devices = await device_service.list_all_devices()

    for device in devices:
        try:
            health = await health_service.check_device(device.id)

            # Update metrics
            device_health_gauge.labels(
                device_id=device.id,
                environment=device.environment
            ).set(health_status_to_numeric(health.status))

            # Alert on critical/error status
            if health.status in ["critical", "error"]:
                await alert_service.trigger_alert(
                    severity="warning" if health.status == "critical" else "error",
                    message=f"Device {device.name} health is {health.status}",
                    device_id=device.id
                )

        except Exception as e:
            logger.error(
                "Health check failed",
                device_id=device.id,
                error=str(e)
            )
```

---

## MCP-Specific Safety Nets

### MCP Protocol-Level Safety

**Rate Limiting for Tool Calls:**

```python
# Rate limiting for tool execution
from datetime import datetime, timedelta
from collections import defaultdict

class MCPRateLimiter:
    """Rate limiter for MCP tool calls."""

    def __init__(self):
        self.call_counts = defaultdict(list)  # user_id -> list of timestamps
        self.limits = {
            "free": 100,  # 100 calls per hour
            "basic": 500,
            "professional": 2000
        }

    async def check_rate_limit(self, user_id: str, tool_tier: str):
        """Check if user has exceeded rate limit for tier."""
        limit = self.limits.get(tool_tier, 100)
        now = datetime.utcnow()
        one_hour_ago = now - timedelta(hours=1)

        # Remove old timestamps
        self.call_counts[user_id] = [
            ts for ts in self.call_counts[user_id]
            if ts > one_hour_ago
        ]

        # Check limit
        if len(self.call_counts[user_id]) >= limit:
            raise RateLimitExceededError(
                f"Rate limit exceeded: {limit} calls per hour for {tool_tier} tier"
            )

        # Record this call
        self.call_counts[user_id].append(now)

# Test rate limiting
@pytest.mark.asyncio
async def test_rate_limiting_enforced(mcp_client, rate_limiter):
    """Test that rate limiting prevents excessive tool calls."""
    await mcp_client.initialize()

    # Make calls up to limit
    for i in range(100):
        response = await mcp_client.call_method(
            "tools/call",
            {"name": "system.get_overview", "arguments": {"device_id": "dev-001"}}
        )
        assert "result" in response

    # Next call should fail
    response = await mcp_client.call_method(
        "tools/call",
        {"name": "system.get_overview", "arguments": {"device_id": "dev-001"}}
    )
    assert "error" in response
    assert "rate limit" in response["error"]["message"].lower()
```

**Concurrent Tool Execution Limits:**

```python
# Limit concurrent tool executions
import asyncio
from asyncio import Semaphore

class MCPConcurrencyLimiter:
    """Limit concurrent tool executions."""

    def __init__(self, max_concurrent: int = 10):
        self.semaphore = Semaphore(max_concurrent)
        self.active_tools = {}

    async def execute_with_limit(self, tool_name: str, executor_func, *args, **kwargs):
        """Execute tool with concurrency limit."""
        async with self.semaphore:
            # Record active execution
            execution_id = str(uuid.uuid4())
            self.active_tools[execution_id] = {
                "tool_name": tool_name,
                "started_at": datetime.utcnow()
            }

            try:
                result = await executor_func(*args, **kwargs)
                return result
            finally:
                # Remove from active
                del self.active_tools[execution_id]

# Test concurrency limits
@pytest.mark.asyncio
async def test_concurrent_execution_limit(mcp_server):
    """Test that server limits concurrent tool executions."""
    limiter = MCPConcurrencyLimiter(max_concurrent=5)

    # Start 10 concurrent tool calls
    tasks = []
    for i in range(10):
        task = limiter.execute_with_limit(
            "system.get_overview",
            slow_tool_executor,  # Takes 2 seconds
            device_id=f"dev-{i:03d}"
        )
        tasks.append(task)

    # Only 5 should run concurrently
    results = await asyncio.gather(*tasks)
    assert len(results) == 10

    # Verify max 5 concurrent
    assert max(len(limiter.active_tools) for _ in range(10)) <= 5
```

**Malformed Request Handling:**

```python
# Test malformed MCP requests
@pytest.mark.e2e
@pytest.mark.asyncio
async def test_malformed_request_handling(mcp_client):
    """Test that server gracefully handles malformed requests."""

    test_cases = [
        # Missing jsonrpc field
        ('{"method": "tools/list", "id": 1}', -32600),  # Invalid Request

        # Invalid JSON
        ('{"incomplete": ', -32700),  # Parse error

        # Wrong jsonrpc version
        ('{"jsonrpc": "1.0", "method": "tools/list", "id": 1}', -32600),

        # Missing method field
        ('{"jsonrpc": "2.0", "id": 1}', -32600),

        # Invalid method type
        ('{"jsonrpc": "2.0", "method": 123, "id": 1}', -32600),

        # Params not object/array
        ('{"jsonrpc": "2.0", "method": "tools/list", "params": "invalid", "id": 1}', -32600)
    ]

    for malformed_request, expected_code in test_cases:
        try:
            response = await mcp_client.send_raw(malformed_request)
            # Should return error response
            assert "error" in response
            assert response["error"]["code"] == expected_code
        except Exception:
            # Connection may be closed on invalid JSON
            pass
```

**Timeout Protection:**

```python
# Test tool execution timeouts
@pytest.mark.asyncio
async def test_tool_execution_timeout(mcp_client):
    """Test that tool executions timeout after maximum duration."""

    # Configure timeout
    mcp_server.config.TOOL_EXECUTION_TIMEOUT_SECONDS = 30

    # Call a tool that takes too long (mocked to sleep 60 seconds)
    with patch('routeros_mcp.tools.system.get_overview') as mock_tool:
        async def slow_execution(*args, **kwargs):
            await asyncio.sleep(60)
            return {"result": "never reached"}

        mock_tool.side_effect = slow_execution

        response = await mcp_client.call_method(
            "tools/call",
            {"name": "system.get_overview", "arguments": {"device_id": "dev-001"}}
        )

        # Should timeout and return error
        assert "error" in response
        assert "timeout" in response["error"]["message"].lower()
```

### MCP Client Compatibility Testing

**Client Compatibility Matrix:**

```markdown
| MCP Client | Protocol Version | Tools | Resources | Prompts | Tested |
|------------|-----------------|-------|-----------|---------|--------|
| Claude Desktop | 2024-11-05 | ✅ | ✅ | ✅ | ✅ |
| MCP Inspector | 2024-11-05 | ✅ | ✅ | ✅ | ✅ |
| Custom Client | 2024-11-05 | ✅ | ⚠️ Phase 2 | ⚠️ Phase 2 | ✅ |
```

**Client Compatibility Tests:**

```python
# Test against different MCP clients
@pytest.mark.e2e
@pytest.mark.parametrize("client_name,client_version", [
    ("claude-desktop", "1.0.0"),
    ("mcp-inspector", "0.1.0"),
    ("custom-client", "1.0.0")
])
async def test_client_compatibility(client_name, client_version):
    """Test MCP server works with different clients."""

    client = MCPClient(
        transport="stdio",
        command=["python", "-m", "routeros_mcp.server"]
    )

    # Initialize with client info
    init_response = await client.initialize(
        protocol_version="2024-11-05",
        capabilities={"tools": {}},
        client_info={"name": client_name, "version": client_version}
    )

    # Server should accept any client
    assert "result" in init_response
    assert init_response["result"]["serverInfo"]["name"] == "routeros-mcp"

    # Tools should work regardless of client
    tools_response = await client.call_method("tools/list")
    assert len(tools_response["result"]["tools"]) > 0

    await client.close()
```

---

## LLM-in-the-Loop Testing Strategy

### Overview

Following MCP best practices, test not just functionality but also **LLM usability** - whether AI models can discover, understand, and correctly use the tools.

### Tool Selection Testing

**Purpose:** Verify LLMs select the correct tool for user intents

```python
# tests/llm/test_tool_selection.py

import pytest
from routeros_mcp.testing.llm_simulator import LLMSimulator

@pytest.mark.asyncio
async def test_llm_selects_correct_tool_for_device_list():
    """Verify LLM chooses registry/list for 'show me all devices'."""
    simulator = LLMSimulator()

    user_intent = "Show me all devices"
    selected_tool = await simulator.select_tool(user_intent, available_tools=all_mcp_tools)

    assert selected_tool.name == "registry/list"
    assert "device_id" not in selected_tool.parameters  # Should not ask for device_id


@pytest.mark.asyncio
async def test_llm_selects_correct_tool_for_interface_stats():
    """Verify LLM chooses interface/list for interface information."""
    simulator = LLMSimulator()

    user_intent = "What interfaces does dev-lab-01 have?"
    selected_tool = await simulator.select_tool(user_intent, available_tools=all_mcp_tools)

    assert selected_tool.name == "interface/list"
    assert selected_tool.parameters["device_id"] == "dev-lab-01"
```

### Tool Description Quality Testing

**Purpose:** Validate intent-based descriptions guide LLM correctly

```python
@pytest.mark.asyncio
async def test_tool_description_clarity():
    """Verify tool descriptions are clear and intent-based."""
    tools = await mcp_server.list_tools()

    for tool in tools:
        description = tool["description"]

        # Must include "Use when" guidance
        assert "Use when:" in description or "use when" in description.lower(), \
            f"Tool {tool['name']} missing 'Use when' guidance"

        # Must not be overly verbose (token-conscious)
        assert len(description) < 2000, \
            f"Tool {tool['name']} description too long ({len(description)} chars)"

        # Must include return value description
        assert "Returns:" in description or "returns" in description.lower(), \
            f"Tool {tool['name']} missing return value description"
```

### Synthetic Workload Generation

**Purpose:** Generate realistic user scenarios to test tool chain execution

```python
# tests/llm/test_workflows.py

@pytest.mark.asyncio
async def test_workflow_device_onboarding():
    """Test complete device onboarding workflow."""
    simulator = LLMSimulator()

    user_request = "Add a new lab router at 192.168.1.10 named lab-router-01"

    # LLM should execute this tool chain:
    expected_chain = [
        ("registry/add", {"name": "lab-router-01", "management_address": "192.168.1.10:443", ...}),
        ("system/get-overview", {"device_id": "lab-router-01"}),
        ("health/check", {"device_id": "lab-router-01"})
    ]

    actual_chain = await simulator.execute_workflow(user_request, mcp_server)

    assert len(actual_chain) == len(expected_chain)
    for (expected_tool, _), (actual_tool, _) in zip(expected_chain, actual_chain):
        assert actual_tool == expected_tool


@pytest.mark.asyncio
async def test_workflow_troubleshooting():
    """Test troubleshooting workflow."""
    simulator = LLMSimulator()

    user_request = "Why is dev-lab-01 not responding?"

    # Expected tool chain for troubleshooting
    actual_chain = await simulator.execute_workflow(user_request, mcp_server)

    # Should check health first
    assert actual_chain[0][0] == "health/get"

    # Should check device overview
    assert "system/get-overview" in [tool for tool, _ in actual_chain]

    # Should not attempt writes (tier enforcement)
    write_tools = ["interface/configure", "system/reboot", "config/apply"]
    for tool, _ in actual_chain:
        assert tool not in write_tools
```

### Tool Parameter Validation Testing

**Purpose:** Verify LLMs provide valid parameters based on schema

```python
@pytest.mark.asyncio
async def test_llm_respects_parameter_types():
    """Verify LLM provides correctly typed parameters."""
    simulator = LLMSimulator()

    user_request = "List interfaces on dev-lab-01"

    tool_call = await simulator.select_tool_with_params(user_request, all_mcp_tools)

    # Verify correct types
    assert isinstance(tool_call.parameters["device_id"], str)
    if "disabled" in tool_call.parameters:
        assert isinstance(tool_call.parameters["disabled"], bool)


@pytest.mark.asyncio
async def test_llm_handles_required_vs_optional_params():
    """Verify LLM distinguishes required from optional parameters."""
    simulator = LLMSimulator()

    user_request = "Check health of dev-lab-01"

    tool_call = await simulator.select_tool_with_params(user_request, all_mcp_tools)

    # Required parameter must be present
    assert "device_id" in tool_call.parameters

    # Optional parameters may or may not be present
    if "include_history" in tool_call.parameters:
        assert isinstance(tool_call.parameters["include_history"], bool)
```

### Error Recovery Testing

**Purpose:** Verify LLMs can recover from errors with actionable error messages

```python
@pytest.mark.asyncio
async def test_llm_recovers_from_not_found_error():
    """Verify LLM handles device not found and retries correctly."""
    simulator = LLMSimulator()

    # Initial request with wrong device ID
    user_request = "Get overview of dev-nonexistent"

    result = await simulator.execute_with_recovery(user_request, mcp_server)

    # Should get NOT_FOUND error with suggestions
    assert result.first_error.code == -32003
    assert "registry/list" in result.first_error.suggestions

    # Should recover by listing available devices
    assert result.recovery_action == "list_devices"
    assert result.second_attempt_tool == "registry/list"

    # Should succeed on second attempt with correct device
    assert result.final_success is True


@pytest.mark.asyncio
async def test_llm_recovers_from_forbidden_error():
    """Verify LLM handles tier permission errors."""
    simulator = LLMSimulator()

    user_request = "Reboot dev-prod-01"

    result = await simulator.execute_with_recovery(user_request, mcp_server)

    # Should get FORBIDDEN error
    assert result.first_error.code == -32002
    assert "allow_advanced_writes" in result.first_error.details

    # Should understand it needs different device or permission change
    assert result.recovery_action in ["choose_different_device", "request_permission"]
```

### Prompt Engineering Validation

**Purpose:** Validate prompts guide LLMs through complex workflows

```python
@pytest.mark.asyncio
async def test_prompt_guides_firmware_upgrade_workflow():
    """Verify firmware upgrade prompt provides clear guidance."""
    simulator = LLMSimulator()

    prompt = await mcp_server.get_prompt("device_firmware_upgrade")

    # Simulate LLM following prompt
    result = await simulator.follow_prompt(
        prompt=prompt,
        context={"device_id": "dev-lab-01"},
        mcp_server=mcp_server
    )

    # Verify workflow steps executed in correct order
    expected_steps = [
        "snapshot/create-pre-upgrade",
        "system/get-packages",
        "firmware/check-compatibility",
        "plan/create",
        "plan/apply"
    ]

    assert len(result.steps) == len(expected_steps)
    for expected, actual in zip(expected_steps, result.steps):
        assert expected in actual.tool_name


@pytest.mark.asyncio
async def test_prompt_includes_safety_warnings():
    """Verify prompts include appropriate safety warnings."""
    simulator = LLMSimulator()

    prompt = await mcp_server.get_prompt("device_firmware_upgrade")

    # Check for safety warnings in prompt
    assert "backup" in prompt.content.lower()
    assert "lab" in prompt.content.lower() or "testing" in prompt.content.lower()
    assert "rollback" in prompt.content.lower()

    # Verify LLM respects warnings
    result = await simulator.follow_prompt(prompt, {"device_id": "dev-prod-01"})

    # Should create backup before upgrade
    assert any("snapshot/create" in step.tool_name for step in result.steps)
```

### Tool Description Metrics

Track and improve tool description quality:

```python
# tests/llm/test_description_metrics.py

@pytest.mark.asyncio
async def test_tool_discovery_accuracy():
    """Measure how often LLM selects correct tool for intent."""
    simulator = LLMSimulator()

    test_scenarios = [
        ("Show all devices", "registry/list"),
        ("Get health of dev-lab-01", "health/get"),
        ("List interfaces on dev-lab-01", "interface/list"),
        ("Check logs on dev-lab-01", "system/get-logs"),
        # ... 40+ more scenarios
    ]

    correct = 0
    total = len(test_scenarios)

    for user_intent, expected_tool in test_scenarios:
        selected_tool = await simulator.select_tool(user_intent, all_mcp_tools)
        if selected_tool.name == expected_tool:
            correct += 1

    accuracy = correct / total
    assert accuracy >= 0.90, f"Tool selection accuracy {accuracy:.2%} below 90% threshold"


@pytest.mark.asyncio
async def test_parameter_inference_accuracy():
    """Measure how often LLM provides correct parameters."""
    simulator = LLMSimulator()

    test_scenarios = [
        ("Get health of dev-lab-01", {"device_id": "dev-lab-01"}),
        ("List disabled interfaces on dev-lab-01", {"device_id": "dev-lab-01", "disabled": True}),
        # ... more scenarios
    ]

    correct = 0
    total = len(test_scenarios)

    for user_intent, expected_params in test_scenarios:
        tool_call = await simulator.select_tool_with_params(user_intent, all_mcp_tools)
        if tool_call.parameters == expected_params:
            correct += 1

    accuracy = correct / total
    assert accuracy >= 0.85, f"Parameter inference accuracy {accuracy:.2%} below 85% threshold"
```

### LLM Testing Infrastructure

```python
# routeros_mcp/testing/llm_simulator.py

from typing import List, Dict, Any
import anthropic

class LLMSimulator:
    """Simulate LLM behavior for testing MCP tools.

    Uses real LLM (Claude) to test tool selection and usage.
    """

    def __init__(self, model: str = "claude-3-5-sonnet-20241022"):
        self.client = anthropic.Anthropic()
        self.model = model

    async def select_tool(self, user_intent: str, available_tools: List[Dict]) -> Dict:
        """Let LLM select tool for user intent."""
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            tools=available_tools,
            messages=[{"role": "user", "content": user_intent}]
        )

        # Extract tool selection from response
        if response.stop_reason == "tool_use":
            tool_use = next(block for block in response.content if block.type == "tool_use")
            return {
                "name": tool_use.name,
                "parameters": tool_use.input
            }

        raise ValueError(f"LLM did not select a tool. Response: {response}")

    async def execute_workflow(
        self,
        user_request: str,
        mcp_server
    ) -> List[tuple[str, Dict[str, Any]]]:
        """Execute complete workflow with tool chaining."""
        # Implementation: Let LLM execute multi-step workflow
        pass

    async def execute_with_recovery(self, user_request: str, mcp_server):
        """Execute request and test error recovery."""
        # Implementation: Test error handling and recovery
        pass
```

### LLM Testing Best Practices

1. **Use Real LLMs**: Test with actual Claude/GPT models, not mocks
2. **Measure Metrics**: Track tool selection accuracy, parameter accuracy, workflow success rate
3. **Iterate on Descriptions**: Improve descriptions based on LLM behavior
4. **Test Error Recovery**: Verify LLMs understand actionable error messages
5. **Validate Prompts**: Ensure prompts guide LLMs through complex workflows
6. **Test Multiple Models**: Validate across Claude, GPT-4, and other LLMs

### Implementation Checklist

- [ ] LLM simulator implemented for testing
- [ ] Tool selection accuracy tests (target: 90%+)
- [ ] Parameter inference accuracy tests (target: 85%+)
- [ ] Workflow execution tests for common scenarios
- [ ] Error recovery tests with actionable error messages
- [ ] Prompt engineering validation tests
- [ ] Description quality metrics tracked
- [ ] Multi-model compatibility tests (Claude, GPT-4, Mistral)

---

## Summary: TDD and Testing Best Practices

### TDD Workflow Checklist

- [ ] Write failing test first (RED)
- [ ] Implement minimal code to pass (GREEN)
- [ ] Refactor while keeping tests passing
- [ ] Test both success and error paths
- [ ] Use descriptive test names
- [ ] One assertion per test (guideline)
- [ ] Test behavior, not implementation
- [ ] Achieve 85%+ overall coverage
- [ ] Achieve 100% coverage on core modules
- [ ] Run tests frequently during development

### Testing Strategy Summary

✅ **Unit tests** - Fast, isolated, pure logic
✅ **Integration tests** - Components working together
✅ **Lab tests** - Real RouterOS devices
✅ **E2E tests** - Complete MCP workflows
✅ **MCP protocol tests** - JSON-RPC 2.0 compliance, capability negotiation, schema validation
✅ **MCP transport tests** - Stdio and HTTP/SSE modes
✅ **MCP safety tests** - Rate limiting, concurrency limits, timeouts, malformed requests
✅ **Client compatibility** - Multiple MCP clients, protocol versions
✅ **Mocks** - External dependencies only (RouterOS, OAuth, MCP clients)
✅ **Coverage** - 85% overall, 100% core modules
✅ **TDD** - Test-first development
✅ **Regression** - RouterOS version compatibility matrix
✅ **Smoke tests** - Post-deployment validation
✅ **Health checks** - Continuous monitoring

### MCP-Specific Testing Highlights

**MCP Protocol Compliance:**
- JSON-RPC 2.0 message format validation
- Initialize handshake sequencing
- Capability negotiation (tools, resources, prompts)
- Error code mapping (-32600 to -32603)
- Tool schema validation (JSON Schema Draft 7)

**MCP Tool Testing:**
- Schema validation for all tools
- Token estimation accuracy
- Tool tier enforcement (free, basic, professional)
- Metadata validation (tier, estimated_tokens)
- Input validation and error responses

**MCP Transport Testing:**
- Stdio transport (process lifecycle, stdio buffering)
- HTTP/SSE transport (concurrent connections, session management)
- Transport mode switching
- Graceful degradation

**MCP Safety Nets:**
- Rate limiting (per-tier limits)
- Concurrent execution limits (prevent resource exhaustion)
- Tool execution timeouts (prevent hanging)
- Malformed request handling (parse errors, invalid JSON-RPC)
- Token budget warnings (prevent LLM context overflow)

**Cross-references:**
- See [Doc 04 (MCP Tools Interface)](04-mcp-tools-interface-and-json-schema-specification.md) for tool JSON schemas
- See [Doc 08 (Observability)](08-observability-logging-metrics-and-diagnostics.md) for test metrics and monitoring
- See [Doc 09 (Operations)](09-operations-deployment-self-update-and-runbook.md) for CI/CD testing integration
- See [Doc 00 (Overview)](00-overview-and-objectives.md) for MCP protocol architecture

**This comprehensive testing strategy ensures confidence in correctness, safety, and reliability of the RouterOS MCP service across all MCP protocol features and operational scenarios.**
