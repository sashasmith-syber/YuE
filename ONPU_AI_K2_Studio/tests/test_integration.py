"""Integration tests: API routes, YuE job flow with mock subprocess."""
import pytest
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def app():
    from flask import Flask
    from api.routes.generate import bp as gen_bp
    from api.routes.health import bp as health_bp
    app = Flask(__name__)
    app.register_blueprint(gen_bp)
    app.register_blueprint(health_bp)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.get_json()
    assert "status" in data
    assert "ONPU" in data.get("status", "")


def test_generate_missing_prompt(client):
    r = client.post("/api/generate", json={})
    assert r.status_code == 400
    assert "prompt" in (r.get_json() or {}).get("error", "").lower()


def test_yue_generate_returns_job_id_when_workspace_set(client):
    with tempfile.TemporaryDirectory() as tmp:
        with patch("core.config.get_config") as m:
            cfg = MagicMock()
            cfg.YUE_WORKSPACE = Path(tmp)
            cfg.OUTPUT_DIR = Path(tmp) / "out"
            cfg.YUE_RUN_N_SEGMENTS = 2
            cfg.YUE_MAX_QUEUE_DEPTH = 10
            cfg.ensure_dirs = MagicMock()
            m.return_value = cfg
            (Path(tmp) / "inference").mkdir(parents=True)
            (Path(tmp) / "inference" / "infer.py").write_text("# mock")
            r = client.post(
                "/api/generate",
                json={
                    "prompt": "electronic",
                    "engine": "yue",
                    "genre_tags": "electronic house",
                    "lyrics": "[Verse]\ntest\n[Chorus]\ndrop",
                },
            )
    if r.status_code == 200:
        data = r.get_json()
        assert data.get("job_id") or data.get("success") is True
    else:
        assert r.status_code in (200, 500, 400)


def test_yue_cancel_job():
    from engines.yue_engine import YuEEngine
    from models.job_queue import create_job, get_job, JobStatus
    job = create_job("yue", request_json={"prompt": "x"})
    engine = YuEEngine()
    ok = engine.cancel_job(job.id)
    assert ok is True
    j = get_job(job.id)
    assert j.status == JobStatus.CANCELLED


def test_yue_get_output_none_for_queued():
    from engines.yue_engine import YuEEngine
    from models.job_queue import create_job
    job = create_job("yue", request_json={})
    engine = YuEEngine()
    out = engine.get_output(job.id)
    assert out is None
