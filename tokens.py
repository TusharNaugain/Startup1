"""Token-consumption decorator — Firebase edition."""
from functools import wraps
from flask import jsonify, redirect, url_for, request, current_app
from flask_login import current_user
from firebase_models import log_usage, update_user_tokens


def _wants_json():
    if request.is_json:
        return True
    return 'application/json' in request.headers.get('Accept', '')


def _paywall_response():
    if _wants_json():
        return jsonify({
            'error':     'You have used all your free tokens.',
            'paywall':   True,
            'plans_url': url_for('payment.plans'),
        }), 402
    return redirect(url_for('payment.plans'))


def _response_status(response):
    if isinstance(response, tuple) and len(response) >= 2:
        try:
            return int(response[1])
        except (TypeError, ValueError):
            return 200
    if hasattr(response, 'status_code'):
        return response.status_code
    return 200


def consume_token(tool_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return _paywall_response()
            if not current_user.can_use_tool():
                return _paywall_response()

            response = view_func(*args, **kwargs)

            if 200 <= _response_status(response) < 300:
                try:
                    if not current_user.has_unlimited:
                        new_tokens = max((current_user.tokens_remaining or 1) - 1, 0)
                        update_user_tokens(current_user.email, new_tokens)
                        current_user.tokens_remaining = new_tokens
                    log_usage(current_user.email, tool_name)
                except Exception as exc:
                    current_app.logger.warning('token debit failed: %s', exc)

            return response
        return wrapper
    return decorator
