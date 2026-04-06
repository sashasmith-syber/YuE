"""
Input sanitization and request validation.
Defense-in-depth: genre whitelist, lyrics injection prevention, audio quarantine flow.
"""
from __future__ import annotations

import re
from pathlib import Path

from flask import request

from core.security import sanitize_prompt, sanitize_genre_tags, sanitize_lyrics
from core.tag_whitelist import validate_genre_tags_whitelist, get_tag_whitelist
from core.security_limits import (
    MAX_JSON_BODY,
    LYRICS_MAX_CHARS,
    GENRE_MAX_CHARS,
    PROMPT_MAX_CHARS,
    LYRICS_REQUIRED_MARKERS,
    AUDIO_MAX_BYTES,
)
from core.exceptions import ValidationError

# WAV: RIFF....WAVE
WAV_MAGIC = b"RIFF"
WAV_WAVE_OFFSET = 8
# MP3: ID3 or \xff\xfb / \xff\xfa
MP3_ID3 = b"ID3"
MP3_FFFB = b"\xff\xfb"
MP3_FFFA = b"\xff\xfa"


def validate_generate_request() -> None:
    """Validate /api/generate body; raise ValidationError if invalid."""
    if request.content_length and request.content_length > MAX_JSON_BODY:
        raise ValidationError("Request body too large", field="body")
    data = request.get_json(silent=True)
    if data is not None and not isinstance(data, dict):
        raise ValidationError("JSON body must be an object")
    if not data or "prompt" not in data:
        raise ValidationError("Missing 'prompt' field", field="prompt")
    prompt = sanitize_prompt(data.get("prompt"), max_length=PROMPT_MAX_CHARS)
    if not prompt:
        raise ValidationError("Invalid or empty prompt", field="prompt")
    engine = (data.get("engine") or "musicgen").strip().lower()
    if engine not in ("musicgen", "yue"):
        raise ValidationError("Invalid engine", field="engine")
    if engine == "yue":
        genre_raw = data.get("genre_tags") or prompt
        if len(genre_raw) > GENRE_MAX_CHARS:
            raise ValidationError(f"Genre tags exceed {GENRE_MAX_CHARS} chars", field="genre_tags")
        try:
            validate_genre_tags_whitelist(sanitize_genre_tags(genre_raw, GENRE_MAX_CHARS))
        except ValueError as e:
            raise ValidationError(str(e), field="genre_tags")
        lyrics_raw = data.get("lyrics")
        if lyrics_raw is not None:
            if len(lyrics_raw) > LYRICS_MAX_CHARS:
                raise ValidationError(f"Lyrics exceed {LYRICS_MAX_CHARS} chars", field="lyrics")
            try:
                sanitize_lyrics(lyrics_raw, max_length=LYRICS_MAX_CHARS)
            except ValueError as e:
                raise ValidationError(str(e), field="lyrics")
            lower = lyrics_raw.lower()
            if lyrics_raw.strip() and not any(m in lower for m in LYRICS_REQUIRED_MARKERS):
                raise ValidationError(
                    "Lyrics must contain at least one [Verse] or [Chorus] marker",
                    field="lyrics",
                )


def validate_audio_upload(data: bytes, filename: str) -> None:
    """
    Validate uploaded audio: max size, magic bytes.
    Raises ValidationError if invalid.
    """
    if len(data) > AUDIO_MAX_BYTES:
        raise ValidationError(f"Audio file exceeds 10MB limit (got {len(data) / (1024*1024):.1f}MB)")
    if len(data) < 12:
        raise ValidationError("File too small to be valid audio")
    ext = Path(filename).suffix.lower()
    if ext == ".wav":
        if data[:4] != WAV_MAGIC or (len(data) >= 12 and data[8:12] != b"WAVE"):
            raise ValidationError("Invalid WAV: bad magic bytes")
    elif ext == ".mp3":
        if not (data[:3] == MP3_ID3 or data[:2] == MP3_FFFB[:2] or data[:2] == MP3_FFFA[:2]):
            raise ValidationError("Invalid MP3: bad magic bytes")
    else:
        if data[:4] == WAV_MAGIC:
            pass
        elif data[:3] == MP3_ID3 or (len(data) >= 2 and data[0:2] in (MP3_FFFB[:2], MP3_FFFA[:2])):
            pass
        else:
            raise ValidationError("Unsupported or invalid audio format")


def validate_audio_duration_and_sr(path: Path, max_duration_s: int = 30) -> None:
    """
    Optional: FFmpeg/ffprobe to verify duration <= 30s and sample rate 16k-48k.
    Raises ValidationError if check fails. Skip if ffprobe not available.
    """
    try:
        import subprocess
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=sample_rate",
                "-of", "default=noprint_wrappers=1", str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise ValidationError("Could not probe audio file")
        out = result.stdout or ""
        for line in out.splitlines():
            if "duration=" in line:
                try:
                    d = float(line.split("=")[-1].strip())
                    if d > max_duration_s:
                        raise ValidationError(f"Audio duration {d:.1f}s exceeds {max_duration_s}s limit")
                except (IndexError, ValueError):
                    pass
            if "sample_rate=" in line:
                try:
                    sr = int(line.split("=")[-1].strip())
                    if sr < 16000 or sr > 48000:
                        raise ValidationError(f"Sample rate {sr} outside 16kHz-48kHz")
                except (IndexError, ValueError):
                    pass
    except FileNotFoundError:
        pass  # ffprobe not installed; skip probe
    except ValidationError:
        raise
    except Exception:
        raise ValidationError("Audio probe failed")
