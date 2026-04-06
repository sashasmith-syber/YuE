"""
Async job queue manager — singleton, aiosqlite, Prompt 004.
One queue manager per process; coordinates with workers.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from models.job_queue import (
    Job,
    JobStatus,
    LANE_FAST,
    LANE_SLOW,
    get_job_db_path,
    get_job,
    update_job as sync_update_job,
    _init_sqlite,
)

logger = logging.getLogger(__name__)

# Type aliases
JobID = str
GenerationRequest = Dict[str, Any]


async def _ensure_db(path: Path) -> None:
    """Ensure DB file and schema exist (sync init in executor)."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _init_sqlite)


class QueueManager:
    """
    Singleton async queue manager. Use get_queue_manager().
    """
    _instance: Optional["QueueManager"] = None
    _lock = asyncio.Lock()

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = Path(db_path) if db_path else get_job_db_path()
        self._conn: Any = None
        self._write_lock = asyncio.Lock()
        self._initialized = False

    async def _get_conn(self):
        if self._conn is None:
            await _ensure_db(self._db_path)
            try:
                import aiosqlite
                self._conn = await aiosqlite.connect(str(self._db_path))
                self._conn.row_factory = aiosqlite.Row
            except ImportError:
                logger.warning("aiosqlite not installed; queue manager using sync fallback")
                self._conn = None
            self._initialized = True
        return self._conn

    async def submit(self, request: GenerationRequest) -> JobID:
        """Enqueue a generation request. Returns job_id."""
        engine = (request.get("engine") or "musicgen").strip().lower()
        lane = LANE_FAST if engine == "musicgen" else LANE_SLOW
        opts = request.get("options") or {}
        priority = max(1, min(10, int(opts.get("priority") or request.get("priority") or 5)))
        job_id = str(uuid.uuid4())[:12]
        now = time.time()
        request_json = json.dumps(request) if isinstance(request, dict) else request

        conn = await self._get_conn()
        if conn is None:
            # Fallback: use sync create_job
            from models.job_queue import create_job
            payload = request if isinstance(request, dict) else {}
            job = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: create_job(engine, request_json=payload, priority=priority),
            )
            return job.id

        async with self._write_lock:
            await conn.execute(
                """INSERT INTO generation_jobs
                   (id, engine_type, status, priority, created_at, updated_at, request_json, lane, queued_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, engine, JobStatus.QUEUED.value, priority, now, now, request_json, lane, now),
            )
            await conn.commit()
        return job_id

    async def claim_next(self, worker_id: str, capabilities: List[str]) -> Optional[Job]:
        """Claim next queued job for a lane this worker can handle. Returns Job or None."""
        conn = await self._get_conn()
        if conn is None:
            return await self._claim_next_sync(worker_id, capabilities)

        async with self._write_lock:
            # Prefer slow (yue) if worker has yue, else fast (musicgen)
            for lane, engine in [(LANE_SLOW, "yue"), (LANE_FAST, "musicgen")]:
                if engine not in capabilities:
                    continue
                cur = await conn.execute(
                    """SELECT * FROM generation_jobs
                       WHERE lane = ? AND status = 'queued' AND (cancel_requested IS NULL OR cancel_requested = 0)
                       ORDER BY priority DESC, created_at ASC LIMIT 1""",
                    (lane,),
                )
                row = await cur.fetchone()
                await cur.close()
                if row is None:
                    continue
                job_id = row["id"]
                now = time.time()
                await conn.execute(
                    """UPDATE generation_jobs SET status = ?, assigned_worker = ?, started_at = ?, updated_at = ?
                       WHERE id = ?""",
                    (JobStatus.RUNNING.value, worker_id, now, now, job_id),
                )
                await conn.commit()
                j = get_job(job_id)
                return j
        return None

    async def _claim_next_sync(self, worker_id: str, capabilities: List[str]) -> Optional[Job]:
        """Fallback when aiosqlite not available: use sync list_queued and update_job."""
        from models.job_queue import list_queued, update_job, count_running
        for engine in ["yue", "musicgen"]:
            if engine not in capabilities:
                continue
            if engine == "yue" and count_running("yue") > 0:
                continue
            if engine == "musicgen" and count_running("musicgen") >= 5:
                continue
            jobs = list_queued(engine, limit=1)
            if not jobs:
                continue
            job = jobs[0]
            jid = job.id
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: update_job(jid, status=JobStatus.RUNNING, started_at=time.time(), assigned_worker=worker_id),
            )
            return get_job(jid)
        return None

    async def update_progress(self, job_id: JobID, status: str, message: str) -> None:
        """Update job status_message and optionally status."""
        conn = await self._get_conn()
        if conn is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: sync_update_job(job_id, status_message=message))
            return
        async with self._write_lock:
            await conn.execute(
                "UPDATE generation_jobs SET status_message = ?, updated_at = ? WHERE id = ?",
                (message, time.time(), job_id),
            )
            if status:
                await conn.execute("UPDATE generation_jobs SET status = ? WHERE id = ?", (status, job_id))
            await conn.commit()

    async def complete(self, job_id: JobID, result_path: Path, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Mark job completed with result path and optional metadata."""
        conn = await self._get_conn()
        now = time.time()
        meta_json = json.dumps(metadata) if metadata else None
        if conn is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: sync_update_job(
                    job_id,
                    status=JobStatus.COMPLETE,
                    result_path=str(result_path),
                    result_metadata=metadata,
                    completed_at=now,
                ),
            )
            return
        async with self._write_lock:
            await conn.execute(
                """UPDATE generation_jobs SET status = ?, result_path = ?, result_metadata = ?, completed_at = ?, updated_at = ?
                   WHERE id = ?""",
                (JobStatus.COMPLETE.value, str(result_path), meta_json, now, now, job_id),
            )
            await conn.commit()

    async def fail(self, job_id: JobID, error: Exception) -> None:
        """Mark job failed with error message and optional traceback."""
        import traceback
        err_msg = str(error)
        err_tb = traceback.format_exc()
        conn = await self._get_conn()
        if conn is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: sync_update_job(job_id, status=JobStatus.FAILED, error=err_msg, error_traceback=err_tb),
            )
            return
        async with self._write_lock:
            await conn.execute(
                """UPDATE generation_jobs SET status = ?, error = ?, error_traceback = ?, updated_at = ?
                   WHERE id = ?""",
                (JobStatus.FAILED.value, err_msg, err_tb, time.time(), job_id),
            )
            await conn.commit()

    async def cancel(self, job_id: JobID) -> bool:
        """Request cancel; returns True if job was queued or running."""
        j = get_job(job_id)
        if not j or j.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return False
        conn = await self._get_conn()
        now = time.time()
        if conn is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: sync_update_job(job_id, status=JobStatus.CANCELLED, cancel_requested=True, cancel_requested_at=now),
            )
            return True
        async with self._write_lock:
            await conn.execute(
                """UPDATE generation_jobs SET status = ?, cancel_requested = 1, cancel_requested_at = ?, updated_at = ?
                   WHERE id = ?""",
                (JobStatus.CANCELLED.value, now, now, job_id),
            )
            await conn.commit()
        return True

    def get_status(self, job_id: JobID) -> Any:
        """Sync: return status object with .status, .message, .queue_position, .estimated_completion."""
        j = get_job(job_id)
        if not j:
            return type("Status", (), {"status": "unknown", "message": "Job not found", "queue_position": None, "estimated_completion": None})()
        msg = j.status_message or j.error or ""
        # Optional: queue position (count queued before this job)
        queue_position = None
        if j.status == JobStatus.QUEUED:
            from models.job_queue import list_queued
            queued = list_queued(j.engine_type, limit=100)
            for i, q in enumerate(queued):
                if q.id == job_id:
                    queue_position = i + 1
                    break
        return type("Status", (), {
            "status": j.status.value,
            "message": msg,
            "queue_position": queue_position,
            "estimated_completion": None,
            "result_path": j.result_path,
        })()

    def get_queue_depth(self, engine_type: Optional[str] = None) -> int:
        """Sync: count queued (+ optionally running) for engine_type or all."""
        from models.job_queue import list_queued, count_running
        if engine_type:
            return len(list_queued(engine_type, limit=1000)) + count_running(engine_type)
        return len(list_queued("musicgen", limit=1000)) + count_running("musicgen") + len(list_queued("yue", limit=1000)) + count_running("yue")

    def list_active(self) -> List[Job]:
        """Sync: list jobs with status queued or running."""
        from models.job_queue import list_active_jobs
        return list_active_jobs()

    async def update_worker(self, worker_id: str, hostname: str = "", capabilities: List[str] = None, current_job_id: Optional[str] = None, load_score: float = 0.0) -> None:
        """Worker heartbeat and state."""
        conn = await self._get_conn()
        if conn is None:
            return
        now = time.time()
        caps_json = json.dumps(capabilities or [])
        async with self._write_lock:
            await conn.execute(
                """INSERT INTO workers (worker_id, hostname, capabilities, last_heartbeat, current_job_id, load_score, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, 1)
                   ON CONFLICT(worker_id) DO UPDATE SET
                     hostname=excluded.hostname, capabilities=excluded.capabilities, last_heartbeat=excluded.last_heartbeat,
                     current_job_id=excluded.current_job_id, load_score=excluded.load_score, is_active=1""",
                (worker_id, hostname, caps_json, now, current_job_id, load_score),
            )
            await conn.commit()

    async def requeue_stalled(self, timeout_seconds: int = 300) -> int:
        """Requeue jobs whose assigned worker has not heartbeated. Returns count requeued."""
        conn = await self._get_conn()
        if conn is None:
            return 0
        # Find workers that are stale
        async with self._write_lock:
            cur = await conn.execute(
                "SELECT worker_id FROM workers WHERE is_active = 1 AND last_heartbeat < ?",
                (time.time() - timeout_seconds,),
            )
            stale = await cur.fetchall()
            await cur.close()
            for row in stale:
                wid = row["worker_id"] if hasattr(row, "keys") else row[0]
                await conn.execute(
                    "UPDATE generation_jobs SET status = 'queued', assigned_worker = NULL, started_at = NULL WHERE assigned_worker = ? AND status = 'running'",
                    (wid,),
                )
            await conn.execute("UPDATE workers SET is_active = 0 WHERE last_heartbeat < ?", (time.time() - timeout_seconds,))
            await conn.commit()
        return len(stale)

    async def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Delete completed/failed/cancelled jobs older than max_age_hours. Returns count deleted."""
        conn = await self._get_conn()
        if conn is None:
            return 0
        cutoff = time.time() - max_age_hours * 3600
        async with self._write_lock:
            cur = await conn.execute(
                "DELETE FROM generation_jobs WHERE status IN ('complete', 'failed', 'cancelled') AND updated_at < ?",
                (cutoff,),
            )
            await conn.commit()
            return cur.rowcount if hasattr(cur, "rowcount") else 0

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


def get_queue_manager(db_path: Optional[Path] = None) -> QueueManager:
    """Return singleton QueueManager."""
    if QueueManager._instance is None:
        QueueManager._instance = QueueManager(db_path)
    return QueueManager._instance
