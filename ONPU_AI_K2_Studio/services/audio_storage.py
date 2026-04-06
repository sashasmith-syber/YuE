"""
Local and optional cloud sync for generated audio.
All paths via config; no hardcoded credentials.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

from core.config import get_config
from core.security import safe_filename

logger = logging.getLogger(__name__)


def save_audio_local(
    audio_base64: str,
    prefix: str = "onpu",
    extension: str = "wav",
) -> Path:
    """Save base64 WAV to configured OUTPUT_DIR. Returns path."""
    cfg = get_config()
    cfg.ensure_dirs()
    name = safe_filename(prefix, suffix=extension)
    path = cfg.OUTPUT_DIR / name
    data = base64.b64decode(audio_base64)
    path.write_bytes(data)
    logger.info("Saved audio to %s", path)
    return path


def load_audio_as_base64(path: Path) -> Optional[str]:
    """Load file and return base64 string."""
    if not path.is_file():
        return None
    return base64.b64encode(path.read_bytes()).decode("utf-8")
