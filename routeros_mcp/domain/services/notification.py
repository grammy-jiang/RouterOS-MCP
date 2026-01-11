"""Notification service for email notifications.

This service implements notification delivery for approval requests and
job execution status, providing email templates and multiple backends
(SMTP for production, mock for testing).

See Phase 5 #9 requirements for detailed specifications.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


@dataclass
class EmailNotification:
    """Email notification message."""

    to_address: str
    subject: str
    body_text: str
    body_html: str | None = None


class NotificationBackend(ABC):
    """Abstract base class for notification backends."""

    @abstractmethod
    async def send_email(self, notification: EmailNotification) -> bool:
        """Send an email notification.

        Args:
            notification: Email notification to send

        Returns:
            True if sent successfully, False otherwise
        """
        pass


class MockNotificationBackend(NotificationBackend):
    """Mock notification backend for testing and development.

    Stores sent notifications in memory instead of actually sending them.
    """

    def __init__(self) -> None:
        """Initialize mock backend."""
        self.sent_notifications: list[EmailNotification] = []

    async def send_email(self, notification: EmailNotification) -> bool:
        """Store email notification in memory.

        Args:
            notification: Email notification to store

        Returns:
            True (always succeeds)
        """
        self.sent_notifications.append(notification)
        logger.info(
            f"Mock: Email notification queued to {notification.to_address}",
            extra={
                "to_address": notification.to_address,
                "subject": notification.subject,
            },
        )
        return True

    def clear(self) -> None:
        """Clear all stored notifications."""
        self.sent_notifications.clear()


class SMTPNotificationBackend(NotificationBackend):
    """SMTP email notification backend for production use."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        use_tls: bool = True,
        username: str | None = None,
        password: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        """Initialize SMTP backend.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            use_tls: Use STARTTLS for secure connection
            username: SMTP authentication username
            password: SMTP authentication password
            timeout: Connection timeout in seconds
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.use_tls = use_tls
        self.username = username
        self.password = password
        self.timeout = timeout

    async def send_email(self, notification: EmailNotification) -> bool:
        """Send email via SMTP.

        Args:
            notification: Email notification to send

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            import asyncio
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = notification.subject
            msg["To"] = notification.to_address

            # Attach text body
            msg.attach(MIMEText(notification.body_text, "plain"))

            # Attach HTML body if provided
            if notification.body_html:
                msg.attach(MIMEText(notification.body_html, "html"))

            # Send via SMTP (run in executor to avoid blocking)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_smtp, msg, notification.to_address)

            logger.info(
                f"Email sent to {notification.to_address}",
                extra={
                    "to_address": notification.to_address,
                    "subject": notification.subject,
                },
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send email to {notification.to_address}: {e}",
                extra={
                    "to_address": notification.to_address,
                    "subject": notification.subject,
                    "error": str(e),
                },
            )
            return False

    def _send_smtp(self, msg: "MIMEMultipart", to_address: str) -> None:
        """Send message via SMTP (blocking operation).

        Args:
            msg: Email message
            to_address: Recipient address
        """
        import smtplib

        if self.use_tls:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout)
            smtp.starttls()
        else:
            smtp = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=self.timeout)

        try:
            if self.username and self.password:
                smtp.login(self.username, self.password)

            smtp.sendmail(msg["From"] or "noreply@example.com", to_address, msg.as_string())
        finally:
            smtp.quit()


class NotificationService:
    """Service for sending notifications via email.

    Provides:
    - Email notifications for approval requests (created, approved, rejected)
    - Email notifications for job execution (started, completed, failed)
    - Template-based email generation
    - Support for multiple backends (SMTP, mock)
    """

    def __init__(
        self,
        backend: NotificationBackend,
        from_address: str = "routeros-mcp@example.com",
    ) -> None:
        """Initialize notification service.

        Args:
            backend: Notification backend to use
            from_address: Email address to use as sender
        """
        self.backend = backend
        self.from_address = from_address

    async def send_approval_requested(
        self,
        to_address: str,
        plan_id: str,
        requested_by: str,
        plan_summary: str,
        notes: str | None = None,
    ) -> bool:
        """Send notification when approval is requested.

        Args:
            to_address: Recipient email address
            plan_id: Plan requiring approval
            requested_by: User who requested approval
            plan_summary: Summary of plan changes
            notes: Optional notes from requester

        Returns:
            True if sent successfully, False otherwise
        """
        subject = f"Approval Requested for Plan {plan_id}"

        body_text = f"""
Approval Requested for RouterOS Configuration Plan

Plan ID: {plan_id}
Requested by: {requested_by}
Summary: {plan_summary}
"""
        if notes:
            body_text += f"\nNotes: {notes}"

        body_text += """

Please review and approve or reject this plan at your earliest convenience.
"""

        notification = EmailNotification(
            to_address=to_address,
            subject=subject,
            body_text=body_text.strip(),
        )

        return await self.backend.send_email(notification)

    async def send_approval_approved(
        self,
        to_address: str,
        plan_id: str,
        approved_by: str,
        plan_summary: str,
        notes: str | None = None,
    ) -> bool:
        """Send notification when approval is granted.

        Args:
            to_address: Recipient email address (requester)
            plan_id: Approved plan ID
            approved_by: User who approved the request
            plan_summary: Summary of plan changes
            notes: Optional notes from approver

        Returns:
            True if sent successfully, False otherwise
        """
        subject = f"Plan {plan_id} Approved"

        body_text = f"""
RouterOS Configuration Plan Approved

Plan ID: {plan_id}
Approved by: {approved_by}
Summary: {plan_summary}
"""
        if notes:
            body_text += f"\nApprover notes: {notes}"

        body_text += """

Your plan has been approved and is ready for execution.
"""

        notification = EmailNotification(
            to_address=to_address,
            subject=subject,
            body_text=body_text.strip(),
        )

        return await self.backend.send_email(notification)

    async def send_approval_rejected(
        self,
        to_address: str,
        plan_id: str,
        rejected_by: str,
        plan_summary: str,
        notes: str | None = None,
    ) -> bool:
        """Send notification when approval is rejected.

        Args:
            to_address: Recipient email address (requester)
            plan_id: Rejected plan ID
            rejected_by: User who rejected the request
            plan_summary: Summary of plan changes
            notes: Optional notes from rejector

        Returns:
            True if sent successfully, False otherwise
        """
        subject = f"Plan {plan_id} Rejected"

        body_text = f"""
RouterOS Configuration Plan Rejected

Plan ID: {plan_id}
Rejected by: {rejected_by}
Summary: {plan_summary}
"""
        if notes:
            body_text += f"\nRejection reason: {notes}"

        body_text += """

Your plan has been rejected. Please review the feedback and submit a revised plan.
"""

        notification = EmailNotification(
            to_address=to_address,
            subject=subject,
            body_text=body_text.strip(),
        )

        return await self.backend.send_email(notification)

    async def send_job_executed(
        self,
        to_address: str,
        job_id: str,
        plan_id: str | None,
        job_type: str,
        status: str,
        result_summary: str,
    ) -> bool:
        """Send notification when job execution completes.

        Args:
            to_address: Recipient email address
            job_id: Job ID
            plan_id: Associated plan ID (if any)
            job_type: Type of job executed
            status: Job status (completed/failed)
            result_summary: Summary of execution results

        Returns:
            True if sent successfully, False otherwise
        """
        status_text = "Completed Successfully" if status == "completed" else "Failed"
        subject = f"Job {job_id} {status_text}"

        body_text = f"""
RouterOS Job Execution {status_text}

Job ID: {job_id}
Job Type: {job_type}
Status: {status}
"""
        if plan_id:
            body_text += f"Plan ID: {plan_id}\n"

        body_text += f"""
Result: {result_summary}

This is an automated notification from RouterOS MCP Service.
"""

        notification = EmailNotification(
            to_address=to_address,
            subject=subject,
            body_text=body_text.strip(),
        )

        return await self.backend.send_email(notification)


def create_notification_service(
    enabled: bool = False,
    backend_type: str = "mock",
    from_address: str = "routeros-mcp@example.com",
    smtp_host: str = "localhost",
    smtp_port: int = 587,
    smtp_use_tls: bool = True,
    smtp_username: str | None = None,
    smtp_password: str | None = None,
    smtp_timeout: float = 10.0,
) -> NotificationService | None:
    """Create notification service from configuration.

    Args:
        enabled: Whether notifications are enabled
        backend_type: Backend type ("smtp" or "mock")
        from_address: Sender email address
        smtp_host: SMTP server hostname (for SMTP backend)
        smtp_port: SMTP server port (for SMTP backend)
        smtp_use_tls: Use STARTTLS (for SMTP backend)
        smtp_username: SMTP authentication username (for SMTP backend)
        smtp_password: SMTP authentication password (for SMTP backend)
        smtp_timeout: SMTP connection timeout (for SMTP backend)

    Returns:
        NotificationService instance if enabled, None otherwise
    """
    if not enabled:
        logger.info("Notifications disabled")
        return None

    if backend_type == "smtp":
        backend: NotificationBackend = SMTPNotificationBackend(
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            use_tls=smtp_use_tls,
            username=smtp_username,
            password=smtp_password,
            timeout=smtp_timeout,
        )
        logger.info(f"Notification service initialized with SMTP backend: {smtp_host}:{smtp_port}")
    else:
        backend = MockNotificationBackend()
        logger.info("Notification service initialized with mock backend")

    return NotificationService(backend=backend, from_address=from_address)
