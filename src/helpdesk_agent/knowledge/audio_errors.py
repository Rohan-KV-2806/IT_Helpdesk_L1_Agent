KNOWLEDGE_BASE = {
    "id": "audio_errors",
    "title": "Audio / Sound Errors",
    "description": "No sound, missing or disabled audio devices, endpoint problems, and Windows Audio service issues.",
    "categories": ["audio", "sound", "speaker", "headphones", "microphone", "playback", "no sound"],
    "workflow": {
        "Testing": ["check_audio_state", "check_audio_devices"],
        "Diagnosis": ["check_audio_services", "check_audio_devices"],
        "Analysis": "Determine whether the issue is reproduced and whether the failing layer is the device or Windows Audio services.",
        "Fix": ["restart_audio_services", "enable_audio_device"],
        "Verification": ["check_audio_state", "check_audio_devices", "check_audio_services"],
        "Retry": "After a failed fix, verify again and use evidence to select another supported fix or escalate. Do not repeat a failed fix blindly.",
        "Escalation": ["hardware failure", "vendor driver is required", "device remains absent", "policy/privacy issue"],
    },
    "diagnoses": {
        "service_problem": {"evidence": "Windows Audio or AudioEndpointBuilder is stopped or unhealthy.", "fixes": ["restart_audio_services"]},
        "device_disabled": {"evidence": "The reported audio device exists but is disabled.", "fixes": ["enable_audio_device"]},
        "device_missing": {"evidence": "No suitable audio device is enumerated.", "fixes": []},
        "healthy": {"evidence": "Audio devices and services appear healthy; the reported problem cannot currently be reproduced.", "fixes": []},
    },
    "tool_labels": {
        "Testing": ["check_audio_state", "check_audio_devices"],
        "Diagnosis": ["check_audio_services", "check_audio_devices"],
        "Fix": ["restart_audio_services", "enable_audio_device"],
        "Verification": ["check_audio_state", "check_audio_devices", "check_audio_services"],
    },
    "rules": [
        "Test before fixing.",
        "Enable only the exact audio device identified by diagnostics.",
        "Do not install arbitrary vendor drivers.",
        "A successful service restart is not proof that sound was restored; verify again.",
    ],
}
