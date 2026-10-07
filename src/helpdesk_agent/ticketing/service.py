from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ..config import TICKETS_ROOT


def _ticket_id() -> str:
    return f"TKT-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6].upper()}"


def create_ticket(problem: str, category: str | None, history: list[dict], reason: str) -> tuple[str, Path]:
    TICKETS_ROOT.mkdir(parents=True, exist_ok=True)
    ticket_id = _ticket_id()
    payload = {
        "ticket_id": ticket_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "category": category,
        "summary": problem,
        "triage_reason": reason,
        "diagnostic_history": history,
        "status": "Open",
    }
    path = TICKETS_ROOT / f"{ticket_id}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return ticket_id, path


def save_report(report: dict, reports_root: Path) -> Path:
    reports_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    path = reports_root / f"report-{stamp}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
