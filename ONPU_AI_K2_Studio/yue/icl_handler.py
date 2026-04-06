"""
In-context learning: reference audio preprocessing for YuE.
Resample 16kHz, mono, normalize -3dB, trim to 30s. Quarantine → validate → clean.
"""
from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Tuple

from core.config import get_config
from core.exceptions import ValidationError

logger = logging.getLogger(__name__)

ALLOWED_AUDIO_EXT = {".wav", ".mp3"}
MAX_REF_DURATION_S = 30
ICL_SAMPLE_RATE = 16000
PEAK_DB = -3.0
MAX_REF_SIZE_MB = 10


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _ffprobe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0 and r.stdout:
            return float(r.stdout.strip())
    except Exception:
        pass
    return 0.0


def preprocess_reference_audio(
    source_path: Path,
    job_id: str,
    target_duration_s: float = MAX_REF_DURATION_S,
    sample_rate: int = ICL_SAMPLE_RATE,
    peak_db: float = PEAK_DB,
) -> Path:
    """
    Resample to 16kHz, mono, normalize to peak_db, trim to target_duration_s.
    Saves to uploads/clean/reference_{job_id}.wav.
    """
    cfg = get_config()
    cfg.ensure_dirs()
    out_path = cfg.CLEAN_UPLOADS_DIR / f"reference_{job_id}.wav"
    if not _ffmpeg_available():
        # Fallback: copy and hope (or raise)
        import shutil
        shutil.copy(source_path, out_path)
        logger.warning("ffmpeg not available; copied reference without preprocessing")
        return out_path
    # ffmpeg: -i in -ar 16000 -ac 1 -af loudnorm=I=-3 -t 30 out.wav
    cmd = [
        "ffmpeg", "-y", "-i", str(source_path),
        "-ar", str(sample_rate),
        "-ac", "1",
        "-af", f"loudnorm=I={peak_db}",
        "-t", str(target_duration_s),
        str(out_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise ValidationError(f"ffmpeg failed: {(r.stderr or '')[-500:]}")
    except subprocess.TimeoutExpired:
        raise ValidationError("Reference audio preprocessing timed out")
    if not out_path.is_file():
        raise ValidationError("Preprocessed reference file was not created")
    return out_path


def validate_ref_audio(path: Path) -> None:
    """Raise ValidationError if path is not a valid audio file (size, duration)."""
    if not path.is_file():
        raise ValidationError(f"Reference file not found: {path}")
    if path.suffix.lower() not in ALLOWED_AUDIO_EXT and path.suffix.lower() not in (".flac", ".ogg"):
        raise ValidationError(f"Unsupported format: {path.suffix}")
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > MAX_REF_SIZE_MB:
        raise ValidationError(f"Reference file too large: {size_mb:.1f}MB (max {MAX_REF_SIZE_MB}MB)")
    dur = _ffprobe_duration(path)
    if dur > MAX_REF_DURATION_S + 5:
        logger.warning("Reference duration %.1fs exceeds %ds; will be trimmed", dur, MAX_REF_DURATION_S)


def stage_ref_audio(
    vocal_path: Optional[str] = None,
    instrumental_path: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Tuple[Optional[Path], Optional[Path]]:
    """
    Validate and return resolved paths. If job_id given and paths are files,
    optionally preprocess to clean/reference_{job_id}_vocal.wav and reference_{job_id}_inst.wav.
    """
    cfg = get_config()
    root = cfg.CLEAN_UPLOADS_DIR
    jid = job_id or uuid.uuid4().hex[:8]
    v_path = None
    i_path = None
    if vocal_path:
        p = Path(vocal_path)
        if not p.is_absolute():
            p = root / p if (root / p).exists() else cfg.QUARANTINE_DIR / p
        validate_ref_audio(p)
        v_path = preprocess_reference_audio(p, f"{jid}_vocal") if p.is_file() else p.resolve()
    if instrumental_path:
        p = Path(instrumental_path)
        if not p.is_absolute():
            p = root / p if (root / p).exists() else cfg.QUARANTINE_DIR / p
        validate_ref_audio(p)
        i_path = preprocess_reference_audio(p, f"{jid}_inst") if p.is_file() else p.resolve()
    return v_path, i_path
