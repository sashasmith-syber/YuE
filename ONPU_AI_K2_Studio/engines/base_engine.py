"""
Abstract base for all music generation engines.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseEngine(ABC):
    """Abstract base class for MusicGen, YuE, and future engines."""

    name: str = "base"
    supports_async: bool = False

    @abstractmethod
    def generate(
        self,
        prompt: str,
        duration_seconds: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Generate audio from prompt. Returns dict with at least:
        - success: bool
        - audio: base64-encoded WAV (on success)
        - format: "wav"
        - sample_rate: int
        - duration: float
        - error: str (on failure)
        """
        pass

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """True if model/resources are loaded and ready."""
        pass

    def load(self) -> bool:
        """Optional: load model. Default no-op."""
        return True

    def unload(self) -> None:
        """Optional: release resources."""
        pass
