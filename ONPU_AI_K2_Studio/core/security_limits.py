"""
Security constants and patterns: limits, magic bytes, injection blocks.
No secrets; used by validation and infer_wrapper.
"""
from __future__ import annotations

import re

# Length limits
LYRICS_MAX_CHARS = 5000
GENRE_MAX_CHARS = 500
PROMPT_MAX_CHARS = 2000
MAX_JSON_BODY = 16 * 1024 * 1024  # 16MB

# Audio upload (ICL)
AUDIO_MAX_BYTES = 10 * 1024 * 1024  # 10MB
AUDIO_MAX_DURATION_S = 30
AUDIO_SAMPLE_RATE_MIN = 16000
AUDIO_SAMPLE_RATE_MAX = 48000

# Output validation (YuE WAV)
WAV_MAGIC = b"RIFF"
WAV_WAVE = b"WAVE"
OUTPUT_FILE_MIN_BYTES = 1 * 1024 * 1024   # 1MB
OUTPUT_FILE_MAX_BYTES = 50 * 1024 * 1024  # 50MB

# Subprocess
YUE_SUBPROCESS_TIMEOUT_DEFAULT = 600  # seconds
YUE_TERMINATE_WAIT_S = 5
YUE_VMEM_LIMIT_MB_DEFAULT = 16384  # 16GB
YUE_NICE_DEFAULT = 10  # low CPU priority

# Template / injection block patterns (lyrics)
INJECTION_PATTERNS = [
    re.compile(r"<\?php", re.I),
    re.compile(r"<%", re.I),
    re.compile(r"\$\{"),
    re.compile(r"\{\{"),
    re.compile(r"<\s*script", re.I),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"on\w+\s*=", re.I),
]
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")

# Genre: allow only alphanumeric, space, hyphen, underscore, comma
GENRE_STRICT_PATTERN = re.compile(r"^[a-zA-Z0-9\s\-_,.]+$")

# Required lyrics structure for YuE
LYRICS_REQUIRED_MARKERS = ("[verse]", "[chorus]")
