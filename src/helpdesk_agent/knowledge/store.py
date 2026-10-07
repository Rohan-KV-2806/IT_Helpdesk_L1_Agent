from __future__ import annotations

from pathlib import Path

from ..config import KB_ROOT


def discover_kbs() -> dict[str, Path]:
    """Discover all Markdown KBs at runtime.

    The filename itself is the classifier's category identifier. There is no
    hardcoded category-to-file mapping.
    """
    if not KB_ROOT.exists():
        return {}
    return {
        path.name: path
        for path in sorted(KB_ROOT.glob("*.md"), key=lambda p: p.name.lower())
        if path.is_file()
    }


def load_kb(filename: str) -> str:
    """Load one discovered KB by its exact runtime filename."""
    kbs = discover_kbs()
    path = kbs.get(filename)
    if path is None:
        raise FileNotFoundError(f"Knowledge base '{filename}' was not found in {KB_ROOT}")
    return path.read_text(encoding="utf-8")


def build_kb_catalog(preview_chars: int = 1800) -> str:
    """Build a compact dynamic catalog for classification.

    The model gets the exact filenames plus a preview from each KB, without
    requiring Python to encode any semantic classification rules.
    """
    kbs = discover_kbs()
    if not kbs:
        return "No Markdown knowledge-base files were found."

    sections: list[str] = []
    for filename, path in kbs.items():
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        preview = text[:preview_chars]
        if len(text) > preview_chars:
            preview += "\n[preview truncated]"
        sections.append(f"### {filename}\n{preview}")
    return "\n\n".join(sections)
