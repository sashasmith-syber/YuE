"""
Async workers: FastWorker (MusicGen, 5 concurrent), SlowWorker (YuE, 1 concurrent).
Prompt 004 — worker loop with claim_next, execute, complete/fail.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_config
from engines.engine_factory import get_engine
from services.queue_manager import get_queue_manager, QueueManager

logger = logging.getLogger(__name__)


class BaseWorker:
    """Base worker loop: heartbeat, claim, execute, complete/fail."""

    def __init__(
        self,
        worker_id: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        queue_manager: Optional[QueueManager] = None,
        max_concurrent: int = 1,
    ) -> None:
        self.worker_id = worker_id or str(uuid.uuid4())[:8]
        self.capabilities = capabilities or []
        self._qm = queue_manager or get_queue_manager()
        self._max_concurrent = max_concurrent
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=max(1, max_concurrent))
        self._current_jobs: List[str] = []

    async def run(self) -> None:
        """Main loop: heartbeat, claim, execute."""
        self._running = True
        logger.info("Worker %s started (capabilities=%s)", self.worker_id, self.capabilities)
        while self._running:
            try:
                await self._qm.update_worker(
                    self.worker_id,
                    hostname=os.environ.get("COMPUTERNAME", "localhost"),
                    capabilities=self.capabilities,
                    current_job_id=self._current_jobs[0] if self._current_jobs else None,
                    load_score=len(self._current_jobs) / max(1, self._max_concurrent),
                )
                job = await self._qm.claim_next(self.worker_id, self.capabilities)
                if not job:
                    await asyncio.sleep(1)
                    continue
                self._current_jobs.append(job.id)
                try:
                    await self.execute_job(job)
                except asyncio.TimeoutError:
                    await self._qm.fail(job.id, TimeoutError("Job exceeded max duration"))
                except Exception as e:
                    logger.exception("Job %s failed: %s", job.id, e)
                    await self._qm.fail(job.id, e)
                finally:
                    if job.id in self._current_jobs:
                        self._current_jobs.remove(job.id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Worker loop error: %s", e)
                await asyncio.sleep(2)
        logger.info("Worker %s stopped", self.worker_id)

    async def execute_job(self, job: Any) -> None:
        """Override in subclass. Run job and call queue_manager.complete or .fail."""
        raise NotImplementedError

    def stop(self) -> None:
        self._running = False


class FastWorker(BaseWorker):
    """MusicGen: max 5 concurrent, lane=fast."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("capabilities", ["musicgen"])
        kwargs.setdefault("max_concurrent", 5)
        super().__init__(**kwargs)

    async def execute_job(self, job: Any) -> None:
        engine = get_engine("musicgen")
        req = job.request_json or {}
        payload = {
            "prompt": req.get("prompt", ""),
            "duration_seconds": req.get("duration") or req.get("duration_seconds") or 10,
            "temperature": float(req.get("temperature", 1.0)),
            "top_k": int(req.get("top_k", 250)),
            "top_p": float(req.get("top_p", 0.9)),
            "guidance_scale": float(req.get("guidance_scale", 3.0)),
        }
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: engine.generate(
                prompt=payload["prompt"],
                duration_seconds=payload["duration_seconds"],
                temperature=payload["temperature"],
                top_k=payload["top_k"],
                top_p=payload["top_p"],
                guidance_scale=payload["guidance_scale"],
            ),
        )
        if not result.get("success"):
            await self._qm.fail(job.id, Exception(result.get("error", "Generation failed")))
            return
        cfg = get_config()
        out_dir = Path(cfg.OUTPUT_DIR) / "musicgen_worker"
        out_dir.mkdir(parents=True, exist_ok=True)
        wav_path = out_dir / f"{job.id}.wav"
        audio_b64 = result.get("audio")
        if audio_b64:
            wav_path.write_bytes(base64.b64decode(audio_b64))
        await self._qm.complete(
            job.id,
            wav_path,
            metadata={
                "duration": result.get("duration"),
                "sample_rate": result.get("sample_rate"),
                "engine": "musicgen",
            },
        )


class SlowWorker(BaseWorker):
    """YuE: max 1 concurrent, lane=slow, GPU."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("capabilities", ["yue"])
        kwargs.setdefault("max_concurrent", 1)
        super().__init__(**kwargs)

    async def execute_job(self, job: Any) -> None:
        engine = get_engine("yue")
        if not hasattr(engine, "execute_job"):
            await self._qm.fail(job.id, RuntimeError("YuE engine does not support execute_job"))
            return

        def on_progress(msg: str) -> None:
            try:
                asyncio.get_event_loop().call_soon_threadsafe(
                    lambda: asyncio.create_task(self._qm.update_progress(job.id, "running", msg))
                )
            except Exception:
                pass

        loop = asyncio.get_event_loop()
        result_path = await loop.run_in_executor(
            self._executor,
            lambda: engine.execute_job(job, progress_callback=on_progress),
        )
        if result_path and result_path.is_file():
            await self._qm.complete(job.id, result_path, metadata={"engine": "yue"})
        else:
            await self._qm.fail(job.id, RuntimeError("No output file produced"))
