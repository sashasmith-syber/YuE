"""
MusicGen engine — refactored from original K2 music_generator.
Preserves existing MusicGen functionality exactly.
"""
from __future__ import annotations

import io
import base64
import logging
import threading
from typing import Any, Dict, Optional

import numpy as np
import soundfile as sf
import torch

from core.config import get_config
from engines.base_engine import BaseEngine

logger = logging.getLogger(__name__)


class MusicGenEngine(BaseEngine):
    """MusicGen AI music generation; same behavior as original K2."""

    name = "musicgen"
    supports_async = False
    _instance: Optional["MusicGenEngine"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "MusicGenEngine":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_model") and self._model is not None:
            return
        self._model = None
        self._processor = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("MusicGenEngine initialized. Device: %s", self.device)

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> bool:
        if self._model is not None:
            return True
        cfg = get_config()
        model_name = cfg.MUSICGEN_MODEL
        try:
            from transformers import MusicgenProcessor, MusicgenForConditionalGeneration
            logger.info("Loading MusicGen model: %s", model_name)
            self._processor = MusicgenProcessor.from_pretrained(model_name)
            self._model = MusicgenForConditionalGeneration.from_pretrained(model_name)
            self._model.to(self.device)
            self._model.eval()
            logger.info("MusicGen loaded on %s", self.device)
            return True
        except Exception as e:
            logger.error("Failed to load MusicGen: %s", e)
            return False

    def generate(
        self,
        prompt: str,
        duration_seconds: Optional[int] = None,
        temperature: float = 1.0,
        top_k: int = 250,
        top_p: float = 0.9,
        guidance_scale: float = 3.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        cfg = get_config()
        duration = duration_seconds or 10
        duration = min(max(1, duration), cfg.MUSICGEN_MAX_DURATION)
        if not self.is_loaded and not self.load():
            return {"success": False, "error": "Failed to load model"}
        try:
            inputs = self._processor(
                text=[prompt],
                padding=True,
                return_tensors="pt",
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            with torch.no_grad():
                audio_values = self._model.generate(
                    **inputs,
                    max_new_tokens=int(duration * 256),
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    guidance_scale=guidance_scale,
                )
            audio = audio_values.cpu().numpy()[0]
            if len(audio.shape) > 1:
                audio = audio[0]
            audio = audio / (np.max(np.abs(audio)) + 1e-8)
            buffer = io.BytesIO()
            sf.write(buffer, audio, cfg.MUSICGEN_SAMPLE_RATE, format="WAV")
            buffer.seek(0)
            audio_b64 = base64.b64encode(buffer.read()).decode("utf-8")
            return {
                "success": True,
                "audio": audio_b64,
                "format": "wav",
                "sample_rate": cfg.MUSICGEN_SAMPLE_RATE,
                "duration": duration,
                "prompt": prompt,
                "model": cfg.MUSICGEN_MODEL,
            }
        except Exception as e:
            logger.exception("MusicGen generation failed")
            return {"success": False, "error": str(e)}
