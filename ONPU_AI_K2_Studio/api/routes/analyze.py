"""
DNA analysis routes (Soundblueprint); existing behavior preserved.
"""
from __future__ import annotations

import base64
import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)
bp = Blueprint("analyze", __name__, url_prefix="/api")


def _get_analyzer():
    from soundblueprint import get_analyzer, analyze_audio
    return get_analyzer(), analyze_audio


@bp.route("/analyze", methods=["POST"])
def analyze():
    """Analyze audio file (multipart 'audio'); returns full DNA + completeness."""
    try:
        if "audio" not in request.files:
            return jsonify({"error": "No audio file provided"}), 400
        audio_file = request.files["audio"]
        audio_data = audio_file.read()
        _, analyze_audio_fn = _get_analyzer()
        result = analyze_audio_fn(audio_data)
        if result.get("error"):
            return jsonify(result), 500
        return jsonify(result)
    except Exception as e:
        logger.exception("Analyze failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/analyze/dna", methods=["POST"])
def analyze_dna():
    """JSON body: { "audio": "base64_encoded_audio" }. Returns dna + completeness."""
    try:
        data = request.get_json() or {}
        if "audio" not in data:
            return jsonify({"error": "Missing 'audio' field"}), 400
        audio_data = base64.b64decode(data["audio"])
        _, analyze_audio_fn = _get_analyzer()
        result = analyze_audio_fn(audio_data)
        if result.get("error"):
            return jsonify(result), 500
        return jsonify({
            "dna": result.get("dna"),
            "completeness": result.get("completeness"),
            "duration": result.get("duration"),
            "dimensions": result.get("dimensions"),
        })
    except Exception as e:
        logger.exception("Analyze DNA failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/compare", methods=["POST"])
def compare():
    """Compare two DNA profiles. JSON: { "dna1": {...}, "dna2": {...} }."""
    try:
        data = request.get_json() or {}
        if "dna1" not in data or "dna2" not in data:
            return jsonify({"error": "Missing dna1 or dna2"}), 400
        analyzer, _ = _get_analyzer()
        result = analyzer.compare_dna(data["dna1"], data["dna2"])
        return jsonify(result)
    except Exception as e:
        logger.exception("Compare failed")
        return jsonify({"error": str(e)}), 500


@bp.route("/dimensions", methods=["GET"])
def dimensions():
    """Get ONPU DNA dimension definitions."""
    try:
        from soundblueprint import DNA_DIMENSIONS
        return jsonify(DNA_DIMENSIONS)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
