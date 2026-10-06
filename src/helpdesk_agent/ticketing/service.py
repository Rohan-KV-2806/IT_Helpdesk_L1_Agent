from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from ..config import TICKET_ROOT


def create_ticket(user_problem: str, intent: str, history: list[dict], reason: str) -> tuple[str, Path]:
    TICKET_ROOT.mkdir(parents=True, exist_ok=True)
    ticket_id = "TKT-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
    path = TICKET_ROOT / f"{ticket_id}.json"

    payload = {
        "ticket_id": ticket_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "category": intent,
        "priority": "Medium",
        "summary": user_problem.strip(),
        "triage_reason": reason,
        "diagnostic_history": history,
        "status": "Open",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ticket_id, path
