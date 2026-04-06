# ONPU AI K2 Studio — Architecture

Unified project integrating **MusicGen** (short clips), **YuE** (long-form lyrics2song), and **Soundblueprint** DNA analysis.

## Layout

```
ONPU_AI_K2_Studio/
├── core/                 # Config, security, exceptions
├── engines/              # Base engine, MusicGen, YuE, factory
├── api/
│   ├── routes/           # generate, analyze, health
│   └── middleware/       # auth, rate_limit, validation
├── models/               # Job queue, DNA profile
├── services/             # Audio storage, Prometheus metrics
├── yue/                  # YuE infer wrapper, prompt builder, ICL
├── extension/            # Chrome extension (add mode toggle)
├── docker/               # Dockerfile.yue, compose, Prometheus
├── scripts/              # setup_yue, validate_install
├── tests/
├── soundblueprint.py     # DNA analysis (existing behavior)
├── run.py                # Flask app entry
├── .env.example
├── requirements.txt
└── README_ARCHITECTURE.md
```

## Design

- **Unified generation**: `POST /api/generate` with `engine: "musicgen" | "yue"`. MusicGen unchanged; YuE runs in isolated subprocess with timeout and optional resource limits.
- **Config**: All paths and secrets from env; `core.config.get_config()`. No hardcoded credentials.
- **Security**: `core.security` for sanitization; `api.middleware` for auth (optional API key) and per-engine rate limiting.
- **YuE**: `yue.infer_wrapper` runs YuE `infer.py` in subprocess; `yue.prompt_builder` maps genre/DNA to prompts; `yue.icl_handler` validates ref audio.

## Running

1. Copy `.env.example` to `.env`, set `YUE_WORKSPACE` if using YuE.
2. `pip install -r requirements.txt`
3. `python scripts/validate_install.py`
4. `python run.py` → http://localhost:5000

## Extension

Point the existing K2 Chrome extension at this API. Add a **mode toggle** (MusicGen vs YuE) and, for YuE, inputs for genre tags, lyrics, and ref audio.

## Docker

- `docker-compose -f docker/docker-compose.yml up -d` for the backend.
- YuE GPU worker: use `Dockerfile.yue` and mount the YuE repo; set `YUE_WORKSPACE` in the service.

---

## Security (defense-in-depth)

- **Subprocess isolation**: YuE runs via `InferWrapper` with timeout (max 600s), `SIGTERM` → 5s → `SIGKILL`, memory limit (16GB default), and low CPU priority (`nice` 10). Input: genre/lyrics length limits; output: WAV magic bytes and file size (1MB–50MB).
- **Input sanitization**: Genre tags whitelisted from YuE official list (`core/tag_whitelist`). Lyrics: HTML/XML stripped, template-injection patterns blocked, max 5000 chars; for YuE, at least one `[Verse]` or `[Chorus]` required. Audio uploads: max 10MB, magic-byte check, optional ffprobe (duration ≤30s, 16–48kHz).
- **Filesystem**: Uploads go to `quarantine/` then move to `clean/` after validation. Output files set to 0o644; optional 24h auto-cleanup.
- **Network**: YuE inference runs with **`HF_HUB_OFFLINE=1`** so no network access during generation. Models must be cached beforehand. *YuE requires internet only for initial model download, not for generation.*
- **Secrets**: Use `python-dotenv` with `.env` or `.env.local` (gitignored). No secrets in logs or error traces. Production: set `K2_PRODUCTION=1`; `validate_install.py` then requires `.env` or `.env.local` to exist.
