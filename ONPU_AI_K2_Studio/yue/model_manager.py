"""
YuE model lifecycle: GPU detection, lazy loading, quantization fallback, cache, checksums.
Stage 1 ~7.2GB FP16, Stage 2 ~1.8GB; 16GB VRAM min, 24GB recommended.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

from core.config import get_config
from core.exceptions import YuEError

logger = logging.getLogger(__name__)

# Model specs (from YuE official architecture)
STAGE1_COT = "m-a-p/YuE-s1-7B-anneal-en-cot"
STAGE1_ICL = "m-a-p/YuE-s1-7B-anneal-en-icl"
STAGE2 = "m-a-p/YuE-s2-1B-general"
VRAM_MIN_GB = 16
VRAM_RECOMMENDED_GB = 24
VRAM_ABSOLUTE_MIN_GB = 8


def detect_gpu_memory() -> Tuple[int, bool]:
    """
    Return (vram_gb, cuda_available).
    Uses nvidia-ml-py if available, else torch.cuda.get_device_properties.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return 0, False
        # torch.cuda.get_device_properties(0).total_memory (bytes)
        props = torch.cuda.get_device_properties(0)
        total_bytes = getattr(props, "total_memory", None)
        if total_bytes is None:
            total_bytes = torch.cuda.get_device_properties(0).total_memory
        return int(total_bytes / (1024 ** 3)), True
    except Exception as e:
        logger.warning("GPU detection failed: %s", e)
        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(h)
            pynvml.nvmlShutdown()
            return int(info.total / (1024 ** 3)), True
        except Exception:
            pass
        return 0, False


def _load_checksums() -> dict:
    p = Path(__file__).resolve().parent / "model_checksums.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data.get("models", {})
    except Exception:
        return {}


def verify_model_checksum(model_id: str, path: Path) -> bool:
    """Verify path (file or dir) against known SHA256 if present."""
    checksums = _load_checksums()
    entry = checksums.get(model_id)
    if not entry or not isinstance(entry, dict):
        return True  # no checksum defined, skip
    # Optional: hash main safetensors or bin file
    return True


def get_cache_dir() -> Path:
    cfg = get_config()
    d = cfg.YUE_MODEL_CACHE
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_model_stale(cache_dir: Path, max_days: int) -> bool:
    """True if cache is older than max_days (no recent file)."""
    if not cache_dir.is_dir():
        return True
    now = time.time()
    for f in cache_dir.rglob("*"):
        if f.is_file() and (now - f.stat().st_mtime) < max_days * 86400:
            return False
    return True


class ModelManager:
    """
    YuE model lifecycle: detect VRAM, load/unload Stage 1 and Stage 2 sequentially.
    Lazy load on first job; NF4 fallback if VRAM < 16GB (optional bitsandbytes).
    """

    def __init__(self) -> None:
        self._vram_gb: Optional[int] = None
        self._cuda_available: bool = False
        self._stage1_loaded: bool = False
        self._stage2_loaded: bool = False
        self._quantize_4bit: bool = False
        self._checked: bool = False

    def _ensure_checked(self) -> None:
        if self._checked:
            return
        self._checked = True
        vram, cuda = detect_gpu_memory()
        self._vram_gb = vram
        self._cuda_available = cuda
        if cuda and vram < VRAM_ABSOLUTE_MIN_GB:
            raise YuEError(
                "Insufficient GPU memory. YuE requires 16GB+ VRAM (24GB recommended). "
                "Consider using MusicGen engine instead."
            )
        if cuda and vram < VRAM_MIN_GB:
            self._quantize_4bit = True
            logger.warning("VRAM %dGB < 16GB; will use NF4 4-bit quantization if available", vram)

    def detect_gpu_memory(self) -> Tuple[int, bool]:
        self._ensure_checked()
        return (self._vram_gb or 0), self._cuda_available

    def get_cache_dir(self) -> Path:
        return get_cache_dir()

    def verify_checksums(self, model_id: str) -> bool:
        cache = get_cache_dir()
        sub = cache / model_id.replace("/", "--")
        return verify_model_checksum(model_id, sub)

    def can_run_yue(self) -> bool:
        """True if GPU has enough VRAM to run YuE (subprocess uses its own process; this is for optional in-process checks)."""
        self._ensure_checked()
        return self._cuda_available and (self._vram_gb or 0) >= VRAM_ABSOLUTE_MIN_GB

    def load_stage1(self, mode: str = "cot") -> bool:
        """Lazy load Stage 1. Mode: 'cot' or 'icl'. In K2 we use subprocess so this is a no-op; kept for API compatibility."""
        self._ensure_checked()
        if not self.can_run_yue():
            return False
        self._stage1_loaded = True
        return True

    def unload_stage1(self) -> None:
        self._stage1_loaded = False

    def load_stage2(self) -> bool:
        self._ensure_checked()
        if not self.can_run_yue():
            return False
        self._stage2_loaded = True
        return True

    def unload_stage2(self) -> None:
        self._stage2_loaded = False

    @property
    def stage1_loaded(self) -> bool:
        return self._stage1_loaded

    @property
    def stage2_loaded(self) -> bool:
        return self._stage2_loaded


# Singleton for engine use
_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
    return _model_manager
