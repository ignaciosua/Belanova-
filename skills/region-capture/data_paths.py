#!/usr/bin/env python3
"""
Shared runtime paths for region-capture.

By default this skill writes to macro-agent runtime data so both skills
operate over the same element map/captures.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
WORKSPACE_SKILLS_DIR = SKILL_DIR.parent
DEFAULT_SHARED_DATA_DIR = WORKSPACE_SKILLS_DIR / "macro-agent" / "data" / "local"
LOCAL_FALLBACK_DATA_DIR = SKILL_DIR / "data" / "local"

_env_data_dir = os.getenv("REGION_CAPTURE_DATA_DIR") or os.getenv("MACRO_CAPTURE_DATA_DIR")
if _env_data_dir:
    LOCAL_DATA_DIR = Path(_env_data_dir).expanduser().resolve()
elif DEFAULT_SHARED_DATA_DIR.exists() or (WORKSPACE_SKILLS_DIR / "macro-agent").exists():
    LOCAL_DATA_DIR = DEFAULT_SHARED_DATA_DIR
else:
    LOCAL_DATA_DIR = LOCAL_FALLBACK_DATA_DIR

ELEMENTS_FILE = LOCAL_DATA_DIR / "elements.json"
CAPTURES_DIR = LOCAL_DATA_DIR / "captures"

EXAMPLE_ELEMENTS_FILE = WORKSPACE_SKILLS_DIR / "macro-agent" / "data" / "examples" / "elements.json"


def _copy_if_missing(src: Path, dst: Path) -> None:
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def ensure_local_data() -> None:
    """Ensure runtime directories/files exist before capture starts."""
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)

    if EXAMPLE_ELEMENTS_FILE.exists():
        _copy_if_missing(EXAMPLE_ELEMENTS_FILE, ELEMENTS_FILE)
    elif not ELEMENTS_FILE.exists():
        ELEMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        ELEMENTS_FILE.write_text("{}\n", encoding="utf-8")
