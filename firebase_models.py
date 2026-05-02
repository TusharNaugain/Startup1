"""Firebase Firestore helpers — replaces SQLAlchemy models.

Collections:
  users/{email}       — user profile, plan, tokens
  payments/{id}       — payment records
  usage_logs/{id}     — tool usage per user
  otps/{email}        — temporary OTP store (expires in 10 min)
"""
import uuid
from datetime import datetime, timezone, timedelta
from flask_login import UserMixin
import firebase_admin
from firebase_admin import firestore

PLAN_TOKENS = {
    'free':      10,
    'starter':   100,
    'pro':       250,
    'unlimited': None,  # None = unlimited
}

PLAN_PRICES = {
    'starter':   299,
    'pro':       399,
    'unlimited': 599,
}


def _db():
    return firestore.client()


# ─── User ────────────────────────────────────────────────────────────────────

class FirebaseUser(UserMixin):
    """Thin wrapper around a Firestore user document for Flask-Login."""

    def __init__(self, data: dict):
        self.email              = data['email']
        self.plan               = data.get('plan', 'free')
        self.tokens_remaining   = data.get('tokens_remaining', PLAN_TOKENS['free'])
        self.is_admin           = data.get('is_admin', False)
        self.created_at         = data.get('created_at')

    # Flask-Login requires get_id() to return a string
    def get_id(self):
        return self.email

    @property
    def id(self):
        return self.email

    @property
    def has_unlimited(self):
        return self.is_admin or self.plan == 'unlimited'

    def can_use_tool(self):
        return self.is_admin or self.has_unlimited or (self.tokens_remaining or 0) > 0

    def consume_token(self):
        """In-memory decrement — caller must persist via update_user_tokens()."""
        if self.has_unlimited:
            return
        if self.tokens_remaining > 0:
            self.tokens_remaining -= 1


def get_user(email: str):
    """Return user dict or None."""
    doc = _db().collection('users').document(email).get()
    return doc.to_dict() if doc.exists else None


def get_firebase_user(email: str):
    """Return FirebaseUser or None."""
    data = get_user(email)
    return FirebaseUser(data) if data else None


def create_user(email: str, admin_email: str = '') -> FirebaseUser:
    """Create and return a new user document."""
    is_admin = bool(admin_email and email.lower() == admin_email.lower())
    data = {
        'email':            email,
        'plan':             'unlimited' if is_admin else 'free',
        'tokens_remaining': None if is_admin else PLAN_TOKENS['free'],
        'is_admin':         is_admin,
        'created_at':       datetime.now(timezone.utc),
    }
    _db().collection('users').document(email).set(data)
    return FirebaseUser(data)


def update_user_tokens(email: str, new_tokens: int, new_plan: str = None):
    update = {'tokens_remaining': new_tokens}
    if new_plan:
        update['plan'] = new_plan
    _db().collection('users').document(email).update(update)


def get_all_users():
    docs = _db().collection('users').stream()
    users = [FirebaseUser(d.to_dict()) for d in docs]
    # Sort by created_at descending in Python — no index needed
    users.sort(key=lambda u: u.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return users


def get_user_count():
    return len(list(_db().collection('users').stream()))


# ─── OTP ─────────────────────────────────────────────────────────────────────

def store_otp(email: str, otp: str):
    """Store OTP with 10-minute TTL and reset attempts counter."""
    _db().collection('otps').document(email).set({
        'otp':        otp,
        'expires_at': datetime.now(timezone.utc) + timedelta(minutes=10),
        'attempts':   0,
    })


def verify_otp(email: str, otp_input: str):
    """
    Returns:
      'ok'       — OTP matches and is still valid
      'expired'  — OTP has expired
      'wrong'    — Wrong OTP (attempts incremented)
      'locked'   — Too many wrong attempts (≥ 3)
      'not_found'— No OTP record exists
    """
    ref = _db().collection('otps').document(email)
    doc = ref.get()
    if not doc.exists:
        return 'not_found'

    data = doc.to_dict()
    expires = data['expires_at']
    # Firestore returns timezone-aware datetimes
    if isinstance(expires, datetime) and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires:
        ref.delete()
        return 'expired'

    attempts = data.get('attempts', 0)
    if attempts >= 3:
        ref.delete()
        return 'locked'

    if data['otp'] != otp_input.strip():
        ref.update({'attempts': attempts + 1})
        return 'wrong'

    ref.delete()
    return 'ok'


# ─── Payment ──────────────────────────────────────────────────────────────────

def create_payment(user_email, plan, amount, txn_id, screenshot_path=None):
    payment_id = uuid.uuid4().hex
    data = {
        'id':              payment_id,
        'user_email':      user_email,
        'plan':            plan,
        'amount':          amount,
        'txn_id':          txn_id,
        'screenshot_path': screenshot_path,
        'status':          'pending',
        'admin_note':      None,
        'created_at':      datetime.now(timezone.utc),
        'reviewed_at':     None,
    }
    _db().collection('payments').document(payment_id).set(data)
    return data


def get_pending_payments():
    """Fetch all pending payments sorted by created_at ascending — no index needed."""
    docs = _db().collection('payments').stream()
    results = [d.to_dict() for d in docs if d.to_dict().get('status') == 'pending']
    results.sort(key=lambda p: p.get('created_at') or datetime.min.replace(tzinfo=timezone.utc))
    return results


def get_recent_payments(limit=20):
    """Fetch recently reviewed payments (approved or rejected)."""
    docs = _db().collection('payments').order_by(
        'created_at', direction=firestore.Query.DESCENDING
    ).limit(50).stream()
    results = []
    for d in docs:
        data = d.to_dict()
        if data.get('status') != 'pending':
            results.append(data)
            if len(results) >= limit:
                break
    return results


def get_payments_for_user(user_email):
    """Fetch payments for a specific user — no compound index needed."""
    docs = _db().collection('payments').stream()
    results = [d.to_dict() for d in docs if d.to_dict().get('user_email') == user_email]
    results.sort(key=lambda p: p.get('created_at') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return results


def get_payment(payment_id):
    doc = _db().collection('payments').document(payment_id).get()
    return doc.to_dict() if doc.exists else None


def review_payment(payment_id, status, admin_note=None):
    _db().collection('payments').document(payment_id).update({
        'status':      status,
        'admin_note':  admin_note,
        'reviewed_at': datetime.now(timezone.utc),
    })


# ─── Usage Log ────────────────────────────────────────────────────────────────

def log_usage(user_email: str, tool: str):
    log_id = uuid.uuid4().hex
    _db().collection('usage_logs').document(log_id).set({
        'id':         log_id,
        'user_email': user_email,
        'tool':       tool,
        'created_at': datetime.now(timezone.utc),
    })


def get_usage_count():
    return len(list(_db().collection('usage_logs').stream()))


# ─── Help Desk / Support Tickets ─────────────────────────────────────────────

def create_ticket(user_email: str, subject: str, message: str) -> str:
    ticket_id = uuid.uuid4().hex
    _db().collection('support_tickets').document(ticket_id).set({
        'id':         ticket_id,
        'user_email': user_email,
        'subject':    subject,
        'message':    message,
        'status':     'open',      # open | resolved
        'admin_reply': None,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
    })
    return ticket_id


def get_all_tickets(status_filter=None):
    query = _db().collection('support_tickets').order_by(
        'created_at', direction=firestore.Query.DESCENDING
    )
    docs = query.stream()
    tickets = [d.to_dict() for d in docs]
    if status_filter:
        tickets = [t for t in tickets if t.get('status') == status_filter]
    return tickets


def get_tickets_for_user(user_email: str):
    docs = _db().collection('support_tickets').stream()
    results = [d.to_dict() for d in docs if d.to_dict().get('user_email') == user_email]
    results.sort(key=lambda t: t.get('created_at') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return results


def update_ticket(ticket_id: str, status: str, admin_reply: str = None):
    _db().collection('support_tickets').document(ticket_id).update({
        'status':      status,
        'admin_reply': admin_reply,
        'updated_at':  datetime.now(timezone.utc),
    })

