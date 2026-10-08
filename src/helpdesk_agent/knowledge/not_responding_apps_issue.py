KNOWLEDGE_BASE = {
    "id": "not_responding_apps_issue",
    "title": "Not Responding Applications",
    "description": "Visible Windows applications reported as Not Responding.",
    "categories": ["not responding", "app frozen", "application hung", "program frozen", "program not responding"],
    "workflow": {
        "Testing": ["check_not_responding_apps"],
        "Diagnosis": ["check_not_responding_apps"],
        "Analysis": "Confirm the reported application is actually visible and Not Responding, then use its exact diagnostic PID.",
        "Fix": ["close_unresponsive_app"],
        "Verification": ["check_not_responding_apps"],
        "Retry": "If the same application remains unresponsive after the supported close attempt, do not repeatedly force-close it; escalate.",
        "Escalation": ["application remains unresponsive", "data-loss risk", "vendor defect", "system-wide freeze"],
    },
    "diagnoses": {
        "verified_unresponsive_app": {"evidence": "The exact application is visible and Windows reports it as Not Responding.", "fixes": ["close_unresponsive_app"]},
        "not_reproduced": {"evidence": "No visible application is currently reported as Not Responding.", "fixes": []},
    },
    "tool_labels": {
        "Testing": ["check_not_responding_apps"],
        "Diagnosis": ["check_not_responding_apps"],
        "Fix": ["close_unresponsive_app"],
        "Verification": ["check_not_responding_apps"],
    },
    "rules": [
        "Never close an application before diagnostics identify it as Not Responding.",
        "Use the exact PID returned by diagnostics.",
        "Do not repeatedly force-close an application after the KB-supported attempt fails.",
    ],
}
