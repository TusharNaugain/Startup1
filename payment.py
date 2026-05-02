"""Payment blueprint — Firebase edition."""
import os
import uuid
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, current_app
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from extensions import limiter
from firebase_models import create_payment, get_payments_for_user, PLAN_PRICES, PLAN_TOKENS
from emailer import notify_admin_payment_pending

payment_bp = Blueprint('payment', __name__, url_prefix='/billing')

ALLOWED_SCREENSHOT_EXT = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024  # 5 MB


def _allowed_screenshot(filename):
    if '.' not in filename:
        return False
    return filename.rsplit('.', 1)[-1].lower() in ALLOWED_SCREENSHOT_EXT


@payment_bp.route('/plans')
@login_required
def plans():
    return render_template('payment/plans.html', prices=PLAN_PRICES, tokens=PLAN_TOKENS)


@payment_bp.route('/submit/<plan>', methods=['GET', 'POST'])
@login_required
@limiter.limit('5 per minute')
def submit(plan):
    if plan not in PLAN_PRICES:
        flash('Unknown plan.', 'error')
        return redirect(url_for('payment.plans'))

    expected_amount = PLAN_PRICES[plan]

    if request.method == 'POST':
        txn_id     = (request.form.get('txn_id') or '').strip()
        amount_raw = (request.form.get('amount') or '').strip()
        screenshot = request.files.get('screenshot')

        errors = []
        if not txn_id or len(txn_id) < 6 or len(txn_id) > 128:
            errors.append('Please enter a valid transaction / UTR ID.')
        try:
            amount = int(amount_raw)
        except (TypeError, ValueError):
            errors.append('Amount must be a whole rupee value.')
            amount = 0
        if amount and amount != expected_amount:
            errors.append(
                f'Amount must be exactly Rs {expected_amount} for the {plan} plan. '
                f'You entered Rs {amount}.'
            )
        if not screenshot or not screenshot.filename:
            errors.append('Please upload a payment screenshot.')
        elif not _allowed_screenshot(screenshot.filename):
            errors.append('Screenshot must be PNG, JPG, WEBP, or GIF.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template(
                'payment/submit.html',
                plan=plan, amount=expected_amount,
                tokens=PLAN_TOKENS.get(plan), txn_id=txn_id,
            )

        # Save screenshot
        ext       = screenshot.filename.rsplit('.', 1)[-1].lower()
        safe_name = f"{uuid.uuid4().hex}.{ext}"
        save_dir  = current_app.config['PAYMENT_SCREENSHOT_FOLDER']
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, safe_name)

        screenshot.seek(0, os.SEEK_END)
        size = screenshot.tell()
        screenshot.seek(0)
        if size > MAX_SCREENSHOT_BYTES:
            flash('Screenshot is too large (5 MB limit).', 'error')
            return render_template(
                'payment/submit.html',
                plan=plan, amount=expected_amount,
                tokens=PLAN_TOKENS.get(plan), txn_id=txn_id,
            )
        screenshot.save(save_path)

        payment = create_payment(
            user_email=current_user.email,
            plan=plan,
            amount=expected_amount,
            txn_id=txn_id,
            screenshot_path=save_path,
        )
        notify_admin_payment_pending(payment, current_user.email)

        flash(
            'Payment submitted! Tokens will be credited within 24 hours after verification.',
            'success'
        )
        return redirect(url_for('payment.thank_you'))

    return render_template(
        'payment/submit.html',
        plan=plan, amount=expected_amount,
        tokens=PLAN_TOKENS.get(plan), txn_id='',
    )


@payment_bp.route('/thank-you')
@login_required
def thank_you():
    return render_template('payment/thank_you.html')


@payment_bp.route('/my-payments')
@login_required
def my_payments():
    payments = get_payments_for_user(current_user.email)
    return render_template('payment/my_payments.html', payments=payments)
