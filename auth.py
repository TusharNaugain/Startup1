"""Auth blueprint — email OTP login flow (no passwords).

Flow:
  GET  /auth/login           → show email input form
  POST /auth/login           → generate OTP, email it, redirect to /auth/verify
  GET  /auth/verify          → show OTP input form
  POST /auth/verify          → validate OTP, create user if new, log in
  GET  /auth/logout          → logout
"""
import random
import string

from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session
)
from flask_login import login_user, logout_user, login_required, current_user

from extensions import limiter
from firebase_models import (
    get_firebase_user, create_user, store_otp, verify_otp,
    get_firebase_user
)
from emailer import send_otp_email

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


def _generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))


# ── Step 1: Enter email ───────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        if not email or '@' not in email:
            flash('Please enter a valid email address.', 'error')
            return render_template('auth/login.html')

        otp = _generate_otp()
        store_otp(email, otp)
        sent = send_otp_email(email, otp)

        if not sent:
            flash('Could not send OTP. Please check mail config or try again.', 'error')
            return render_template('auth/login.html')

        # Store email in session so verify step knows who we're dealing with
        session['otp_email'] = email
        flash(f'A 6-digit OTP has been sent to {email}. Check your inbox.', 'info')
        return redirect(url_for('auth.verify'))

    return render_template('auth/login.html')


# ── Step 2: Enter OTP ────────────────────────────────────────────────────────

@auth_bp.route('/verify', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def verify():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    email = session.get('otp_email')
    if not email:
        flash('Session expired. Please enter your email again.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        otp_input = (request.form.get('otp') or '').strip()
        result = verify_otp(email, otp_input)

        if result == 'ok':
            from flask import current_app
            admin_email = current_app.config.get('ADMIN_EMAIL', '')

            # Get or create user
            user = get_firebase_user(email)
            if user is None:
                user = create_user(email, admin_email=admin_email)

            session.pop('otp_email', None)
            login_user(user, remember=True)
            flash('Welcome! You are now logged in.', 'success')
            next_url = request.args.get('next') or '/'
            if not next_url.startswith('/'):
                next_url = '/'
            return redirect(next_url)

        elif result == 'expired':
            session.pop('otp_email', None)
            flash('OTP has expired. Please request a new one.', 'error')
            return redirect(url_for('auth.login'))
        elif result == 'locked':
            session.pop('otp_email', None)
            flash('Too many wrong attempts. Please request a new OTP.', 'error')
            return redirect(url_for('auth.login'))
        elif result == 'wrong':
            flash('Incorrect OTP. Please try again.', 'error')
        else:
            session.pop('otp_email', None)
            flash('No OTP found. Please request a new one.', 'error')
            return redirect(url_for('auth.login'))

    return render_template('auth/verify_otp.html', email=email)


# ── Resend OTP ────────────────────────────────────────────────────────────────

@auth_bp.route('/resend-otp', methods=['POST'])
@limiter.limit('3 per minute')
def resend_otp():
    email = session.get('otp_email')
    if not email:
        flash('Session expired. Please start again.', 'error')
        return redirect(url_for('auth.login'))

    otp = _generate_otp()
    store_otp(email, otp)
    sent = send_otp_email(email, otp)
    if sent:
        flash(f'New OTP sent to {email}.', 'info')
    else:
        flash('Failed to resend OTP. Please try again.', 'error')
    return redirect(url_for('auth.verify'))


# ── Logout ───────────────────────────────────────────────────────────────────

@auth_bp.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    logout_user()
    # DO NOT call session.clear() here. It deletes the '_remember': 'clear' 
    # flag set by logout_user(), which prevents the remember_me cookie from being deleted!
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))
