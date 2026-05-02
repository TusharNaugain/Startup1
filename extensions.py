"""Shared Flask extension instances — Firebase edition.

SQLAlchemy and Bcrypt removed; Firebase Admin SDK handles persistence.
Flask-Login, Flask-Limiter, and Flask-Mail are kept.
"""
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail

# ── Flask extensions ──────────────────────────────────────────────────────────
login_manager = LoginManager()
csrf          = CSRFProtect()
limiter       = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])
mail          = Mail()

login_manager.login_view         = 'auth.login'
login_manager.login_message      = 'Please log in to access this page.'
login_manager.login_message_category = 'info'


# ── Firebase initialisation ───────────────────────────────────────────────────
def init_firebase():
    """Call once from app.py during app startup."""
    if firebase_admin._apps:
        return  # already initialised

    cred_json = os.environ.get('FIREBASE_CREDENTIALS')
    if cred_json:
        # Production: credentials stored as JSON string in env var
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
    else:
        # Local dev: look for a file in the project root
        local_path = os.path.join(os.path.dirname(__file__), 'firebase_credentials.json')
        if os.path.exists(local_path):
            cred = credentials.Certificate(local_path)
        else:
            raise RuntimeError(
                "Firebase credentials not found.\n"
                "Set FIREBASE_CREDENTIALS env var (JSON string) in production,\n"
                "or place firebase_credentials.json in the project root for local dev."
            )

    firebase_admin.initialize_app(cred)
