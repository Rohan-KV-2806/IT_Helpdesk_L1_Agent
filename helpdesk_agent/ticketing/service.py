from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from ..config import TICKETS_ROOT

def _id(): return f"TKT-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6].upper()}"
def create_ticket(problem,category,history,reason):
    TICKETS_ROOT.mkdir(parents=True,exist_ok=True); tid=_id(); payload={"ticket_id":tid,"created_at":datetime.now().isoformat(timespec="seconds"),"category":category,"summary":problem,"triage_reason":reason,"diagnostic_history":history,"status":"Open"}; path=TICKETS_ROOT/f"{tid}.json"; path.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding="utf-8"); return tid,path
def save_report(report,reports_root):
    reports_root.mkdir(parents=True,exist_ok=True); path=reports_root/f"report-{datetime.now():%Y%m%d-%H%M%S-%f}.json"; path.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8"); return path
