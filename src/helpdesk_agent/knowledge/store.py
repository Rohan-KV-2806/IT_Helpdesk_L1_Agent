from __future__ import annotations

from pathlib import Path

from ..config import CATEGORY_FILES, KB_ROOT


def find_kb(category: str) -> Path:
    filename = CATEGORY_FILES[category]
    exact = KB_ROOT / filename
    if exact.exists():
        return exact

    # A little tolerance for the filenames the project has used during development.
    aliases = {
        "Windows Update Stuck / Failing": ["windows_update.md", "windows_update_stuck.md", "windows_update_stuck_failing.md"],
        "Application Not Responding / Frozen App": ["application_not_responding.md", "application_frozen.md"],
        "Time / Date Synchronization Problem": ["time_date_synchronization.md", "time_synchronization.md", "time_date.md"],
        "Internet": ["internet_connectivity.md", "internet.md"],
    }
    for name in aliases.get(category, []):
        p = KB_ROOT / name
        if p.exists():
            return p
    raise FileNotFoundError(f"Knowledge base not found for '{category}' in {KB_ROOT}")


def load_kb(category: str) -> str:
    return find_kb(category).read_text(encoding="utf-8")
