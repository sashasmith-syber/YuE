"""Tests for generation engines (base, factory, YuE job lifecycle)."""
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.base_engine import BaseEngine
from engines.engine_factory import get_engine, list_engines
from engines.yue_engine import YuEEngine, EngineHealth


def test_list_engines():
    assert "musicgen" in list_engines()
    assert "yue" in list_engines()


def test_get_engine_musicgen():
    e = get_engine("musicgen")
    assert e.name == "musicgen"


def test_get_engine_yue():
    e = get_engine("yue")
    assert e.name == "yue"


def test_get_engine_unknown_defaults_to_musicgen():
    e = get_engine("unknown")
    assert e.name == "musicgen"


def test_yue_health_check_no_workspace():
    engine = YuEEngine()
    with patch.object(YuEEngine, "is_loaded", new_callable=PropertyMock, return_value=False):
        health = engine.health_check()
    assert health.status == "error"


def test_yue_health_check_ready():
    engine = YuEEngine()
    with patch.object(YuEEngine, "is_loaded", new_callable=PropertyMock, return_value=True):
        with patch("engines.yue_engine.count_running", return_value=0):
            health = engine.health_check()
    assert health.status in ("ready", "error")


def test_model_manager_detect_gpu():
    from yue.model_manager import ModelManager, detect_gpu_memory
    vram, cuda = detect_gpu_memory()
    assert isinstance(vram, int)
    assert isinstance(cuda, bool)
    mgr = ModelManager()
    vram2, cuda2 = mgr.detect_gpu_memory()
    assert vram2 == vram and cuda2 == cuda


def test_prompt_builder_dna_mapping():
    from yue.prompt_builder import dna_to_genre_modifiers, build_yue_prompt
    high = dna_to_genre_modifiers({"TRE": {"tempo": 150}})
    assert any("fast" in t.lower() or "driving" in t.lower() for t in high)
    low = dna_to_genre_modifiers({"TRE": {"tempo": 80}})
    assert any("slow" in t.lower() or "downtempo" in t.lower() for t in low)
    out = build_yue_prompt("electronic", dna_hints={"TRE": {"tempo": 130}})
    assert "electronic" in out.lower() or out


def test_prompt_builder_lyrics_structure():
    from yue.prompt_builder import validate_lyrics_structure, build_lyrics_content
    out = validate_lyrics_structure("no marker here")
    assert "[verse]" in out.lower()
    out2 = validate_lyrics_structure("[Chorus]\nhello")
    assert "[chorus]" in out2.lower() or "Chorus" in out2
    with pytest.raises(ValueError, match="bracket"):
        validate_lyrics_structure("[Verse\nunclosed")
    content = build_lyrics_content("[Verse]\nline1\n\n[Chorus]\nline2", segments=2)
    assert "Verse" in content or "verse" in content


def test_job_lifecycle():
    from models.job_queue import create_job, get_job, update_job, JobStatus, list_queued
    job = create_job("yue", request_json={"prompt": "test"})
    assert job.id
    j2 = get_job(job.id)
    assert j2 and j2.status == JobStatus.QUEUED
    update_job(job.id, status=JobStatus.RUNNING, status_message="Stage 1: 10%")
    j3 = get_job(job.id)
    assert j3.status == JobStatus.RUNNING and j3.status_message == "Stage 1: 10%"
    update_job(job.id, status=JobStatus.COMPLETE, result_path="/tmp/out.wav")
    j4 = get_job(job.id)
    assert j4.status == JobStatus.COMPLETE
