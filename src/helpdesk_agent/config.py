from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def project_root() -> Path:
    """Resolve the folder from which the application is launched.

    This matches the user's requirement that commands execute from the
    directory where the app is running.
    """
    return Path.cwd()


load_dotenv(project_root() / ".env")

CLOUD_API_ENDPOINT = os.getenv("CLOUD_API_ENDPOINT", "").strip()
CLOUD_API_KEY = os.getenv("CLOUD_API_KEY", "").strip()
CLOUD_MODEL = os.getenv("CLOUD_MODEL", "").strip()
LOCAL_MODEL = os.getenv("LOCAL_MODEL", "").strip()

MODEL_CONTEXT = int(os.getenv("MODEL_CONTEXT", "4096"))
MODEL_THREADS = int(os.getenv("MODEL_THREADS", "2"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "6"))

KB_ROOT = project_root() / "KnowledgeBase"
TICKET_ROOT = project_root() / "data" / "tickets"

INTENT_TO_KB = {
    "OUTLOOK_PROBLEM": "outlook_problem.md",
    "DNS_PROBLEM": "dns_problem.md",
    "IP_CONFIGURATION": "ip_configuration.md",
    "WINDOWS_UPDATE": "windows_update.md",
    "VPN_PROBLEM": "vpn_problem.md",
    "OTHER_UNKNOWN": "other_unknown.md",
    "PRINTER_PROBLEM": "printer_problem.md",
    "FILE_FOLDER_PERMISSION": "file_folder_permission.md",
    "INTERNET_CONNECTIVITY": "internet_connectivity.md",
    "NETWORK_ADAPTER": "network_adapter.md",
    "APPLICATION_NOT_RESPONDING": "application_not_responding.md",
    "REMOTE_DESKTOP": "remote_desktop.md",
    "WIFI_PROBLEM": "wifi_problem.md",
    "HIGH_MEMORY_USAGE": "high_memory_usage.md",
    "WINDOWS_SERVICE": "windows_service.md",
    "SYSTEM_INFORMATION": "system_information.md",
    "HIGH_CPU_USAGE": "high_cpu_usage.md",
    "DISK_SPACE": "disk_space.md",
}
INTENTS = list(INTENT_TO_KB.keys())
