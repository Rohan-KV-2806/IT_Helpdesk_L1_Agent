KNOWLEDGE_BASE = {
    "id": "cpu_memory_issue",
    "title": "CPU / Memory Performance Issues",
    "description": "High CPU, RAM pressure, sluggish Windows performance, and user-space resource consumption.",
    "categories": ["cpu", "memory", "ram", "slow", "performance", "high usage"],
    "workflow": {
        "Testing": ["check_system_performance", "check_top_cpu_processes", "check_top_memory_processes"],
        "Diagnosis": ["check_system_performance", "check_top_cpu_processes", "check_top_memory_processes"],
        "Analysis": (
            "High percentage alone is not proof of a fault. Confirm sustained pressure and identify the process "
            "or system component responsible before choosing a fix."
        ),
        "Fix": ["close_high_resource_process", "clean_temp_files"],
        "Verification": ["check_system_performance", "check_top_cpu_processes", "check_top_memory_processes"],
        "Retry": "After a failed fix, re-test. If pressure remains without a clear safe user-space cause, escalate rather than using registry, page-file, BIOS, driver, clean-boot, or security-disabling changes.",
        "Escalation": [
            "hardware failure",
            "driver/kernel/system-interrupt cause",
            "persistent memory leak",
            "repeated out-of-memory or crash condition",
            "malware investigation",
            "page-file, registry, BIOS/UEFI, or clean-boot changes are required",
        ],
    },
    "diagnoses": {
        "user_process_pressure": {"evidence": "A user-space process is the clear resource consumer and is safe to close.", "fixes": ["close_high_resource_process"]},
        "low_storage": {"evidence": "Low system-drive free space is contributing to the reported performance problem.", "fixes": ["clean_temp_files"]},
        "system_or_unknown_pressure": {"evidence": "Pressure persists without a clear removable user-space cause.", "fixes": []},
    },
    "tool_labels": {
        "Testing": ["check_system_performance", "check_top_cpu_processes", "check_top_memory_processes"],
        "Diagnosis": ["check_system_performance", "check_top_cpu_processes", "check_top_memory_processes"],
        "Fix": ["close_high_resource_process", "clean_temp_files"],
        "Verification": ["check_system_performance", "check_top_cpu_processes", "check_top_memory_processes"],
    },
    "rules": [
        "Never treat high CPU or memory percentage alone as proof of a fault.",
        "Never close the agent process, its parent, or protected Windows system processes.",
        "Do not delete personal files or user application data as generic cleanup.",
        "Do not disable Microsoft/security services, alter the registry, change page-file settings, or touch BIOS/UEFI.",
    ],
}
