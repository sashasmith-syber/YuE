"""
System health and status checks.
Prompt 004: /health/ready (DB + worker), /health/live (heartbeat).
"""
from flask import Blueprint, jsonify

from engines.engine_factory import get_engine, list_engines
from models.job_queue import _init_sqlite

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.route("/health", methods=["GET"])
def health():
    """Health check for extension and monitoring."""
    engine = get_engine("musicgen")
    return jsonify({
        "status": "ONPU K2 OPERATIONAL",
        "description": "Persona-Driven AI for Music — backend ready",
        "model_loaded": engine.is_loaded,
        "device": getattr(engine, "device", "n/a"),
    })


@bp.route("/health/ready", methods=["GET"])
def health_ready():
    """Readiness: DB connection OK; optional: at least one worker active."""
    try:
        ok = _init_sqlite()
        if not ok:
            return jsonify({"ready": False, "reason": "DB unavailable"}), 503
        # Optionally check workers table for active worker (Prompt 004)
        return jsonify({"ready": True})
    except Exception as e:
        return jsonify({"ready": False, "reason": str(e)}), 503


@bp.route("/health/live", methods=["GET"])
def health_live():
    """Liveness: process not stuck (simple ping)."""
    return jsonify({"live": True})


@bp.route("/status", methods=["GET"])
def status():
    """Detailed status: engines and features."""
    musicgen = get_engine("musicgen")
    yue = get_engine("yue")
    return jsonify({
        "musicgen_loaded": musicgen.is_loaded,
        "yue_configured": yue.is_loaded,
        "device": getattr(musicgen, "device", "n/a"),
        "engines": list_engines(),
        "features": ["text_to_music", "audio_analysis", "dna_extraction", "yue_long_form", "job_queue"],
    })
