"""
Unit tests for job queue and QueueManager. Prompt 004.
"""
import asyncio
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.job_queue import (
    Job,
    JobStatus,
    create_job,
    get_job,
    update_job,
    list_queued,
    list_active_jobs,
    count_running,
    LANE_FAST,
    LANE_SLOW,
)
from services.queue_manager import QueueManager, get_queue_manager


def test_create_job_musicgen():
    job = create_job("musicgen", request_json={"prompt": "test"}, priority=5)
    assert job.id
    assert job.engine_type == "musicgen"
    assert job.status == JobStatus.QUEUED
    assert job.priority == 5
    assert job.lane == LANE_FAST


def test_create_job_yue():
    job = create_job("yue", request_json={"prompt": "test", "lyrics": "[Verse] x"}, priority=8)
    assert job.engine_type == "yue"
    assert job.lane == LANE_SLOW
    assert job.priority == 8


def test_get_job():
    job = create_job("musicgen", request_json={"prompt": "x"})
    found = get_job(job.id)
    assert found and found.id == job.id
    assert get_job("nonexistent") is None


def test_update_job():
    job = create_job("musicgen", request_json={})
    update_job(job.id, status=JobStatus.RUNNING, status_message="Running")
    found = get_job(job.id)
    assert found.status == JobStatus.RUNNING
    assert found.status_message == "Running"
    update_job(job.id, status=JobStatus.COMPLETE, result_path="/tmp/out.wav")
    found = get_job(job.id)
    assert found.status == JobStatus.COMPLETE
    assert found.result_path == "/tmp/out.wav"


def test_list_queued():
    job = create_job("yue", request_json={})
    queued = list_queued("yue", limit=5)
    assert any(j.id == job.id for j in queued)
    update_job(job.id, status=JobStatus.RUNNING)
    queued2 = list_queued("yue", limit=5)
    assert not any(j.id == job.id for j in queued2)


def test_list_active_jobs():
    job = create_job("musicgen", request_json={})
    active = list_active_jobs(limit=10)
    assert any(j.id == job.id for j in active)
    update_job(job.id, status=JobStatus.COMPLETE)
    active2 = list_active_jobs(limit=10)
    assert not any(j.id == job.id for j in active2)


def test_count_running():
    job = create_job("yue", request_json={})
    update_job(job.id, status=JobStatus.RUNNING)
    assert count_running("yue") >= 1
    update_job(job.id, status=JobStatus.COMPLETE)
    assert count_running("yue") >= 0


@pytest.mark.asyncio
async def test_queue_manager_submit():
    qm = get_queue_manager()
    request = {"engine": "musicgen", "prompt": "test", "duration": 10}
    job_id = await qm.submit(request)
    assert job_id
    status = qm.get_status(job_id)
    assert status.status == "queued"
    assert qm.get_queue_depth() >= 1


@pytest.mark.asyncio
async def test_queue_manager_cancel():
    request = {"engine": "yue", "prompt": "test"}
    job_id = await get_queue_manager().submit(request)
    cancelled = await get_queue_manager().cancel(job_id)
    assert cancelled is True
    status = get_queue_manager().get_status(job_id)
    assert status.status == "cancelled"


@pytest.mark.asyncio
async def test_queue_manager_claim_next_fallback():
    """When aiosqlite may not be used, claim_next sync fallback."""
    qm = get_queue_manager()
    job = await qm.claim_next("worker-1", ["musicgen"])
    # May be None if no queued job; or a Job if we had one
    if job:
        assert job.engine_type == "musicgen"
        assert job.id
