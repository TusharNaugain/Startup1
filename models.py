"""Database models: User, Payment, UsageLog.

Plans:
  free       — 10 lifetime tokens (signup grant)
  starter    — ₹299 / 100 tokens
  pro        — ₹399 / 250 tokens
  unlimited  — ₹599 / unlimited usage (tokens column ignored when plan=='unlimited')
"""
from datetime import datetime
from flask_login import UserMixin
from extensions import db, login_manager

PLAN_TOKENS = {
    'free': 10,
    'starter': 100,
    'pro': 250,
    'unlimited': None,  # None = unlimited
}

PLAN_PRICES = {
    'starter': 299,
    'pro': 399,
    'unlimited': 599,
}


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(32), nullable=False, default='free')
    tokens_remaining = db.Column(db.Integer, nullable=False, default=PLAN_TOKENS['free'])
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    payments = db.relationship('Payment', backref='user', lazy='dynamic',
                               cascade='all, delete-orphan')
    usages = db.relationship('UsageLog', backref='user', lazy='dynamic',
                             cascade='all, delete-orphan')

    @property
    def has_unlimited(self):
        return self.plan == 'unlimited'

    def can_use_tool(self):
        return self.has_unlimited or self.tokens_remaining > 0

    def consume_token(self):
        """Decrement tokens (no-op for unlimited plan). Caller commits."""
        if self.has_unlimited:
            return
        if self.tokens_remaining > 0:
            self.tokens_remaining -= 1


class Payment(db.Model):
    __tablename__ = 'payments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    plan = db.Column(db.String(32), nullable=False)            # starter / pro / unlimited
    amount = db.Column(db.Integer, nullable=False)             # in INR (whole rupees)
    txn_id = db.Column(db.String(128), nullable=False)         # UPI transaction reference
    screenshot_path = db.Column(db.String(512), nullable=True) # uploaded image path
    status = db.Column(db.String(16), nullable=False, default='pending', index=True)
    # status: pending / approved / rejected
    admin_note = db.Column(db.String(512), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)


class UsageLog(db.Model):
    __tablename__ = 'usage_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    tool = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
