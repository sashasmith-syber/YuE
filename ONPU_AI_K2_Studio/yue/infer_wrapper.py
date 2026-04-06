"""
Safe subprocess wrapper for YuE inference.
Defense-in-depth: timeout, resource limits, clean terminate, input/output validation.
YuE runs with no network (HF_HUB_OFFLINE=1) after models cached.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from core.config import get_config
from core.exceptions import YuEError
from core.security_limits import (
    LYRICS_MAX_CHARS,
    GENRE_MAX_CHARS,
    YUE_SUBPROCESS_TIMEOUT_DEFAULT,
    YUE_TERMINATE_WAIT_S,
    YUE_VMEM_LIMIT_MB_DEFAULT,
    YUE_NICE_DEFAULT,
    WAV_MAGIC,
    WAV_WAVE,
    OUTPUT_FILE_MIN_BYTES,
    OUTPUT_FILE_MAX_BYTES,
)

logger = logging.getLogger(__name__)

# Path-safe: only these chars in path components
_PATH_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-/")


def _sanitize_path_component(s: str) -> str:
    """Allow only safe path chars; prevent traversal."""
    return "".join(c for c in s if c in _PATH_SAFE) or "output"


def _validate_output_wav(path: Path) -> None:
    """Verify WAV magic bytes and file size bounds. Raises YuEError if invalid."""
    if not path.is_file():
        raise YuEError("Output file not produced")
    size = path.stat().st_size
    if size < OUTPUT_FILE_MIN_BYTES or size > OUTPUT_FILE_MAX_BYTES:
        raise YuEError(f"Output file size out of bounds: {size} bytes")
    with open(path, "rb") as f:
        head = f.read(12)
    if len(head) < 12 or head[:4] != WAV_MAGIC or head[8:12] != WAV_WAVE:
        raise YuEError("Output file is not a valid WAV")


def _preexec_unix(mem_limit_mb: int, nice_val: int) -> None:
    """Set resource limits and nice in child (Unix). Call only in child process."""
    try:
        import resource
        limit = mem_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    except Exception:
        pass
    try:
        os.nice(nice_val)
    except Exception:
        pass


class InferWrapper:
    """
    Run YuE infer in isolated subprocess with timeout and resource limits.
    terminate() sends SIGTERM, waits YUE_TERMINATE_WAIT_S, then SIGKILL.
    """

    def __init__(
        self,
        genre_txt: str,
        lyrics_txt: str,
        output_dir: str,
        use_dual_tracks: bool = False,
        vocal_ref_path: Optional[str] = None,
        instrumental_ref_path: Optional[str] = None,
        prompt_start_time: float = 0.0,
        prompt_end_time: float = 30.0,
    ) -> None:
        if len(genre_txt) > GENRE_MAX_CHARS:
            raise YuEError(f"Genre text exceeds {GENRE_MAX_CHARS} chars")
        if len(lyrics_txt) > LYRICS_MAX_CHARS:
            raise YuEError(f"Lyrics exceed {LYRICS_MAX_CHARS} chars")
        self.genre_txt = genre_txt
        self.lyrics_txt = lyrics_txt or "[verse]\n\n"
        self.output_dir = Path(output_dir)
        self.use_dual_tracks = use_dual_tracks
        # Paths must be pre-validated by caller (under clean uploads / allowed dir)
        self.vocal_ref_path = str(vocal_ref_path) if vocal_ref_path else None
        self.instrumental_ref_path = str(instrumental_ref_path) if instrumental_ref_path else None
        self.prompt_start_time = prompt_start_time
        self.prompt_end_time = prompt_end_time
        self._process: Optional[subprocess.Popen] = None
        self._started = False

    def _build_cmd_and_env(self, tmp_dir: Path, infer_dir: Path, infer_script: Path) -> tuple[list[str], dict[str, str]]:
        cfg = get_config()
        genre_file = tmp_dir / "genre.txt"
        lyrics_file = tmp_dir / "lyrics.txt"
        genre_file.write_text(self.genre_txt, encoding="utf-8")
        lyrics_file.write_text(self.lyrics_txt, encoding="utf-8")
        out_sub = self.output_dir / "yue_subprocess"
        out_sub.mkdir(parents=True, exist_ok=True)
        cmd = [
            "python",
            str(infer_script),
            "--cuda_idx", str(cfg.YUE_CUDA_DEVICE),
            "--stage1_model", cfg.YUE_STAGE1_MODEL,
            "--stage2_model", cfg.YUE_STAGE2_MODEL,
            "--genre_txt", str(genre_file),
            "--lyrics_txt", str(lyrics_file),
            "--run_n_segments", str(cfg.YUE_RUN_N_SEGMENTS),
            "--output_dir", str(out_sub),
            "--max_new_tokens", str(cfg.YUE_MAX_NEW_TOKENS),
        ]
        if self.use_dual_tracks and self.vocal_ref_path and self.instrumental_ref_path:
            cmd += [
                "--use_dual_tracks_prompt",
                "--vocal_track_prompt_path", self.vocal_ref_path,
                "--instrumental_track_prompt_path", self.instrumental_ref_path,
                "--prompt_start_time", str(self.prompt_start_time),
                "--prompt_end_time", str(self.prompt_end_time),
            ]
        env = os.environ.copy()
        env["CUDA_VISIBLE_DEVICES"] = str(cfg.YUE_CUDA_DEVICE)
        env["HF_HUB_OFFLINE"] = "1"  # No network during inference
        return cmd, env

    def terminate(self) -> None:
        """SIGTERM → wait YUE_TERMINATE_WAIT_S → SIGKILL if still alive."""
        if not self._process or not self._started:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=YUE_TERMINATE_WAIT_S)
        except subprocess.TimeoutExpired:
            try:
                self._process.kill()
                self._process.wait(timeout=5)
            except Exception:
                pass
        except Exception:
            pass
        self._process = None

    def run(self) -> dict:
        """Execute YuE infer; return dict with success, audio (base64), or error."""
        cfg = get_config()
        workspace = cfg.YUE_WORKSPACE
        if not workspace or not workspace.is_dir():
            raise YuEError("YUE_WORKSPACE not set or not a directory")
        infer_dir = workspace / "inference"
        infer_script = infer_dir / cfg.YUE_INFER_SCRIPT
        if not infer_script.is_file():
            raise YuEError(f"YuE infer script not found: {infer_script}")
        timeout = getattr(cfg, "YUE_SUBPROCESS_TIMEOUT", None) or YUE_SUBPROCESS_TIMEOUT_DEFAULT
        mem_mb = cfg.YUE_SUBPROCESS_MAX_MEMORY_MB or YUE_VMEM_LIMIT_MB_DEFAULT
        nice_val = getattr(cfg, "YUE_NICE", None) or YUE_NICE_DEFAULT
        with tempfile.TemporaryDirectory(prefix="yue_k2_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            cmd, env = self._build_cmd_and_env(tmp_path, infer_dir, infer_script)
            creationflags = 0
            preexec_fn = None
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                preexec_fn = lambda: _preexec_unix(mem_mb, nice_val)
            try:
                self._process = subprocess.Popen(
                    cmd,
                    cwd=str(infer_dir),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=(os.name != "nt"),
                    creationflags=creationflags,
                    preexec_fn=preexec_fn if os.name != "nt" else None,
                )
                self._started = True
                try:
                    stdout, stderr = self._process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    self.terminate()
                    raise YuEError(f"YuE subprocess timed out after {timeout}s")
                if self._process.returncode != 0:
                    err = (stderr or "")[-1000:]
                    raise YuEError(f"YuE infer failed: {err}")
            finally:
                self.terminate()
        out_sub = self.output_dir / "yue_subprocess"
        wavs = list(out_sub.glob("**/*.wav")) if out_sub.is_dir() else []
        if not wavs:
            return {
                "success": True,
                "audio": "",
                "format": "wav",
                "sample_rate": 16000,
                "duration": cfg.YUE_RUN_N_SEGMENTS * 30,
                "prompt": self.genre_txt,
                "model": "yue",
            }
        latest = max(wavs, key=lambda p: p.stat().st_mtime)
        _validate_output_wav(latest)
        import base64
        audio_b64 = base64.b64encode(latest.read_bytes()).decode("utf-8")
        return {
            "success": True,
            "audio": audio_b64,
            "format": "wav",
            "sample_rate": 16000,
            "duration": cfg.YUE_RUN_N_SEGMENTS * 30,
            "prompt": self.genre_txt,
            "model": "yue",
        }


def run_yue_infer(
    genre_txt: str,
    lyrics_txt: str,
    output_dir: str,
    use_dual_tracks: bool = False,
    vocal_ref_path: Optional[str] = None,
    instrumental_ref_path: Optional[str] = None,
    prompt_start_time: float = 0.0,
    prompt_end_time: float = 30.0,
) -> dict:
    """Run YuE infer via InferWrapper. Paths must be pre-validated (under quarantine/clean)."""
    wrapper = InferWrapper(
        genre_txt=genre_txt,
        lyrics_txt=lyrics_txt,
        output_dir=output_dir,
        use_dual_tracks=use_dual_tracks,
        vocal_ref_path=vocal_ref_path,
        instrumental_ref_path=instrumental_ref_path,
        prompt_start_time=prompt_start_time,
        prompt_end_time=prompt_end_time,
    )
    return wrapper.run()
