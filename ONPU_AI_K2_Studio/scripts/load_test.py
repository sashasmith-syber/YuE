#!/usr/bin/env python3
"""
Load test: submit mixed MusicGen + YuE jobs. Prompt 004 validation.
Usage: python scripts/load_test.py [--jobs N] [--ratio 4:1]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Ensure env loaded
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / ".env.local")
except ImportError:
    pass


def main():
    parser = argparse.ArgumentParser(description="Submit mixed jobs for load test")
    parser.add_argument("--jobs", type=int, default=20, help="Total jobs to submit")
    parser.add_argument("--ratio", type=str, default="4:1", help="MusicGen:YuE ratio (e.g. 4:1)")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:5000", help="API base URL")
    parser.add_argument("--timeout", type=int, default=60, help="Request timeout in seconds")
    args = parser.parse_args()
    try:
        m, y = map(int, args.ratio.split(":"))
    except Exception:
        m, y = 4, 1
    total = args.jobs
    n_musicgen = int(total * m / (m + y)) or 1
    n_yue = total - n_musicgen

    try:
        import requests
    except ImportError:
        print("Install requests: pip install requests")
        sys.exit(1)

    base = args.base_url.rstrip("/")
    job_ids = []
    print(f"Submitting {n_musicgen} MusicGen + {n_yue} YuE jobs...")
    for i in range(n_musicgen):
        r = requests.post(
            f"{base}/api/generate",
            json={"prompt": f"load test musicgen {i}", "engine": "musicgen", "duration": 5},
            timeout=10,
        )
        if r.status_code in (200, 202):
            data = r.json()
            if data.get("job_id"):
                job_ids.append(("musicgen", data["job_id"]))
            else:
                job_ids.append(("musicgen", f"sync-{i}"))
        else:
            print(f"MusicGen {i}: {r.status_code} {r.text[:100]}")
    for i in range(n_yue):
        r = requests.post(
            f"{base}/api/generate",
            json={
                "prompt": "load test yue",
                "engine": "yue",
                "genre_tags": "electronic",
                "lyrics": "[Verse]\ntest\n[Chorus]\ntest",
            },
            timeout=args.timeout,
        )
        if r.status_code in (200, 202):
            data = r.json()
            if data.get("job_id"):
                job_ids.append(("yue", data["job_id"]))
        else:
            print(f"YuE {i}: {r.status_code} {r.text[:100]}")

    print(f"Submitted {len(job_ids)} jobs. Polling status for 30s...")
    for _ in range(6):
        time.sleep(5)
        for engine, jid in job_ids[:3]:
            r = requests.get(f"{base}/api/jobs/{jid}/status", timeout=5)
            if r.ok:
                d = r.json()
                print(f"  {engine} {jid}: {d.get('status')} {d.get('progress', '')[:40]}")
    print("Load test run complete. Check server logs for errors.")


if __name__ == "__main__":
    main()
