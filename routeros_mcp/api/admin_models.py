"""Request/Response models for admin API."""

from pydantic import BaseModel, Field


class RejectionRequest(BaseModel):
    """Request to reject a plan."""

    reason: str = Field(..., description="Reason for rejection")
