"""
Production YuE engine: queue-based generation, status, cancel, health, DNA on complete.
Implements BaseEngine; uses InferWrapper for subprocess, job_queue for state.
"""
from __future__ import annotations

import base64
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from core.config import get_config
from core.exceptions import YuEError
from engines.base_engine import BaseEngine
from models.job_queue import (
    Job,
    JobStatus,
    create_job,
    get_job,
    update_job,
    list_queued,
    count_running,
)

logger = logging.getLogger(__name__)


@dataclass
class EngineHealth:
    status: str  # ready | busy | error
    vram_gb: float = 0.0
    message: str = ""


class YuEEngine(BaseEngine):
    """YuE generation: enqueue job, worker runs InferWrapper, DNA on complete."""

    name = "yue"
    supports_async = True
    _worker_started = False
    _worker_lock = threading.Lock()

    def __init__(
        self,
        config: Optional[Any] = None,
        model_manager: Optional[Any] = None,
    ) -> None:
        self._config = config or get_config()
        self._model_manager = model_manager
        if self._model_manager is None:
            try:
                from yue.model_manager import get_model_manager
                self._model_manager = get_model_manager()
            except Exception:
                pass

    @property
    def is_loaded(self) -> bool:
        cfg = self._config if hasattr(self, "_config") else get_config()
        return cfg.YUE_WORKSPACE is not None and cfg.YUE_WORKSPACE.is_dir()

    def load(self) -> bool:
        cfg = self._config if hasattr(self, "_config") and self._config else get_config()
        cfg.ensure_dirs()
        return self.is_loaded

    def generate(
        self,
        prompt: str,
        duration_seconds: Optional[int] = None,
        genre_tags: Optional[str] = None,
        lyrics: Optional[str] = None,
        use_icl: bool = False,
        vocal_ref_path: Optional[str] = None,
        instrumental_ref_path: Optional[str] = None,
        prompt_start_time: float = 0.0,
        prompt_end_time: float = 30.0,
        mode: str = "text_to_music",
        dna_profile: Optional[Dict[str, Any]] = None,
        duration_segments: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if not self.is_loaded:
            return {"success": False, "error": "YuE workspace not configured (set YUE_WORKSPACE)"}
        cfg = self._config if hasattr(self, "_config") and self._config else get_config()
        if cfg.YUE_MAX_QUEUE_DEPTH <= len(list_queued("yue", limit=100)):
            return {"success": False, "error": "YuE job queue full"}
        request_json = {
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "genre_tags": genre_tags or prompt,
            "lyrics": lyrics,
            "use_icl": use_icl,
            "vocal_ref_path": vocal_ref_path,
            "instrumental_ref_path": instrumental_ref_path,
            "prompt_start_time": prompt_start_time,
            "prompt_end_time": prompt_end_time,
            "mode": mode,
            "dna_profile": dna_profile,
            "duration_segments": duration_segments or cfg.YUE_RUN_N_SEGMENTS,
        }
        job = create_job("yue", request_json=request_json)
        self._start_worker()
        return {"success": True, "job_id": job.id}

    def _start_worker(self) -> None:
        with YuEEngine._worker_lock:
            if YuEEngine._worker_started:
                return
            YuEEngine._worker_started = True
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()

    def _worker_loop(self) -> None:
        cfg = get_config()
        while True:
            try:
                if count_running("yue") > 0:
                    time.sleep(2)
                    continue
                jobs = list_queued("yue", limit=1)
                if not jobs:
                    time.sleep(2)
                    continue
                job = jobs[0]
                update_job(job.id, status=JobStatus.RUNNING, status_message="Stage 1: 0%")
                try:
                    self._run_job(job)
                except Exception as e:
                    logger.exception("YuE job %s failed", job.id)
                    update_job(job.id, status=JobStatus.FAILED, error=str(e))
            except Exception as e:
                logger.exception("YuE worker error: %s", e)
            time.sleep(1)

    def execute_job(self, job: Job, progress_callback: Optional[Callable[[str], None]] = None) -> Optional[Path]:
        """
        Run one job (used by async worker). Returns result path or None on failure.
        progress_callback(msg) is called with status strings e.g. "Stage 1: 45%".
        """
        def prog(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)
            update_job(job.id, status_message=msg)
        return self._run_job(job, progress_callback=prog)

    def _run_job(self, job: Job, progress_callback: Optional[Callable[[str], None]] = None) -> Optional[Path]:
        from yue.infer_wrapper import run_yue_infer
        from yue.prompt_builder import build_yue_prompt, build_lyrics_content
        cfg = self._config if hasattr(self, "_config") and self._config else get_config()
        req = job.request_json or {}
        if progress_callback:
            progress_callback("Stage 1: 0%")
        genre_tags = req.get("genre_tags") or req.get("prompt", "electronic")
        lyrics = req.get("lyrics") or ""
        segments = int(req.get("duration_segments") or cfg.YUE_RUN_N_SEGMENTS)
        dna_profile = req.get("dna_profile")
        genre_txt = build_yue_prompt(genre_tags, lyrics=lyrics, dna_hints=dna_profile)
        lyrics_txt = build_lyrics_content(lyrics, segments=segments)
        if progress_callback:
            progress_callback("Stage 1: 50%")
        use_dual = req.get("use_icl") and req.get("vocal_ref_path") and req.get("instrumental_ref_path")
        vocal_ref = str(req.get("vocal_ref_path")) if req.get("vocal_ref_path") else None
        inst_ref = str(req.get("instrumental_ref_path")) if req.get("instrumental_ref_path") else None
        result = run_yue_infer(
            genre_txt=genre_txt,
            lyrics_txt=lyrics_txt,
            output_dir=str(cfg.OUTPUT_DIR),
            use_dual_tracks=use_dual,
            vocal_ref_path=vocal_ref,
            instrumental_ref_path=inst_ref,
            prompt_start_time=float(req.get("prompt_start_time", 0)),
            prompt_end_time=float(req.get("prompt_end_time", 30)),
        )
        if not result.get("success"):
            update_job(job.id, status=JobStatus.FAILED, error=result.get("error", "Unknown error"))
            return None
        if progress_callback:
            progress_callback("Stage 2: 80%")
        out_sub = Path(str(cfg.OUTPUT_DIR)) / "yue_subprocess"
        wavs = list(out_sub.glob("**/*.wav")) if out_sub.is_dir() else []
        result_path = None
        if wavs:
            latest = max(wavs, key=lambda p: p.stat().st_mtime)
            result_path = str(latest)
            from services.output_cleanup import set_output_permissions
            set_output_permissions(latest)
        if progress_callback:
            progress_callback("Complete")
        update_job(job.id, status=JobStatus.COMPLETE, result_path=result_path, status_message="Complete")
        if result_path and Path(result_path).is_file():
            try:
                dna_profile_id = self._run_dna_analysis(Path(result_path), job.id)
                if dna_profile_id:
                    update_job(job.id, dna_profile_id=dna_profile_id)
            except Exception as e:
                logger.warning("DNA analysis for job %s failed: %s", job.id, e)
        return Path(result_path) if result_path else None

    def _run_dna_analysis(self, wav_path: Path, job_id: str) -> Optional[str]:
        try:
            from soundblueprint import analyze_audio
            data = wav_path.read_bytes()
            result = analyze_audio(data)
            if result.get("error"):
                return None
            from models.dna_profile import DNAProfile
            profile = DNAProfile(
                dna=result.get("dna", {}),
                completeness=result.get("completeness", 0),
                duration=result.get("duration", 0),
                dimensions=result.get("dimensions", []),
            )
            return job_id + "_dna"
        except Exception:
            return None

    def get_status(self, job_id: str) -> Any:
        """Return status object with .status and .message."""
        j = get_job(job_id)
        if not j:
            return type("Status", (), {"status": "unknown", "message": "Job not found"})()
        msg = j.status_message or j.error or ""
        return type("Status", (), {"status": j.status.value, "message": msg})()

    def cancel_job(self, job_id: str) -> bool:
        j = get_job(job_id)
        if not j:
            return False
        if j.status != JobStatus.QUEUED and j.status != JobStatus.RUNNING:
            return False
        update_job(job_id, status=JobStatus.CANCELLED)
        return True

    def get_output(self, job_id: str) -> Optional[Path]:
        j = get_job(job_id)
        if not j or j.status != JobStatus.COMPLETE or not j.result_path:
            return None
        p = Path(j.result_path)
        return p if p.is_file() else None

    def health_check(self) -> EngineHealth:
        vram_gb = 0.0
        try:
            if self._model_manager:
                vram, cuda = self._model_manager.detect_gpu_memory()
                vram_gb = float(vram)
        except Exception:
            pass
        running = count_running("yue")
        if not self.is_loaded:
            return EngineHealth(status="error", vram_gb=vram_gb, message="YUE_WORKSPACE not set")
        if running > 0:
            return EngineHealth(status="busy", vram_gb=vram_gb, message="Generation in progress")
        return EngineHealth(status="ready", vram_gb=vram_gb)
