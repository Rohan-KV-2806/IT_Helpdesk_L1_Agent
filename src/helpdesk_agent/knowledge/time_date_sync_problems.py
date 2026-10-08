KNOWLEDGE_BASE = {
    "id": "time_date_sync_problems",
    "title": "Time / Date Synchronization Problems",
    "description": "Windows clock drift, failed time synchronization, Windows Time service state, and source problems.",
    "categories": ["time", "date", "clock", "time sync", "date sync", "wrong time"],
    "workflow": {
        "Testing": ["check_time_status", "check_time_service"],
        "Diagnosis": ["check_time_source", "check_time_status", "check_time_service"],
        "Analysis": "Determine whether the clock is actually unsynchronized and whether the Windows Time service or source is implicated.",
        "Fix": ["fix_sync_time", "fix_restart_time_service"],
        "Verification": ["check_time_status", "check_time_service", "check_time_source"],
        "Retry": "After a failed synchronization attempt, verify again. Use the remaining supported fix only when evidence justifies it.",
        "Escalation": ["enterprise time policy", "persistent failure", "hardware clock failure", "domain infrastructure issue"],
    },
    "diagnoses": {
        "service_problem": {"evidence": "Windows Time service is not running or is unhealthy.", "fixes": ["fix_restart_time_service"]},
        "sync_problem": {"evidence": "Time status/source evidence indicates synchronization is failing or stale.", "fixes": ["fix_sync_time"]},
        "healthy": {"evidence": "Clock is synchronized with a valid source and recent successful synchronization is shown.", "fixes": []},
    },
    "tool_labels": {
        "Testing": ["check_time_status", "check_time_service"],
        "Diagnosis": ["check_time_source", "check_time_status", "check_time_service"],
        "Fix": ["fix_sync_time", "fix_restart_time_service"],
        "Verification": ["check_time_status", "check_time_service", "check_time_source"],
    },
    "rules": [
        "Test before fixing.",
        "Do not alter enterprise/domain time policy.",
        "Verify the clock and synchronization state after every fix.",
    ],
}
