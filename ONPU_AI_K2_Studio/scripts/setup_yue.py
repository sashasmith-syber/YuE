#!/usr/bin/env python3
"""
YuE environment bootstrap: validate workspace, create dirs, check infer script.
No credentials; paths from env/config.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import get_config


def main() -> int:
    cfg = get_config()
    cfg.ensure_dirs()
    print("Config:")
    print(f"  UPLOAD_DIR: {cfg.UPLOAD_DIR}")
    print(f"  OUTPUT_DIR: {cfg.OUTPUT_DIR}")
    print(f"  YUE_WORKSPACE: {cfg.YUE_WORKSPACE}")
    if not cfg.YUE_WORKSPACE or not cfg.YUE_WORKSPACE.is_dir():
        print("  YUE_WORKSPACE not set or missing. Set YUE_WORKSPACE to YuE repo root.")
        return 1
    infer_script = cfg.YUE_WORKSPACE / "inference" / cfg.YUE_INFER_SCRIPT
    if not infer_script.is_file():
        print(f"  YuE infer script not found: {infer_script}")
        return 1
    print(f"  YuE infer: {infer_script} OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
