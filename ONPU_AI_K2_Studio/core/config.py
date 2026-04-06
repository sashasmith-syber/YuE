"""
Unified configuration management.
All paths absolute or relative to project root. No hardcoded credentials.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

# Project root: directory containing this package's parent
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_project_root() -> Path:
    """Return absolute project root path."""
    return _PROJECT_ROOT


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """Get env var; raise if required and missing."""
    value = os.environ.get(key, default)
    if required and (value is None or value.strip() == ""):
        raise ValueError(f"Required environment variable not set: {key}")
    return value


class Config:
    """Unified configuration; values from env with sane defaults."""

    # Server
    HOST: str = get_env("K2_HOST") or "0.0.0.0"
    PORT: int = int(get_env("K2_PORT") or "5000")
    DEBUG: bool = (get_env("K2_DEBUG") or "false").lower() in ("1", "true", "yes")
    MAX_CONTENT_LENGTH_MB: int = int(get_env("K2_MAX_CONTENT_MB") or "16")

    # Paths (relative to project root unless overridden)
    UPLOAD_DIR: Path = _PROJECT_ROOT / "data" / "uploads"
    QUARANTINE_DIR: Path = _PROJECT_ROOT / "data" / "uploads" / "quarantine"
    CLEAN_UPLOADS_DIR: Path = _PROJECT_ROOT / "data" / "uploads" / "clean"
    OUTPUT_DIR: Path = _PROJECT_ROOT / "data" / "output"
    YUE_WORKSPACE: Optional[Path] = None  # Set via YUE_WORKSPACE env
    TEMP_DIR: Path = _PROJECT_ROOT / "data" / "tmp"
    OUTPUT_CLEANUP_AGE_HOURS: int = 24

    # MusicGen
    MUSICGEN_MODEL: str = get_env("MUSICGEN_MODEL") or "facebook/musicgen-medium"
    MUSICGEN_MAX_DURATION: int = int(get_env("MUSICGEN_MAX_DURATION") or "30")
    MUSICGEN_SAMPLE_RATE: int = 32000

    # YuE (subprocess)
    YUE_INFER_SCRIPT: str = "infer.py"
    YUE_STAGE1_MODEL: str = get_env("YUE_STAGE1_MODEL") or "m-a-p/YuE-s1-7B-anneal-en-cot"
    YUE_STAGE2_MODEL: str = get_env("YUE_STAGE2_MODEL") or "m-a-p/YuE-s2-1B-general"
    YUE_MAX_NEW_TOKENS: int = int(get_env("YUE_MAX_NEW_TOKENS") or "3000")
    YUE_RUN_N_SEGMENTS: int = int(get_env("YUE_RUN_N_SEGMENTS") or "2")
    YUE_SUBPROCESS_TIMEOUT: int = int(get_env("YUE_SUBPROCESS_TIMEOUT") or "600")
    YUE_SUBPROCESS_MAX_MEMORY_MB: Optional[int] = None  # Set in __init__ from env (default 16384)
    YUE_NICE: int = int(get_env("YUE_NICE") or "10")
    YUE_CUDA_DEVICE: str = get_env("YUE_CUDA_DEVICE") or "0"
    YUE_MODEL_CACHE: Path = _PROJECT_ROOT / "models" / "yue"
    YUE_MAX_QUEUE_DEPTH: int = int(get_env("YUE_MAX_QUEUE_DEPTH") or "10")
    YUE_MODEL_STALE_DAYS: int = int(get_env("YUE_MODEL_STALE_DAYS") or "7")
    # Security: production mode (validate_install requires .env)
    PRODUCTION_MODE: bool = (get_env("K2_PRODUCTION") or "false").lower() in ("1", "true", "yes")

    # Soundblueprint
    SOUNDBLUEPRINT_SAMPLE_RATE: int = 22050

    # Security / rate limits (tuned per engine in middleware)
    RATE_LIMIT_REQUESTS: int = int(get_env("K2_RATE_LIMIT_REQUESTS") or "60")
    RATE_LIMIT_WINDOW_S: int = int(get_env("K2_RATE_LIMIT_WINDOW_S") or "60")

    # Metrics
    PROMETHEUS_ENABLED: bool = (get_env("K2_PROMETHEUS_ENABLED") or "false").lower() in ("1", "true", "yes")
    METRICS_PORT: int = int(get_env("K2_METRICS_PORT") or "9090")

    def __init__(self) -> None:
        yue_ws = get_env("YUE_WORKSPACE")
        if yue_ws:
            self.YUE_WORKSPACE = Path(yue_ws).resolve()
        x = get_env("YUE_SUBPROCESS_MAX_MEMORY_MB")
        if x:
            self.YUE_SUBPROCESS_MAX_MEMORY_MB = int(x)
        else:
            self.YUE_SUBPROCESS_MAX_MEMORY_MB = 16384  # 16GB default
        self.UPLOAD_DIR = Path(get_env("K2_UPLOAD_DIR") or str(self.UPLOAD_DIR)).resolve()
        self.QUARANTINE_DIR = Path(get_env("K2_QUARANTINE_DIR") or str(self.UPLOAD_DIR / "quarantine")).resolve()
        self.CLEAN_UPLOADS_DIR = Path(get_env("K2_CLEAN_UPLOADS_DIR") or str(self.UPLOAD_DIR / "clean")).resolve()
        self.OUTPUT_DIR = Path(get_env("K2_OUTPUT_DIR") or str(self.OUTPUT_DIR)).resolve()
        self.TEMP_DIR = Path(get_env("K2_TEMP_DIR") or str(self.TEMP_DIR)).resolve()
        self.OUTPUT_CLEANUP_AGE_HOURS = int(get_env("K2_OUTPUT_CLEANUP_AGE_HOURS") or "24")
        self.YUE_MODEL_CACHE = Path(get_env("YUE_MODEL_CACHE") or str(self.YUE_MODEL_CACHE)).resolve()

    def ensure_dirs(self) -> None:
        """Create configured directories if missing."""
        for d in (self.UPLOAD_DIR, self.QUARANTINE_DIR, self.CLEAN_UPLOADS_DIR, self.OUTPUT_DIR, self.TEMP_DIR):
            d.mkdir(parents=True, exist_ok=True)


# Singleton
_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
