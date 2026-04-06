"""
Request authentication. Placeholder: no hardcoded credentials.
Auth can be enabled via env (e.g. API key or JWT) and validated here.
"""
from __future__ import annotations

import os
from functools import wraps
from flask import request, jsonify

from core.exceptions import AuthError


def _get_api_key() -> str | None:
    return os.environ.get("K2_API_KEY") or os.environ.get("API_KEY")


def require_auth(f):
    """Decorator: require K2_API_KEY or API_KEY header if set. If no key configured, skip check."""
    @wraps(f)
    def wrapped(*args, **kwargs):
        expected = _get_api_key()
        if not expected:
            return f(*args, **kwargs)
        provided = request.headers.get("X-API-Key") or request.headers.get("Authorization", "").replace("Bearer ", "")
        if provided != expected:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapped
