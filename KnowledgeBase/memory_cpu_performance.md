# memory_cpu_performance.md — L1 Troubleshooting Knowledge Base: Memory and CPU Performance Problems

**Applies to:** Windows 10 / Windows 11 workstations  
**Agent role:** IT Helpdesk L1 automated agent  
**Purpose:** L1 handling of reports such as high CPU usage, high memory/RAM usage, system slowdown caused by resource pressure, applications consuming excessive CPU/RAM, and performance degradation caused by common user-space/background activity.

---

## 1. SCOPE

This knowledge base covers L1 investigation and remediation of **CPU and memory performance symptoms** when the machine is still usable enough for the agent to collect evidence.

### In scope

- Verifying whether CPU or memory pressure is actually present.
- Identifying the processes responsible for the observed CPU or memory consumption.
- Closing a verified, non-critical user application/process that is consuming excessive resources.
- Restarting Windows when a transient system-wide performance problem remains after safer L1 actions.
- Disabling clearly non-essential user startup applications when they are contributing to repeated background resource usage.
- Cleaning **temporary files** when low storage is contributing to system performance problems.
- Re-checking CPU/memory/storage state after every state-changing fix.
- Escalating when evidence points to drivers, kernel/system processes, hardware, memory leaks, persistent paging/commit pressure, malware investigation, corruption, or another issue outside safe L1 remediation.

### Out of scope — escalate instead

- Hardware failure or suspected failing RAM/storage/CPU/GPU.
- Driver faults, especially when **System**, **System interrupts**, or kernel-mode activity is the dominant resource consumer and the responsible driver cannot be safely identified.
- Persistent memory leaks that return after application restart/reboot or require application/vendor debugging.
- Kernel paged/nonpaged-pool exhaustion without a clear safe user-space cause.
- Repeated out-of-memory conditions with no removable user-space cause.
- Page-file configuration changes as a routine performance fix.
- Registry changes intended to improve performance.
- BIOS/UEFI changes, overclocking, undervolting, or hardware configuration changes.
- Clean boot / selective service disabling as routine L1 remediation.
- Uninstalling software merely because it uses resources.
- Disabling Microsoft/security services to reduce CPU or RAM usage.
- Deleting user documents, Downloads, Pictures, Desktop files, application data, or browser profiles as a generic “cleanup.”
- Malware removal beyond whatever approved enterprise security workflow exists.
- Whole-OS freezes, crashes, blue screens, or repeated bugchecks.

---

## 2. CORE PRINCIPLE

**High CPU or high memory percentage by itself is NOT proof of a problem.** Windows uses memory for active processes, caches, and other system purposes, and short CPU spikes are normal.

The agent must establish an objective resource-pressure condition and identify the likely consumer before changing anything.

Microsoft's Windows performance guidance recommends looking at system resource counters and then correlating CPU/memory pressure with the processes responsible. It also notes that short CPU spikes are acceptable; sustained pressure should be investigated. citehttps://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-performance-problems-in-windows

Never reason like this:

```text
Memory = 90% → memory problem → clean files
CPU = 100% for 5 seconds → CPU problem → kill process
```

Instead reason like this:

```text
USER REPORT
    ↓
MEASURE CURRENT CPU + MEMORY STATE
    ↓
IS THERE REAL, SUSTAINED RESOURCE PRESSURE?
    ↓
IDENTIFY THE PROCESS / SYSTEM COMPONENT RESPONSIBLE
    ↓
CHOOSE THE LEAST-INVASIVE L1 ACTION JUSTIFIED BY EVIDENCE
    ↓
VERIFY AGAIN
    ↓
RESOLVED OR ESCALATE
```

---

## 3. MANDATORY WORKFLOW

Every session MUST follow this sequence unless the KB explicitly says to escalate earlier.

```text
USER REPORTS SLOW / HIGH CPU / HIGH MEMORY
            ↓
1. VERIFY CURRENT PERFORMANCE STATE
            ↓
2. IDENTIFY CPU / MEMORY CONSUMERS
            ↓
3. DETERMINE WHETHER AN L1 FIX IS JUSTIFIED
            ↓
4. APPLY ONE APPROVED L1 FIX
            ↓
5. RE-CHECK PERFORMANCE
            ↓
        ┌───────────────┐
        │               │
      HEALTHY        STILL BAD
        │               │
     RESOLVED       MORE L1 ACTION JUSTIFIED?
                        │
                  ┌─────┴─────┐
                 YES          NO
                  │            │
              FIX + VERIFY   TICKET
                  │
             STILL BAD → TICKET
```

### Forbidden flows

```text
USER REPORT → IMMEDIATE PROCESS TERMINATION
USER REPORT → DELETE TEMP/RECENT/USER FILES
USER REPORT → DISABLE STARTUP APPS
USER REPORT → REBOOT WITHOUT APPROVAL
HIGH MEMORY PERCENTAGE → ASSUME MEMORY LEAK
HIGH CPU → ASSUME BAD APPLICATION
FIX COMPLETED → RESOLVED WITHOUT MEASUREMENT
```

---

## 4. AVAILABLE TOOLS

The canonical tool identifiers are exactly as listed below. The agent may select tools according to this KB and the evidence returned by previous diagnostics.

### 4.1 Diagnostics

| Tool | Purpose |
|---|---|
| `check_system_performance` | Capture current overall CPU, memory, commit, available memory, disk activity/latency where available, uptime, and other high-level performance indicators. |
| `check_top_cpu_processes` | Identify processes currently consuming the most CPU and record process name, PID, CPU usage, and user/system context where available. |
| `check_top_memory_processes` | Identify processes currently consuming the most physical memory/working set and record process name, PID, memory usage, and user/system context where available. |
| `check_disk_space` | Check free space on the Windows system drive and identify whether storage is critically low enough to contribute to performance problems. |
| `check_startup_apps` | Identify enabled startup applications and their reported startup impact, so unnecessary background launchers can be considered as a preventive L1 action. |

### 4.2 L1 fixes

| Tool | Purpose |
|---|---|
| `close_high_resource_process` | Close a **verified non-critical user application/process** that is demonstrably responsible for excessive CPU or memory use. |
| `restart_computer` | Restart Windows to clear transient resource pressure after safer L1 actions are ineffective or when the KB explicitly justifies a restart. |
| `disable_startup_app` | Disable a verified, clearly non-essential user startup application to reduce recurring background resource consumption. |
| `clean_temporary_files` | Remove temporary files using a Windows-supported cleanup mechanism when low free disk space or temporary-file buildup is relevant. |

### 4.3 Control actions

| Tool | Purpose |
|---|---|
| `ask_user` | Request required information or explicit approval for a state-changing action. |
| `escalate` | End L1 handling and create a ticket with the gathered evidence. |
| `resolved` | End the session with status RESOLVED and produce the final report. |

---

## 5. PHASE 1 — VERIFY THE PERFORMANCE PROBLEM

### 5.1 First diagnostic

The first diagnostic must normally be:

```text
check_system_performance
```

The agent must obtain objective measurements before selecting a fix.

At minimum, capture where the operating system exposes the values:

| Metric | Why it matters |
|---|---|
| Total CPU utilization / idle time | Determines whether CPU is actually under sustained pressure. |
| Available physical memory | Indicates how much RAM is immediately available. |
| Memory in use | Shows current physical memory consumption. |
| Committed memory / commit limit | Helps identify virtual-memory pressure rather than relying only on Task Manager's memory percentage. |
| Top-level disk activity / latency | Low storage or overloaded storage can make a memory-pressure problem appear worse. |
| System uptime | Helps identify very long-running sessions as context, not proof of failure. |

Microsoft's performance troubleshooting guidance uses **Available MBytes**, **Committed Bytes In Use**, and process **Working Set** when investigating memory pressure. For CPU it recommends correlating low CPU idle time with the processes consuming CPU. citehttps://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-performance-problems-in-windows

### 5.2 CPU interpretation

As diagnostic guidance, sustained CPU pressure should be distinguished from short spikes.

Microsoft's current high-CPU guidance investigates situations where CPU usage remains around **80% or higher for extended periods**, and its broader performance guide treats CPU conditions sustained for about a minute as a reason to investigate. citehttps://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-high-cpu-usage-guidance

Therefore:

- A short spike is not, by itself, a verified performance failure.
- Sustained high CPU should trigger process identification.
- The agent should prefer another measurement after a short observation window when the initial reading is only a transient spike.

### 5.3 Memory interpretation

Do **not** use `Memory %` alone as the verification condition.

Memory pressure should be judged using the combination of:

- available physical memory,
- committed memory versus commit limit,
- top process Working Set / physical memory consumers,
- evidence of heavy paging or system-wide slowdown when available.

Microsoft's performance guidance gives these example counter ranges:

| Memory counter | Healthy | Warning | Critical |
|---|---:|---:|---:|
| Available memory | >10% or at least 4 GB | <10% | <1% or <500 MB |
| % Committed Bytes In Use | 0–50% | 60–80% | 80–100% |

These are **diagnostic guidance, not automatic proof of a fault**. The agent must correlate the resource measurements with the user's actual performance symptom and process-level evidence. citehttps://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-performance-problems-in-windows

### 5.4 No problem reproduced

If the measurements are normal and the reported slowdown cannot be reproduced:

- STOP.
- Do not terminate processes.
- Do not clean files.
- Do not disable startup apps.
- Do not reboot simply because the user reported “high usage.”
- Do not create a ticket solely because the user reported a symptom that is not currently reproducible.

Use `resolved` with:

```text
problem_verified = false
fix_attempted = null
ticket_required = false
```

The report should clearly say that no current CPU/memory performance fault was reproduced.

---

## 6. PHASE 2 — IDENTIFY THE RESOURCE CONSUMER

If real CPU or memory pressure is verified, determine **what is consuming the resource** before changing anything.

### 6.1 CPU

Run:

```text
check_top_cpu_processes
```

Microsoft recommends sorting Task Manager by CPU usage to identify the process or application driving the load and then investigating the highest consumers. citehttps://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-high-cpu-usage-guidance

The agent should record:

- process name,
- PID,
- CPU utilization,
- whether it is an interactive user application,
- whether it appears to be a Windows/system process,
- whether the process remains a top consumer during more than one observation.

### 6.2 Memory

Run:

```text
check_top_memory_processes
```

Correlate the largest Working Set / physical-memory consumers with the system's available memory. Microsoft explicitly recommends using process Working Set to identify top RAM consumers. citehttps://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-performance-problems-in-windows

The agent must NOT label the largest process a “memory leak” merely because it uses a lot of RAM. A memory leak is an inference requiring evidence such as steadily increasing consumption that does not return after normal workload changes/restart and generally needs deeper application/system analysis.

### 6.3 System / kernel consumers

If the dominant resource consumer is clearly one of the following classes:

- `System`
- `System interrupts`
- a Windows kernel component
- a protected system process
- an unclear `svchost.exe`/service grouping where the responsible service cannot be safely isolated by the available L1 tools

**Do not terminate it.**

Windows separates user-mode applications/services from kernel-mode components and drivers, and Microsoft treats deeper analysis of kernel/system CPU consumers as a diagnostic problem requiring more specialized tooling. citehttps://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-performance-problems-in-windows

Collect the evidence and escalate unless another clearly documented L1 action is justified by this KB.

---

## 7. PHASE 3 — L1 FIX DECISION

### 7.1 Fix A — Close a verified resource-heavy user process

`close_high_resource_process` is permitted only when ALL of the following are true:

1. CPU or memory pressure has been objectively verified.
2. The target process is a **user application/process**, not a protected/system-critical Windows process.
3. The process is a demonstrated major contributor to the observed pressure.
4. Closing it is a reasonable L1 action for the reported symptom.
5. The user has been warned that unsaved work may be lost.
6. The user explicitly approves the action.

The agent must not:

- terminate random background processes,
- terminate `System`, `System interrupts`, or protected Windows processes,
- terminate a security product merely because it uses CPU/RAM,
- terminate multiple processes at once as a “cleanup,”
- assume that a process is safe to kill solely from its name.

After the process is closed, re-run the relevant performance diagnostic.

If CPU/memory pressure improves substantially and the user's symptom is relieved → `resolved`.

If the pressure remains → continue with the KB; do not repeatedly terminate processes without new evidence.

### 7.2 Fix B — Restart Windows

`restart_computer` is a valid L1 remediation for a **persistent but non-specific/transient** performance problem when:

- the system is under verified resource pressure,
- no unsafe/system-critical process should be terminated,
- a restart is a reasonable attempt to clear transient state,
- the user has been warned that applications will close,
- the user explicitly approves the restart.

Microsoft's performance guidance for Windows also recommends closing unused apps and restarting the PC when performance does not improve after closing unnecessary applications. citehttps://support.microsoft.com/en-us/windows/experience/performance-optimization/tips-to-improve-pc-performance-in-windows

After restart, the agent must verify CPU/memory state again before declaring success.

A restart is **not** proof that an underlying cause has been solved. If high resource usage immediately returns, continue diagnosis or escalate.

### 7.3 Fix C — Disable a clearly non-essential startup application

`check_startup_apps` may be used when the evidence suggests that unnecessary applications are contributing to recurring background resource consumption, especially after boot/sign-in.

A startup app may be disabled only when it is:

- clearly a user/application startup entry,
- not required for Windows to boot,
- not a security/control agent that the organization requires,
- not an unknown executable,
- reasonably safe to disable and easy to re-enable.

The user must explicitly approve disabling the selected startup app.

Microsoft documents Task Manager and Settings as the supported ways to configure startup applications and notes that startup apps can increase background activity and slow the startup experience. citehttps://support.microsoft.com/en-gb/windows/experience/startup-boot/configure-startup-applications-in-windows

Disabling startup applications is mainly a **recurrence-prevention** action. It should not be claimed as the direct reason current CPU/memory pressure disappeared unless verification proves that the relevant process stopped and the resource state improved.

### 7.4 Fix D — Clean temporary files when storage is genuinely low

First run:

```text
check_disk_space
```

Only consider `clean_temporary_files` when low free space is objectively established and there is a reasonable performance relationship.

Microsoft documents that low free disk space can reduce system performance and recommends Storage Sense / temporary-file cleanup as a supported way to free space. citehttps://support.microsoft.com/en-us/windows/experience/performance-optimization/tips-to-improve-pc-performance-in-windows

The cleanup action must target **temporary/system cleanup locations only** through a Windows-supported mechanism.

The agent must NOT delete:

- Documents,
- Downloads,
- Desktop files,
- Pictures/Videos,
- arbitrary “large files,”
- application databases,
- browser profiles,
- user project folders,
- files merely because they appear in “Recent.”

#### Important: “Recent files” are NOT a generic CPU/RAM fix

Do **not** tell the user that clearing the Windows “Recent files” list will solve high CPU or high RAM usage. The Recent list is primarily a history/shortcut mechanism; removing those entries does not meaningfully free physical RAM or CPU capacity.

Temporary-file cleanup can help when the **disk is actually low on space**. It is not a general treatment for high memory utilization.

After cleanup, re-check disk space and then re-check CPU/memory if the original symptom was performance-related.

### 7.5 What the L1 agent must NOT do

Do not use this KB to justify:

- manually resizing or disabling the page file,
- editing performance-related registry settings,
- disabling Windows services at random,
- disabling antivirus/security controls,
- changing power plans solely because CPU usage is high,
- changing processor affinity/priority without a documented reason,
- uninstalling applications as a first-line performance fix,
- performing a clean boot,
- modifying BIOS/UEFI settings,
- changing virtual-memory settings as a routine “RAM cleanup.”

Microsoft's page-file documentation makes clear that page-file behavior is part of Windows virtual-memory management and that sizing depends on workload/system requirements; it is not a universal L1 performance knob. citehttps://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/introduction-to-the-page-file

---

## 8. PHASE 4 — VERIFY AFTER EVERY FIX

A fix is never a resolution by itself.

### After `close_high_resource_process`

Re-run:

```text
check_system_performance
check_top_cpu_processes and/or check_top_memory_processes
```

Confirm that:

- the target process is no longer running, or no longer the problematic consumer,
- resource pressure has materially improved,
- the user's performance complaint is addressed as far as observable evidence allows.

### After `clean_temporary_files`

Re-run:

```text
check_disk_space
check_system_performance
```

Confirm that disk space improved and that the performance symptom improved if low disk space was part of the diagnosis.

### After `disable_startup_app`

A startup change should not be described as an immediate resolution unless the relevant workload is no longer running and current measurements improve. The primary purpose is to prevent the same application from launching automatically in future sessions.

### After `restart_computer`

Re-run the performance diagnostics after Windows is back up.

If the system is healthy → RESOLVED.

If the same high-usage condition returns immediately or repeatedly → do not keep rebooting as a loop. Escalate with evidence or continue only with another L1 action explicitly justified by this KB.

---

## 9. DIAGNOSIS / ESCALATION MATRIX

| Evidence | L1 handling |
|---|---|
| CPU/memory currently normal | Stop; RESOLVED / problem not reproduced |
| High CPU caused by a verified user application | Ask approval → close process → verify |
| High memory caused by a verified user application | Ask approval → close process → verify |
| Several unnecessary user apps/background apps contribute to pressure | Close the most relevant verified process first; consider startup cleanup only when recurring behavior is evidenced |
| Performance remains degraded after safe user-process remediation | Ask approval → restart → verify |
| Startup applications clearly contribute to repeated background load | Ask approval → disable selected non-essential startup app → verify future/current state as appropriate |
| Low system-drive free space is objectively established | Ask approval → clean temporary files → verify disk/performance |
| `System` / `System interrupts` / kernel component is dominant CPU consumer | Do not terminate; escalate with evidence |
| Unknown/protected process is dominant | Do not terminate; escalate |
| Memory pressure persists with no clear user process cause | Escalate |
| Memory usage steadily grows again after restart / app restart | Suspected leak or deeper system issue → escalate |
| Commit/page-file pressure remains severe without safe L1 cause | Escalate |
| Suspected hardware fault | Escalate |
| Malware suspected | Use the organization's security process / escalate; do not improvise malware removal |
| User asks to delete “recent files” as a RAM fix | Explain that this is not an evidence-based RAM/CPU fix; diagnose actual resource use instead |
| User asks to delete personal files to make the PC faster | Do not do this automatically; use supported storage diagnostics and temporary-file cleanup only |

---

## 10. REPORTING CONTRACT

For RESOLVED cases, the final report should include:

```text
status = RESOLVED
problem_verified = true|false
category = this KB filename
summary = original user report
diagnosis = evidence-based explanation
actions_taken = exact diagnostics/fixes executed
verification_successful = true|false
message = concise explanation to the user
```

### `problem_verified`

- `false` when the reported performance problem could not be reproduced by current measurements.
- `true` when objective CPU/memory/storage evidence confirmed the reported performance condition.

Do **not** set `problem_verified = true` merely because a diagnostic tool ran.

### `verification_successful`

This means the **post-fix check** demonstrated that the chosen fix actually improved or resolved the verified condition.

A successful command execution is not the same as successful troubleshooting.

---

## 11. EXAMPLE REASONING PATHS

### Example A — High memory from a user application

```text
User: “My PC is extremely slow and RAM is very high.”
        ↓
check_system_performance
        ↓
Memory pressure confirmed
        ↓
check_top_memory_processes
        ↓
User application is dominant consumer
        ↓
ask_user for approval to close it
        ↓
close_high_resource_process
        ↓
check_system_performance
        ↓
Memory pressure cleared
        ↓
RESOLVED
```

### Example B — High CPU from a system component

```text
User: “My CPU is stuck near 100%.”
        ↓
check_system_performance
        ↓
Sustained high CPU
        ↓
check_top_cpu_processes
        ↓
System / kernel-related consumer
        ↓
Do NOT terminate
        ↓
Collect evidence
        ↓
ESCALATE
```

### Example C — Low disk contributing to general slowness

```text
User: “My computer is extremely slow.”
        ↓
check_system_performance
        ↓
check_disk_space
        ↓
System drive has critically low free space
        ↓
ask_user for approval
        ↓
clean_temporary_files
        ↓
check_disk_space
        ↓
check_system_performance
        ↓
Performance improves
        ↓
RESOLVED
```

### Example D — “Clean Recent Files to fix RAM”

```text
User: “Delete recent files because my RAM is high.”
        ↓
check_system_performance
        ↓
Actual RAM pressure may or may not exist
        ↓
check_top_memory_processes if needed
        ↓
Do not clear Recent history as a RAM fix
        ↓
Use evidence to choose an actual L1 action
```

### Example E — Memory pressure remains after restart

```text
check_system_performance
        ↓
High memory pressure
        ↓
check_top_memory_processes
        ↓
No clear user-space cause
        ↓
restart_computer (with approval)
        ↓
check_system_performance
        ↓
Pressure returns quickly
        ↓
ESCALATE
```

---

## 12. L1 DECISION RULE

The agent must always prefer the **least invasive action supported by evidence**.

```text
MEASURE
  ↓
IDENTIFY
  ↓
ACT ONLY ON VERIFIED CAUSE
  ↓
VERIFY
  ↓
STOP WHEN FIXED
  ↓
ESCALATE WHEN L1 EVIDENCE/TOOLS ARE EXHAUSTED
```

The goal of this KB is not to make CPU or memory numbers look lower by any means necessary. The goal is to identify a real performance problem, safely remediate common L1 causes, and escalate problems that require deeper system, driver, hardware, security, or application investigation.

---

## 13. RESEARCH BASIS

This KB was based primarily on current Microsoft documentation available during preparation:

1. **Troubleshoot performance problems in Windows** — Microsoft Learn. Covers CPU, memory, storage, user/kernel separation, process Working Set, Available Memory, Commit, CPU idle/user/privileged time, and investigation of sustained resource pressure.  
   https://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-performance-problems-in-windows

2. **High CPU usage troubleshooting guidance** — Microsoft Learn. Recommends Task Manager/Resource Monitor to identify high-CPU processes and distinguishes sustained high CPU from temporary spikes.  
   https://learn.microsoft.com/en-us/troubleshoot/windows-server/performance/troubleshoot-high-cpu-usage-guidance

3. **Tips to improve PC performance in Windows** — Microsoft Support. Documents closing unused apps, restarting the PC, disabling unnecessary startup apps, freeing storage, and temporary-file cleanup as supported performance actions.  
   https://support.microsoft.com/en-us/windows/experience/performance-optimization/tips-to-improve-pc-performance-in-windows

4. **Configure Startup applications in Windows** — Microsoft Support. Documents configuring startup apps through Settings and Task Manager and explains startup impact.  
   https://support.microsoft.com/en-gb/windows/experience/startup-boot/configure-startup-applications-in-windows

5. **Introduction to the page file** — Microsoft Learn. Explains the Windows page file and why virtual-memory configuration is workload/system dependent rather than a universal RAM-performance fix.  
   https://learn.microsoft.com/en-us/troubleshoot/windows-client/performance/introduction-to-the-page-file

---

**Core rule:** **VERIFY → IDENTIFY THE RESOURCE CONSUMER → APPLY THE LEAST-INVASIVE JUSTIFIED L1 FIX → VERIFY AGAIN → RESOLVED OR ESCALATE.**
