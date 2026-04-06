"""Secrets audit: no password/secret/key/token string literals; only os.getenv/config."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_no_secrets_in_py_files():
    """Grep for password|secret|key|token in *.py; must only be in os.getenv or config/get_env."""
    sensitive = re.compile(
        r"\b(password|secret|api_key|apikey|token|credential)\s*=\s*['\"][^'\"]+['\"]",
        re.I,
    )
    env_ok = re.compile(r"os\.environ\.get|get_env|config\.|\.get\([\"'](?:password|secret|key|token)")
    allowed = re.compile(r"#.*|\.example|\.env\.example|placeholder|example\.com")
    violations = []
    for py in ROOT.rglob("*.py"):
        if "test_" in py.name or "__pycache__" in str(py):
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in sensitive.finditer(text):
            snippet = text[max(0, m.start() - 20) : m.end() + 20]
            if env_ok.search(snippet) or allowed.search(snippet):
                continue
            # Check if line uses getenv
            line_start = text.rfind("\n", 0, m.start()) + 1
            line = text[line_start : text.find("\n", m.start())]
            if "getenv" in line or "get_env" in line or "os.environ" in line:
                continue
            violations.append(f"{py.relative_to(ROOT)}: {m.group(0)[:50]}...")
    assert not violations, "Possible secrets in code: " + "; ".join(violations[:5])
