"""
Rate limiting per engine (in-memory). Production may use Redis.
"""
from __future__ import annotations

import time
import threading
from collections import defaultdict
from flask import request, jsonify

from core.config import get_config
from core.exceptions import RateLimitError

_store: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()
_WINDOW = 60.0  # seconds


def _clean_old(now: float, window: float, times: list[float]) -> None:
    cutoff = now - window
    while times and times[0] < cutoff:
        times.pop(0)


def check_rate_limit(engine: str) -> None:
    """Raise RateLimitError if over limit for this engine."""
    cfg = get_config()
    limit = cfg.RATE_LIMIT_REQUESTS
    window = float(cfg.RATE_LIMIT_WINDOW_S)
    key = f"generate:{engine}"
    now = time.time()
    with _lock:
        _clean_old(now, window, _store[key])
        if len(_store[key]) >= limit:
            raise RateLimitError("Rate limit exceeded for this engine")
        _store[key].append(now)


def rate_limit_by_engine(f):
    """Decorator: rate limit using engine from JSON body (default musicgen)."""
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        try:
            data = request.get_json() or {}
            engine = (data.get("engine") or "musicgen").strip().lower()
            check_rate_limit(engine)
        except RateLimitError as e:
            return jsonify({"error": e.message}), 429
        return f(*args, **kwargs)
    return wrapped
