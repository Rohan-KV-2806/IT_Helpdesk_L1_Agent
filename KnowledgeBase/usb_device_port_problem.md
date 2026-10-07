# USB Device / USB Port Problem

## Category

**USB Device / USB Port Problem**

## Scope

Use this knowledge base for Windows USB problems such as:

- USB device not recognized
- USB device not detected / not registered by Windows
- Unknown USB device
- USB device showing a Device Manager error
- USB device disabled
- USB device repeatedly disconnecting or failing to start
- One or more USB ports not working
- USB host controller / root hub problems that affect USB devices

This knowledge base is for Windows L1 troubleshooting only.

Do not diagnose a physical hardware defect solely from software output. A dead USB port cannot always be distinguished from a bad cable, bad device, insufficient power, a hub/dock problem, or a Windows PnP/driver problem without a known-good device test.

---

# Mandatory Workflow

Always follow:

**VERIFY → DIAGNOSE → APPLY APPROPRIATE L1 FIX → VERIFY AGAIN → RESOLVED OR TICKET**

Never do:

**USER COMPLAINT → ASSUME USB PROBLEM → FIX**

The user's statement is a reported symptom, not proof that the problem currently exists.

---

# Step 1 — Verify the Reported USB Problem

Run:

`check_usb_devices`

This is the first required diagnostic for every USB request.

The diagnostic should inspect currently present Plug and Play USB devices and report, at minimum:

- Friendly name
- Device class
- Instance ID / PNP device ID
- Windows status
- Configuration Manager problem code when available

Interpretation:

### Case A — The affected USB device is present and healthy

If the user reported that a specific USB device is failing, but the device is present and has no problem state, the reported problem is **not reproduced**.

Return:

- `RESOLVED`
- `problem_verified=false`
- no fix
- no ticket

Do not perform unrelated USB changes.

### Case B — The affected USB device is present with a problem

The problem is verified.

Continue to diagnosis using the actual problem code/status.

### Case C — The affected device is not present

Do not immediately claim hardware failure.

Run:

`scan_usb_devices`

`scan_usb_devices` forces Windows to rescan for hardware changes. Microsoft documents `pnputil /scan-devices` for this purpose and recommends checking connected devices afterward.

Then run:

`check_usb_devices`

again.

If the user explicitly reported that the affected device is physically connected to the affected USB port and it is still absent after the hardware rescan, treat the failure to enumerate as **verified**.

Do not invent a Device Manager error code when Windows has not reported one.

---

# Step 2 — Verify USB Controller Health When Needed

Run:

`check_usb_controllers`

when:

- multiple USB devices or ports are affected
- the affected device remains missing after a hardware rescan
- the USB device has a problem that may originate from the USB bus/controller
- `check_usb_devices` reports USB host controller / root hub errors

The diagnostic should inspect USB host controllers and USB root hubs and report their Windows status and Configuration Manager problem code when available.

A healthy controller/root hub does **not** prove that a physical USB port is healthy.

---

# Device Manager / PnP Problem Codes

Use the actual reported Configuration Manager problem code as evidence.

Important examples:

| Code | Meaning / L1 interpretation |
|---|---|
| 0 | Device is working properly. |
| 10 | Device failed to start. |
| 14 | Device needs a restart. |
| 18 | Device needs to be reinstalled. Do not perform driver removal automatically in this L1 workflow. |
| 19 | Device configuration/driver registry problem. Do not edit the registry automatically. |
| 22 | Device is disabled. Re-enable is an allowed L1 action. |
| 24 | Device is not present / not working correctly. Reconnect/rescan and verify. |
| 28 | Driver is not installed. Do not invent or download a driver automatically. Escalate if the L1 actions below do not resolve it. |
| 29 | Device is disabled by firmware/resource configuration. BIOS/firmware work is outside this L1 workflow; escalate. |
| 31 | Windows cannot load the required driver. Restart/rescan may be attempted; escalate if unresolved. |
| 37 | Windows cannot initialize the device driver. Restart/rescan may be attempted; escalate if unresolved. |
| 38 | Previous driver instance is still loaded. A Windows restart may be required; restart the device/controller first where appropriate, then escalate if a reboot is required. |
| 39 | Driver may be corrupted or missing. Do not edit the registry automatically; escalate if L1 restart/rescan does not solve it. |
| 41 | Windows loaded the driver but cannot find the hardware. Verify reconnect/rescan; escalate if still missing. |
| 43 | Windows stopped the device because it reported a problem. Restart/rescan may be attempted; escalate if unresolved. |
| 45 | Device is not currently connected. Do not treat a stale non-present device as a live failure. |
| 47 | Device was prepared for safe removal. Reconnect it and rescan. |
| 52 | Windows cannot verify the driver signature. Do not bypass driver-signing protections; escalate/vendor support. |

Microsoft documents Device Manager problem codes and their meanings, including Codes 10, 14, 22, 28, 43, 45 and others.

Code 22 specifically means the device is disabled and Microsoft's recommended action is to enable the device. citeturn619983search1

---

# Step 3 — Apply Only an Evidence-Based L1 Fix

All state-changing actions require explicit user approval through the application's Yes/No approval dialog.

Never apply a fix merely because it is a common USB troubleshooting step.

Never uninstall all USB controllers, root hubs, or drivers automatically.

Never modify the registry automatically.

Never disable security features or driver-signing enforcement.

Never download or install a driver from an unknown source.

## Fix A — Re-enable a Disabled USB Device

Tool:

`enable_usb_device`

Use only when the diagnostic evidence identifies the affected USB device with:

`ConfigManagerErrorCode = 22`

Microsoft identifies Code 22 as a disabled device and recommends enabling it.

After the fix, go to **Step 4 — Mandatory Verification**.

## Fix B — Restart the Affected USB Device

Tool:

`restart_usb_device`

Use only when:

- the affected USB device is present in the diagnostic output, and
- Windows reports a device problem/status that makes a restart reasonable, and
- the device has a concrete Instance ID / PNP device ID available from the latest diagnostic result.

The application must pass the exact device Instance ID to the tool. The model must not invent or manually construct an Instance ID.

Windows PnPUtil supports restarting a device by its instance ID. Microsoft documents `/restart-device` for this purpose.

After the fix, go to **Step 4 — Mandatory Verification**.

## Fix C — Restart the Affected USB Controller / Root Hub

Tool:

`restart_usb_controller`

Use only when `check_usb_controllers` provides evidence that a specific USB host controller or root hub is affected, or when multiple affected USB devices clearly point to the same failing USB controller/root hub.

The application must pass the exact controller/root-hub Instance ID obtained from the diagnostic result.

This action can temporarily disconnect attached USB devices. It therefore requires explicit user approval.

Windows PnPUtil supports restarting a device by instance ID.

After the fix, go to **Step 4 — Mandatory Verification**.

---

# Step 4 — Mandatory Verification After Every Fix

A successful command is **not** proof that the USB problem is fixed.

Immediately after any USB fix, run the original relevant diagnostic again.

For a specific USB device:

`check_usb_devices`

For a controller/root-hub issue:

`check_usb_controllers`

Verification rules:

### Resolved

Return `RESOLVED` only when the new diagnostic proves the original problem is gone.

Examples:

- the affected device is now present and healthy
- the original problem code is gone
- the device/controller reports a healthy state
- the user-reported USB function is restored according to the available diagnostic evidence

### Not resolved

If the same problem remains after the supported L1 fix:

- do not repeat the same fix indefinitely
- do not guess another cause
- do not perform unrelated USB changes
- escalate to a ticket

---

# USB Port-Specific Handling

Software diagnostics can confirm USB controller/device problems, but they cannot always prove that one physical USB port is electrically or mechanically defective.

For a complaint such as:

> "This USB port is not working."

If no software-side USB error is found, the agent may use `ASK_USER` to request a controlled physical test:

> Connect a known-good USB device to the affected port and tell me whether Windows detects it.

Do not create a physical-hardware diagnosis from a single failed device.

Useful evidence for a likely physical/port-side failure includes:

- a known-good USB device works in other ports but not in the affected port
- the affected port still fails after Windows rescans the hardware
- USB controllers/root hubs are healthy
- the same known-good device is repeatedly not detected only on the affected port

If the port cannot be restored by supported L1 software actions, escalate.

Do not ask the user to open the computer or perform electrical/hardware repair as part of L1 troubleshooting.

---

# Rescan Rule

`scan_usb_devices` is a diagnostic action, not a proof of resolution.

After scanning, always check the resulting device state with:

`check_usb_devices`

Do not return `RESOLVED` merely because the scan command completed successfully.

PnPUtil is included with supported Windows versions, and Microsoft documents `/scan-devices` to force Windows to detect hardware changes.

---

# Power / Cable / Hub Considerations

If Windows does not report a software error, consider that the failure may involve:

- insufficient power
- an unsupported USB device
- a bad cable
- an external hub or dock
- a physically damaged port
- a device-side hardware failure

Microsoft notes that a USB device may fail when the PC cannot provide enough power, and recommends using external power where supported, powering the PC, disconnecting unused USB devices, or trying another computer/port.

The agent should **not** automatically change global USB power-management settings as an L1 fix unless a separately approved and documented tool is later added for that purpose.

---

# Driver Handling

Driver problems may be indicated by codes such as 28, 31, 37, 39, 43 or 52.

For this L1 agent:

- allow restart/rescan when appropriate
- do not automatically uninstall device drivers
- do not automatically delete driver packages
- do not modify registry driver entries
- do not bypass Windows driver-signing/security protections
- do not download drivers from arbitrary websites
- escalate when the remaining remedy requires vendor-specific driver/firmware work or manual driver installation

Microsoft documents reinstalling drivers as a resolution for several Device Manager error codes, but that is intentionally kept outside the automated L1 tool set here because the agent does not have a trusted vendor-driver source or a safe device-specific driver-selection workflow.

---

# Escalation Conditions

Create a ticket when any of the following is true:

1. The verified USB problem remains after the supported L1 fix.
2. The device/controller repeatedly returns the same failure after restart/rescan.
3. A required action fails because administrator permissions are unavailable.
4. The problem requires driver installation from a hardware vendor.
5. The problem requires BIOS/UEFI or firmware changes.
6. The problem strongly indicates physical hardware failure.
7. A known-good device fails only on the affected physical port and software-side repair does not restore it.
8. The knowledge base has no safe supported L1 fix for the observed condition.

Ticket information must contain only factual evidence from the user's report and actual diagnostic/tool results.

Do not create a ticket because the model returned invalid JSON, selected an invalid tool, or made another internal application error.

---

# Required Tool Names

The application must provide these exact tool names before this knowledge base is enabled:

## Diagnostics

- `check_usb_devices`
- `scan_usb_devices`
- `check_usb_controllers`

## Fixes

- `enable_usb_device`
- `restart_usb_device`
- `restart_usb_controller`

The model must use these exact identifiers and nothing else.

---

# Decision Flow

```text
User USB complaint
        ↓
check_usb_devices
        ↓
Is the reported problem reproduced?
   ┌────┴────┐
  NO        YES
   ↓          ↓
If device is   Diagnose using actual
missing,       status/problem code
scan + check        ↓
again          Is a supported L1 fix justified?
   ↓          ┌────┴────┐
Still absent  NO        YES
and user says  ↓          ↓
connected?   ESCALATE   Ask approval
   ↓                      ↓
 YES                     FIX
   ↓                      ↓
VERIFIED                VERIFY AGAIN
                           ↓
                    Fixed? ── No ──→ TICKET
                      ↓
                     YES
                      ↓
                  RESOLVED
```

For physical USB-port complaints, insert the required known-good-device user test when software evidence alone cannot verify the physical port.

---

# Core Rules

- Test first.
- Use evidence, not assumptions.
- Fix only a verified problem.
- Use only the exact registered tools.
- State-changing actions require explicit user approval.
- Verify the original problem after every fix.
- A successful command is not the same as a successful repair.
- Do not repeatedly apply the same failed fix.
- Do not guess that a USB port is physically damaged from software output alone.
- Escalate when safe L1 troubleshooting is exhausted.
- Internal model/application errors are never user support tickets.

---

# Research Basis

This knowledge base was prepared against current Microsoft documentation for Windows USB/PnP troubleshooting:

- Microsoft Support — Fix USB-C problems in Windows: https://support.microsoft.com/en-us/windows/hardware/usb/fix-usb-c-problems-in-windows
- Microsoft Support — Error codes in Device Manager in Windows: https://support.microsoft.com/en-us/windows/hardware/drivers/error-codes-in-device-manager-in-windows
- Microsoft Learn — PnPUtil command examples: https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/pnputil-examples
- Microsoft Learn — PnPUtil command syntax: https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/pnputil-command-syntax
- Microsoft Learn — Get-PnpDevice: https://learn.microsoft.com/en-us/powershell/module/pnpdevice/get-pnpdevice
- Microsoft Learn — Win32_PnPEntity / ConfigManagerErrorCode: https://learn.microsoft.com/en-us/windows/win32/cimwin32prov/win32-pnpentity
- Microsoft Learn — Device Manager problem codes: https://learn.microsoft.com/en-us/windows-hardware/drivers/debugger/device-manager-problem-codes
