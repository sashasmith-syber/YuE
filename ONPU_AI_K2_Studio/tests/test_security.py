"""Tests for security layer (sanitization, paths)."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.security import sanitize_prompt, sanitize_genre_tags, safe_filename, sanitize_lyrics


def test_sanitize_prompt_empty():
    assert sanitize_prompt("") == ""
    assert sanitize_prompt(None) == ""


def test_sanitize_prompt_ok():
    assert sanitize_prompt("hello world") == "hello world"
    assert "electronic" in sanitize_prompt("  electronic  dance  ")


def test_sanitize_genre_tags():
    assert sanitize_genre_tags("house, bass") != ""
    assert sanitize_genre_tags("") == ""


def test_safe_filename():
    assert safe_filename("out", ".wav").endswith(".wav")
    assert "output" in safe_filename("../../../etc/passwd")


def test_sanitize_lyrics_strips_html():
    assert "<script>" not in sanitize_lyrics("hello <script>alert(1)</script> world")


def test_sanitize_lyrics_blocks_injection():
    with pytest.raises(ValueError, match="disallowed"):
        sanitize_lyrics("<?php system($_GET['x']); ?>")
    with pytest.raises(ValueError, match="disallowed"):
        sanitize_lyrics("${7*7}")
    with pytest.raises(ValueError, match="disallowed"):
        sanitize_lyrics("{{config}}")


def test_sanitize_lyrics_max_length():
    long_text = "a" * 10000
    assert len(sanitize_lyrics(long_text, max_length=5000)) <= 5000
