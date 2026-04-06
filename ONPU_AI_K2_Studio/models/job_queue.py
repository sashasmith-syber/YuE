"""
Async job management for long-running generation (e.g. YuE).
SQLite backend for persistence; in-memory fallback when DB unavailable.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.config import get_config


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # Prompt 004 extended lifecycle
    RECEIVED = "received"
    VALIDATED = "validated"
    COMPLETING = "completing"
    # Backward compat aliases
    PENDING = "queued"
    COMPLETED = "complete"


# Lane: fast=musicgen (5 concurrent), slow=yue (1 concurrent)
LANE_FAST = "fast"
LANE_SLOW = "slow"


@dataclass
class Job:
    id: str
    engine_type: str
    status: JobStatus = JobStatus.QUEUED
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status_message: Optional[str] = None
    result_path: Optional[str] = None
    error: Optional[str] = None
    request_json: Optional[Dict[str, Any]] = None
    dna_profile_id: Optional[str] = None
    # Prompt 004 extended fields
    lane: Optional[str] = None  # fast | slow
    validated_at: Optional[float] = None
    queued_at: Optional[float] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    estimated_duration: Optional[int] = None
    assigned_worker: Optional[str] = None
    gpu_device: Optional[int] = None
    result_metadata: Optional[Dict[str, Any]] = None
    error_traceback: Optional[str] = None
    cancel_requested: bool = False
    cancel_requested_at: Optional[float] = None

    def touch(self) -> None:
        self.updated_at = time.time()


_lock = threading.Lock()
_memory_jobs: Dict[str, Job] = {}
_use_sqlite: Optional[bool] = None
_conn: Optional[sqlite3.Connection] = None


def _db_path() -> Path:
    cfg = get_config()
    return Path(cfg.OUTPUT_DIR) / "generation_jobs.db"


def get_job_db_path() -> Path:
    """Return path to job queue SQLite DB (for QueueManager/aiosqlite)."""
    return _db_path()


def _ensure_migrations(conn: sqlite3.Connection) -> None:
    """Add Prompt 004 columns and tables if missing."""
    cur = conn.execute("PRAGMA table_info(generation_jobs)")
    cols = {row[1] for row in cur.fetchall()}
    for col, typ in [
        ("lane", "TEXT"),
        ("validated_at", "REAL"),
        ("queued_at", "REAL"),
        ("started_at", "REAL"),
        ("completed_at", "REAL"),
        ("estimated_duration", "INTEGER"),
        ("assigned_worker", "TEXT"),
        ("gpu_device", "INTEGER"),
        ("result_metadata", "TEXT"),
        ("error_traceback", "TEXT"),
        ("cancel_requested", "INTEGER DEFAULT 0"),
        ("cancel_requested_at", "REAL"),
    ]:
        if col not in cols:
            conn.execute(f"ALTER TABLE generation_jobs ADD COLUMN {col} {typ}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            worker_id TEXT PRIMARY KEY,
            hostname TEXT,
            capabilities TEXT,
            last_heartbeat REAL,
            current_job_id TEXT,
            load_score REAL,
            is_active INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queue_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL DEFAULT (strftime('%s','now')),
            engine_type TEXT,
            status TEXT,
            count INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON generation_jobs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_lane_priority ON generation_jobs(lane, priority DESC, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_worker ON generation_jobs(assigned_worker)")
    conn.commit()


def _init_sqlite() -> bool:
    global _conn, _use_sqlite
    with _lock:
        if _use_sqlite is not None:
            return _use_sqlite
        try:
            p = _db_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(p), check_same_thread=False)
            _conn.execute("""
                CREATE TABLE IF NOT EXISTS generation_jobs (
                    id TEXT PRIMARY KEY,
                    engine_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    status_message TEXT,
                    result_path TEXT,
                    error TEXT,
                    request_json TEXT,
                    dna_profile_id TEXT
                )
            """)
            _conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_engine_status ON generation_jobs(engine_type, status)")
            _ensure_migrations(_conn)
            _use_sqlite = True
        except Exception:
            _use_sqlite = False
        return _use_sqlite


def _job_columns() -> str:
    return """id, engine_type, status, priority, created_at, updated_at,
        status_message, result_path, error, request_json, dna_profile_id,
        lane, validated_at, queued_at, started_at, completed_at, estimated_duration,
        assigned_worker, gpu_device, result_metadata, error_traceback,
        cancel_requested, cancel_requested_at"""


def _row_to_job(row: tuple) -> Job:
    n = len(row)
    id_ = row[0]
    engine_type = row[1]
    status = JobStatus(row[2]) if row[2] else JobStatus.QUEUED
    priority = int(row[3] or 0)
    created_at = row[4] or 0.0
    updated_at = row[5] or 0.0
    status_message = row[6]
    result_path = row[7]
    error = row[8]
    request_json = row[9]
    dna_profile_id = row[10]
    req = json.loads(request_json) if isinstance(request_json, str) and request_json else request_json
    lane = row[11] if n > 11 else None
    validated_at = row[12] if n > 12 else None
    queued_at = row[13] if n > 13 else None
    started_at = row[14] if n > 14 else None
    completed_at = row[15] if n > 15 else None
    estimated_duration = row[16] if n > 16 else None
    assigned_worker = row[17] if n > 17 else None
    gpu_device = row[18] if n > 18 else None
    result_metadata = json.loads(row[19]) if n > 19 and isinstance(row[19], str) and row[19] else (row[19] if n > 19 else None)
    error_traceback = row[20] if n > 20 else None
    cancel_requested = bool(row[21]) if n > 21 else False
    cancel_requested_at = row[22] if n > 22 else None
    return Job(
        id=id_,
        engine_type=engine_type,
        status=status,
        priority=priority,
        created_at=created_at,
        updated_at=updated_at,
        status_message=status_message,
        result_path=result_path,
        error=error,
        request_json=req,
        dna_profile_id=dna_profile_id,
        lane=lane,
        validated_at=validated_at,
        queued_at=queued_at,
        started_at=started_at,
        completed_at=completed_at,
        estimated_duration=estimated_duration,
        assigned_worker=assigned_worker,
        gpu_device=gpu_device,
        result_metadata=result_metadata,
        error_traceback=error_traceback,
        cancel_requested=cancel_requested,
        cancel_requested_at=cancel_requested_at,
    )


def create_job(engine: str, request_json: Optional[Dict[str, Any]] = None, priority: int = 0) -> Job:
    job_id = str(uuid.uuid4())[:12]
    lane = LANE_FAST if engine == "musicgen" else LANE_SLOW
    priority = max(1, min(10, int(priority or 5)))
    job = Job(
        id=job_id,
        engine_type=engine,
        status=JobStatus.QUEUED,
        priority=priority,
        request_json=request_json,
        lane=lane,
        queued_at=time.time(),
    )
    if _init_sqlite() and _conn:
        with _lock:
            _conn.execute(
                """INSERT INTO generation_jobs
                   (id, engine_type, status, priority, created_at, updated_at, request_json, lane, queued_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job.id, job.engine_type, job.status.value, job.priority, job.created_at, job.updated_at,
                 json.dumps(request_json) if request_json else None, lane, job.queued_at),
            )
            _conn.commit()
    else:
        with _lock:
            _memory_jobs[job_id] = job
    return job


def get_job(job_id: str) -> Optional[Job]:
    if _init_sqlite() and _conn:
        with _lock:
            cur = _conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,))
            row = cur.fetchone()
            return _row_to_job(row) if row else None
    with _lock:
        return _memory_jobs.get(job_id)


def update_job(
    job_id: str,
    status: Optional[JobStatus] = None,
    result_path: Optional[str] = None,
    error: Optional[str] = None,
    status_message: Optional[str] = None,
    dna_profile_id: Optional[str] = None,
    started_at: Optional[float] = None,
    completed_at: Optional[float] = None,
    assigned_worker: Optional[str] = None,
    result_metadata: Optional[Dict[str, Any]] = None,
    error_traceback: Optional[str] = None,
    cancel_requested: Optional[bool] = None,
    cancel_requested_at: Optional[float] = None,
) -> None:
    if _init_sqlite() and _conn:
        with _lock:
            updates = ["updated_at = ?"]
            args: List[Any] = [time.time()]
            if status is not None:
                updates.append("status = ?")
                args.append(status.value)
            if result_path is not None:
                updates.append("result_path = ?")
                args.append(result_path)
            if error is not None:
                updates.append("error = ?")
                args.append(error)
            if status_message is not None:
                updates.append("status_message = ?")
                args.append(status_message)
            if dna_profile_id is not None:
                updates.append("dna_profile_id = ?")
                args.append(dna_profile_id)
            if started_at is not None:
                updates.append("started_at = ?")
                args.append(started_at)
            if completed_at is not None:
                updates.append("completed_at = ?")
                args.append(completed_at)
            if assigned_worker is not None:
                updates.append("assigned_worker = ?")
                args.append(assigned_worker)
            if result_metadata is not None:
                updates.append("result_metadata = ?")
                args.append(json.dumps(result_metadata))
            if error_traceback is not None:
                updates.append("error_traceback = ?")
                args.append(error_traceback)
            if cancel_requested is not None:
                updates.append("cancel_requested = ?")
                args.append(1 if cancel_requested else 0)
            if cancel_requested_at is not None:
                updates.append("cancel_requested_at = ?")
                args.append(cancel_requested_at)
            args.append(job_id)
            _conn.execute(f"UPDATE generation_jobs SET {', '.join(updates)} WHERE id = ?", args)
            _conn.commit()
        return
    with _lock:
        job = _memory_jobs.get(job_id)
        if job:
            job.touch()
            if status is not None:
                job.status = status
            if result_path is not None:
                job.result_path = result_path
            if error is not None:
                job.error = error
            if status_message is not None:
                job.status_message = status_message
            if dna_profile_id is not None:
                job.dna_profile_id = dna_profile_id
            if started_at is not None:
                job.started_at = started_at
            if completed_at is not None:
                job.completed_at = completed_at
            if assigned_worker is not None:
                job.assigned_worker = assigned_worker
            if result_metadata is not None:
                job.result_metadata = result_metadata
            if error_traceback is not None:
                job.error_traceback = error_traceback
            if cancel_requested is not None:
                job.cancel_requested = cancel_requested
            if cancel_requested_at is not None:
                job.cancel_requested_at = cancel_requested_at


def list_queued(engine_type: str, limit: int = 10) -> List[Job]:
    """Jobs with status='queued' for engine_type, ORDER BY priority DESC, created_at ASC."""
    if _init_sqlite() and _conn:
        with _lock:
            cur = _conn.execute(
                """SELECT * FROM generation_jobs WHERE engine_type = ? AND status = 'queued'
                   ORDER BY priority DESC, created_at ASC LIMIT ?""",
                (engine_type, limit),
            )
            return [_row_to_job(row) for row in cur.fetchall()]
    with _lock:
        jobs = [j for j in _memory_jobs.values() if j.engine_type == engine_type and j.status == JobStatus.QUEUED]
        jobs.sort(key=lambda j: (-j.priority, j.created_at))
        return jobs[:limit]


def count_running(engine_type: str) -> int:
    if _init_sqlite() and _conn:
        with _lock:
            cur = _conn.execute(
                "SELECT COUNT(*) FROM generation_jobs WHERE engine_type = ? AND status = 'running'",
                (engine_type,),
            )
            return cur.fetchone()[0]
    with _lock:
        return sum(1 for j in _memory_jobs.values() if j.engine_type == engine_type and j.status == JobStatus.RUNNING)


def list_active_jobs(limit: int = 100) -> List[Job]:
    """List jobs with status queued or running, for queue dashboard."""
    if _init_sqlite() and _conn:
        with _lock:
            cur = _conn.execute(
                "SELECT * FROM generation_jobs WHERE status IN ('queued', 'running') ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            return [_row_to_job(row) for row in cur.fetchall()]
    with _lock:
        jobs = [j for j in _memory_jobs.values() if j.status in (JobStatus.QUEUED, JobStatus.RUNNING)]
        jobs.sort(key=lambda j: -j.created_at)
        return jobs[:limit]
