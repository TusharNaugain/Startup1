"""Auth blueprint: signup, login, logout."""
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField
from wtforms.validators import DataRequired, Email, Length, EqualTo

from extensions import db, bcrypt, limiter
from models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


class SignupForm(FlaskForm):
    email = StringField('Email', validators=[
        DataRequired(), Email(), Length(max=255)
    ])
    password = PasswordField('Password', validators=[
        DataRequired(), Length(min=8, max=128, message='Password must be at least 8 characters.')
    ])
    confirm = PasswordField('Confirm Password', validators=[
        DataRequired(), EqualTo('password', message='Passwords must match.')
    ])


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField('Password', validators=[DataRequired(), Length(max=128)])


@auth_bp.route('/signup', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = SignupForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        existing = User.query.filter_by(email=email).first()
        if existing:
            flash('That email is already registered. Try logging in.', 'error')
            return render_template('auth/signup.html', form=form)

        pw_hash = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        admin_email = (current_app_admin_email() or '').lower()
        user = User(
            email=email,
            password_hash=pw_hash,
            is_admin=(email == admin_email),
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Welcome! You have 10 free tokens to try things out.', 'success')
        return redirect(url_for('home'))

    return render_template('auth/signup.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        if not user or not bcrypt.check_password_hash(user.password_hash, form.password.data):
            flash('Invalid email or password.', 'error')
            return render_template('auth/login.html', form=form)

        login_user(user, remember=True)
        next_url = request.args.get('next')
        # Only allow internal redirects (prevent open-redirect)
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect(url_for('home'))

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


def current_app_admin_email():
    from flask import current_app
    return current_app.config.get('ADMIN_EMAIL')
