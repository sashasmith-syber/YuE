"""
Genre tag whitelist for YuE (from official YuE top tags).
Only whitelisted tags are accepted in genre prompts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import FrozenSet

logger = logging.getLogger(__name__)

# Fallback: embedded whitelist (ASCII-safe subset of YuE top tags)
_DEFAULT_WHITELIST: FrozenSet[str] = frozenset({
    "pop", "rock", "electronic", "classical", "r&b", "folk", "rap", "soundtrack",
    "country", "indie-rock", "punk", "hiphop", "hip-hop", "experimental", "funk",
    "blues", "ambient", "new age", "experimental pop", "classic rock", "indie rock",
    "alternative rock", "reggae", "electro pop", "k-pop", "dance", "hip hop",
    "80s", "dancehall", "disco", "house", "instrumental", "lounge", "latin",
    "hardcore", "soul", "grunge", "world", "techno", "indie pop", "downtempo",
    "trap", "avant-garde", "chillout", "new wave", "rnb", "pop rock", "indie folk",
    "opera", "metal", "gospel", "electro", "dance pop", "synthpop", "dubstep",
    "beats", "bass", "vocal", "female", "male", "bright", "dark", "uplifting",
    "inspiring", "airy", "electronic", "acoustic", "electric guitar", "piano",
    "drums", "synthesizer", "bass guitar", "808 bass", "synth bass", "funky bass",
    "fast tempo", "high energy", "driving", "medium tempo", "steady groove",
    "slow tempo", "laid back", "downtempo", "driving beat", "heavy percussion",
    "groovy", "syncopated", "funky", "sparse percussion", "ambient", "floaty",
    "bright", "airy", "shimmering", "warm", "analog", "vintage", "dark", "muffled", "sub-heavy",
})


def _normalize_tag(t: str) -> str:
    return t.strip().lower()


def get_tag_whitelist(whitelist_path: Path | None = None) -> FrozenSet[str]:
    """Return frozenset of allowed genre tags (lowercase)."""
    if whitelist_path and whitelist_path.is_file():
        try:
            raw = whitelist_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            tags = data.get("genre", data.get("tags", []))
            if isinstance(tags, list):
                return frozenset(_normalize_tag(t) for t in tags if t and isinstance(t, str))
        except Exception as e:
            logger.warning("Could not load tag whitelist from %s: %s", whitelist_path, e)
    return _DEFAULT_WHITELIST


def validate_genre_tags_whitelist(tag_string: str, whitelist: FrozenSet[str] | None = None) -> str:
    """
    Validate and filter genre string: only allow whitelisted tags.
    Returns space-joined allowed tags; raises ValueError if no tags allowed.
    """
    if whitelist is None:
        whitelist = get_tag_whitelist()
    parts = [p.strip() for p in tag_string.split() if p.strip()]
    allowed = [p for p in parts if _normalize_tag(p) in whitelist]
    if not allowed:
        raise ValueError("No allowed genre tags; use only tags from the official YuE list")
    return " ".join(allowed[:50])  # cap number of tags
