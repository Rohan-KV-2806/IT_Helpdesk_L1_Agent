from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable


@dataclass
class ToolResult:
    success: bool
    output: str


@dataclass
class ToolDefinition:
    name: str
    category: str  # DIAGNOSTIC or FIX
    description: str
    requires_approval: bool
    runner: Callable[[dict], ToolResult]


def _run_ps(script: str, timeout: int = 30) -> ToolResult:
    if os.name != "nt":
        return ToolResult(False, "This diagnostic is only supported on Windows.")
    try:
        p = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
        )
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode != 0:
            return ToolResult(False, out or err or f"PowerShell exited with code {p.returncode}.")
        return ToolResult(True, out or "Command completed successfully.")
    except Exception as exc:
        return ToolResult(False, str(exc))


def _run_cmd(args: list[str], timeout: int = 30) -> ToolResult:
    if os.name != "nt":
        return ToolResult(False, "This diagnostic is only supported on Windows.")
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        out = ((p.stdout or "") + ("\n" + p.stderr if p.stderr else "")).strip()
        return ToolResult(p.returncode == 0, out or f"Process exited with code {p.returncode}.")
    except Exception as exc:
        return ToolResult(False, str(exc))


def check_adapter_state(_: dict) -> ToolResult:
    return _run_ps("Get-NetAdapter | Select-Object Name,Status,LinkSpeed,MacAddress | Format-Table -AutoSize | Out-String")


def check_ip_config(_: dict) -> ToolResult:
    return _run_cmd(["ipconfig", "/all"])


def check_gateway(_: dict) -> ToolResult:
    script = r'''
$cfg = Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway -ne $null} | Select-Object -First 1
if (-not $cfg) { Write-Output "No IPv4 default gateway found."; exit 2 }
$gw = $cfg.IPv4DefaultGateway.NextHop
Write-Output "Default gateway: $gw"
Test-Connection -ComputerName $gw -Count 2 -Quiet | ForEach-Object { "Gateway reachable: $_" }
'''
    return _run_ps(script)


def check_internet_ip(_: dict) -> ToolResult:
    # ICMP is useful as one signal; also perform a small HTTPS check so a blocked ICMP echo
    # does not automatically mean that the Internet is unavailable.
    results = []
    try:
        ip_ok = any(x for x in socket.getaddrinfo("example.com", 443))
        results.append(f"DNS socket resolution available: {ip_ok}")
    except Exception as exc:
        results.append(f"DNS socket resolution failed: {exc}")
    try:
        req = urllib.request.Request("https://example.com/", method="HEAD", headers={"User-Agent": "IT-Helpdesk-L1-Agent/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            results.append(f"HTTPS Internet check: HTTP {r.status}")
            https_ok = 200 <= r.status < 500
    except Exception as exc:
        results.append(f"HTTPS Internet check failed: {exc}")
        https_ok = False
    return ToolResult(https_ok, "\n".join(results))


def check_dns(_: dict) -> ToolResult:
    try:
        result = socket.gethostbyname_ex("example.com")
        return ToolResult(True, f"DNS resolution succeeded: {result[2]}")
    except Exception as exc:
        return ToolResult(False, f"DNS resolution failed: {exc}")


def enable_adapter(_: dict) -> ToolResult:
    return _run_ps("Get-NetAdapter | Where-Object {$_.Status -eq 'Disabled'} | Enable-NetAdapter -Confirm:$false", 30)


def fix_renew_dhcp(_: dict) -> ToolResult:
    return _run_cmd(["ipconfig", "/renew"], 60)


def fix_flush_dns(_: dict) -> ToolResult:
    return _run_cmd(["ipconfig", "/flushdns"])


def fix_reset_winsock(_: dict) -> ToolResult:
    return _run_cmd(["netsh", "winsock", "reset"], 30)


def fix_reset_tcpip(_: dict) -> ToolResult:
    return _run_cmd(["netsh", "int", "ip", "reset"], 30)


def check_not_responding_apps(_: dict) -> ToolResult:
    script = r'''
Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.Responding -eq $false } |
Select-Object ProcessName,Id,MainWindowTitle,Responding |
Format-Table -AutoSize | Out-String
'''
    result = _run_ps(script)
    if result.success and not result.output.strip():
        return ToolResult(True, "No visible application is currently reported as Not Responding.")
    return result


def close_unresponsive_app(args: dict) -> ToolResult:
    pid = str(args.get("pid", "")).strip()
    name = str(args.get("process_name", "")).strip()
    if not pid and not name:
        return ToolResult(False, "No verified target process was supplied.")
    if pid and not pid.isdigit():
        return ToolResult(False, "Invalid process ID.")
    if pid:
        script = f"Stop-Process -Id {int(pid)} -Force -ErrorAction Stop; Write-Output 'Process {int(pid)} terminated.'"
    else:
        safe_name = name.replace("'", "''")
        script = f"Get-Process -Name '{safe_name}' -ErrorAction Stop | Stop-Process -Force -ErrorAction Stop; Write-Output 'Process {safe_name} terminated.'"
    return _run_ps(script, 30)


def check_windows_update_status(_: dict) -> ToolResult:
    script = r'''
$svc = Get-Service -Name wuauserv -ErrorAction SilentlyContinue
$bits = Get-Service -Name BITS -ErrorAction SilentlyContinue
Write-Output "Windows Update service: $($svc.Status)"
Write-Output "BITS service: $($bits.Status)"
try { Get-WindowsUpdateLog -LogPath "$env:TEMP\WindowsUpdate.log" -ErrorAction Stop | Out-Null; Write-Output "Windows Update log generated successfully." } catch { Write-Output "Windows Update log generation unavailable: $($_.Exception.Message)" }
'''
    return _run_ps(script, 45)


def check_windows_update_services(_: dict) -> ToolResult:
    return _run_ps("Get-Service wuauserv,BITS,cryptsvc | Select-Object Name,Status,StartType | Format-Table -AutoSize | Out-String")


def check_pending_reboot(_: dict) -> ToolResult:
    script = r'''
$paths = @(
'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending',
'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired'
)
$found = @($paths | Where-Object { Test-Path $_ })
if ($found.Count -gt 0) { "Pending reboot: YES"; $found | ForEach-Object { "Indicator: $_" } } else { "Pending reboot: NO" }
'''
    return _run_ps(script)


def check_windows_update_error(_: dict) -> ToolResult:
    script = r'''
$events = Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WindowsUpdateClient'} -MaxEvents 8 -ErrorAction SilentlyContinue
if (-not $events) { "No recent Windows UpdateClient events found."; exit 0 }
$events | Select-Object TimeCreated,Id,LevelDisplayName,Message | Format-List | Out-String
'''
    return _run_ps(script)


def fix_restart_update_services(_: dict) -> ToolResult:
    return _run_ps("Restart-Service wuauserv,BITS -Force -ErrorAction Stop; Get-Service wuauserv,BITS | Select-Object Name,Status | Format-Table -AutoSize | Out-String", 45)


def fix_reset_windows_update_components(_: dict) -> ToolResult:
    script = r'''
Stop-Service wuauserv,BITS,cryptsvc -Force -ErrorAction Stop
$stamp = Get-Date -Format 'yyyyMMddHHmmss'
$sd = Join-Path $env:SystemRoot "SoftwareDistribution"
$cr = Join-Path $env:SystemRoot "System32\catroot2"
if (Test-Path $sd) { Rename-Item $sd "SoftwareDistribution.old.$stamp" -ErrorAction Stop }
if (Test-Path $cr) { Rename-Item $cr "catroot2.old.$stamp" -ErrorAction Stop }
Start-Service cryptsvc,BITS,wuauserv -ErrorAction Stop
Write-Output "Windows Update component directories were renamed and services restarted."
'''
    return _run_ps(script, 90)


def check_time_status(_: dict) -> ToolResult:
    script = r'''
Get-Date | ForEach-Object { "Local time: $_" }
Get-TimeZone | ForEach-Object { "Time zone: $($_.Id) ($($_.DisplayName))" }
w32tm /query /status
'''
    return _run_ps(script)


def check_time_service(_: dict) -> ToolResult:
    return _run_ps("Get-Service W32Time | Select-Object Name,Status,StartType | Format-List | Out-String")


def check_time_source(_: dict) -> ToolResult:
    return _run_cmd(["w32tm", "/query", "/source"])


def fix_sync_time(_: dict) -> ToolResult:
    first = _run_cmd(["w32tm", "/resync"], 30)
    if first.success:
        time.sleep(1)
    return first


def fix_restart_time_service(_: dict) -> ToolResult:
    return _run_ps("Restart-Service W32Time -Force -ErrorAction Stop; Start-Service W32Time -ErrorAction Stop; Get-Service W32Time | Select-Object Name,Status | Format-Table -AutoSize | Out-String", 30)


TOOLS: dict[str, ToolDefinition] = {
    # Internet
    "check_adapter_state": ToolDefinition("check_adapter_state", "DIAGNOSTIC", "Inspect Windows network adapters.", False, check_adapter_state),
    "check_ip_config": ToolDefinition("check_ip_config", "DIAGNOSTIC", "Inspect IP, gateway and DNS configuration.", False, check_ip_config),
    "check_gateway": ToolDefinition("check_gateway", "DIAGNOSTIC", "Test reachability of the configured default gateway.", False, check_gateway),
    "check_internet_ip": ToolDefinition("check_internet_ip", "DIAGNOSTIC", "Test end-to-end Internet reachability.", False, check_internet_ip),
    "check_dns": ToolDefinition("check_dns", "DIAGNOSTIC", "Test DNS resolution.", False, check_dns),
    "enable_adapter": ToolDefinition("enable_adapter", "FIX", "Enable a verified disabled network adapter.", True, enable_adapter),
    "fix_renew_dhcp": ToolDefinition("fix_renew_dhcp", "FIX", "Renew DHCP configuration when evidence supports it.", True, fix_renew_dhcp),
    "fix_flush_dns": ToolDefinition("fix_flush_dns", "FIX", "Flush the Windows DNS resolver cache.", True, fix_flush_dns),
    "fix_reset_winsock": ToolDefinition("fix_reset_winsock", "FIX", "Reset Winsock when the KB explicitly permits it.", True, fix_reset_winsock),
    "fix_reset_tcpip": ToolDefinition("fix_reset_tcpip", "FIX", "Reset TCP/IP when the KB explicitly permits it.", True, fix_reset_tcpip),
    # Application not responding
    "check_not_responding_apps": ToolDefinition("check_not_responding_apps", "DIAGNOSTIC", "Find visible Windows applications reported as Not Responding.", False, check_not_responding_apps),
    "close_unresponsive_app": ToolDefinition("close_unresponsive_app", "FIX", "Close a verified unresponsive application.", True, close_unresponsive_app),
    # Windows Update
    "check_windows_update_status": ToolDefinition("check_windows_update_status", "DIAGNOSTIC", "Inspect Windows Update service and update state.", False, check_windows_update_status),
    "check_windows_update_services": ToolDefinition("check_windows_update_services", "DIAGNOSTIC", "Inspect required Windows Update services.", False, check_windows_update_services),
    "check_pending_reboot": ToolDefinition("check_pending_reboot", "DIAGNOSTIC", "Check whether Windows is waiting for a reboot.", False, check_pending_reboot),
    "check_windows_update_error": ToolDefinition("check_windows_update_error", "DIAGNOSTIC", "Inspect recent Windows UpdateClient errors.", False, check_windows_update_error),
    "fix_restart_update_services": ToolDefinition("fix_restart_update_services", "FIX", "Restart relevant Windows Update services.", True, fix_restart_update_services),
    "fix_reset_windows_update_components": ToolDefinition("fix_reset_windows_update_components", "FIX", "Reset Windows Update component directories and restart services.", True, fix_reset_windows_update_components),
    # Time/date
    "check_time_status": ToolDefinition("check_time_status", "DIAGNOSTIC", "Inspect current Windows time, timezone and sync state.", False, check_time_status),
    "check_time_service": ToolDefinition("check_time_service", "DIAGNOSTIC", "Inspect Windows Time service state.", False, check_time_service),
    "check_time_source": ToolDefinition("check_time_source", "DIAGNOSTIC", "Inspect the configured Windows time source.", False, check_time_source),
    "fix_sync_time": ToolDefinition("fix_sync_time", "FIX", "Request Windows time synchronization.", True, fix_sync_time),
    "fix_restart_time_service": ToolDefinition("fix_restart_time_service", "FIX", "Restart the Windows Time service.", True, fix_restart_time_service),
}
