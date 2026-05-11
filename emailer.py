"""Outbound email helpers — Multi Find Relevance edition.

Uses Resend (https://resend.com) HTTP API instead of SMTP because Vercel
(and most serverless platforms) block outbound SMTP connections.

Provides:
  - send_otp_email          : send login OTP to user
  - notify_admin_payment_pending
  - notify_user_payment_approved
  - notify_user_payment_rejected

Required env vars (set in Vercel dashboard):
  RESEND_API_KEY     — from https://resend.com/api-keys
  MAIL_FROM          — verified sender address (e.g. noreply@yourdomain.com)
                       OR use Resend's shared domain: onboarding@resend.dev (testing only)
  ADMIN_EMAIL        — where admin payment notifications go
"""

import os
import requests
from flask import current_app

RESEND_API_URL = "https://api.resend.com/emails"


def _get_resend_key():
    return os.environ.get("RESEND_API_KEY") or current_app.config.get("RESEND_API_KEY")


def _get_mail_from():
    return (
        os.environ.get("MAIL_FROM")
        or current_app.config.get("MAIL_FROM")
        or current_app.config.get("MAIL_DEFAULT_SENDER")
        or current_app.config.get("MAIL_USERNAME")
    )


def _mail_configured():
    """Return True if Resend is configured."""
    return bool(_get_resend_key())


def _safe_send(to: str, subject: str, body: str) -> bool:
    """Send an email via Resend HTTP API. Returns True on success."""
    api_key = _get_resend_key()
    mail_from = _get_mail_from()

    if not api_key:
        current_app.logger.warning("RESEND_API_KEY not set — skipping email send.")
        return False

    if not mail_from:
        # Fall back to Resend's test sender (works without domain verification)
        mail_from = "onboarding@resend.dev"
        current_app.logger.warning(
            "MAIL_FROM not set — using Resend test sender. "
            "Emails will only be delivered to the Resend account owner's address."
        )

    try:
        resp = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "from": mail_from,
                "to": [to],
                "subject": subject,
                "text": body,
            },
            timeout=10,
        )
        if resp.status_code in (200, 201):
            return True
        else:
            current_app.logger.warning(
                "Resend API error %s: %s", resp.status_code, resp.text
            )
            return False
    except Exception as exc:
        current_app.logger.warning("Resend send failed: %s", exc)
        return False


# ── OTP ───────────────────────────────────────────────────────────────────────

def send_otp_email(email: str, otp: str) -> bool:
    """Send a login OTP to the user. Returns True on success."""

    # Always print OTP to terminal — handy in dev / when email not configured
    print(f"\n[OTP] ✉️  {email}  →  {otp}\n", flush=True)

    if not _mail_configured():
        current_app.logger.info(
            "RESEND_API_KEY not set — OTP printed to terminal only."
        )
        # In development, allow login without real email delivery
        is_dev = os.environ.get("FLASK_ENV", "production") == "development"
        return is_dev  # True in dev (bypass), False in prod (force real delivery)

    subject = "Your Multi Find Relevance login code"
    body = f"""Hi,

Your Multi Find Relevance login code is:

    {otp}

This code expires in 10 minutes. Do not share it with anyone.

If you did not request this, you can safely ignore this email.

— Multi Find Relevance
"""
    return _safe_send(email, subject, body)


# ── Payment notifications ─────────────────────────────────────────────────────

def notify_admin_payment_pending(payment: dict, user_email: str):
    if not _mail_configured():
        return
    admin_email = (
        os.environ.get("ADMIN_EMAIL")
        or current_app.config.get("ADMIN_EMAIL")
    )
    if not admin_email:
        return

    from flask import url_for
    try:
        review_url = url_for("admin.dashboard", _external=True)
    except RuntimeError:
        review_url = "/admin"

    subject = f"[Multi Find Relevance] Payment pending — {user_email}"
    body = f"""A new payment has been submitted for review.

User:         {user_email}
Plan:         {payment['plan']}
Amount:       Rs {payment['amount']}
Transaction:  {payment['txn_id']}

Review and approve / reject here:
{review_url}
"""
    _safe_send(admin_email, subject, body)


def notify_user_payment_approved(payment: dict, user_email: str):
    if not _mail_configured():
        return
    subject = "[Multi Find Relevance] Payment approved"
    body = f"""Hi {user_email},

Your payment has been approved! Your account is now on the '{payment['plan']}' plan.

Plan:        {payment['plan']}
Amount:      Rs {payment['amount']}
Transaction: {payment['txn_id']}

Head back to the dashboard to start using your tokens.

— Multi Find Relevance
"""
    _safe_send(user_email, subject, body)


def notify_user_payment_rejected(payment: dict, user_email: str, reason: str):
    if not _mail_configured():
        return
    subject = "[Multi Find Relevance] Payment could not be verified"
    body = f"""Hi {user_email},

We could not verify your recent payment. Reason:

  {reason or 'Not specified.'}

Transaction reference: {payment['txn_id']}

If this looks like a mistake, reply to this email with your payment receipt.

— Multi Find Relevance
"""
    _safe_send(user_email, subject, body)
