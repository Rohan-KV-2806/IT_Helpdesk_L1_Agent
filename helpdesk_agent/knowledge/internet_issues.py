KNOWLEDGE_BASE = {
    "id": "internet_issues",
    "title": "Internet Connectivity Issues",
    "description": "Internet, Wi-Fi, IP configuration, gateway, DNS, and local connectivity problems.",
    "categories": ["internet", "wifi", "network", "dns", "ip", "gateway", "no connection"],
    "workflow": {
        "Testing": ["check_adapter_state", "check_ip_config"],
        "Diagnosis": ["check_gateway", "check_dns", "check_internet_ip"],
        "Analysis": (
            "Confirm the reported outage using actual evidence. Work from the local link and IP layer toward "
            "gateway, DNS, and Internet reachability. A healthy check means the issue is not reproduced at that layer."
        ),
        "Fix": ["enable_adapter", "fix_renew_dhcp", "fix_flush_dns", "fix_reset_winsock", "fix_reset_tcpip"],
        "Verification": ["check_adapter_state", "check_ip_config", "check_gateway", "check_dns", "check_internet_ip"],
        "Retry": "After a failed fix, verify first. Do not repeat the same failed fix unless the user explicitly instructs a retry.",
        "Escalation": [
            "persistent failure after supported local fixes",
            "physical/network infrastructure failure",
            "VPN or vendor-specific configuration",
            "administrator or enterprise policy is required",
        ],
    },
    "diagnoses": {
        "adapter_disabled": {"evidence": "The relevant adapter is Disabled.", "fixes": ["enable_adapter"]},
        "invalid_ip": {"evidence": "The active adapter does not have a usable IPv4 configuration.", "fixes": ["fix_renew_dhcp"]},
        "dns_failure": {"evidence": "DNS resolution fails while lower-layer connectivity is working.", "fixes": ["fix_flush_dns"]},
        "network_stack": {
            "evidence": "Evidence supports a local Winsock/TCP-IP stack problem after simpler checks.",
            "fixes": ["fix_reset_winsock", "fix_reset_tcpip"],
        },
        "not_reproduced": {
            "evidence": "Adapter, IP, gateway, DNS, and Internet reachability checks succeed.",
            "fixes": [],
        },
    },
    "tool_labels": {
        "Testing": ["check_adapter_state", "check_ip_config"],
        "Diagnosis": ["check_gateway", "check_dns", "check_internet_ip"],
        "Fix": ["enable_adapter", "fix_renew_dhcp", "fix_flush_dns", "fix_reset_winsock", "fix_reset_tcpip"],
        "Verification": ["check_adapter_state", "check_ip_config", "check_gateway", "check_dns", "check_internet_ip"],
    },
    "rules": [
        "Test before any fix.",
        "Enable only the exact adapter identified by diagnostics.",
        "Do not claim a physical Wi-Fi/router problem from software evidence alone.",
        "Do not repeat a failed fix blindly.",
    ],
}
