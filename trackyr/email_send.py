"""Gmail SMTP email sender using app passwords."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from trackyr.config import cfg

log = logging.getLogger(__name__)


def send_email(subject: str, html_body: str, to: str | None = None) -> bool:
    """Send an HTML email via Gmail SMTP.

    Uses SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD from config.
    Returns True on success, False on failure.
    """
    to = to or cfg.email_to
    if not all([cfg.smtp_user, cfg.smtp_password, to]):
        log.warning("Email not configured — skipping send")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.smtp_user
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=30) as server:
            server.starttls(context=context)
            server.login(cfg.smtp_user, cfg.smtp_password)
            server.send_message(msg)
        log.info("Email sent: %s -> %s", subject, to)
        return True
    except Exception:
        log.exception("Failed to send email: %s", subject)
        return False
