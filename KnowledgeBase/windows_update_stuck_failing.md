# windows_update_stuck_failing.md — L1 Troubleshooting Knowledge Base: Windows Update Stuck / Failing

**Applies to:** Windows 10 / Windows 11 workstations
**Agent role:** IT Helpdesk L1 automated agent
**Category:** WINDOWS_UPDATE_STUCK_FAILING
**Technical basis:** Verified against Microsoft Learn Windows Update troubleshooting guidance (see References).

---

## 1. SCOPE

This knowledge base covers L1 handling of end-user reports about **Windows Update not progressing or failing**, such as:

- "Windows Update is stuck."
- "Windows Update is not downloading."
- "Windows Update keeps failing."
- "Windows Update is stuck at 0%."
- "Windows Update is stuck at 100%."
- "Windows Update won't install."
- "Windows Update failed."
- "My PC keeps trying to install the same update."

**In scope:**

- Verifying that an actual Windows Update failure or stuck condition exists (objective state, not the user's wording).
- Diagnosing the type of failure with supported diagnostics.
- Restarting Windows Update services (`fix_restart_update_services`) when service evidence justifies it.
- Resetting Windows Update components/cache (`fix_reset_windows_update_components`) when the documented, stricter preconditions are met.
- Re-verifying after every fix, escalating with evidence when L1 scope is exhausted.

**Out of scope (escalate instead):**

- Component store / system file corruption (error `0x80073712` and similar — requires DISM/SFC or in-place repair, which is L2).
- Servicing stack failures where `%windir%\WinSxS\pending.xml` is stuck across reboots (CBS servicing transaction — L2).
- WSUS/SCCM/Intune deployment infrastructure problems.
- Proxy, firewall, or TLS interception issues blocking update endpoints.
- Windows feature upgrades (in-place upgrades) and OS reinstalls.
- Third-party antivirus interference investigation.

---

## 2. MANDATORY LIFECYCLE

```
USER REPORTS WINDOWS UPDATE PROBLEM
        ↓
1. VERIFY THE PROBLEM ACTUALLY EXISTS
        ↓
2. DIAGNOSE THE FAILURE
        ↓
3. SELECT AN APPROPRIATE L1 FIX
        ↓
4. EXECUTE THE FIX
        ↓
5. VERIFY WINDOWS UPDATE AGAIN
        ↓
      ┌────────────────┐
      │                │
    WORKED          STILL FAILING
      │                │
   RESOLVED      MORE L1 ACTION JUSTIFIED?
                     │
                ┌────┴────┐
               YES       NO
                │         │
             FIX+VERIFY  TICKET
               (once)     + REPORT
```

**Forbidden flows (never use):**

```
USER COMPLAINT → IMMEDIATE WINDOWS UPDATE RESET
USER COMPLAINT → RESTART UPDATE SERVICES
FIX COMPLETED → RESOLVED          (never resolve without re-verification)
USER COMPLAINT → TICKET           (unless verified AND no supported L1 remediation remains)
```

---

## 3. AVAILABLE TOOLS

The agent may use **only** these tools. Commands appear only inside tool descriptions as documented mechanics; the canonical identifiers are exactly as listed.

### 3.1 Diagnostics

| Tool | Purpose |
|---|---|
| `check_windows_update_status` | Determine whether Windows Update is actually failing/stuck: service state, current update activity, pending/available updates, download/install progress, error state, repeated-failure pattern, restart-waiting state. |
| `check_windows_update_services` | Determine whether the Windows Update-related services are in a correct state. |
| `check_pending_reboot` | Determine whether Windows is waiting for a restart before updates can progress. |
| `check_windows_update_error` | Determine whether Windows Update has returned a specific error code or failure state, and which one. |

### 3.2 Fixes

| Tool | Purpose |
|---|---|
| `fix_restart_update_services` | Restart Windows Update-related service(s) proven stopped, stuck, or malfunctioning. |
| `fix_reset_windows_update_components` | Full L1 component/cache repair: stop services, rename `SoftwareDistribution` and `catroot2` folders, restart services. More invasive. |

### 3.3 Control actions

| Tool | Purpose |
|---|---|
| `ask_user` | Request information or approval (e.g., approve a service restart, save work before a repair that will interrupt downloads). |
| `escalate` | End L1 handling and create a ticket with gathered evidence. |
| `resolved` | End the session with status RESOLVED and produce the final report. |

---

## 4. PHASE 1 — VERIFY (`check_windows_update_status`)

### 4.1 Principle

The user's statement is a reported symptom. "My Windows Update is broken" does **not** prove Windows Update is failing. Before touching services, cache, registry, or restart state, the agent must establish objective Windows Update state. Do **NOT** immediately restart services, delete the update cache, reset components, reboot, modify the registry, or run repairs.

### 4.2 What the tool checks and gathers

`check_windows_update_status` inspects the Windows Update agent state (via the Windows Update Agent API / update history records) and reports:

| Field | Meaning |
|---|---|
| `wu_service_state` | State of the Windows Update service (`wuauserv`). **Note:** on Windows 10/11, `wuauserv` is Manual (Trigger Start) by default and is legitimately **Stopped** when no update activity is running. A stopped service alone is NOT evidence of failure. |
| `current_activity` | Whether a scan, download, or installation is actively in progress right now. |
| `available_updates` | Count/list of updates pending installation. |
| `installation_state` | Per-update state: not started / downloading (with %) / pending / installing (with %) / failed / awaiting restart. |
| `download_progress` / `install_progress` | Percentage where reported (0%, 100%, etc.). |
| `error_state` | Whether the agent currently reports a failure, and the error code if so. |
| `repeated_failure` | Whether the same update KB has failed multiple times (from update history). |
| `restart_pending` | Whether an installed update is waiting for a reboot to finish. |
| `last_scan_result` | Whether the last scan succeeded, failed, or has never run. |

### 4.3 Result classification

**HEALTHY — no verified problem** (any of):

- No updates pending and last scan succeeded.
- Updates are **actively progressing** (download % or install % advancing between two checks separated by a reasonable observation window — see 4.4).
- An update is **awaiting restart** and nothing else is wrong (see `check_pending_reboot` handling — this is normal, not a failure).
- The last failure in history is old and a later scan/install succeeded.

→ STOP. Do not fix. Return RESOLVED / NOT REPRODUCED (`problem_verified = false`).

**PROBLEM VERIFIED** (any of):

- The same update shows **Failed** in installation state, and update history shows it has failed **more than once**.
- A download or installation percentage (commonly 0% or 99–100%) shows **no progress across an observation window** (see 4.4).
- The agent reports a **current error state** (confirmed by `check_windows_update_error`).
- A scan repeatedly fails or never completes.
- An update is stuck in the **Pending restart** state but `check_pending_reboot` shows **no restart is actually pending** (inconsistent servicing state — evidence of a stuck servicing transaction).

**INCONCLUSIVE:**

- Tool output incomplete, contradictory, or unreadable.
- Progress unknown (no % reported) and no error recorded.

→ Perform the **minimum additional diagnostic** needed (usually a second status observation, `check_windows_update_services`, `check_pending_reboot`, or `check_windows_update_error`). Never guess.

### 4.4 What does NOT count as "stuck"

Do **NOT** classify Windows Update as stuck merely because:

- an update takes time — large cumulative updates legitimately take many minutes
- download speed is slow (corporate bandwidth throttling is common)
- CPU or disk usage changes during installation
- installation takes several minutes
- Windows is waiting for a restart
- an update is pending
- an update is available

**A delayed operation is not a failed operation.** Recommended observation: compare progress between two status checks roughly 5 minutes apart. Zero movement over two checks = evidence of "stuck"; movement (even slow) = healthy.

---

## 5. PHASE 2 — NO PROBLEM FOUND

If `check_windows_update_status` shows Windows Update functioning normally and no actual failure or stuck condition is present:

**STOP.**

- Do not diagnose further.
- Do not restart services.
- Do not reset update components.
- Do not make system changes.
- Do not create a ticket.

Return `resolved` with `problem_verified = false`, diagnosis "Windows Update currently appears healthy", `fix_attempted = null`, `ticket_required = false`. The report must state clearly that the reported failure could not be reproduced.

---

## 6. PHASE 3 — DIAGNOSE THE VERIFIED PROBLEM

Diagnosis begins **only after** verification. Use the diagnostics to distinguish between:

| # | Failure type | Typical evidence |
|---|---|---|
| 1 | Windows Update service not running (when it should be) | service stopped **while an update operation is active or has just failed** — not merely stopped while idle |
| 2 | Windows Update service malfunction | service Running but errors/timeouts returned during scans or installs |
| 3 | Update stuck in pending/download/install state | progress frozen across observation window; no error recorded |
| 4 | Repeated update installation failure | same KB failed 2+ times in history; current error state |
| 5 | Pending restart preventing progress | `check_pending_reboot` positive; update awaiting reboot |
| 6 | Component/cache problem | repeated failures with cache-related error codes (e.g., `0x8024200B` "update handler didn't install, needs re-download"), or service restart did not restore operation |
| 7 | Persistent failure requiring escalation | failures continue after all supported L1 actions; corruption-type error codes |
| 8 | Outside L1 scope | WSUS/SCCM, proxy/TLS, `0x80073712` component-store corruption, stuck CBS transaction |

Do not assume the cause. Do not diagnose "components are corrupted" merely because an update failed once. Do not diagnose "service problem" merely because an update is slow. **The diagnostic evidence must justify the diagnosis.**

### 6.1 `check_windows_update_services`

**Purpose:** verify the state of the services the update procedure depends on.

| Service | Default startup (verified) | Healthy state | Unhealthy state |
|---|---|---|---|
| Windows Update (`wuauserv`) | Manual (Trigger Start) | Stopped while idle; Running during active scan/download/install | Stopped **during active update work**, or fails to start on demand |
| BITS (`bits`) | Manual (Trigger Start) | Stopped while idle; Running during downloads | Disabled, or Stopped during an active download |
| Cryptographic Services (`cryptsvc`) | Automatic | Running | Stopped/Disabled (signature validation breaks → installs fail) |
| Windows Installer (`msiserver`) | Manual | Stopped while idle | Not relevant unless installer-based updates fail |
| Application Identity (`appidsvc`) | Manual | Either (not critical for most updates) | Rarely a blocker |

**Important fields to inspect:** service state (Running/Stopped/Disabled), start type, and whether update activity is currently in progress (stopped-during-activity is the real failure signal).

**Interpretation:**

- All services in the healthy column → service state is NOT the cause; continue diagnosis (do not restart services).
- `wuauserv` or `bits` stopped while an update operation is active, or `cryptsvc` stopped/disabled → **service problem (type 1/2)** → `fix_restart_update_services` is eligible.
- A service **Disabled** at startup type (error `0x80070422` family) → starting it is appropriate; also note the disabled start type in the ticket if it was deliberately set by policy (possible GPO conflict — may need escalation after restart attempt).

**When restarting is appropriate:** only with the evidence above, and only after the problem is verified. **When to escalate instead:** service will not start, immediately stops again after starting, or access denied.

### 6.2 `check_pending_reboot`

**Purpose:** determine whether a required restart is blocking update progress.

A pending restart is **not automatically a failure**. Windows frequently installs updates that finalize at boot. The verified evidence sources (registry markers):

| Marker | Location | Type |
|---|---|---|
| CBS `RebootPending` | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending` | subkey (existence = signal) |
| WU `RebootRequired` | `HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired` | subkey |
| Pending file renames | `HKLM\SYSTEM\CurrentControlSet\Control\Session Manager` → value `PendingFileRenameOperations` | REG_MULTI_SZ value (note: can false-positive from antivirus housekeeping) |
| CBS `PackagesPending` | under `...\Component Based Servicing\PackagesPending` | enumerates the KB numbers awaiting completion |

**Interpretation:**

- **WU `RebootRequired` set, everything else clean** → ordinary, healthy "restart owed." Not a failure. The appropriate action is a restart — **but no restart tool exists in this KB's toolset**, so per the rule "if the available FIX tools do not include a restart operation, do not invent one": instruct the user to restart at their convenience (via `ask_user`/report), then stop. Mark as handled with `problem_verified` reflecting the actual condition and no system modification performed.
- **WU marker set AND an update still shows "installing"** → updates cannot progress while a reboot is owed; same handling: restart is required, no L1 fix applies.
- **CBS `RebootPending` persists across reboots** (or `PackagesPending` names a stuck KB and `%windir%\WinSxS\pending.xml` exists) → stuck servicing transaction → **outside L1 scope → escalate**. Do NOT delete CBS keys or `pending.xml`; that destroys evidence and does not drain the queue.
- **Only `PendingFileRenameOperations` populated** → usually a third-party installer/AV, not Windows Update; restart clears it; not a WU failure.

### 6.3 `check_windows_update_error`

**Purpose:** retrieve the specific error code from the current failure state or update history.

**Interpretation rules:**

- Only use meanings documented in this KB (table below). Do not claim an error code has a meaning unless documented here.
- Record the exact code, the KB it applies to, and the operation phase (download/install).

**Documented error code meanings:**

| Code | Documented meaning | L1 action |
|---|---|---|
| `0x80070422` | A required service is disabled (commonly `wuauserv` or `bits`) | Eligible for `fix_restart_update_services` (start service); if disabled by policy and re-disables → escalate |
| `0x80246008` | BITS interface failure — BITS disabled or malfunctioning | Service restart eligible |
| `0x80070020` | File in use — another process locked an update file | Retry via service restart once; if recurs → escalate (AV interference suspected) |
| `0x8024200B` | Update handler could not install; update must be re-downloaded (corrupt/incomplete cache) | Component reset eligible |
| `0x80070002` / `0x80070003` | Missing/corrupt update files (commonly cache-related) | Service restart first; component reset eligible if it recurs |
| `0x800705B4` | Operation timeout | Service restart once; escalate if recurs |
| `0x8024402C` / `0x80245006` | Cannot resolve/reach the update server — proxy or network path problem | Outside L1 fix tools → escalate (network/proxy team) |
| `0x8024402F` | Service registration / metadata corruption | Component reset eligible |
| `0x80073712` | Component store corruption (a file Windows Update needs is damaged/missing) | **L1 fix cannot repair this → escalate** (requires DISM/SFC/in-place repair) |
| `0x80070643` | Generic installer failure (often SSU-related or third-party blocker) | Service restart once; escalate if recurs |
| `0x80004005` | Unspecified failure | Not diagnostic on its own; continue evidence-based diagnosis; escalate if persistent |

Codes not in this table: record verbatim in the report/ticket, mark interpretation "undocumented — escalate with evidence."

---

## 7. PHASE 4 — L1 FIXES

General rules for all fixes:

1. **Never apply a fix without satisfying its documented preconditions** (Sections 4 and 6 evidence).
2. All fixes change system state → **user approval via `ask_user` is required** (warn the user that in-progress downloads will restart from scratch after a cache reset).
3. Admin (elevated) privileges are required for both fixes.
4. After EVERY fix, re-run verification (Section 9). **A successful command is not proof of a fix.**
5. Never repeat a failed fix. One attempt per fix per session, unless the KB explicitly documents otherwise (it does not).

### 7.1 `fix_restart_update_services`

| Field | Value |
|---|---|
| **Purpose** | Restart the Windows Update-related service(s) when diagnostics prove a service is stopped (while update work is active), disabled, or malfunctioning. |
| **Applicable conditions** | Diagnosis type 1 or 2 from Section 6: `wuauserv`/`bits` stopped during active update work; `cryptsvc` stopped/disabled; service Running but returning errors (`0x80070422`, `0x80246008`, `0x800705B4` family). |
| **Preconditions** | Problem verified (Phase 1) AND service evidence from `check_windows_update_services` (Section 6.1). **Do not restart services merely because the user reported a problem.** |
| **Evidence required** | Service state record; active-operation context; relevant error code if any. |
| **What the fix changes** | Stops (if stuck) and restarts `wuauserv`, `bits`, and `cryptsvc` in correct order (documented mechanics: `net stop`/`net start` on each). No files are deleted or renamed. |
| **Risk level** | Low. In-progress downloads restart from the beginning. |
| **Admin required** | Yes. |
| **User approval** | Required (`ask_user`). |
| **Expected result** | Services return to Running; next scan/download proceeds. |
| **Verification procedure** | Re-run `check_windows_update_status`: confirm services Running, then confirm the original symptom is gone — i.e., the previously failing update **downloads/installs successfully or now progresses** (not merely that the service started). |
| **Failure condition** | Service will not start, stops again immediately, or the update fails again with the same error. |
| **Next step if unsuccessful** | If the error evidence is cache-class (`0x8024200B`, recurring `0x80070002/3`) and the component-reset preconditions are now met → `fix_reset_windows_update_components` (once). Otherwise → escalate. |

### 7.2 `fix_reset_windows_update_components`

**This is the invasive L1 repair. It is the LAST L1 action, never the first.**

| Field | Value |
|---|---|
| **Purpose** | Repair a corrupted Windows Update component/cache state by rebuilding the update download cache and reset folder state. |
| **Applicable conditions** | Diagnosis type 6 (component/cache problem): repeated install failures with cache-class error codes, **after** `fix_restart_update_services` has failed or is ruled out by evidence. |
| **Preconditions (ALL required)** | 1. Problem verified in Phase 1. 2. Failure is repeated (not a single failure). 3. `check_pending_reboot` is **clean** — **never** run this while a restart is owed or a CBS transaction is pending (it cannot fix a stuck `pending.xml` and may worsen servicing state). 4. Evidence points at cache/components (Section 6.3 cache-class codes, or services healthy yet installs keep failing). |
| **Evidence required** | Status record, service record, error code(s), pending-reboot record. |
| **What the fix changes (documented mechanics)** | Stops `wuauserv`, `bits`, `cryptsvc` (and `msiserver` if running); renames `%systemroot%\SoftwareDistribution` → `SoftwareDistribution.old` and `%systemroot%\System32\catroot2` → `catroot2.old` (folders are renamed, not deleted — Windows rebuilds fresh ones; the `.old` copies are the rollback path); restarts the stopped services. |
| **Components affected** | Update download cache (`SoftwareDistribution`), update signature/catalog cache (`catroot2`). Update **history is preserved** (history lives in the DataStore, which is inside SoftwareDistribution — note: history may be reset on next successful operation; this is expected and harmless). |
| **Risk level** | **Medium.** In-progress downloads are discarded and re-downloaded from zero; BITS queue entries are lost; `catroot2` rebuild takes time on first scan. |
| **Admin required** | Yes. |
| **Restart required?** | A restart is **recommended** after the reset (folders/files may be locked by running services; Microsoft guidance restarts services afterward, and a reboot before re-testing is the safest practice). Warn the user in the approval prompt. |
| **User approval** | Required (`ask_user`), with an explicit warning: downloads restart from scratch and a reboot is recommended. |
| **Expected result** | Fresh `SoftwareDistribution` and `catroot2` are created; the next update scan/download/install proceeds cleanly. |
| **Verification procedure** | After the reset (and recommended restart), re-run `check_windows_update_status` and confirm the original failing update now **downloads and installs successfully**. The reset completing is NOT success. |
| **Failure condition** | The same update fails again after the reset, or a corruption-class error (`0x80073712`) appears. |
| **Next step if unsuccessful** | Escalate. L1 remediation is exhausted. |

**When NOT to use this fix:**

- The problem has not been verified (Phase 1).
- Windows Update failed only once.
- A restart is pending (`check_pending_reboot` positive) — restart first (user action), re-verify, and only re-diagnose if problems persist.
- `check_windows_update_services` evidence points purely at a stopped service → use the service restart fix instead.
- A simpler supported L1 action is sufficient.

---

## 8. MULTIPLE L1 ACTIONS

The agent may attempt a second L1 fix **only if all** of the following hold:

1. The first fix failed (post-fix verification unsuccessful).
2. The problem remains verified.
3. **New** diagnostic evidence supports the second fix (re-run the relevant diagnostics).
4. The KB explicitly allows that second fix (the only allowed second action is `fix_reset_windows_update_components` after a failed/insufficient `fix_restart_update_services`).

Strictly forbidden:

- Blindly running every Windows Update repair.
- Repeatedly performing the same repair (one attempt per fix, ever, per session).
- Cycling between service restart and component reset.
- Running `fix_reset_windows_update_components` more than once.

The flow must always move toward resolution or escalation:

```
VERIFY → DIAGNOSE → Fix A (restart services) → VERIFY
   → still broken → re-diagnose → evidence supports it?
        → YES: Fix B (reset components, once) → VERIFY → RESOLVED or TICKET
        → NO:  TICKET
```

---

## 9. MANDATORY FIX → VERIFY

After ANY fix executes:

```
FIX
 ↓
CHECK WINDOWS UPDATE AGAIN (check_windows_update_status, plus
check_windows_update_services / check_windows_update_error as relevant)
 ↓
Is the ORIGINAL problem gone?
 ↓
YES → RESOLVED
NO  → continue ONLY if another documented L1 action is justified
      otherwise → TICKET
```

Verification must test the **original reported failure**:

- Original problem "update installation fails" → verification = the update **installs successfully** (or a re-scan + install cycle succeeds). A successful service restart is NOT enough.
- Original problem "Windows Update is stuck at X%" → verification = the update **actually progresses past X%** or completes.
- Original problem "same update keeps failing" → verification = the update **succeeds**, not merely that the error temporarily disappeared.

**Do NOT declare RESOLVED merely because:**

- a diagnostic completed
- the fix command completed
- the service started
- the update cache was reset
- an error message temporarily disappeared
- Windows restarted
- the machine booted normally

---

## 10. ESCALATION / TICKET CONDITIONS

Raise a ticket (with `escalate`) when **any** of the following is true. The ticket reason must cite gathered evidence.

| Condition | Typical evidence |
|---|---|
| The applicable L1 fix fails | post-fix verification still failing |
| Windows Update remains broken after verification following both supported fixes | full action history attached |
| The same update repeatedly fails after supported remediation | history shows 2+ failures persisting |
| A required repair needs higher privileges | access denied running services/renames elevated |
| The condition is outside L1 scope | `0x80073712` component-store corruption; stuck CBS transaction (`RebootPending` surviving reboots, `pending.xml` present); WSUS/SCCM; proxy/TLS; `0x8024402C/0x80245006` network-path errors |
| The system indicates a deeper Windows/system problem | servicing stack failures, recurring unspecified errors |
| Update deployment requires higher-level administrative intervention | GPO-disabled services, managed-update conflicts |
| Evidence of a broader organizational update problem | same KB failing across many machines (ask the user / known-issue flag) |
| No supported safe L1 action remains | all prerequisites exhausted |

**Do NOT create a ticket simply because:**

- the user reported a problem,
- one diagnostic failed to identify a cause,
- Windows Update is slow,
- an update is pending,
- a restart is owed (user action, not a ticket),
- the model/application made an invalid tool selection.

**An internal agent/application failure is NOT a user support issue.** Application errors are logged internally and never become ticket reasons.

---

## 11. NO FALSE RESOLUTION / NO INFINITE LOOPING

- Never output RESOLVED without successful verification of the original problem (Section 9).
- Do not repeatedly call the same diagnostic without a documented reason.
- Do not repeatedly restart Windows Update services.
- Do not repeatedly reset Windows Update components.
- The normal flow is: **VERIFY → DIAGNOSE → FIX → VERIFY**.
- If verification after the fix fails and no additional documented L1 action is justified → **TICKET**. Do not continue troubleshooting indefinitely.

---

## 12. TEST SCENARIOS

All scenarios are safe and reversible on a dev machine. Cleanup steps are included.

### TEST 1 — Windows Update is healthy
- **Condition:** Machine fully up to date; last scan succeeded; no pending updates.
- **Reproduce:** Nothing — user simply reports "Windows Update is broken."
- **Expected verification:** `check_windows_update_status` → healthy state.
- **Expected diagnostic path:** None.
- **Expected fix:** **None.**
- **Expected post-fix verification:** N/A.
- **Expected final result:** RESOLVED / NOT REPRODUCED; `problem_verified = false`; no fix; no ticket.

### TEST 2 — Windows Update service problem
- **Condition:** `wuauserv` stopped while an update operation should run. Reproduce: set the Windows Update service startup to Disabled temporarily, attempt an update (fails with `0x80070422`).
- **Expected verification:** Problem verified — active failure with service evidence.
- **Expected diagnostic path:** `check_windows_update_services` → service Disabled/stopped during active work.
- **Expected fix:** `fix_restart_update_services` (approval obtained).
- **Expected post-fix verification:** Service Running; update scan/download proceeds.
- **Expected final result:** RESOLVED if the update proceeds. **Cleanup:** restore the original startup type.

### TEST 3 — Update remains stuck after service restart
- **Condition:** After `fix_restart_update_services`, the same update still fails (simulate by repeating the failure condition, e.g., re-disabling the service or using a lab update known to fail).
- **Expected flow:** Verify → diagnose → restart services → verify → still broken → re-diagnose → evidence supports component reset (cache-class code or repeated failure) and `check_pending_reboot` clean → `fix_reset_windows_update_components` → verify → RESOLVED or TICKET.
- **Expected final result:** RESOLVED if the update now installs; TICKET if it fails again. The component reset is run **only** because its documented conditions were met.

### TEST 4 — Component/cache repair succeeds
- **Condition:** Reproducible cache-class failure: fill `C:\Windows\SoftwareDistribution\Download` with a deliberately truncated/corrupt partially-downloaded update file (lab-only simulation) or use a known-corrupt lab download state.
- **Expected verification:** Repeated install failure with `0x8024200B`-class evidence; services healthy; no pending reboot.
- **Expected diagnostic path:** Status → services → pending reboot (clean) → error (`0x8024200B`).
- **Expected fix:** `fix_reset_windows_update_components` (approval, restart warning).
- **Expected post-fix verification:** Fresh folders created; update re-downloads fully and installs.
- **Expected final result:** RESOLVED. **Cleanup:** delete `SoftwareDistribution.old` / `catroot2.old` after confirming stability.

### TEST 5 — Update failure remains after all supported L1 actions
- **Condition:** Persistent failure that survives both fixes (e.g., `0x80073712` component-store corruption simulated by removing a servicing-stack file on a disposable lab VM).
- **Expected flow:** Verify → diagnose → restart services → verify → still failing → evidence supports reset (pending reboot clean) → reset components → verify → still failing.
- **Expected final result:** TICKET with full evidence; `0x80073712` flagged as L2 (DISM/SFC/in-place repair required).
- **Cleanup:** rebuild the lab VM.

### TEST 6 — Pending restart, not an actual failure
- **Condition:** Install any update that requires a restart; leave the machine un-rebooted.
- **Expected verification:** Status shows "Pending restart"; `check_pending_reboot` positive (WU `RebootRequired` set); no error state.
- **Expected behavior:** The agent must NOT classify this as a Windows Update failure and must NOT run any repair. It instructs the user to restart (no restart tool exists — do not invent one) and ends the session as handled-not-a-failure.
- **Expected final result:** RESOLVED (or "no action required" equivalent) with `problem_verified = false` for a "failure," diagnosis noting restart owed; **no fixes, no ticket.**
- **Cleanup:** restart the machine.

### TEST 7 — Reported failure that cannot currently be reproduced
- **Condition:** An update failed yesterday but a later scan/install succeeded; or the failure only occurs at a specific time (maintenance window).
- **Expected flow:** Verify → status healthy / last operation succeeded → STOP.
- **Expected final result:** RESOLVED / NOT REPRODUCED; `problem_verified = false`; no fixes; no ticket. Report notes that the historical failure is recorded but not currently active.

---

## 13. FINAL REPORT

After every session, the application must produce a JSON report clearly distinguishing: whether the problem was verified, what evidence was found, the diagnosis, the fix attempted, fix success, whether the original problem was verified as cleared, and whether a ticket is required.

**Resolved:**

```json
{
  "status": "RESOLVED",
  "problem_verified": true,
  "diagnosis": "Windows Update service stopped during active download; BITS and wuauserv restarted.",
  "fix_attempted": "fix_restart_update_services",
  "fix_successful": true,
  "verification_successful": true,
  "actions_taken": ["check_windows_update_status", "check_windows_update_services",
                    "ask_user", "fix_restart_update_services",
                    "check_windows_update_status", "resolved"],
  "ticket_required": false,
  "reason": "Services restarted; previously failing update downloaded and installed successfully on re-verification."
}
```

**Could not be reproduced:**

```json
{
  "status": "RESOLVED",
  "problem_verified": false,
  "diagnosis": "No current Windows Update failure was detected.",
  "fix_attempted": null,
  "fix_successful": false,
  "verification_successful": true,
  "actions_taken": ["check_windows_update_status", "resolved"],
  "ticket_required": false,
  "reason": "The reported condition could not be reproduced. Windows Update is operating normally."
}
```

**Unresolved (ticket required):**

```json
{
  "status": "TICKET_REQUIRED",
  "problem_verified": true,
  "diagnosis": "Repeated installation failure of KB5034441 with error 0x80073712; component-store corruption suspected. L1 service restart and component reset attempted without success.",
  "fix_attempted": "fix_reset_windows_update_components",
  "fix_successful": false,
  "verification_successful": false,
  "actions_taken": ["check_windows_update_status", "check_windows_update_services",
                    "check_pending_reboot", "check_windows_update_error",
                    "ask_user", "fix_restart_update_services", "check_windows_update_status",
                    "ask_user", "fix_reset_windows_update_components", "check_windows_update_status", "escalate"],
  "ticket_required": true,
  "ticket_reason": "Update KB5034441 still fails with 0x80073712 after both supported L1 fixes. Error indicates component store corruption requiring DISM/SFC or in-place repair (L2)."
}
```

---

## 14. SAFETY REQUIREMENTS

1. **Verify the problem before modifying the system** — no fix before Phase 1 completes.
2. **Evidence-based diagnosis** — every diagnosis cites diagnostic output; never guess from the complaint.
3. **Least invasive repair first** — service restart before component reset, always.
4. **Never perform unrelated system modifications** — no registry edits, no deleting CBS keys or `pending.xml`, no `netsh winsock reset` as part of this KB (that belongs to the connectivity KB's scope, not here).
5. **Never run the component reset while a restart is owed** — check `check_pending_reboot` first, every time.
6. **Never claim success without post-fix verification** of the original symptom.
7. **Do not repeatedly perform the same repair** — one attempt per fix.
8. **Do not bypass higher-level escalation requirements** — corruption-class errors go to L2 with evidence, not to repeated L1 attempts.
9. **Do not invent diagnostics or fixes** — use only the tools in Section 3; if a needed action has no tool (e.g., reboot), instruct the user, do not improvise a tool.
10. **Do not treat internal agent errors as user problems** — application failures are logged internally and never become ticket reasons.
11. **Preserve diagnostic information** — status records, service states, error codes, and action history must be retained for the report and any ticket.

---

## 15. COMMON MISTAKES THE AGENT MUST AVOID

| Mistake | Why it's wrong | Correct behavior |
|---|---|---|
| Resetting components on first complaint | Problem not verified; invasive fix applied blindly | Phase 1 verification first |
| Treating a stopped `wuauserv` as broken | It is Manual (Trigger Start) and normally stopped while idle | Only stopped-during-active-work is evidence |
| Calling an update "stuck at 0%" after seconds | Downloads can be slow; % may lag before metadata is processed | Observe progress across two checks ~5 min apart |
| Treating "Pending restart" as a failure | Normal post-install state | `check_pending_reboot` → user restart, no repair |
| Flushing/re-setting to fix `0x80073712` | Component-store corruption is beyond cache reset | Escalate with the code |
| Declaring RESOLVED after the reset command completed | Cache rebuilt ≠ update installed | Verify the update actually installs |
| Restarting services repeatedly | No new evidence, no new outcome | One attempt; escalate if it fails |
| Running both fixes back-to-back without re-diagnosis | Fix B needs its own evidence | Re-verify, re-diagnose, then Fix B if justified |
| Resetting components while a reboot is owed | Cannot drain a pending servicing transaction; may worsen state | Pending reboot → user restart first |
| Deleting CBS keys or `pending.xml` | Destroys evidence, doesn't fix the stuck queue | Escalate to L2 |
| Ticket because the tool errored | Internal failure is not user evidence | Log internally; continue or restart the flow |

---

## 16. REFERENCES (VERIFIED TECHNICAL BASIS)

- Microsoft Learn — *Fix Windows Update issues* guided walkthrough (common error codes, reset order): https://learn.microsoft.com/en-us/windows/troubleshoot/windows-update/windows-update-troubleshooting
- Microsoft Learn — *Additional resources for Windows Update* (manual component reset steps, folder renames, service list): https://learn.microsoft.com/en-us/troubleshoot/windows-client/installing-updates-features-roles/additional-resources-for-windows-update
- Microsoft Q&A — Reset Windows Update components (service stop/rename/start script): https://learn.microsoft.com/en-us/answers/questions/2338408/article-reset-windows-update-components
- Pending reboot registry markers (CBS `RebootPending`, WU `Auto Update\RebootRequired`, `PendingFileRenameOperations`): Microsoft Q&A and community-verified references; key-vs-value distinction per Microsoft.Windows/RebootPending documentation.
- Service default startup types (`wuauserv` Manual trigger-start, BITS Manual, `cryptsvc` Automatic): Microsoft Q&A and Automox worklet documentation.
- Error code meanings: Microsoft guided walkthrough common-code list; Automox common Windows Update error codes reference.
