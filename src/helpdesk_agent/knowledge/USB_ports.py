KNOWLEDGE_BASE = {
    "id": "USB_ports",
    "title": "USB Device / Port Problems",
    "description": "USB devices, ports, Plug and Play state, disabled devices, and USB controller problems.",
    "categories": ["usb", "usb port", "device not detected", "flash drive", "mouse", "keyboard"],
    "workflow": {
        "Testing": ["check_usb_devices", "scan_usb_devices"],
        "Diagnosis": ["check_usb_devices", "check_usb_controllers"],
        "Analysis": (
            "Use actual PnP status and ConfigManagerErrorCode evidence. Software evidence can identify device "
            "or controller failures but cannot by itself prove a physical port is damaged."
        ),
        "Fix": ["enable_usb_device", "restart_usb_device", "restart_usb_controller"],
        "Verification": ["check_usb_devices", "check_usb_controllers"],
        "Retry": "After a failed fix, perform the KB verification. Do not repeat the same failed fix unless the user explicitly asks to retry it.",
        "Escalation": [
            "verified physical port failure",
            "known-good device fails on the affected physical port",
            "driver or firmware installation is required",
            "BIOS/UEFI changes are required",
            "hardware failure is suspected",
        ],
    },
    "diagnoses": {
        "disabled_device": {"evidence": "The reported USB device is present but disabled/problematic in PnP.", "fixes": ["enable_usb_device"]},
        "device_error": {"evidence": "The reported device has a PnP problem code supporting a restart.", "fixes": ["restart_usb_device"]},
        "controller_error": {"evidence": "A USB controller/root hub has a problem state.", "fixes": ["restart_usb_controller"]},
        "not_detected": {"evidence": "The expected device is absent from enumeration; rescan and user confirmation are needed before claiming physical failure.", "fixes": []},
        "healthy": {"evidence": "USB devices/controllers currently report healthy states; the complaint is not reproduced in software.", "fixes": []},
    },
    "tool_labels": {
        "Testing": ["check_usb_devices", "scan_usb_devices"],
        "Diagnosis": ["check_usb_devices", "check_usb_controllers"],
        "Fix": ["enable_usb_device", "restart_usb_device", "restart_usb_controller"],
        "Verification": ["check_usb_devices", "check_usb_controllers"],
    },
    "rules": [
        "Test first.",
        "Use exact instance IDs from diagnostic output.",
        "Do not uninstall drivers, delete driver packages, modify registry driver entries, or bypass driver security.",
        "Do not claim a physical port failure from enumeration alone.",
    ],
}
