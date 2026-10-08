from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: str


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    category: str
    description: str
    requires_approval: bool
    runner: Callable[[dict[str, Any]], ToolResult]
    argument_schema: dict[str, Any] = field(default_factory=dict)


_CAPABILITIES: dict[str, ToolDefinition] = {}


def capability(
    name: str,
    category: str,
    description: str,
    *,
    requires_approval: bool = False,
    argument_schema: dict[str, Any] | None = None,
):
    """Declare one executable OS capability.

    This is a capability catalog, not a troubleshooting workflow. The KBs
    decide when a capability is relevant; this module only implements it and
    supplies its safety metadata.
    """

    def decorator(func: Callable[[dict[str, Any]], ToolResult]):
        if name in _CAPABILITIES:
            raise RuntimeError(f"Duplicate executable capability: {name}")
        _CAPABILITIES[name] = ToolDefinition(
            name=name,
            category=category,
            description=description,
            requires_approval=requires_approval,
            runner=func,
            argument_schema=argument_schema or {},
        )
        return func

    return decorator


def get_capabilities() -> dict[str, ToolDefinition]:
    return dict(_CAPABILITIES)


def _ps(script: str, timeout: int = 30) -> ToolResult:
    if os.name != "nt":
        return ToolResult(False, "This diagnostic is supported only on Windows.")
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        output = stdout or stderr or f"PowerShell exited with code {completed.returncode}."
        return ToolResult(completed.returncode == 0, output)
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"PowerShell command timed out after {timeout} seconds.")
    except Exception as exc:
        return ToolResult(False, f"PowerShell execution failed: {exc}")


def _cmd(args: list[str], timeout: int = 30) -> ToolResult:
    if os.name != "nt":
        return ToolResult(False, "This diagnostic is supported only on Windows.")
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        output = stdout
        if stderr:
            output = f"{output}\n{stderr}".strip()
        if not output:
            output = f"Process exited with code {completed.returncode}."
        return ToolResult(completed.returncode == 0, output)
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"Command timed out after {timeout} seconds: {' '.join(args)}")
    except FileNotFoundError:
        return ToolResult(False, f"Required Windows command was not found: {args[0]}")
    except Exception as exc:
        return ToolResult(False, f"Command execution failed: {exc}")


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# ------------------------------ Network ------------------------------

@capability(
    "check_adapter_state", "DIAGNOSTIC", "Inspect network adapter state, link status and speed."
)
def check_adapter_state(_: dict[str, Any]) -> ToolResult:
    return _ps(
        "Get-NetAdapter | Select-Object Name,Status,LinkSpeed,MacAddress | "
        "Format-Table -AutoSize | Out-String"
    )


@capability(
    "check_ip_config", "DIAGNOSTIC", "Inspect IPv4 configuration, DHCP state, gateway and DNS settings."
)
def check_ip_config(_: dict[str, Any]) -> ToolResult:
    return _cmd(["ipconfig", "/all"])


@capability(
    "check_gateway", "DIAGNOSTIC", "Test reachability of the active IPv4 default gateway."
)
def check_gateway(_: dict[str, Any]) -> ToolResult:
    script = r"""
$c = Get-NetIPConfiguration | Where-Object {$_.IPv4DefaultGateway} | Select-Object -First 1
if (-not $c) { Write-Error 'No IPv4 default gateway was found.'; exit 2 }
$g = $c.IPv4DefaultGateway.NextHop
$ok = Test-Connection -TargetName $g -Count 2 -Quiet -ErrorAction SilentlyContinue
Write-Output "Default gateway: $g"
Write-Output "Gateway reachable: $ok"
if (-not $ok) { exit 3 }
"""
    return _ps(script)


@capability(
    "check_dns", "DIAGNOSTIC", "Test DNS resolution using a public hostname."
)
def check_dns(_: dict[str, Any]) -> ToolResult:
    try:
        addresses = socket.gethostbyname_ex("example.com")[2]
        return ToolResult(True, f"DNS resolution succeeded for example.com: {', '.join(addresses)}")
    except Exception as exc:
        return ToolResult(False, f"DNS resolution failed for example.com: {exc}")


@capability(
    "check_internet_ip", "DIAGNOSTIC", "Test outbound HTTPS Internet reachability."
)
def check_internet_ip(_: dict[str, Any]) -> ToolResult:
    request = urllib.request.Request(
        "https://example.com/",
        method="GET",
        headers={"User-Agent": "IT-Helpdesk-L1-Agent/2.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return ToolResult(True, f"HTTPS Internet check succeeded: HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        # An HTTP response proves Internet reachability even when the endpoint
        # itself refuses the request.
        return ToolResult(True, f"HTTPS Internet path reached the server: HTTP {exc.code}")
    except Exception as exc:
        return ToolResult(False, f"HTTPS Internet check failed: {exc}")


@capability(
    "enable_adapter",
    "FIX",
    "Enable one exact network adapter named in the diagnostic evidence.",
    requires_approval=True,
    argument_schema={"name": "Exact adapter Name from check_adapter_state"},
)
def enable_adapter(arguments: dict[str, Any]) -> ToolResult:
    name = str(arguments.get("name", "")).strip()
    if not name or any(c in name for c in "\r\n\x00"):
        return ToolResult(False, "A valid adapter name from diagnostics is required.")
    script = (
        f"$n={_ps_quote(name)}; "
        "$a=Get-NetAdapter -Name $n -ErrorAction Stop; "
        "if($a.Status -eq 'Disabled'){Enable-NetAdapter -Name $n -Confirm:$false -ErrorAction Stop; "
        "Write-Output ('Adapter enabled: ' + $n)} else {Write-Output ('Adapter was not disabled: ' + $a.Status)}"
    )
    return _ps(script)


@capability("fix_renew_dhcp", "FIX", "Renew DHCP configuration for active network adapters.", requires_approval=True)
def fix_renew_dhcp(_: dict[str, Any]) -> ToolResult:
    return _cmd(["ipconfig", "/renew"], 60)


@capability("fix_flush_dns", "FIX", "Flush the Windows DNS client cache.", requires_approval=True)
def fix_flush_dns(_: dict[str, Any]) -> ToolResult:
    return _cmd(["ipconfig", "/flushdns"])


@capability("fix_reset_winsock", "FIX", "Reset the Windows Winsock catalog.", requires_approval=True)
def fix_reset_winsock(_: dict[str, Any]) -> ToolResult:
    return _cmd(["netsh", "winsock", "reset"], 30)


@capability("fix_reset_tcpip", "FIX", "Reset the Windows TCP/IP stack configuration.", requires_approval=True)
def fix_reset_tcpip(_: dict[str, Any]) -> ToolResult:
    return _cmd(["netsh", "int", "ip", "reset"], 30)


# -------------------------- Not responding ---------------------------

@capability(
    "check_not_responding_apps",
    "DIAGNOSTIC",
    "Find visible Windows applications currently marked Not Responding.",
)
def check_not_responding_apps(_: dict[str, Any]) -> ToolResult:
    result = _ps(
        "Get-Process | Where-Object {$_.MainWindowHandle -ne 0 -and $_.Responding -eq $false} | "
        "Select-Object ProcessName,Id,MainWindowTitle,Responding | "
        "Format-Table -AutoSize | Out-String"
    )
    if result.success and not result.output.strip():
        return ToolResult(True, "No visible application is currently reported as Not Responding.")
    return result


@capability(
    "close_unresponsive_app",
    "FIX",
    "Close the exact verified unresponsive application using its diagnostic PID.",
    requires_approval=True,
    argument_schema={"pid": "PID from check_not_responding_apps", "process_name": "Expected process name from diagnostic evidence"},
)
def close_unresponsive_app(arguments: dict[str, Any]) -> ToolResult:
    pid = str(arguments.get("pid", "")).strip()
    process_name = str(arguments.get("process_name", "")).strip()
    if not pid.isdigit() or int(pid) <= 0:
        return ToolResult(False, "A valid PID from check_not_responding_apps is required.")
    if any(c in process_name for c in "'\"\r\n"):
        return ToolResult(False, "Invalid process_name argument.")
    protected_pids = {os.getpid(), os.getppid()}
    if int(pid) in protected_pids:
        return ToolResult(False, "The agent process itself cannot be terminated.")
    expected_name = _ps_quote(process_name) if process_name else "$null"
    script = f"""
$p = Get-Process -Id {int(pid)} -ErrorAction Stop
$protected = @('System','Idle','Registry','smss','csrss','wininit','services','lsass','winlogon','dwm')
if ($protected -contains $p.ProcessName) {{ throw 'Protected system process cannot be closed.' }}
if ($p.MainWindowHandle -eq 0) {{ throw 'The PID does not have a visible application window.' }}
if ($p.Responding) {{ throw 'The application is no longer reported as Not Responding.' }}
if ($null -ne {expected_name} -and {expected_name} -ne '$null' -and $p.ProcessName -ne {expected_name}) {{ throw 'The diagnostic PID no longer belongs to the expected process.' }}
$p.CloseMainWindow() | Out-Null
Start-Sleep -Seconds 2
if (-not $p.HasExited) {{ $p.Kill() }}
Write-Output ("Process closed: " + $p.ProcessName + " (PID " + $p.Id + ")")
"""
    return _ps(script, 20)


# ----------------------------- Time ----------------------------------

@capability("check_time_status", "DIAGNOSTIC", "Inspect Windows clock synchronization status and local time.")
def check_time_status(_: dict[str, Any]) -> ToolResult:
    script = r"""
Get-Date | ForEach-Object {"Local time: $_"}
Get-TimeZone | ForEach-Object {"Time zone: $($_.Id) ($($_.DisplayName))"}
w32tm /query /status
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
"""
    return _ps(script)


@capability("check_time_service", "DIAGNOSTIC", "Inspect the Windows Time service state and start type.")
def check_time_service(_: dict[str, Any]) -> ToolResult:
    return _ps("Get-Service W32Time | Select-Object Name,Status,StartType | Format-List | Out-String")


@capability("check_time_source", "DIAGNOSTIC", "Inspect the configured Windows time synchronization source.")
def check_time_source(_: dict[str, Any]) -> ToolResult:
    return _cmd(["w32tm", "/query", "/source"])


@capability("fix_sync_time", "FIX", "Request Windows to synchronize the clock with its configured time source.", requires_approval=True)
def fix_sync_time(_: dict[str, Any]) -> ToolResult:
    return _cmd(["w32tm", "/resync"], 30)


@capability("fix_restart_time_service", "FIX", "Restart the Windows Time service.", requires_approval=True)
def fix_restart_time_service(_: dict[str, Any]) -> ToolResult:
    return _ps(
        "Restart-Service W32Time -Force -ErrorAction Stop; "
        "Start-Service W32Time -ErrorAction Stop; "
        "Get-Service W32Time | Select-Object Name,Status | Format-Table -AutoSize | Out-String"
    )


# ------------------------------- USB ---------------------------------

@capability("check_usb_devices", "DIAGNOSTIC", "Inspect currently enumerated USB Plug and Play devices and problem codes.")
def check_usb_devices(_: dict[str, Any]) -> ToolResult:
    script = r"""
$d = Get-CimInstance Win32_PnPEntity | Where-Object {$_.PNPDeviceID -like 'USB\*'} |
    Select-Object Name,PNPClass,PNPDeviceID,Status,ConfigManagerErrorCode
if (-not $d) {
    Write-Output 'No currently enumerated USB PnP devices were found.'
} else {
    $d | Format-List | Out-String
}
"""
    return _ps(script)


@capability("scan_usb_devices", "DIAGNOSTIC", "Ask Windows Plug and Play to rescan for device changes.")
def scan_usb_devices(_: dict[str, Any]) -> ToolResult:
    return _cmd(["pnputil.exe", "/scan-devices"], 45)


@capability("check_usb_controllers", "DIAGNOSTIC", "Inspect USB host controllers and root hubs for problem states.")
def check_usb_controllers(_: dict[str, Any]) -> ToolResult:
    script = r"""
$d = Get-CimInstance Win32_PnPEntity |
    Where-Object {$_.PNPClass -eq 'USB' -and $_.Name -match 'Host Controller|Root Hub|USB xHCI|USB eXtensible'} |
    Select-Object Name,PNPClass,PNPDeviceID,Status,ConfigManagerErrorCode
if (-not $d) {
    Write-Output 'No USB controller/root hub entries were found.'
} else {
    $d | Format-List | Out-String
}
"""
    return _ps(script)


def _validated_instance_id(arguments: dict[str, Any], prefixes: tuple[str, ...]) -> str | None:
    value = str(arguments.get("instance_id", "")).strip().strip('"')
    if not value:
        return None
    upper = value.upper()
    if not any(upper.startswith(prefix) for prefix in prefixes):
        return None
    if any(token in value for token in [";", "|", "\n", "\r", "`", "$", "&&"]):
        return None
    return value


@capability(
    "enable_usb_device",
    "FIX",
    "Enable one exact verified USB device by Plug and Play instance ID.",
    requires_approval=True,
    argument_schema={"instance_id": r"Exact USB\... instance ID from diagnostics"},
)
def enable_usb_device(arguments: dict[str, Any]) -> ToolResult:
    instance_id = _validated_instance_id(arguments, ("USB\\",))
    if not instance_id:
        return ToolResult(False, "A valid USB instance_id from diagnostics is required.")
    return _cmd(["pnputil.exe", "/enable-device", instance_id], 45)


@capability(
    "restart_usb_device",
    "FIX",
    "Restart one exact verified USB device by Plug and Play instance ID.",
    requires_approval=True,
    argument_schema={"instance_id": r"Exact USB\... instance ID from diagnostics"},
)
def restart_usb_device(arguments: dict[str, Any]) -> ToolResult:
    instance_id = _validated_instance_id(arguments, ("USB\\",))
    if not instance_id:
        return ToolResult(False, "A valid USB instance_id from diagnostics is required.")
    return _cmd(["pnputil.exe", "/restart-device", instance_id], 45)


@capability(
    "restart_usb_controller",
    "FIX",
    "Restart one exact verified USB controller or root hub by instance ID.",
    requires_approval=True,
    argument_schema={"instance_id": r"Exact USB\... or PCI\... controller instance ID from diagnostics"},
)
def restart_usb_controller(arguments: dict[str, Any]) -> ToolResult:
    instance_id = _validated_instance_id(arguments, ("USB\\", "PCI\\"))
    if not instance_id:
        return ToolResult(False, "A valid USB/PCI controller instance_id from diagnostics is required.")
    return _cmd(["pnputil.exe", "/restart-device", instance_id], 45)


# ------------------------------ Audio --------------------------------

@capability("check_audio_state", "DIAGNOSTIC", "Inspect Windows sound devices and Plug and Play state.")
def check_audio_state(_: dict[str, Any]) -> ToolResult:
    return _ps(
        "Get-CimInstance Win32_SoundDevice | Select-Object Name,Status,PNPDeviceID | "
        "Format-List | Out-String"
    )


@capability("check_audio_devices", "DIAGNOSTIC", "Inspect audio endpoints and media-class devices.")
def check_audio_devices(_: dict[str, Any]) -> ToolResult:
    script = r"""
Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue |
    Select-Object Status,FriendlyName,InstanceId | Format-List | Out-String
Get-PnpDevice -Class Media -ErrorAction SilentlyContinue |
    Select-Object Status,FriendlyName,InstanceId | Format-List | Out-String
"""
    return _ps(script)


@capability("check_audio_services", "DIAGNOSTIC", "Inspect Windows Audio and AudioEndpointBuilder service state.")
def check_audio_services(_: dict[str, Any]) -> ToolResult:
    return _ps(
        "Get-Service Audiosrv,AudioEndpointBuilder | "
        "Select-Object Name,Status,StartType | Format-Table -AutoSize | Out-String"
    )


@capability("restart_audio_services", "FIX", "Restart the Windows Audio services.", requires_approval=True)
def restart_audio_services(_: dict[str, Any]) -> ToolResult:
    return _ps(
        "Restart-Service Audiosrv,AudioEndpointBuilder -Force -ErrorAction Stop; "
        "Get-Service Audiosrv,AudioEndpointBuilder | "
        "Select-Object Name,Status | Format-Table -AutoSize | Out-String"
    )


@capability(
    "enable_audio_device",
    "FIX",
    "Enable one exact verified audio device by Plug and Play instance ID.",
    requires_approval=True,
    argument_schema={"instance_id": "Exact audio InstanceId from diagnostics"},
)
def enable_audio_device(arguments: dict[str, Any]) -> ToolResult:
    instance_id = str(arguments.get("instance_id", "")).strip()
    if not instance_id or any(c in instance_id for c in "'\"\r\n\x00"):
        return ToolResult(False, "A valid audio device instance_id from diagnostics is required.")
    script = (
        f"Enable-PnpDevice -InstanceId {_ps_quote(instance_id)} -Confirm:$false -ErrorAction Stop; "
        "Write-Output 'Audio device enabled.'"
    )
    return _ps(script)


# -------------------------- CPU / memory ------------------------------

@capability(
    "check_system_performance",
    "DIAGNOSTIC",
    "Measure current CPU, memory, free memory and system-drive free space.",
)
def check_system_performance(_: dict[str, Any]) -> ToolResult:
    script = r"""
$o = Get-CimInstance Win32_OperatingSystem
$cpu = (Get-Counter '\Processor(_Total)\% Processor Time').CounterSamples.CookedValue
$mem = (($o.TotalVisibleMemorySize - $o.FreePhysicalMemory) / $o.TotalVisibleMemorySize) * 100
$freeMemGb = $o.FreePhysicalMemory / 1MB
$drive = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'" | Select-Object -First 1
Write-Output ("CPU usage: " + [math]::Round($cpu,1) + "%")
Write-Output ("Memory usage: " + [math]::Round($mem,1) + "%")
Write-Output ("Free physical memory: " + [math]::Round($freeMemGb,2) + " GB")
if ($drive) { Write-Output ("C: free space: " + [math]::Round($drive.FreeSpace/1GB,2) + " GB") }
"""
    return _ps(script)


@capability(
    "check_top_cpu_processes",
    "DIAGNOSTIC",
    "Identify current top CPU-consuming processes with PIDs.",
)
def check_top_cpu_processes(_: dict[str, Any]) -> ToolResult:
    script = r"""
$p = Get-CimInstance Win32_PerfFormattedData_PerfProc_Process -ErrorAction Stop |
    Where-Object {$_.IDProcess -gt 0 -and $_.Name -ne '_Total'} |
    Sort-Object PercentProcessorTime -Descending |
    Select-Object -First 12 Name,IDProcess,PercentProcessorTime
$p | Format-Table -AutoSize | Out-String
"""
    return _ps(script)


@capability(
    "check_top_memory_processes",
    "DIAGNOSTIC",
    "Identify current top memory-consuming processes with PIDs.",
)
def check_top_memory_processes(_: dict[str, Any]) -> ToolResult:
    script = r"""
Get-Process |
    Sort-Object WorkingSet64 -Descending |
    Select-Object -First 12 ProcessName,Id,@{N='MemoryMB';E={[math]::Round($_.WorkingSet64/1MB,1)}},Responding |
    Format-Table -AutoSize | Out-String
"""
    return _ps(script)


@capability(
    "close_high_resource_process",
    "FIX",
    "Close one verified user-space process identified by a diagnostic PID.",
    requires_approval=True,
    argument_schema={"pid": "PID from CPU/memory process diagnostics"},
)
def close_high_resource_process(arguments: dict[str, Any]) -> ToolResult:
    pid = str(arguments.get("pid", "")).strip()
    if not pid.isdigit() or int(pid) <= 0:
        return ToolResult(False, "A valid PID from CPU/memory diagnostics is required.")
    protected_pids = {os.getpid(), os.getppid()}
    if int(pid) in protected_pids:
        return ToolResult(False, "The agent process or its parent cannot be terminated.")
    script = f"""
$p = Get-Process -Id {int(pid)} -ErrorAction Stop
$protected = @('System','Idle','Registry','smss','csrss','wininit','services','lsass','winlogon','dwm','svchost')
if ($protected -contains $p.ProcessName) {{ throw 'Protected system process cannot be closed.' }}
Stop-Process -Id {int(pid)} -Force -ErrorAction Stop
Write-Output ("Process terminated: " + $p.ProcessName + " (PID " + $p.Id + ")")
"""
    return _ps(script, 20)


@capability(
    "clean_temp_files",
    "FIX",
    "Remove current-user temporary files when low system storage is evidenced.",
    requires_approval=True,
)
def clean_temp_files(_: dict[str, Any]) -> ToolResult:
    script = r"""
$files = Get-ChildItem $env:TEMP -Force -ErrorAction SilentlyContinue |
    Where-Object {-not $_.PSIsContainer}
$count = 0
foreach ($file in $files) {
    try { Remove-Item $file.FullName -Force -ErrorAction Stop; $count++ } catch {}
}
Write-Output ("Temporary files removed: " + $count)
"""
    return _ps(script)
