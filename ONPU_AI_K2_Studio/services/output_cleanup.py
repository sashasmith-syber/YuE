"""
Output directory: strict permissions (644), auto-cleanup after 24h.
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from core.config import get_config

logger = logging.getLogger(__name__)

# Target file mode: 0o644 (owner rw, group/other r)
OUTPUT_FILE_MODE = 0o644


def set_output_permissions(path: Path) -> None:
    """Set file to 644 (no exec)."""
    try:
        os.chmod(path, OUTPUT_FILE_MODE)
    except OSError as e:
        logger.warning("Could not chmod %s: %s", path, e)


def cleanup_old_outputs(max_age_hours: int | None = None) -> int:
    """
    Remove output files older than max_age_hours. Returns count removed.
    """
    cfg = get_config()
    age = max_age_hours if max_age_hours is not None else cfg.OUTPUT_CLEANUP_AGE_HOURS
    cutoff = time.time() - (age * 3600)
    removed = 0
    for p in cfg.OUTPUT_DIR.rglob("*"):
        if not p.is_file():
            continue
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                removed += 1
        except OSError as e:
            logger.warning("Could not remove %s: %s", p, e)
    if removed:
        logger.info("Cleaned up %d output files older than %dh", removed, age)
    return removed
