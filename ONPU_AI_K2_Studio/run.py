#!/usr/bin/env python3
"""
ONPU AI K2 Studio - Application entry point.
Run from project root: python run.py  or  python -m flask run
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Load .env and .env.local (no overwrite of existing env; never log values)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except ImportError:
    pass

from flask import Flask
from flask_cors import CORS

from core.config import get_config
from api.routes.generate import bp as generate_bp
from api.routes.jobs import bp as jobs_bp
from api.routes.analyze import bp as analyze_bp
from api.routes.health import bp as health_bp

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})
cfg = get_config()
app.config["MAX_CONTENT_LENGTH"] = cfg.MAX_CONTENT_LENGTH_MB * 1024 * 1024

app.register_blueprint(generate_bp)
app.register_blueprint(jobs_bp)
app.register_blueprint(analyze_bp)
app.register_blueprint(health_bp)


@app.route("/")
def index():
    return {
        "name": "ONPU AI K2 Studio API",
        "version": "4.0.0",
        "endpoints": {
            "health": "/api/health",
            "status": "/api/status",
            "generate": "/api/generate",
            "generate_wav": "/api/generate/wav",
            "jobs_status": "/api/jobs/<id>/status",
            "jobs_result": "/api/jobs/<id>/result",
            "jobs_stream": "/api/jobs/<id>/stream",
            "jobs_cancel": "DELETE /api/jobs/<id>",
            "analyze": "/api/analyze",
            "analyze_dna": "/api/analyze/dna",
            "compare": "/api/compare",
            "dimensions": "/api/dimensions",
        },
    }


if __name__ == "__main__":
    import asyncio
    import threading
    from services.worker import FastWorker, SlowWorker

    cfg.ensure_dirs()

    def run_worker(worker_class):
        asyncio.run(worker_class().run())

    # Fast workers (MusicGen) - 2 instances
    for i in range(2):
        t = threading.Thread(target=run_worker, args=(FastWorker,), daemon=True, name=f"fast-{i}")
        t.start()
        print(f"Started {t.name}")

    # Slow worker (YuE) - 1 instance, GPU 0
    t = threading.Thread(target=run_worker, args=(SlowWorker,), daemon=True, name="slow-0")
    t.start()
    print(f"Started {t.name}")

    app.run(host=cfg.HOST, port=cfg.PORT, debug=cfg.DEBUG)
