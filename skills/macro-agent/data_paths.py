#!/usr/bin/env python3
"""
Centraliza rutas de datos del skill macro-agent.

Estructura:
- data/examples/: contenido versionado y seguro para el repositorio.
- data/local/: datos runtime del usuario (capturas, secuencias, estados).
"""

from __future__ import annotations

import shutil
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
DATA_DIR = SKILL_DIR / "data"
EXAMPLES_DIR = DATA_DIR / "examples"
LOCAL_DATA_DIR = DATA_DIR / "local"

ELEMENTS_FILE = LOCAL_DATA_DIR / "elements.json"
CAPTURES_DIR = LOCAL_DATA_DIR / "captures"
SEQUENCES_DIR = LOCAL_DATA_DIR / "sequences"
SOUNDS_STATE_FILE = LOCAL_DATA_DIR / "sounds_state.json"

EXAMPLE_ELEMENTS_FILE = EXAMPLES_DIR / "elements.json"
EXAMPLE_SEQUENCES_DIR = EXAMPLES_DIR / "sequences"
EXAMPLE_SOUNDS_STATE_FILE = EXAMPLES_DIR / "sounds_state.json"


def _copy_if_missing(src: Path, dst: Path) -> None:
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def ensure_local_data() -> None:
    """Inicializa data/local con archivos de ejemplo cuando falten."""
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    SEQUENCES_DIR.mkdir(parents=True, exist_ok=True)

    if EXAMPLE_ELEMENTS_FILE.exists():
        _copy_if_missing(EXAMPLE_ELEMENTS_FILE, ELEMENTS_FILE)
    elif not ELEMENTS_FILE.exists():
        ELEMENTS_FILE.write_text("{}", encoding="utf-8")

    if EXAMPLE_SEQUENCES_DIR.exists() and not any(SEQUENCES_DIR.glob("*.json")):
        for src in EXAMPLE_SEQUENCES_DIR.glob("*.json"):
            _copy_if_missing(src, SEQUENCES_DIR / src.name)

    if EXAMPLE_SOUNDS_STATE_FILE.exists():
        _copy_if_missing(EXAMPLE_SOUNDS_STATE_FILE, SOUNDS_STATE_FILE)
    elif not SOUNDS_STATE_FILE.exists():
        SOUNDS_STATE_FILE.write_text('{"enabled": false, "volume": 0.5}\n', encoding="utf-8")
