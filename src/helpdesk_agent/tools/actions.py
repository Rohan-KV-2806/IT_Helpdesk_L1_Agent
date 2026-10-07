from __future__ import annotations

import os
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class ToolResult:
    success: bool
    output: str


def _run_ps(script: str, timeout: int = 30) -> ToolResult:
    if os.name != "nt":
        return ToolResult(False, "This tool is only supported on Windows.")
    try:
        p = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
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
        return ToolResult(False, "This tool is only supported on Windows.")
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        out = ((p.stdout or "") + ("\n" + p.stderr if p.stderr else "")).strip()
        return ToolResult(p.returncode == 0, out or f"Process exited with code {p.returncode}.")
    except Exception as exc:
        return ToolResult(False, str(exc))


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

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
    results = []
    try:
        ip_ok = bool(socket.getaddrinfo("example.com", 443))
        results.append(f"DNS socket resolution available: {ip_ok}")
    except Exception as exc:
        results.append(f"DNS socket resolution failed: {exc}")
    try:
        req = urllib_request("https://example.com/")
        with req as response:
            results.append(f"HTTPS Internet check: HTTP {response.status}")
            https_ok = 200 <= response.status < 500
    except Exception as exc:
        results.append(f"HTTPS Internet check failed: {exc}")
        https_ok = False
    return ToolResult(https_ok, "\n".join(results))


def urllib_request(url: str):
    import urllib.request

    return urllib.request.urlopen(
        urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "IT-Helpdesk-L1-Agent/1.0"},
        ),
        timeout=8,
    )


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


# ---------------------------------------------------------------------------
# Application responsiveness
# ---------------------------------------------------------------------------

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
        return ToolResult(False, "No target process was supplied in the tool arguments.")
    if pid and not pid.isdigit():
        return ToolResult(False, "Invalid process ID.")
    if pid:
        script = f"Stop-Process -Id {int(pid)} -Force -ErrorAction Stop; Write-Output 'Process {int(pid)} terminated.'"
    else:
        safe_name = name.replace("'", "''")
        script = f"Get-Process -Name '{safe_name}' -ErrorAction Stop | Stop-Process -Force -ErrorAction Stop; Write-Output 'Process {safe_name} terminated.'"
    return _run_ps(script, 30)


# ---------------------------------------------------------------------------
# Windows Update
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Time / date
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# USB / PnP
# ---------------------------------------------------------------------------

def _usb_instance_id(arguments: dict, allow_prefixes: tuple[str, ...]) -> str | None:
    value = str(arguments.get("instance_id", "")).strip().strip('"')
    upper = value.upper()
    if not value or not any(upper.startswith(prefix) for prefix in allow_prefixes):
        return None
    return value


def check_usb_devices(_: dict) -> ToolResult:
    script = r'''
$devices = Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
    Where-Object { $_.PNPDeviceID -like 'USB\*' } |
    Select-Object Name,PNPClass,PNPDeviceID,Status,ConfigManagerErrorCode
if (-not $devices) {
    Write-Output "No currently enumerated USB PnP devices were found."
    exit 0
}
$devices | Format-List | Out-String
'''
    return _run_ps(script)


def scan_usb_devices(_: dict) -> ToolResult:
    return _run_cmd(["pnputil", "/scan-devices"], 45)


def check_usb_controllers(_: dict) -> ToolResult:
    script = r'''
$controllers = Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
    Where-Object {
        $_.PNPClass -eq 'USB' -and
        ($_.Name -match 'Host Controller|Root Hub|USB xHCI|USB eXtensible')
    } |
    Select-Object Name,PNPClass,PNPDeviceID,Status,ConfigManagerErrorCode
if (-not $controllers) {
    Write-Output "No USB host controller or root hub entries were found by this query."
    exit 0
}
$controllers | Format-List | Out-String
'''
    return _run_ps(script)


def enable_usb_device(arguments: dict) -> ToolResult:
    instance_id = _usb_instance_id(arguments, ("USB\\",))
    if instance_id is None:
        return ToolResult(False, "A valid USB instance_id from diagnostic evidence is required.")
    return _run_cmd(["pnputil", "/enable-device", instance_id], 45)


def restart_usb_device(arguments: dict) -> ToolResult:
    instance_id = _usb_instance_id(arguments, ("USB\\",))
    if instance_id is None:
        return ToolResult(False, "A valid USB instance_id from diagnostic evidence is required.")
    return _run_cmd(["pnputil", "/restart-device", instance_id], 45)


def restart_usb_controller(arguments: dict) -> ToolResult:
    instance_id = _usb_instance_id(arguments, ("USB\\", "PCI\\"))
    if instance_id is None:
        return ToolResult(False, "A valid USB/PCI controller instance_id from diagnostic evidence is required.")
    return _run_cmd(["pnputil", "/restart-device", instance_id], 45)


# ---------------------------------------------------------------------------
# CPU / memory / performance
# ---------------------------------------------------------------------------

def check_system_performance(_: dict) -> ToolResult:
    script = r'''
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
$cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
$cpu = Get-CimInstance Win32_Processor -ErrorAction Stop |
    Measure-Object -Property LoadPercentage -Average
$totalMemoryMB = [math]::Round($cs.TotalPhysicalMemory / 1MB, 0)
$freeMemoryMB = [math]::Round($os.FreePhysicalMemory / 1024, 0)
$usedMemoryMB = $totalMemoryMB - $freeMemoryMB
$usedMemoryPct = if ($totalMemoryMB -gt 0) { [math]::Round(($usedMemoryMB / $totalMemoryMB) * 100, 1) } else { 0 }
$commit = try { Get-Counter '\\Memory\\% Committed Bytes In Use' -ErrorAction Stop | Select-Object -ExpandProperty CounterSamples | Select-Object -First 1 } catch { $null }
$systemDrive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$env:SystemDrive'" -ErrorAction SilentlyContinue
Write-Output "CPU load average: $([math]::Round($cpu.Average,1))%"
Write-Output "Physical memory total: $totalMemoryMB MB"
Write-Output "Physical memory available: $freeMemoryMB MB"
Write-Output "Physical memory used: $usedMemoryMB MB ($usedMemoryPct%)"
if ($commit) { Write-Output "Committed memory in use: $([math]::Round($commit.CookedValue,1))%" }
if ($systemDrive) {
    $freeGB = [math]::Round($systemDrive.FreeSpace / 1GB, 2)
    $sizeGB = [math]::Round($systemDrive.Size / 1GB, 2)
    $usedGB = [math]::Round($sizeGB - $freeGB, 2)
    Write-Output "System drive: $env:SystemDrive"
    Write-Output "System drive free: $freeGB GB of $sizeGB GB"
    Write-Output "System drive used: $usedGB GB"
}
Write-Output "Processor count: $([Environment]::ProcessorCount) logical processors"
'''
    return _run_ps(script, 30)


def check_top_cpu_processes(_: dict) -> ToolResult:
    script = r'''
$cores = [Environment]::ProcessorCount
$before = @{}
Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
    try { $before[$_.Id] = $_.TotalProcessorTime.TotalSeconds } catch {}
}
Start-Sleep -Seconds 1
$rows = foreach ($p in Get-Process -ErrorAction SilentlyContinue) {
    try {
        if ($before.ContainsKey($p.Id)) {
            $delta = $p.TotalProcessorTime.TotalSeconds - $before[$p.Id]
            $pct = [math]::Round(($delta / $cores) * 100, 1)
            [pscustomobject]@{
                ProcessName = $p.ProcessName
                Id = $p.Id
                CPUPercent = $pct
            }
        }
    } catch {}
}
$rows | Sort-Object CPUPercent -Descending | Select-Object -First 15 | Format-Table -AutoSize | Out-String
'''
    return _run_ps(script, 45)


def check_top_memory_processes(_: dict) -> ToolResult:
    script = r'''
Get-Process -ErrorAction SilentlyContinue |
    Select-Object ProcessName,Id,
        @{Name='WorkingSetMB';Expression={[math]::Round($_.WorkingSet64 / 1MB, 1)}},
        @{Name='PrivateMemoryMB';Expression={[math]::Round($_.PrivateMemorySize64 / 1MB, 1)}} |
    Sort-Object WorkingSetMB -Descending |
    Select-Object -First 15 |
    Format-Table -AutoSize | Out-String
'''
    return _run_ps(script, 30)


def check_disk_space(_: dict) -> ToolResult:
    script = r'''
$disks = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" -ErrorAction Stop |
    Select-Object DeviceID,
        @{Name='SizeGB';Expression={[math]::Round($_.Size / 1GB, 2)}},
        @{Name='FreeGB';Expression={[math]::Round($_.FreeSpace / 1GB, 2)}},
        @{Name='FreePercent';Expression={if ($_.Size) {[math]::Round(($_.FreeSpace / $_.Size) * 100, 1)} else {0}}}
$disks | Format-Table -AutoSize | Out-String
'''
    return _run_ps(script, 30)


def check_startup_apps(_: dict) -> ToolResult:
    script = r'''
$items = Get-CimInstance Win32_StartupCommand -ErrorAction Stop |
    Select-Object Name,Command,Location,User
if (-not $items) {
    Write-Output "No startup applications were reported by Windows."
    exit 0
}
$items | Sort-Object Name | Format-List | Out-String
'''
    return _run_ps(script, 45)


def close_high_resource_process(args: dict) -> ToolResult:
    pid = str(args.get("pid", "")).strip()
    if not pid.isdigit() or int(pid) <= 4:
        return ToolResult(False, "A valid non-system process PID from the performance diagnostics is required.")

    script = f'''
$targetId = {int(pid)}
$target = Get-CimInstance Win32_Process -Filter "ProcessId=$targetId" -ErrorAction Stop
if (-not $target) {{ throw "Target process no longer exists." }}
$currentSession = (Get-Process -Id $PID -ErrorAction Stop).SessionId
if ([int]$target.SessionId -ne [int]$currentSession) {{ throw "The target process is not in the current interactive user session." }}
$owner = Invoke-CimMethod -InputObject $target -MethodName GetOwner -ErrorAction SilentlyContinue
if ($owner.User -and $owner.User -ne $env:USERNAME) {{ throw "The target process is owned by another user account." }}
Write-Output "Target: $($target.Name) (PID $targetId)"
Write-Output "Owner: $($owner.User)"
Write-Output "Session: $($target.SessionId)"
Stop-Process -Id $targetId -Force -ErrorAction Stop
Write-Output "Process terminated."
'''
    return _run_ps(script, 30)


def restart_computer(_: dict) -> ToolResult:
    return _run_ps("Restart-Computer -Force", 30)


def disable_startup_app(args: dict) -> ToolResult:
    name = str(args.get("name", "")).strip()
    location = str(args.get("location", "")).strip()
    if not name or not location:
        return ToolResult(False, "The startup app name and exact startup location from diagnostics are required.")

    safe_name = name.replace("'", "''")
    safe_location = location.replace("'", "''")
    script = f'''
$name = '{safe_name}'
$location = '{safe_location}'
if ($location -match '^HKCU\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run$') {{
    Remove-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name $name -ErrorAction Stop
    Write-Output "Disabled startup entry '$name' for the current user."
}} elseif ($location -match '^HKLM\\\\Software\\\\Microsoft\\\\Windows\\\\CurrentVersion\\\\Run$') {{
    Remove-ItemProperty -Path 'HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -Name $name -ErrorAction Stop
    Write-Output "Disabled startup entry '$name' for the computer."
}} else {{
    throw "This startup location is not supported by the L1 disable tool: $location"
}}
'''
    return _run_ps(script, 30)


def clean_temporary_files(_: dict) -> ToolResult:
    script = r'''
$root = $env:TEMP
if (-not (Test-Path $root)) { Write-Output "User temporary directory not found: $root"; exit 0 }
$before = (Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue | Measure-Object).Count
$removed = 0
Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop
        $removed++
    } catch {
        # Locked/in-use temporary files are expected and are left alone.
    }
}
$after = (Get-ChildItem -LiteralPath $root -Force -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Output "User temporary directory: $root"
Write-Output "Entries before cleanup: $before"
Write-Output "Entries removed: $removed"
Write-Output "Entries remaining: $after"
'''
    return _run_ps(script, 60)


# ---------------------------------------------------------------------------
# Dynamic execution
# ---------------------------------------------------------------------------

def resolve_tool(name: str) -> Callable[[dict], ToolResult] | None:
    """Resolve an exact tool name to a function defined in this module.

    There is deliberately no central tool-name registry. The selected KB tells
    the agent which names are valid for the workflow; Python only resolves the
    exact name to an implemented callable and executes it.
    """
    value = globals().get(name)
    if not callable(value):
        return None
    if name.startswith("_"):
        return None
    if getattr(value, "__module__", None) != __name__:
        return None
    return value


def run_tool(name: str, arguments: dict) -> ToolResult:
    runner = resolve_tool(name)
    if runner is None:
        raise KeyError(name)
    return runner(arguments)
