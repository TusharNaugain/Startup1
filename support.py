"""Support / Help Desk blueprint."""
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash
)
from flask_login import login_required, current_user
from extensions import limiter
from firebase_models import create_ticket, get_tickets_for_user
from emailer import _mail_configured, _safe_send
from flask_mail import Message

support_bp = Blueprint('support', __name__, url_prefix='/support')


@support_bp.route('/', methods=['GET', 'POST'])
@login_required
@limiter.limit('5 per minute')
def index():
    if request.method == 'POST':
        subject = (request.form.get('subject') or '').strip()[:200]
        message = (request.form.get('message') or '').strip()[:2000]
        if not subject or not message:
            flash('Please fill in both subject and message.', 'error')
            return render_template('support/index.html')

        ticket_id = create_ticket(current_user.email, subject, message)

        # Notify admin by email
        _notify_admin_new_ticket(current_user.email, subject, message, ticket_id)

        flash("✅ Your ticket has been submitted! We'll get back to you soon.", 'success')
        return redirect(url_for('support.my_tickets'))

    return render_template('support/index.html')


@support_bp.route('/my-tickets')
@login_required
def my_tickets():
    tickets = get_tickets_for_user(current_user.email)
    return render_template('support/my_tickets.html', tickets=tickets)


def _notify_admin_new_ticket(user_email, subject, message, ticket_id):
    from flask import current_app
    if not _mail_configured():
        return
    admin_email = current_app.config.get('ADMIN_EMAIL')
    if not admin_email:
        return
    try:
        from flask import url_for as _url_for
        admin_url = _url_for('admin.tickets', _external=True)
    except Exception:
        admin_url = '/admin/tickets'

    msg = Message(
        subject=f'[Multi Find Relevance] Support ticket from {user_email}',
        recipients=[admin_email],
        body=f"""New support ticket submitted.

From:    {user_email}
Subject: {subject}

{message}

---
View all tickets: {admin_url}
"""
    )
    _safe_send(msg)
