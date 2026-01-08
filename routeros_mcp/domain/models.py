"""Domain models for RouterOS MCP.

Pydantic models representing domain entities and DTOs for service layer.
These are separate from SQLAlchemy ORM models to maintain clean separation
between domain and infrastructure layers.
"""

import ipaddress
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator


# Device Capability Flag Constants (Phase 3)
# These flags control access to advanced write operations on RouterOS devices.
# All flags default to False for safety, especially on production devices.

class DeviceCapability(str, Enum):
    """Device capability flags for Phase 3 safety guardrails.
    
    These flags control which high-risk operations are permitted on a device.
    All capabilities default to False unless explicitly enabled.
    
    Phase 3 capabilities (expert workflows):
        - PROFESSIONAL_WORKFLOWS: Enable all professional-tier plan/apply workflows
        - FIREWALL_WRITES: Enable firewall filter/NAT rule writes
        - ROUTING_WRITES: Enable static route and routing policy writes
        - WIRELESS_WRITES: Enable wireless/RF configuration writes
        - DHCP_WRITES: Enable DHCP server configuration writes
        - BRIDGE_WRITES: Enable bridge and VLAN configuration writes
    
    Phase 4 capabilities (diagnostics):
        - BANDWIDTH_TEST: Allow device to be target of bandwidth tests (high resource usage)
    """

    # Core professional tier access
    PROFESSIONAL_WORKFLOWS = "allow_professional_workflows"
    
    # Topic-specific write capabilities (Phase 3)
    FIREWALL_WRITES = "allow_firewall_writes"
    ROUTING_WRITES = "allow_routing_writes"
    WIRELESS_WRITES = "allow_wireless_writes"
    DHCP_WRITES = "allow_dhcp_writes"
    BRIDGE_WRITES = "allow_bridge_writes"
    
    # Phase 4 diagnostics capabilities
    BANDWIDTH_TEST = "allow_bandwidth_test"


# Environment types for device deployment
ENVIRONMENT_LAB = "lab"
ENVIRONMENT_STAGING = "staging"
ENVIRONMENT_PROD = "prod"

# Default allowed environments for Phase 3 expert workflows (lab/staging only)
PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS = [ENVIRONMENT_LAB, ENVIRONMENT_STAGING]


class PlanStatus(str, Enum):
    """Plan status state machine.
    
    Valid transitions:
    - pending → approved
    - pending → cancelled
    - approved → executing
    - approved → cancelled
    - executing → completed
    - executing → failed
    - executing → cancelled
    - executing → rolling_back (Phase 4)
    - rolling_back → rolled_back (Phase 4)
    """
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLING_BACK = "rolling_back"  # Phase 4: Rollback in progress
    ROLLED_BACK = "rolled_back"    # Phase 4: Rollback completed


class HealthStatus(str, Enum):
    """Device health status for adaptive polling (Phase 4).
    
    Used to track device health state and adjust polling intervals.
    
    States:
    - HEALTHY: Device responding normally, all metrics within thresholds
    - DEGRADED: Device responding but with warnings or threshold violations
    - UNREACHABLE: Device not responding to health checks
    """
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNREACHABLE = "unreachable"


class ToolHint(BaseModel):
    """Structured hint for tool responses.

    Hints provide actionable guidance to users based on detected device capabilities
    or configurations. They are designed to be both machine-readable and user-friendly.

    Attributes:
        code: Machine-readable identifier for the hint type (e.g., 'capsman_detected')
        message: Human-readable guidance message
    """

    code: str = Field(..., description="Stable machine-readable hint identifier")
    message: str = Field(..., description="Human-readable guidance message")


class DeviceCreate(BaseModel):
    """DTO for creating a new device."""

    id: str = Field(..., description="Unique device identifier (e.g., 'dev-lab-01')")
    name: str | None = Field(default=None, description="Human-friendly device name")
    management_ip: str = Field(..., description="Management IP address (IPv4 or IPv6)")
    management_port: int = Field(default=443, ge=1, le=65535, description="Management port (1-65535)")
    environment: Literal["lab", "staging", "prod"] = Field(..., description="Environment")
    tags: dict[str, str] = Field(default_factory=dict, description="Device tags")
    
    # Phase 2 capability flags
    allow_advanced_writes: bool = Field(default=False, description="Allow advanced writes")
    allow_professional_workflows: bool = Field(default=False, description="Allow professional workflows")
    
    # Phase 3 topic-specific capability flags
    allow_firewall_writes: bool = Field(default=False, description="Allow firewall writes")
    allow_routing_writes: bool = Field(default=False, description="Allow routing writes")
    allow_wireless_writes: bool = Field(default=False, description="Allow wireless writes")
    allow_dhcp_writes: bool = Field(default=False, description="Allow DHCP writes")
    allow_bridge_writes: bool = Field(default=False, description="Allow bridge writes")
    
    # Phase 4 diagnostics capability flags
    allow_bandwidth_test: bool = Field(default=False, description="Allow bandwidth test (target device)")
    
    # Phase 4 adaptive polling fields
    critical: bool = Field(default=False, description="Critical device (30s polling) vs non-critical (60s)")

    @field_validator("management_ip")
    @classmethod
    def validate_ip_address(cls, v: str) -> str:
        """Validate IP address format (IPv4 or IPv6)."""
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid IP address: '{v}'. Must be a valid IPv4 or IPv6 address.")


class DeviceUpdate(BaseModel):
    """DTO for updating device information."""

    name: str | None = None
    management_ip: str | None = None
    management_port: int | None = Field(default=None, ge=1, le=65535)
    tags: dict[str, str] | None = None
    
    # Phase 2 capability flags
    allow_advanced_writes: bool | None = None
    allow_professional_workflows: bool | None = None
    
    # Phase 3 topic-specific capability flags
    allow_firewall_writes: bool | None = None
    allow_routing_writes: bool | None = None
    allow_wireless_writes: bool | None = None
    allow_dhcp_writes: bool | None = None
    allow_bridge_writes: bool | None = None
    
    # Phase 4 diagnostics capability flags
    allow_bandwidth_test: bool | None = None
    
    # Phase 4 adaptive polling fields
    critical: bool | None = None
    
    status: Literal["healthy", "degraded", "unreachable", "pending", "decommissioned"] | None = None

    @field_validator("management_ip")
    @classmethod
    def validate_ip_address(cls, v: str | None) -> str | None:
        """Validate IP address format (IPv4 or IPv6)."""
        if v is None:
            return v
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            raise ValueError(f"Invalid IP address: '{v}'. Must be a valid IPv4 or IPv6 address.")


class Device(BaseModel):
    """Domain model for a RouterOS device."""

    id: str
    name: str
    management_ip: str
    management_port: int
    environment: Literal["lab", "staging", "prod"]
    status: Literal["healthy", "degraded", "unreachable", "pending", "decommissioned"]
    tags: dict[str, str]

    # Phase 2 capability flags
    allow_advanced_writes: bool
    allow_professional_workflows: bool

    # Phase 3 topic-specific capability flags
    allow_firewall_writes: bool = False
    allow_routing_writes: bool = False
    allow_wireless_writes: bool = False
    allow_dhcp_writes: bool = False
    allow_bridge_writes: bool = False
    
    # Phase 4 diagnostics capability flags
    allow_bandwidth_test: bool = False
    
    # Phase 4 adaptive polling fields
    critical: bool = Field(default=False)
    health_status: Literal["healthy", "degraded", "unreachable"] = Field(default="healthy")
    consecutive_healthy_checks: int = Field(default=0)
    polling_interval_seconds: int = Field(default=60)

    # RouterOS metadata
    routeros_version: str | None = None
    system_identity: str | None = None
    hardware_model: str | None = None
    serial_number: str | None = None
    software_id: str | None = None

    # Timestamps
    last_seen_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
    
    @field_validator("allow_bandwidth_test", "critical", mode="before")
    @classmethod
    def validate_bool_with_none(cls, v: bool | None) -> bool:
        """Handle None values from ORM by returning default False."""
        return v if v is not None else False
    
    @field_validator("health_status", mode="before")
    @classmethod
    def validate_health_status_with_none(cls, v: str | None) -> str:
        """Handle None values from ORM by returning default 'healthy'."""
        return v if v is not None else "healthy"
    
    @field_validator("consecutive_healthy_checks", mode="before")
    @classmethod
    def validate_consecutive_healthy_checks_with_none(cls, v: int | None) -> int:
        """Handle None values from ORM by returning default 0."""
        return v if v is not None else 0
    
    @field_validator("polling_interval_seconds", mode="before")
    @classmethod
    def validate_polling_interval_seconds_with_none(cls, v: int | None) -> int:
        """Handle None values from ORM by returning default 60."""
        return v if v is not None else 60


class CredentialCreate(BaseModel):
    """DTO for creating device credentials."""

    device_id: str = Field(..., description="Device ID")
    credential_type: Literal["rest", "ssh"] = Field(..., description="Credential type")
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password (will be encrypted)")


class HealthCheckResult(BaseModel):
    """Health check result for a device."""

    device_id: str
    status: Literal["healthy", "degraded", "unreachable"]
    timestamp: datetime

    # System metrics
    cpu_usage_percent: float | None = None
    memory_usage_percent: float | None = None
    uptime_seconds: int | None = None

    # Health indicators
    issues: list[str] = Field(default_factory=list, description="List of health issues")
    warnings: list[str] = Field(default_factory=list, description="List of warnings")

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class HealthSummary(BaseModel):
    """Summary of device or fleet health."""

    overall_status: Literal["healthy", "degraded", "unreachable"]
    timestamp: datetime

    # Per-device results (for fleet health)
    devices: list[HealthCheckResult] = Field(default_factory=list)

    # Aggregate statistics
    total_devices: int = 0
    healthy_count: int = 0
    degraded_count: int = 0
    unreachable_count: int = 0


class SystemResource(BaseModel):
    """Normalized system resource metrics."""

    device_id: str
    timestamp: datetime

    # Version and identity
    routeros_version: str
    system_identity: str | None = None
    hardware_model: str | None = None

    # Performance
    uptime_seconds: int
    cpu_usage_percent: float
    cpu_count: int

    # Memory
    memory_total_bytes: int
    memory_free_bytes: int
    memory_used_bytes: int
    memory_usage_percent: float

    # Disk (optional)
    disk_total_bytes: int | None = None
    disk_free_bytes: int | None = None
