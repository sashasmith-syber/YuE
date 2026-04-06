"""
Job queue API: status, result, cancel, SSE stream.
Prompt 004 — async job orchestration.
"""
from __future__ import annotations

import json
import logging
import time
from flask import Blueprint, Response, request, jsonify, send_file
from pathlib import Path

from services.queue_manager import get_queue_manager
from core.config import get_config

logger = logging.getLogger(__name__)
bp = Blueprint("jobs", __name__, url_prefix="/api")


@bp.route("/jobs/<job_id>/status", methods=["GET"])
def job_status(job_id: str):
    """Lightweight status polling. Returns status, progress, queue_position, estimated_completion."""
    qm = get_queue_manager()
    status = qm.get_status(job_id)
    out = {
        "job_id": job_id,
        "status": status.status,
        "progress": getattr(status, "message", ""),
        "queue_position": getattr(status, "queue_position", None),
        "estimated_completion": getattr(status, "estimated_completion", None),
    }
    if status.status == "complete":
        out["result_path"] = getattr(status, "result_path", None)
    return jsonify(out)


@bp.route("/jobs/<job_id>/result", methods=["GET"])
def job_result(job_id: str):
    """Return result: 302 redirect to WAV or 200 with base64 if ?format=base64."""
    qm = get_queue_manager()
    status = qm.get_status(job_id)
    if status.status != "complete":
        return jsonify({"error": "Job not complete", "status": status.status}), 404
    path = getattr(status, "result_path", None)
    if not path:
        return jsonify({"error": "No result path"}), 404
    p = Path(path)
    if not p.is_file():
        return jsonify({"error": "Result file not found"}), 404
    if request.args.get("format") == "base64":
        import base64
        return jsonify({
            "job_id": job_id,
            "format": "wav",
            "audio": base64.b64encode(p.read_bytes()).decode("utf-8"),
        })
    return send_file(p, mimetype="audio/wav", as_attachment=True, download_name=f"job_{job_id}.wav")


@bp.route("/jobs/<job_id>", methods=["DELETE"])
def job_cancel(job_id: str):
    """Cancel a queued or running job. Returns 200 { cancelled: true } or 409 if already completed."""
    import asyncio
    qm = get_queue_manager()
    status = qm.get_status(job_id)
    if status.status in ("complete", "failed", "cancelled", "unknown"):
        return jsonify({"error": "Already completed or not found", "status": status.status}), 409
    try:
        cancelled = asyncio.run(qm.cancel(job_id))
    except Exception as e:
        logger.exception("Cancel failed: %s", e)
        return jsonify({"error": str(e)}), 500
    if cancelled:
        return jsonify({"cancelled": True, "job_id": job_id})
    return jsonify({"error": "Could not cancel"}), 409


@bp.route("/jobs/<job_id>/stream", methods=["GET"])
def job_stream(job_id: str):
    """Server-Sent Events: real-time progress. Events: status, progress, timestamp; final event has result_url."""
    def generate():
        qm = get_queue_manager()
        last_status = None
        while True:
            status = qm.get_status(job_id)
            if status.status != last_status or getattr(status, "message", ""):
                ev = {
                    "status": status.status,
                    "progress": getattr(status, "message", ""),
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                if status.status == "complete":
                    path = getattr(status, "result_path", None)
                    if path:
                        ev["result_url"] = f"/api/jobs/{job_id}/result"
                yield f"data: {json.dumps(ev)}\n\n"
                last_status = status.status
                if status.status in ("complete", "failed", "cancelled", "unknown"):
                    break
            time.sleep(2)
    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@bp.route("/jobs", methods=["GET"])
def list_jobs():
    """List active (queued + running) jobs."""
    qm = get_queue_manager()
    jobs = qm.list_active()
    return jsonify({
        "jobs": [
            {
                "job_id": j.id,
                "engine_type": j.engine_type,
                "status": j.status.value,
                "progress": j.status_message,
                "created_at": j.created_at,
            }
            for j in jobs
        ],
    })
