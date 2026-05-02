"""Admin blueprint — Firebase edition."""
import os
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, abort, send_file, current_app
)
from flask_login import login_required, current_user

from firebase_models import (
    get_pending_payments, get_recent_payments, get_payment,
    get_all_users, get_user_count, get_usage_count,
    review_payment, update_user_tokens, get_firebase_user,
    PLAN_TOKENS
)
from emailer import notify_user_payment_approved, notify_user_payment_rejected

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(404)
        return view_func(*args, **kwargs)
    return wrapper


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    pending     = get_pending_payments()
    recent      = get_recent_payments(20)
    user_count  = get_user_count()
    usage_count = get_usage_count()
    return render_template(
        'admin/dashboard.html',
        pending=pending,
        recent=recent,
        user_count=user_count,
        usage_count=usage_count,
    )


@admin_bp.route('/payments/<payment_id>/screenshot')
@login_required
@admin_required
def screenshot(payment_id):
    payment = get_payment(payment_id)
    if not payment or not payment.get('screenshot_path'):
        abort(404)
    path = payment['screenshot_path']
    if not os.path.isfile(path):
        abort(404)
    return send_file(path)


@admin_bp.route('/payments/<payment_id>/approve', methods=['POST'])
@login_required
@admin_required
def approve(payment_id):
    payment = get_payment(payment_id)
    if not payment:
        abort(404)
    if payment['status'] != 'pending':
        flash('That payment has already been reviewed.', 'info')
        return redirect(url_for('admin.dashboard'))

    user_email = payment['user_email']
    user = get_firebase_user(user_email)
    if not user:
        flash('User no longer exists.', 'error')
        return redirect(url_for('admin.dashboard'))

    # Credit tokens
    plan = payment['plan']
    new_tokens_grant = PLAN_TOKENS.get(plan)
    if new_tokens_grant is None:
        # Unlimited plan
        update_user_tokens(user_email, 0, new_plan=plan)
    else:
        new_balance = (user.tokens_remaining or 0) + new_tokens_grant
        update_user_tokens(user_email, new_balance, new_plan=plan)

    note = (request.form.get('note') or '').strip()[:500] or None
    review_payment(payment_id, 'approved', admin_note=note)

    notify_user_payment_approved(payment, user_email)
    flash(f"Approved Rs {payment['amount']} for {user_email}. Tokens credited.", 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/payments/<payment_id>/reject', methods=['POST'])
@login_required
@admin_required
def reject(payment_id):
    payment = get_payment(payment_id)
    if not payment:
        abort(404)
    if payment['status'] != 'pending':
        flash('That payment has already been reviewed.', 'info')
        return redirect(url_for('admin.dashboard'))

    note = (request.form.get('note') or '').strip()[:500]
    review_payment(payment_id, 'rejected', admin_note=note or None)

    user_email = payment.get('user_email')
    if user_email:
        notify_user_payment_rejected(payment, user_email, note)
    flash('Payment rejected.', 'info')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    all_users = get_all_users()
    return render_template('admin/users.html', users=all_users)


@admin_bp.route('/tickets')
@login_required
@admin_required
def tickets():
    from firebase_models import get_all_tickets
    all_tickets = get_all_tickets()
    open_count  = sum(1 for t in all_tickets if t.get('status') == 'open')
    return render_template('admin/tickets.html', tickets=all_tickets, open_count=open_count)


@admin_bp.route('/tickets/<ticket_id>/reply', methods=['POST'])
@login_required
@admin_required
def reply_ticket(ticket_id):
    from firebase_models import update_ticket
    reply  = (request.form.get('reply') or '').strip()[:2000]
    status = request.form.get('status', 'resolved')
    update_ticket(ticket_id, status=status, admin_reply=reply or None)
    flash('Reply sent and ticket updated.', 'success')
    return redirect(url_for('admin.tickets'))

