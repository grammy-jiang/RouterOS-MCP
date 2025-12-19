"""Domain-specific exceptions for RouterOS MCP.

Domain exceptions represent business rule violations and are separate from
infrastructure (RouterOS client) and MCP protocol errors. These exceptions
should be caught and converted to appropriate MCP errors at the tool layer.
"""


class DomainError(Exception):
    """Base exception for domain layer errors.
    
    Domain errors represent violations of business rules or constraints
    that are enforced at the service layer.
    """

    def __init__(self, message: str, *, context: dict | None = None) -> None:
        """Initialize domain error.
        
        Args:
            message: Human-readable error message
            context: Additional context about the error
        """
        self.message = message
        self.context = context or {}
        super().__init__(message)


class CapabilityNotAllowedError(DomainError):
    """Raised when a device operation requires a capability flag that is not enabled.
    
    This exception enforces Phase 3 safety guardrails by preventing advanced
    write operations on devices that have not been explicitly authorized.
    
    Context should include:
        - device_id: The device identifier
        - environment: Device environment (lab/staging/prod)
        - required_capability: The capability flag that was required
        - current_value: Current value of the capability flag (typically False)
        - allowed_environments: Environments where operation is permitted
        
    Example:
        raise CapabilityNotAllowedError(
            "Firewall writes require 'allow_firewall_writes' capability flag",
            context={
                "device_id": "dev-prod-01",
                "environment": "prod",
                "required_capability": "allow_firewall_writes",
                "current_value": False,
                "allowed_environments": ["lab", "staging"],
            }
        )
    """

    pass


class EnvironmentNotAllowedError(DomainError):
    """Raised when an operation is attempted on a device in a restricted environment.
    
    This exception enforces environment-based restrictions where certain operations
    are only permitted in lab/staging environments and blocked in production.
    
    Context should include:
        - device_id: The device identifier
        - device_environment: The device's environment
        - allowed_environments: List of environments where operation is permitted
        - operation: The operation that was attempted
        
    Example:
        raise EnvironmentNotAllowedError(
            "Firewall writes are only allowed in lab/staging environments",
            context={
                "device_id": "dev-prod-01",
                "device_environment": "prod",
                "allowed_environments": ["lab", "staging"],
                "operation": "firewall_write",
            }
        )
    """

    pass
