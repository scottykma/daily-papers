import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import SMTP_PASSWORD, get

logger = logging.getLogger(__name__)


def send_email(title: str, html_content: str) -> bool:
    if not get("notification.email.enabled", True):
        logger.info("Email notification disabled in config")
        return False

    if not SMTP_PASSWORD:
        logger.warning("SMTP_PASSWORD not set, skipping email notification")
        return False

    sender = get("user.email", "")
    recipient = sender
    smtp_host = get("notification.email.smtp_host", "smtp.gmail.com")
    smtp_port = get("notification.email.smtp_port", 587)

    if not sender:
        logger.warning("User email not configured, skipping email notification")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        msg["From"] = sender
        msg["To"] = recipient
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=get("notification.email.timeout", 15)) as server:
            server.starttls()
            server.login(sender, SMTP_PASSWORD)
            server.sendmail(sender, recipient, msg.as_string())

        logger.info("Email notification sent to %s", recipient)
        return True
    except Exception:
        logger.exception("Failed to send email notification")
        return False


def send_report(title: str, html_content: str) -> dict[str, bool]:
    result = send_email(title, html_content)
    return {"email": result}
