"""
Unified generation endpoint: dispatches to MusicGen or YuE by engine param.
"""
from __future__ import annotations

import logging
from flask import Blueprint, request, jsonify

from engines.engine_factory import get_engine
from core.security import sanitize_prompt, sanitize_genre_tags, sanitize_lyrics
from core.tag_whitelist import validate_genre_tags_whitelist
from core.exceptions import ValidationError
from api.middleware.validation import validate_generate_request

logger = logging.getLogger(__name__)
bp = Blueprint("generate", __name__, url_prefix="/api")


@bp.route("/jobs/<job_id>", methods=["GET"])
def job_status(job_id):
    """Get status of a generation job (YuE async)."""
    engine = get_engine("yue")
    if not hasattr(engine, "get_status"):
        return jsonify({"error": "Job status not supported"}), 400
    status = engine.get_status(job_id)
    out = {"job_id": job_id, "status": status.status, "message": getattr(status, "message", "")}
    if status.status == "complete":
        output_path = engine.get_output(job_id)
        out["result_path"] = str(output_path) if output_path else None
    return jsonify(out)


@bp.route("/jobs/<job_id>/output", methods=["GET"])
def job_output(job_id):
    """Get output WAV path or redirect for completed YuE job."""
    from flask import send_file
    engine = get_engine("yue")
    path = engine.get_output(job_id) if hasattr(engine, "get_output") else None
    if not path or not path.is_file():
        return jsonify({"error": "Output not ready or not found"}), 404
    return send_file(path, mimetype="audio/wav", as_attachment=True, download_name=f"yue_{job_id}.wav")


@bp.route("/generate", methods=["POST"])
def generate():
    """
    Generate music. JSON body:
    - prompt (required): text description
    - engine (optional): "musicgen" | "yue" (default musicgen)
    - duration (optional): seconds (MusicGen 1-30; YuE uses segments)
    - For YuE: genre_tags, lyrics, use_icl, vocal_ref_path, instrumental_ref_path, prompt_start_time, prompt_end_time
    - MusicGen: temperature, top_k, top_p, guidance_scale
    """
    try:
        validate_generate_request()
        data = request.get_json() or {}
        prompt = sanitize_prompt(data["prompt"])
        engine_name = (data.get("engine") or "musicgen").strip().lower()
        engine = get_engine(engine_name)
        duration = data.get("duration")
        if duration is not None:
            try:
                duration = int(duration)
            except (TypeError, ValueError):
                duration = 10
        if engine_name == "musicgen":
            result = engine.generate(
                prompt=prompt,
                duration_seconds=duration or 10,
                temperature=float(data.get("temperature", 1.0)),
                top_k=int(data.get("top_k", 250)),
                top_p=float(data.get("top_p", 0.9)),
                guidance_scale=float(data.get("guidance_scale", 3.0)),
            )
        else:
            genre_raw = sanitize_genre_tags(data.get("genre_tags") or prompt)
            genre_tags = validate_genre_tags_whitelist(genre_raw)
            lyrics_raw = data.get("lyrics")
            lyrics = sanitize_lyrics(lyrics_raw) if lyrics_raw else None
            result = engine.generate(
                prompt=prompt,
                duration_seconds=duration,
                genre_tags=genre_tags,
                lyrics=lyrics,
                use_icl=bool(data.get("use_icl")),
                vocal_ref_path=data.get("vocal_ref_path"),
                instrumental_ref_path=data.get("instrumental_ref_path"),
                prompt_start_time=float(data.get("prompt_start_time", 0)),
                prompt_end_time=float(data.get("prompt_end_time", 30)),
            )
        if result.get("success"):
            if result.get("job_id"):
                return jsonify(result), 202
            return jsonify(result)
        return jsonify(result), 500
    except ValidationError as e:
        return jsonify({"error": e.message}), 400
    except Exception as e:
        logger.exception("Generate failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/generate/wav", methods=["POST"])
def generate_wav():
    """Same as /api/generate but returns WAV file attachment."""
    from flask import send_file
    from io import BytesIO
    from werkzeug.utils import secure_filename
    import base64
    resp = generate()
    if isinstance(resp, tuple):
        body, status = resp
        if status != 200:
            return resp
        data = body.get_json() if hasattr(body, "get_json") else body
    else:
        data = resp.get_json() if hasattr(resp, "get_json") else resp
    if not data or not data.get("audio"):
        return jsonify({"error": "No audio in response"}), 500
    audio_bytes = base64.b64decode(data["audio"])
    prompt = (data.get("prompt") or "output")[:20]
    return send_file(
        BytesIO(audio_bytes),
        mimetype="audio/wav",
        as_attachment=True,
        download_name=secure_filename(f"onpu_{prompt}.wav"),
    )
