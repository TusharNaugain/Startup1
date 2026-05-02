"""Shared Flask extension instances.

Kept in their own module so models.py / auth.py / app.py can all import
them without creating circular imports.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])
mail = Mail()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'
