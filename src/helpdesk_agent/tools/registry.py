from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable


@dataclass
class ToolResult:
    success: bool
    output: str


@dataclass
class ToolDefinition:
    name: str
    description: str
    category: str  # DIAGNOSTIC or FIX
    requires_approval: bool
    runner: Callable[[dict], ToolResult]


def _run_command(args: list[str], timeout: int = 20) -> ToolResult:
    """Run a fixed, pre-approved command from the app's working directory."""
    try:
        completed = subprocess.run(
            args,
            cwd=str(__import__("pathlib").Path.cwd()),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            errors="replace",
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        output = stdout
        if stderr:
            output = f"{output}\nSTDERR: {stderr}".strip()
        return ToolResult(completed.returncode == 0, output or f"Exit code: {completed.returncode}")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(False, str(exc))


def _check_ip_config(_: dict) -> ToolResult:
    if platform.system() == "Windows":
        return _run_command(["ipconfig", "/all"])
    if shutil.which("ifconfig"):
        return _run_command(["ifconfig"])
    if shutil.which("ip"):
        return _run_command(["ip", "addr"])
    return ToolResult(False, "No network configuration command is available.")


def _extract_default_gateway(text: str) -> str | None:
    patterns = [
        r"Default Gateway[ .:]*([0-9]{1,3}(?:\.[0-9]{1,3}){3})",
        r"default via ([0-9]{1,3}(?:\.[0-9]{1,3}){3})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _check_gateway(_: dict) -> ToolResult:
    base = _check_ip_config({})
    if not base.output:
        return ToolResult(False, "Unable to read network configuration.")
    gateway = _extract_default_gateway(base.output)
    if not gateway:
        return ToolResult(False, "No default gateway was detected.\n\nIP_CONFIG:\n" + base.output)
    command = ["ping", "-n", "1", "-w", "2000", gateway] if platform.system() == "Windows" else ["ping", "-c", "1", "-W", "2", gateway]
    result = _run_command(command)
    return ToolResult(result.success, f"Default gateway: {gateway}\n{result.output}")


def _check_public_ip(_: dict) -> ToolResult:
    command = ["ping", "-n", "1", "-w", "2000", "8.8.8.8"] if platform.system() == "Windows" else ["ping", "-c", "1", "-W", "2", "8.8.8.8"]
    return _run_command(command)


def _check_dns(_: dict) -> ToolResult:
    return _run_command(["nslookup", "example.com"])


def _check_adapter_state(_: dict) -> ToolResult:
    if platform.system() == "Windows":
        return _run_command([
            "powershell", "-NoProfile", "-Command",
            "Get-NetAdapter | Select-Object Name,Status,LinkSpeed | Format-Table -AutoSize"
        ])
    return _run_command(["ip", "link"] if shutil.which("ip") else ["ifconfig"])


def _renew_dhcp(_: dict) -> ToolResult:
    if platform.system() != "Windows":
        return ToolResult(False, "DHCP renew is implemented for Windows only.")
    return _run_command(["ipconfig", "/renew"])


def _flush_dns(_: dict) -> ToolResult:
    if platform.system() != "Windows":
        return ToolResult(False, "DNS cache flush is implemented for Windows only.")
    return _run_command(["ipconfig", "/flushdns"])


def _reset_network_stack(_: dict) -> ToolResult:
    if platform.system() != "Windows":
        return ToolResult(False, "Network-stack reset is implemented for Windows only.")
    first = _run_command(["netsh", "winsock", "reset"])
    second = _run_command(["netsh", "int", "ip", "reset"])
    return ToolResult(first.success and second.success, f"Winsock reset:\n{first.output}\n\nTCP/IP reset:\n{second.output}")


TOOLS: dict[str, ToolDefinition] = {
    "check_ip_config": ToolDefinition("check_ip_config", "Read IP configuration", "DIAGNOSTIC", False, _check_ip_config),
    "check_gateway": ToolDefinition("check_gateway", "Test the detected default gateway", "DIAGNOSTIC", False, _check_gateway),
    "check_public_ip": ToolDefinition("check_public_ip", "Test Internet reachability by IP", "DIAGNOSTIC", False, _check_public_ip),
    "check_dns": ToolDefinition("check_dns", "Test DNS name resolution", "DIAGNOSTIC", False, _check_dns),
    "check_adapter_state": ToolDefinition("check_adapter_state", "Inspect network adapter state", "DIAGNOSTIC", False, _check_adapter_state),
    "renew_dhcp": ToolDefinition("renew_dhcp", "Renew DHCP configuration", "FIX", True, _renew_dhcp),
    "flush_dns": ToolDefinition("flush_dns", "Flush Windows DNS resolver cache", "FIX", True, _flush_dns),
    "reset_network_stack": ToolDefinition("reset_network_stack", "Reset Winsock and TCP/IP stack", "FIX", True, _reset_network_stack),
}
