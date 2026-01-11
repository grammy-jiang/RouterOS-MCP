"""Tests for NotificationService.

Tests cover:
- Mock backend functionality
- Email template generation
- Approval notifications (requested, approved, rejected)
- Job execution notifications (completed, failed)
- SMTP backend configuration (mocked)
"""

import pytest

from routeros_mcp.domain.services.notification import (
    EmailNotification,
    MockNotificationBackend,
    NotificationService,
    SMTPNotificationBackend,
    create_notification_service,
)


# ==================== Test: Mock Backend ====================


@pytest.mark.asyncio
async def test_mock_backend_send_email() -> None:
    """Test mock backend stores emails in memory."""
    backend = MockNotificationBackend()

    notification = EmailNotification(
        to_address="user@example.com",
        subject="Test Subject",
        body_text="Test body text",
    )

    result = await backend.send_email(notification)

    assert result is True
    assert len(backend.sent_notifications) == 1
    assert backend.sent_notifications[0].to_address == "user@example.com"
    assert backend.sent_notifications[0].subject == "Test Subject"
    assert backend.sent_notifications[0].body_text == "Test body text"


@pytest.mark.asyncio
async def test_mock_backend_clear() -> None:
    """Test mock backend can clear stored notifications."""
    backend = MockNotificationBackend()

    notification = EmailNotification(
        to_address="user@example.com",
        subject="Test",
        body_text="Test",
    )

    await backend.send_email(notification)
    assert len(backend.sent_notifications) == 1

    backend.clear()
    assert len(backend.sent_notifications) == 0


@pytest.mark.asyncio
async def test_mock_backend_multiple_emails() -> None:
    """Test mock backend stores multiple emails."""
    backend = MockNotificationBackend()

    for i in range(3):
        notification = EmailNotification(
            to_address=f"user{i}@example.com",
            subject=f"Test {i}",
            body_text=f"Body {i}",
        )
        await backend.send_email(notification)

    assert len(backend.sent_notifications) == 3
    assert backend.sent_notifications[0].to_address == "user0@example.com"
    assert backend.sent_notifications[1].to_address == "user1@example.com"
    assert backend.sent_notifications[2].to_address == "user2@example.com"


# ==================== Test: NotificationService - Approval Requested ====================


@pytest.mark.asyncio
async def test_send_approval_requested_success() -> None:
    """Test sending approval requested notification."""
    backend = MockNotificationBackend()
    service = NotificationService(backend=backend, from_address="noreply@example.com")

    result = await service.send_approval_requested(
        to_address="approver@example.com",
        plan_id="plan-123",
        requested_by="user-requester",
        plan_summary="Update firewall rules",
        notes="Urgent request",
    )

    assert result is True
    assert len(backend.sent_notifications) == 1

    notification = backend.sent_notifications[0]
    assert notification.to_address == "approver@example.com"
    assert "plan-123" in notification.subject
    assert "plan-123" in notification.body_text
    assert "user-requester" in notification.body_text
    assert "Update firewall rules" in notification.body_text
    assert "Urgent request" in notification.body_text


@pytest.mark.asyncio
async def test_send_approval_requested_without_notes() -> None:
    """Test sending approval requested notification without notes."""
    backend = MockNotificationBackend()
    service = NotificationService(backend=backend)

    result = await service.send_approval_requested(
        to_address="approver@example.com",
        plan_id="plan-123",
        requested_by="user-requester",
        plan_summary="Update firewall rules",
    )

    assert result is True
    notification = backend.sent_notifications[0]
    assert "Urgent request" not in notification.body_text


# ==================== Test: NotificationService - Approval Approved ====================


@pytest.mark.asyncio
async def test_send_approval_approved_success() -> None:
    """Test sending approval approved notification."""
    backend = MockNotificationBackend()
    service = NotificationService(backend=backend)

    result = await service.send_approval_approved(
        to_address="requester@example.com",
        plan_id="plan-123",
        approved_by="user-approver",
        plan_summary="Update firewall rules",
        notes="Approved with conditions",
    )

    assert result is True
    assert len(backend.sent_notifications) == 1

    notification = backend.sent_notifications[0]
    assert notification.to_address == "requester@example.com"
    assert "plan-123" in notification.subject
    assert "Approved" in notification.subject
    assert "plan-123" in notification.body_text
    assert "user-approver" in notification.body_text
    assert "Update firewall rules" in notification.body_text
    assert "Approved with conditions" in notification.body_text


@pytest.mark.asyncio
async def test_send_approval_approved_without_notes() -> None:
    """Test sending approval approved notification without notes."""
    backend = MockNotificationBackend()
    service = NotificationService(backend=backend)

    result = await service.send_approval_approved(
        to_address="requester@example.com",
        plan_id="plan-123",
        approved_by="user-approver",
        plan_summary="Update firewall rules",
    )

    assert result is True
    notification = backend.sent_notifications[0]
    assert "Approved with conditions" not in notification.body_text


# ==================== Test: NotificationService - Approval Rejected ====================


@pytest.mark.asyncio
async def test_send_approval_rejected_success() -> None:
    """Test sending approval rejected notification."""
    backend = MockNotificationBackend()
    service = NotificationService(backend=backend)

    result = await service.send_approval_rejected(
        to_address="requester@example.com",
        plan_id="plan-123",
        rejected_by="user-approver",
        plan_summary="Update firewall rules",
        notes="Insufficient justification",
    )

    assert result is True
    assert len(backend.sent_notifications) == 1

    notification = backend.sent_notifications[0]
    assert notification.to_address == "requester@example.com"
    assert "plan-123" in notification.subject
    assert "Rejected" in notification.subject
    assert "plan-123" in notification.body_text
    assert "user-approver" in notification.body_text
    assert "Update firewall rules" in notification.body_text
    assert "Insufficient justification" in notification.body_text


@pytest.mark.asyncio
async def test_send_approval_rejected_without_notes() -> None:
    """Test sending approval rejected notification without notes."""
    backend = MockNotificationBackend()
    service = NotificationService(backend=backend)

    result = await service.send_approval_rejected(
        to_address="requester@example.com",
        plan_id="plan-123",
        rejected_by="user-approver",
        plan_summary="Update firewall rules",
    )

    assert result is True
    notification = backend.sent_notifications[0]
    assert "Insufficient justification" not in notification.body_text


# ==================== Test: NotificationService - Job Executed ====================


@pytest.mark.asyncio
async def test_send_job_executed_completed() -> None:
    """Test sending job execution completed notification."""
    backend = MockNotificationBackend()
    service = NotificationService(backend=backend)

    result = await service.send_job_executed(
        to_address="operator@example.com",
        job_id="job-456",
        plan_id="plan-123",
        job_type="apply_plan",
        status="completed",
        result_summary="Successfully applied to 3/3 devices",
    )

    assert result is True
    assert len(backend.sent_notifications) == 1

    notification = backend.sent_notifications[0]
    assert notification.to_address == "operator@example.com"
    assert "job-456" in notification.subject
    assert "Completed Successfully" in notification.subject
    assert "job-456" in notification.body_text
    assert "plan-123" in notification.body_text
    assert "apply_plan" in notification.body_text
    assert "completed" in notification.body_text
    assert "Successfully applied to 3/3 devices" in notification.body_text


@pytest.mark.asyncio
async def test_send_job_executed_failed() -> None:
    """Test sending job execution failed notification."""
    backend = MockNotificationBackend()
    service = NotificationService(backend=backend)

    result = await service.send_job_executed(
        to_address="operator@example.com",
        job_id="job-456",
        plan_id=None,
        job_type="health_check",
        status="failed",
        result_summary="Device unreachable",
    )

    assert result is True
    assert len(backend.sent_notifications) == 1

    notification = backend.sent_notifications[0]
    assert notification.to_address == "operator@example.com"
    assert "job-456" in notification.subject
    assert "Failed" in notification.subject
    assert "job-456" in notification.body_text
    assert "plan-123" not in notification.body_text  # No plan ID
    assert "health_check" in notification.body_text
    assert "failed" in notification.body_text
    assert "Device unreachable" in notification.body_text


# ==================== Test: SMTP Backend Configuration ====================


def test_smtp_backend_initialization() -> None:
    """Test SMTP backend initializes with correct parameters."""
    backend = SMTPNotificationBackend(
        smtp_host="smtp.example.com",
        smtp_port=587,
        from_address="noreply@example.com",
        use_tls=True,
        username="user@example.com",
        password="secret",
        timeout=15.0,
    )

    assert backend.smtp_host == "smtp.example.com"
    assert backend.smtp_port == 587
    assert backend.from_address == "noreply@example.com"
    assert backend.use_tls is True
    assert backend.username == "user@example.com"
    assert backend.password == "secret"
    assert backend.timeout == 15.0


# ==================== Test: Factory Function ====================


def test_create_notification_service_disabled() -> None:
    """Test factory returns None when notifications disabled."""
    service = create_notification_service(enabled=False)
    assert service is None


def test_create_notification_service_mock_backend() -> None:
    """Test factory creates service with mock backend."""
    service = create_notification_service(
        enabled=True,
        backend_type="mock",
        from_address="test@example.com",
    )

    assert service is not None
    assert isinstance(service.backend, MockNotificationBackend)
    assert service.from_address == "test@example.com"


def test_create_notification_service_smtp_backend() -> None:
    """Test factory creates service with SMTP backend."""
    service = create_notification_service(
        enabled=True,
        backend_type="smtp",
        from_address="test@example.com",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_use_tls=False,
        smtp_username="user",
        smtp_password="pass",
        smtp_timeout=20.0,
    )

    assert service is not None
    assert isinstance(service.backend, SMTPNotificationBackend)
    assert service.from_address == "test@example.com"
    assert service.backend.smtp_host == "smtp.example.com"
    assert service.backend.smtp_port == 465
    assert service.backend.from_address == "test@example.com"
    assert service.backend.use_tls is False
    assert service.backend.username == "user"
    assert service.backend.password == "pass"
    assert service.backend.timeout == 20.0


# ==================== Test: Email Notification Dataclass ====================


def test_email_notification_with_html() -> None:
    """Test email notification with HTML body."""
    notification = EmailNotification(
        to_address="user@example.com",
        subject="Test",
        body_text="Plain text",
        body_html="<html><body>HTML</body></html>",
    )

    assert notification.to_address == "user@example.com"
    assert notification.subject == "Test"
    assert notification.body_text == "Plain text"
    assert notification.body_html == "<html><body>HTML</body></html>"


def test_email_notification_without_html() -> None:
    """Test email notification without HTML body."""
    notification = EmailNotification(
        to_address="user@example.com",
        subject="Test",
        body_text="Plain text",
    )

    assert notification.to_address == "user@example.com"
    assert notification.subject == "Test"
    assert notification.body_text == "Plain text"
    assert notification.body_html is None
