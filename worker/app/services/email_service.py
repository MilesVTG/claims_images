"""Email alerting via Microsoft Exchange (Section 21).

Sends high-risk claim alerts and error notifications through EWS using
exchangelib.  Silently no-ops when Exchange credentials are not configured,
keeping dev/test environments functional without an Exchange server.
"""

import logging
import os

from exchangelib import (
    Account,
    Configuration,
    Credentials,
    HTMLBody,
    Mailbox,
    Message,
    DELEGATE,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.services.prompt_service import get_active_prompt

logger = logging.getLogger(__name__)


class EmailService:
    """Send email alerts via Microsoft Exchange (EWS)."""

    def __init__(self):
        self.email = settings.exchange_email
        self.password = settings.exchange_password
        self.server = settings.exchange_server
        self._account: Account | None = None

    @property
    def account(self) -> Account | None:
        if self._account is None and self.email:
            credentials = Credentials(self.email, self.password)
            config = Configuration(
                server=self.server,
                credentials=credentials,
            )
            self._account = Account(
                self.email,
                config=config,
                autodiscover=False,
                access_type=DELEGATE,
            )
        return self._account

    def send(self, to: list[str], subject: str, body: str, is_html: bool = False):
        """Send an email.  Silently skips if Exchange is not configured."""
        if not self.account:
            logger.info("Exchange not configured — skipping email notification")
            return

        msg = Message(
            account=self.account,
            subject=subject,
            body=HTMLBody(body) if is_html else body,
            to_recipients=[Mailbox(email_address=addr) for addr in to],
        )
        msg.send()
        logger.info("Email sent to %s: %s", to, subject)


# Singleton
email_service = EmailService()


def send_alert_email(subject: str, body: str, to: list[str] | None = None):
    """Convenience function — sends to default alert recipients."""
    recipients = to or [
        r.strip()
        for r in settings.alert_recipients.split(",")
        if r.strip()
    ]
    if not recipients:
        logger.warning("No alert recipients configured — skipping email")
        return
    email_service.send(recipients, subject, body)


def send_high_risk_alert(
    db: Session,
    contract_id: str,
    claim_id: str,
    risk_score: float,
    red_flags: list[str],
):
    """Send a high-risk claim alert email if score meets threshold."""
    if risk_score < settings.high_risk_threshold:
        return

    flags_text = "\n".join(f"  - {flag}" for flag in red_flags) if red_flags else "  (none)"
    dashboard_url = f"{settings.dashboard_base_url}/claims/{contract_id}/{claim_id}"

    body_template = get_active_prompt(db, "high_risk_email_template")
    subject_template = get_active_prompt(db, "high_risk_email_subject")

    body = body_template.format(
        contract_id=contract_id,
        claim_id=claim_id,
        risk_score=risk_score,
        flags_text=flags_text,
        dashboard_url=dashboard_url,
    )

    subject = subject_template.format(
        claim_id=claim_id,
        risk_score=risk_score,
    )

    send_alert_email(subject=subject, body=body)
    logger.info(
        "High-risk alert sent for %s/%s (score=%.1f)",
        contract_id, claim_id, risk_score,
    )
