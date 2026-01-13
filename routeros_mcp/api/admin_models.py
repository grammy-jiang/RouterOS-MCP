"""Request/Response models for admin API."""

from typing import Literal
from pydantic import BaseModel, Field


class RejectionRequest(BaseModel):
    """Request to reject a plan."""

    reason: str = Field(..., description="Reason for rejection")


class DeviceCreateRequest(BaseModel):
    """Request to create a new device."""

    name: str = Field(..., description="Human-friendly device name")
    hostname: str = Field(..., description="Management IP address or hostname")
    username: str = Field(..., description="REST API username")
    password: str = Field(..., description="REST API password")
    environment: Literal["lab", "staging", "prod"] = Field(
        default="lab", description="Environment (lab/staging/prod)"
    )
    port: int = Field(default=443, ge=1, le=65535, description="Management port")


class DeviceUpdateRequest(BaseModel):
    """Request to update a device."""

    name: str | None = Field(default=None, description="Human-friendly device name")
    hostname: str | None = Field(default=None, description="Management IP address or hostname")
    username: str | None = Field(default=None, description="REST API username")
    password: str | None = Field(default=None, description="REST API password (leave empty to keep existing)")
    environment: Literal["lab", "staging", "prod"] | None = Field(
        default=None, description="Environment (lab/staging/prod)"
    )
    port: int | None = Field(default=None, ge=1, le=65535, description="Management port")


class UserCreateRequest(BaseModel):
    """Request to create a new user."""

    sub: str = Field(..., description="OIDC subject identifier (unique user ID)")
    email: str | None = Field(default=None, description="User email address")
    display_name: str | None = Field(default=None, description="User display name")
    role_name: str = Field(..., description="Role name to assign")
    device_scopes: list[str] = Field(
        default_factory=list,
        description="Device IDs user can access (empty = full access)"
    )
    is_active: bool = Field(default=True, description="Whether user is active")


class UserUpdateRequest(BaseModel):
    """Request to update a user."""

    email: str | None = Field(default=None, description="User email address")
    display_name: str | None = Field(default=None, description="User display name")
    role_name: str | None = Field(default=None, description="Role name to assign")
    device_scopes: list[str] | None = Field(default=None, description="Device IDs user can access")
    is_active: bool | None = Field(default=None, description="Whether user is active")


class DeviceScopesUpdateRequest(BaseModel):
    """Request to bulk update device scopes for a user."""

    device_scopes: list[str] = Field(
        ...,
        description="Device IDs user can access (empty = full access)"
    )
