from __future__ import annotations

from pathlib import Path

from ..config import INTENT_TO_KB, KB_ROOT


def kb_path_for_intent(intent: str) -> Path:
    filename = INTENT_TO_KB[intent]
    return KB_ROOT / filename


def load_kb(intent: str) -> str:
    path = kb_path_for_intent(intent)
    if not path.exists():
        raise FileNotFoundError(f"Knowledge-base file not found: {path}")
    return path.read_text(encoding="utf-8")
