"""
Audio upload quarantine: write to quarantine dir, validate, then move to clean.
Caller must validate magic bytes and (optionally) ffprobe before promote.
"""
from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path

from core.config import get_config
from core.exceptions import ValidationError
from api.middleware.validation import validate_audio_upload, validate_audio_duration_and_sr

logger = logging.getLogger(__name__)

ALLOWED_EXT = {".wav", ".mp3"}


def quarantine_upload(data: bytes, filename: str) -> Path:
    """
    Write upload to quarantine dir. Returns path in quarantine.
    Does not validate content; caller should call validate_audio_upload(data, filename) first.
    """
    cfg = get_config()
    cfg.ensure_dirs()
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        ext = ".wav"
    name = f"{uuid.uuid4().hex[:12]}{ext}"
    path = cfg.QUARANTINE_DIR / name
    path.write_bytes(data)
    logger.info("Quarantined upload: %s", path.name)
    return path


def promote_to_clean(quarantine_path: Path) -> Path:
    """
    Move file from quarantine to clean after validation.
    Validates duration/sample rate via ffprobe if available.
    Returns path in clean dir.
    """
    cfg = get_config()
    cfg.ensure_dirs()
    if not quarantine_path.is_file():
        raise ValidationError("Quarantine file not found")
    if cfg.QUARANTINE_DIR not in quarantine_path.resolve().parents:
        raise ValidationError("Path not under quarantine")
    validate_audio_duration_and_sr(quarantine_path, max_duration_s=30)
    clean_path = cfg.CLEAN_UPLOADS_DIR / quarantine_path.name
    shutil.move(str(quarantine_path), str(clean_path))
    return clean_path


def save_upload_then_promote(data: bytes, filename: str) -> Path:
    """Validate, quarantine, then promote to clean. Returns path in clean."""
    validate_audio_upload(data, filename)
    qpath = quarantine_upload(data, filename)
    return promote_to_clean(qpath)
