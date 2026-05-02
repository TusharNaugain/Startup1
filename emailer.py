"""Outbound email helpers — Multi Find Relevance edition.

Provides:
  - send_otp_email          : send login OTP to user
  - notify_admin_payment_pending
  - notify_user_payment_approved
  - notify_user_payment_rejected
"""
from flask import current_app, url_for
from flask_mail import Message
from extensions import mail


def _mail_configured():
    return bool(
        current_app.config.get('MAIL_USERNAME') and
        current_app.config.get('MAIL_PASSWORD')
    )


def _safe_send(msg) -> bool:
    try:
        mail.send(msg)
        return True
    except Exception as exc:
        current_app.logger.warning('email send failed: %s', exc)
        return False


# ── OTP ───────────────────────────────────────────────────────────────────────

def send_otp_email(email: str, otp: str) -> bool:
    """Send a login OTP to the user. Returns True on success."""
    import os

    # Always print OTP to terminal — handy in dev
    print(f'\n[OTP] ✉️  {email}  →  {otp}\n', flush=True)

    if not _mail_configured():
        current_app.logger.info('Mail not configured — OTP printed to terminal.')
        return True

    body = f"""Hi,

Your Multi Find Relevance login code is:

    {otp}

This code expires in 10 minutes. Do not share it with anyone.

If you did not request this, you can safely ignore this email.

— Multi Find Relevance
"""
    msg = Message(
        subject='Your Multi Find Relevance login code',
        recipients=[email],
        body=body,
    )
    sent = _safe_send(msg)

    if not sent:
        is_dev = os.environ.get('FLASK_ENV', 'production') == 'development'
        if is_dev:
            current_app.logger.warning('Email send failed — OTP was printed to terminal.')
            return True
        return False

    return True


# ── Payment notifications ─────────────────────────────────────────────────────

def notify_admin_payment_pending(payment: dict, user_email: str):
    if not _mail_configured():
        return
    admin_email = current_app.config.get('ADMIN_EMAIL')
    if not admin_email:
        return
    try:
        review_url = url_for('admin.dashboard', _external=True)
    except RuntimeError:
        review_url = '/admin'

    body = f"""A new payment has been submitted for review.

User:         {user_email}
Plan:         {payment['plan']}
Amount:       Rs {payment['amount']}
Transaction:  {payment['txn_id']}

Review and approve / reject here:
{review_url}
"""
    msg = Message(
        subject=f"[Multi Find Relevance] Payment pending — {user_email}",
        recipients=[admin_email],
        body=body,
    )
    _safe_send(msg)


def notify_user_payment_approved(payment: dict, user_email: str):
    if not _mail_configured():
        return
    body = f"""Hi {user_email},

Your payment has been approved! Your account is now on the '{payment['plan']}' plan.

Plan:        {payment['plan']}
Amount:      Rs {payment['amount']}
Transaction: {payment['txn_id']}

Head back to the dashboard to start using your tokens.

— Multi Find Relevance
"""
    msg = Message(
        subject="[Multi Find Relevance] Payment approved",
        recipients=[user_email],
        body=body,
    )
    _safe_send(msg)


def notify_user_payment_rejected(payment: dict, user_email: str, reason: str):
    if not _mail_configured():
        return
    body = f"""Hi {user_email},

We could not verify your recent payment. Reason:

  {reason or 'Not specified.'}

Transaction reference: {payment['txn_id']}

If this looks like a mistake, reply to this email with your payment receipt.

— Multi Find Relevance
"""
    msg = Message(
        subject="[Multi Find Relevance] Payment could not be verified",
        recipients=[user_email],
        body=body,
    )
    _safe_send(msg)
