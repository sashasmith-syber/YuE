"""
Hardened security layer.
Input sanitization, path safety, lyrics injection prevention.
"""
from __future__ import annotations

import re
import secrets
import unicodedata
from pathlib import Path
from typing import Optional

from .config import get_config
from .security_limits import (
    LYRICS_MAX_CHARS,
    INJECTION_PATTERNS,
    HTML_TAG_PATTERN,
)

# Allowed chars for prompt/genre (strict to avoid injection)
PROMPT_ALLOWED_PATTERN = re.compile(r"^[\w\s.,'\-!?&()/]+$", re.UNICODE)
FILENAME_SAFE_PATTERN = re.compile(r"^[a-zA-Z0-9._\-]+$")


def normalize_unicode(text: str) -> str:
    """NFKC normalization for consistent handling."""
    return unicodedata.normalize("NFKC", text)


def sanitize_prompt(text: Optional[str], max_length: int = 2000) -> str:
    """Sanitize user prompt for generation. Returns safe string or empty."""
    if not text or not isinstance(text, str):
        return ""
    cleaned = normalize_unicode(text)
    cleaned = " ".join(cleaned.strip().split())[:max_length]
    if not PROMPT_ALLOWED_PATTERN.match(cleaned):
        cleaned = "".join(c for c in cleaned if c.isalnum() or c in " .,'-!?&()/")
    return cleaned[:max_length]


def sanitize_genre_tags(tags: Optional[str], max_length: int = 500) -> str:
    """Sanitize genre tag string for YuE (format only; whitelist applied in validation)."""
    if not tags or not isinstance(tags, str):
        return ""
    cleaned = normalize_unicode(tags)
    cleaned = " ".join(cleaned.strip().split())[:max_length]
    cleaned = "".join(c for c in cleaned if c.isalnum() or c in " _,.-")
    return cleaned[:max_length].strip()


def sanitize_lyrics(text: Optional[str], max_length: int = LYRICS_MAX_CHARS) -> str:
    """
    Strip HTML/XML, block template injection, enforce max length.
    Raises ValueError if injection pattern found.
    """
    if not text or not isinstance(text, str):
        return ""
    cleaned = normalize_unicode(text)
    cleaned = HTML_TAG_PATTERN.sub(" ", cleaned)
    for pat in INJECTION_PATTERNS:
        if pat.search(cleaned):
            raise ValueError("Lyrics contain disallowed pattern")
    return " ".join(cleaned.split())[:max_length]


def safe_filename(name: str, suffix: str = "") -> str:
    """Return a safe filename; use random suffix if name invalid."""
    base = name.strip()[:64] if name else "output"
    if not FILENAME_SAFE_PATTERN.match(base):
        base = "output"
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    return base + suffix or ""


def resolve_path_within_root(raw: str, root: Path, subdir: str = "") -> Path:
    """Resolve path ensuring it stays under root (no escape)."""
    root = root.resolve()
    path = (root / subdir / raw).resolve()
    if not str(path).startswith(str(root)):
        raise PermissionError("Path must be under project root")
    return path


def generate_request_id() -> str:
    """Cryptographically safe request id for logging/tracing."""
    return secrets.token_hex(8)
