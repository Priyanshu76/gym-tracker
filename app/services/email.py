"""
Email sending via direct SMTP — replaces n8n's Gmail node.
"""
import smtplib
from email.mime.text import MIMEText

from app.config import get_settings

settings = get_settings()

# Strip any trailing slash once, here — every link below builds off this,
# so a misconfigured SITE_BASE_URL with a trailing slash (a very easy typo
# in a .env file) can no longer produce a broken //api/... double-slash URL.
BASE_URL = settings.site_base_url.rstrip("/")


def send_email(to: str, subject: str, body: str) -> None:
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from, [to], msg.as_string())


def send_verification_email(to: str, display_name: str, request_id: str, token: str) -> None:
    link = f"{BASE_URL}/api/verify-email?request_id={request_id}&token={token}"
    body = (
        f"Hi {display_name},\n\n"
        "Click the link below to verify your email and send your signup request for approval:\n\n"
        f"{link}\n\n"
        "This link expires in 24 hours.\n\nIf you didn't request this, you can ignore this email."
    )
    send_email(to, "Verify your email — Gym Tracker signup", body)


def send_admin_notification(username: str, display_name: str, email: str, request_id: str, approval_token: str) -> None:
    approve_link = f"{BASE_URL}/api/approve-signup?request_id={request_id}&token={approval_token}"
    reject_link = f"{BASE_URL}/api/reject-signup?request_id={request_id}&token={approval_token}"
    body = (
        "A new signup request is waiting for your review.\n\n"
        f"Username: {username}\nDisplay name: {display_name}\nEmail: {email}\n\n"
        f"Approve:\n{approve_link}\n\nReject:\n{reject_link}\n\nThis link expires in 7 days."
    )
    send_email(settings.admin_email, f"New signup request: {username}", body)


def send_welcome_email(to: str, display_name: str, username: str, temp_password: str) -> None:
    login_link = f"{BASE_URL}/"
    body = (
        f"Hi {display_name},\n\n"
        "Your account has been approved. Here are your login details:\n\n"
        f"Username: {username}\nTemporary password: {temp_password}\n\n"
        f"Log in here: {login_link}\n\n"
        "You'll be asked to set your own password the first time you log in.\n\n"
        "This temporary password only appears in this email — store it somewhere safe until you've reset it."
    )
    send_email(to, "Your Gym Tracker account is ready", body)


def send_rejection_email(to: str, display_name: str) -> None:
    body = (
        f"Hi {display_name},\n\n"
        "Thanks for your interest — your signup request wasn't approved this time.\n\n"
        "If you think this was a mistake, feel free to reach out to the site owner directly."
    )
    send_email(to, "Your Gym Tracker signup request", body)


def send_reset_email(to: str, display_name: str, username: str, token: str) -> None:
    link = f"{BASE_URL}/reset-password?username={username}&token={token}"
    body = (
        f"Hi {display_name},\n\n"
        "Click the link below to set a new password. This link expires in 1 hour.\n\n"
        f"{link}\n\nIf you didn't request this, you can safely ignore this email."
    )
    send_email(to, "Reset your Gym Tracker password", body)
