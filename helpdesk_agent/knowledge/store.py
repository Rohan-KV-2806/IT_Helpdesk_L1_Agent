from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from ..config import KB_ROOT

_REQUIRED_KEYS = {"id", "title", "description", "categories", "workflow", "tool_labels"}
_WORKFLOW_KEYS = {"Testing", "Diagnosis", "Analysis", "Fix", "Verification", "Retry", "Escalation"}


def _load_module(path: Path):
    module_name = f"helpdesk_runtime_kb_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load knowledge base module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_kb(path: Path, kb: dict[str, Any]) -> None:
    missing = sorted(_REQUIRED_KEYS - set(kb))
    if missing:
        raise ValueError(f"Knowledge base {path.name} is missing keys: {', '.join(missing)}")

    kb_id = str(kb.get("id", "")).strip()
    if not kb_id:
        raise ValueError(f"Knowledge base {path.name} has an empty id")

    categories = kb.get("categories")
    if not isinstance(categories, list) or not all(isinstance(x, str) and x.strip() for x in categories):
        raise ValueError(f"Knowledge base {path.name} must define categories as a list of strings")

    workflow = kb.get("workflow")
    if not isinstance(workflow, dict):
        raise ValueError(f"Knowledge base {path.name} must define workflow as a dictionary")
    missing_workflow = sorted(_WORKFLOW_KEYS - set(workflow))
    if missing_workflow:
        raise ValueError(
            f"Knowledge base {path.name} is missing workflow sections: {', '.join(missing_workflow)}"
        )

    tool_labels = kb.get("tool_labels")
    if not isinstance(tool_labels, dict):
        raise ValueError(f"Knowledge base {path.name} must define tool_labels as a dictionary")
    for label_group, labels in tool_labels.items():
        if not isinstance(labels, list) or not all(isinstance(x, str) and x.strip() for x in labels):
            raise ValueError(f"Knowledge base {path.name}: tool_labels['{label_group}'] must be a list of strings")


def discover_kbs() -> dict[str, dict[str, Any]]:
    """Discover declarative Python KB modules at runtime.

    There is intentionally no category-to-file mapping here. A KB module is
    accepted when it exports a valid KNOWLEDGE_BASE dictionary.
    """
    KB_ROOT.mkdir(parents=True, exist_ok=True)
    discovered: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for path in sorted(KB_ROOT.glob("*.py"), key=lambda p: p.name.lower()):
        if path.name in {"store.py", "__init__.py"} or path.name.startswith("_"):
            continue
        try:
            module = _load_module(path)
            kb = getattr(module, "KNOWLEDGE_BASE", None)
            if kb is None:
                continue
            if not isinstance(kb, dict):
                raise ValueError("KNOWLEDGE_BASE must be a dictionary")
            _validate_kb(path, kb)
            kb_id = str(kb["id"]).strip()
            if kb_id in discovered:
                raise ValueError(f"duplicate KB id '{kb_id}'")
            discovered[kb_id] = kb
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        raise RuntimeError("Knowledge-base validation failed:\n- " + "\n- ".join(errors))
    return discovered


def load_kb(kb_id: str) -> dict[str, Any]:
    kbs = discover_kbs()
    if kb_id not in kbs:
        raise KeyError(f"Knowledge base '{kb_id}' not found in {KB_ROOT}")
    return kbs[kb_id]


def build_kb_catalog() -> str:
    kbs = discover_kbs()
    if not kbs:
        return "No knowledge bases found."

    rows = []
    for kb_id, kb in kbs.items():
        rows.append(
            f"ID: {kb_id}\n"
            f"TITLE: {kb.get('title', '')}\n"
            f"DESCRIPTION: {kb.get('description', '')}\n"
            f"CATEGORIES: {', '.join(str(x) for x in kb.get('categories', []))}"
        )
    return "\n\n".join(rows)
