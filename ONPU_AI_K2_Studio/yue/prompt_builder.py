"""
Genre / DNA → YuE prompt mapping.
DNA translation matrix, lyrics structure enforcement, genre tag format.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from core.security import sanitize_genre_tags
from core.tag_whitelist import get_tag_whitelist, validate_genre_tags_whitelist

# DNA → YuE genre/style modifiers (from spec)
TRE_HIGH_BPM = (140, 999, ["Fast Tempo", "High Energy", "Driving"])
TRE_MID_BPM = (100, 140, ["Medium Tempo", "Steady Groove"])
TRE_LOW_BPM = (0, 100, ["Slow Tempo", "Laid Back", "Downtempo"])
RIM_HIGH = (0.7, 1.0, ["Driving Beat", "Heavy Percussion", "Four-on-the-Floor"])
RIM_MID = (0.4, 0.7, ["Groovy", "Syncopated", "Funky"])
RIM_LOW = (0.0, 0.4, ["Sparse Percussion", "Ambient", "Floaty"])
# GRM in spec is "Spectral Centroid" - map to brightness (TDU has spectral_centroid; use TRE or SDE as proxy)
BRIGHT_HIGH = (3000, 20000, ["Bright", "Airy", "Shimmering"])
BRIGHT_MID = (1000, 3000, ["Warm", "Analog", "Vintage"])
BRIGHT_LOW = (0, 1000, ["Dark", "Muffled", "Sub-heavy"])
MAX_TAGS_PER_REQUEST = 5
MAX_SEGMENTS = 4
REQUIRED_MARKERS = ("[verse]", "[chorus]", "[bridge]", "[outro]", "[intro]")
MARKER_PATTERN = re.compile(r"\[(\w+)\]", re.I)


def _in_range(value: float, low: float, high: float) -> bool:
    return low <= value <= high


def _tags_from_range(value: float, ranges: List[tuple]) -> List[str]:
    for (low, high, tags) in ranges:
        if _in_range(value, low, high):
            return tags
    return []


def dna_to_genre_modifiers(dna: Dict[str, Any]) -> List[str]:
    """
    Map Soundblueprint DNA dimensions to YuE genre/style modifiers.
    Returns list of modifier strings (whitelist-filtered later).
    """
    out = []
    tre = dna.get("TRE", {})
    if isinstance(tre, dict):
        tempo = tre.get("tempo")
        if tempo is not None:
            out.extend(_tags_from_range(float(tempo), [TRE_HIGH_BPM, TRE_MID_BPM, TRE_LOW_BPM]))
    rim = dna.get("RIM", {})
    if isinstance(rim, dict):
        strength = rim.get("pattern_strength")
        if strength is not None:
            out.extend(_tags_from_range(float(strength), [RIM_HIGH, RIM_MID, RIM_LOW]))
    tdu = dna.get("TDU", {})
    if isinstance(tdu, dict):
        brightness = tdu.get("timbre_brightness", 0)
        if brightness:
            out.extend(_tags_from_range(float(brightness), [BRIGHT_HIGH, BRIGHT_MID, BRIGHT_LOW]))
    return out


def validate_lyrics_structure(lyrics: str) -> str:
    """
    Enforce structure: required markers, bracket balance, max 4 segments.
    Auto-insert [Verse] at start if missing. Raises ValueError if invalid.
    """
    if not lyrics or not lyrics.strip():
        return "[Verse]\n\n"
    text = lyrics.strip()
    opens = len(re.findall(r"\[", text))
    closes = len(re.findall(r"\]", text))
    if opens != closes:
        raise ValueError("Lyrics: bracket imbalance (every [ must have ])")
    lower = text.lower()
    has_marker = any(m in lower for m in REQUIRED_MARKERS)
    if not has_marker:
        text = "[Verse]\n\n" + text
    parts = re.split(r"(\[\w+\])", text, flags=re.IGNORECASE)
    segments = []
    current = []
    for p in parts:
        if p.strip() and re.match(r"\[\w+\]", p.strip(), re.I):
            if current:
                segments.append("".join(current).strip())
            current = [p.strip()]
        else:
            current.append(p)
    if current:
        segments.append("".join(current).strip())
    segments = [s for s in segments if s][:MAX_SEGMENTS]
    return "\n\n".join(segments).strip() or "[Verse]\n\n"


def build_genre_tag_line(tags: List[str]) -> str:
    """Format: [Genre] tag1, tag2, tag3. Max 5 tags; whitelist enforced by caller."""
    whitelist = get_tag_whitelist()
    allowed = [t for t in tags if t.strip().lower() in whitelist][:MAX_TAGS_PER_REQUEST]
    if not allowed:
        return "[Genre] electronic"
    return "[Genre] " + ", ".join(allowed)


def build_yue_prompt(
    genre_tags: str,
    lyrics: Optional[str] = None,
    dna_hints: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Build genre tag string for YuE. Optionally map DNA dimensions to tags.
    Whitelist enforced.
    """
    tags = sanitize_genre_tags(genre_tags or "electronic", max_length=500)
    if dna_hints:
        modifiers = dna_to_genre_modifiers(dna_hints)
        tags = f"{tags} " + " ".join(modifiers) if modifiers else tags
    try:
        return validate_genre_tags_whitelist(tags)
    except ValueError:
        return tags.strip() or "electronic"


def build_lyrics_content(lyrics: Optional[str], segments: int = 2) -> str:
    """Build lyrics.txt with session labels. Validates structure and enforces max segments."""
    if not lyrics or not lyrics.strip():
        return "[Verse]\n\n" * min(segments, MAX_SEGMENTS)
    validated = validate_lyrics_structure(lyrics)
    lines = validated.strip().split("\n\n")
    out = []
    for i, block in enumerate(lines[: min(segments, MAX_SEGMENTS)]):
        out.append(block.strip())
    return "\n\n".join(out)
