#!/usr/bin/env python3
"""
Post-install verification: imports, config, engines, soundblueprint.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    errors = []
    # Production: require .env or .env.local (no secrets in code)
    import os
    prod = (os.environ.get("K2_PRODUCTION") or "").lower() in ("1", "true", "yes")
    if prod:
        env_file = PROJECT_ROOT / ".env"
        env_local = PROJECT_ROOT / ".env.local"
        if not env_file.is_file() and not env_local.is_file():
            errors.append("Production mode: .env or .env.local is required (missing)")
    # Core
    try:
        from core.config import get_config
        get_config().ensure_dirs()
    except Exception as e:
        errors.append(f"core.config: {e}")
    try:
        from core.security import sanitize_prompt
        assert sanitize_prompt("hello") == "hello"
    except Exception as e:
        errors.append(f"core.security: {e}")
    # Engines
    try:
        from engines.engine_factory import get_engine, list_engines
        assert "musicgen" in list_engines()
        assert "yue" in list_engines()
    except Exception as e:
        errors.append(f"engines: {e}")
    # Soundblueprint
    try:
        from soundblueprint import get_analyzer, DNA_DIMENSIONS
        assert len(DNA_DIMENSIONS) > 0
    except Exception as e:
        errors.append(f"soundblueprint: {e}")
    if errors:
        for e in errors:
            print(f"FAIL: {e}")
        return 1
    print("OK: All packages and config valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
