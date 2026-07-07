"""
email_alert.py
--------------
Sends the defect-alert emails. Reads SMTP credentials from environment
variables (see .env.example) so no secrets are hard-coded in the project.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import config


def send_alert_email(subject: str, body: str, to_emails: list) -> tuple[bool, str]:
    """Returns (success, status_message). Does not raise on failure -
    the caller logs whatever status_message comes back."""

    if not to_emails:
        return False, "No recipient email configured for this line."

    if not config.EMAIL_ADDRESS or not config.EMAIL_PASSWORD:
        return False, "SMTP credentials not configured (set EMAIL_ADDRESS / EMAIL_PASSWORD in .env)."

    msg = MIMEMultipart()
    msg["From"] = config.EMAIL_ADDRESS
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(config.SMTP_SERVER, config.SMTP_PORT, context=context) as server:
            server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
            server.sendmail(config.EMAIL_ADDRESS, to_emails, msg.as_string())
        return True, "Sent."
    except Exception as e:
        return False, f"Failed to send: {e}"


def check_and_alert(line_id, line_name, date, target, produced, defected):
    """Business rule: decide whether this day's numbers breach a threshold,
    and if so, build the message and send + log it.
    Returns the alert status string, or None if no alert was needed."""
    import database  # local import to avoid a circular import at module load time

    defect_rate = (defected / produced * 100) if produced else 0

    breached = (
        defect_rate >= config.DEFECT_RATE_THRESHOLD
        or defected >= config.DEFECT_COUNT_THRESHOLD
    )
    if not breached:
        return None

    recipients = database.get_recipients_for_line(line_id)

    subject = f"[ALERT] {line_name} line - defect threshold breached ({date})"
    body = (
        f"Production Alert - LG Electronics\n"
        f"-----------------------------------\n"
        f"Line: {line_name}\n"
        f"Date: {date}\n"
        f"Target: {target}\n"
        f"Produced: {produced}\n"
        f"Defected: {defected}\n"
        f"Defect Rate: {defect_rate:.2f}%\n\n"
        f"This exceeds the configured threshold "
        f"({config.DEFECT_RATE_THRESHOLD}% or {config.DEFECT_COUNT_THRESHOLD} units).\n"
        f"Please review the line and take corrective action."
    )

    success, status = send_alert_email(subject, body, recipients)
    database.log_alert(date, line_id, body, recipients, "SENT" if success else f"FAILED - {status}")
    return "SENT" if success else f"FAILED - {status}"
