"""
Runtime engine selection (MusicGen vs YuE).
"""
from __future__ import annotations

from typing import Optional

from engines.base_engine import BaseEngine
from engines.musicgen_engine import MusicGenEngine
from engines.yue_engine import YuEEngine

_ENGINES: dict[str, BaseEngine] = {}


def get_engine(name: str) -> BaseEngine:
    """Get engine by name: 'musicgen' or 'yue'."""
    global _ENGINES
    name = (name or "musicgen").lower().strip()
    if name not in _ENGINES:
        if name == "yue":
            _ENGINES[name] = YuEEngine()
        else:
            _ENGINES[name] = MusicGenEngine()
    return _ENGINES[name]


def list_engines() -> list[str]:
    """Return available engine names."""
    return ["musicgen", "yue"]
