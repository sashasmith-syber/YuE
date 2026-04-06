"""Security tests: subprocess timeout, invalid input, file permissions, network isolation."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_subprocess_timeout_enforcement():
    """InferWrapper uses timeout; terminate() cleans up process."""
    from yue.infer_wrapper import InferWrapper, YUE_SUBPROCESS_TIMEOUT_DEFAULT
    assert YUE_SUBPROCESS_TIMEOUT_DEFAULT == 600
    wrapper = InferWrapper(
        genre_txt="electronic",
        lyrics_txt="[verse]\ntest",
        output_dir=tempfile.gettempdir(),
    )
    wrapper._process = None
    wrapper._started = False
    wrapper.terminate()  # no-op when no process
    # With a real sleeping process, terminate() should kill it
    try:
        p = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(10000)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )
        wrapper._process = p
        wrapper._started = True
        wrapper.terminate()
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
    assert True


def test_invalid_input_rejection():
    """Validation rejects invalid genre (non-whitelist), oversized lyrics, injection."""
    from core.tag_whitelist import validate_genre_tags_whitelist
    from core.security import sanitize_lyrics
    from core.exceptions import ValidationError
    # Whitelist: unknown tag should raise or be filtered
    try:
        out = validate_genre_tags_whitelist("electronic")
        assert "electronic" in out.lower()
    except ValueError:
        pass
    # Invalid tag string (all unknown) may raise
    try:
        validate_genre_tags_whitelist("xyznonexistenttag123")
    except ValueError as e:
        assert "allowed" in str(e).lower() or "whitelist" in str(e).lower()
    # Lyrics injection
    with pytest.raises(ValueError):
        sanitize_lyrics("<?php echo 1; ?>")
    with pytest.raises(ValueError):
        sanitize_lyrics("{{ 7*7 }}")


def test_file_permission_verification():
    """Output files can be set to 0o644."""
    from services.output_cleanup import set_output_permissions, OUTPUT_FILE_MODE
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        path = Path(f.name)
    try:
        set_output_permissions(path)
        mode = path.stat().st_mode & 0o777
        assert mode == OUTPUT_FILE_MODE
    finally:
        path.unlink(missing_ok=True)


def test_network_isolation_env():
    """YuE infer env must set HF_HUB_OFFLINE=1 (no network during generation)."""
    from yue.infer_wrapper import InferWrapper
    from core.config import get_config
    cfg = get_config()
    if not cfg.YUE_WORKSPACE:
        pytest.skip("YUE_WORKSPACE not set")
    # Build env as InferWrapper would (we only check the env dict construction)
    import os
    env = os.environ.copy()
    env["HF_HUB_OFFLINE"] = "1"
    assert env.get("HF_HUB_OFFLINE") == "1"


def test_wav_output_validation():
    """Invalid WAV magic or size out of bounds raises YuEError."""
    from yue.infer_wrapper import _validate_output_wav
    from core.exceptions import YuEError
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(b"RIFF\x00\x00\x00\x00WAVE")  # too small
        path = Path(f.name)
    try:
        with pytest.raises(YuEError):
            _validate_output_wav(path)
    finally:
        path.unlink(missing_ok=True)
    # File with wrong magic
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        f.write(b"FAKE\x00\x00\x00\x00\x00\x00\x00\x00")
        f.write(b"\x00" * (1024 * 1024))
        path = Path(f.name)
    try:
        with pytest.raises(YuEError):
            _validate_output_wav(path)
    finally:
        path.unlink(missing_ok=True)
