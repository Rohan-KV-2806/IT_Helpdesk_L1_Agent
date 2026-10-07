# application_not_responding.md — L1 Troubleshooting Knowledge Base: Application Not Responding / Frozen Application

**Applies to:** Windows 10 / Windows 11 workstations
**Agent role:** IT Helpdesk L1 automated agent
**Category:** APPLICATION_NOT_RESPONDING

---

## 1. SCOPE

This knowledge base covers L1 handling of end-user reports of a **frozen / not-responding Windows application**, where the user reports symptoms such as:

- "My application is frozen."
- "The app says Not Responding."
- "My program is stuck."
- "This application has stopped responding."
- "The application is hanging."

**In scope:**

- Verifying that an application is actually in a Windows "Not Responding" state.
- Identifying the affected application from diagnostic evidence.
- Closing the verified unresponsive application (the single supported L1 fix).
- Re-verifying after the fix.
- Escalating with evidence when L1 remediation fails.

**Out of scope (escalate instead):**

- Application crashes with error dialogs, blue screens, or error codes (use the crash KB).
- Slow performance without a Not Responding state (no evidence of a freeze).
- Application installation, update, or configuration problems.
- Recurring freezing of the same application across sessions (underlying software defect — L2/vendor).
- System-wide freezes where the whole OS is unresponsive (use the OS freeze KB).
- Terminating system-critical Windows processes (never an L1 action).

---

## 2. MANDATORY WORKFLOW

Every session MUST follow this exact sequence:

```
USER REPORT
    ↓
CHECK ACTUAL WINDOWS STATE (check_not_responding_apps)
    ↓
IS ANY APPLICATION "NOT RESPONDING"?
    ↓
 ┌───────────────┐
 │               │
NO              YES
 │               │
RESOLVED      IDENTIFY APP
(problem_       ↓
verified=   CONFIRM WITH USER IF NEEDED (ask_user)
false)          ↓
          CLOSE UNRESPONSIVE APP (close_unresponsive_app)
                 ↓
             CHECK AGAIN (check_not_responding_apps)
                 ↓
         ┌───────┴───────┐
         │               │
      CLEARED          NOT CLEARED
         │               │
      RESOLVED          TICKET (escalate)
```

**Forbidden flows (never use):**

```
USER REPORT → IMMEDIATELY CLOSE APP
USER REPORT → ASSUME APP IS FROZEN
CLOSE APP → ASSUME SUCCESS → RESOLVED
VERIFY → FIX → VERIFY → FIX → VERIFY → ... (looping)
```

The condition must **always** be verified — before the fix and after the fix.

---

## 3. AVAILABLE TOOLS

The agent may use **only** these tools. Internal mechanics are documented for reference; the canonical tool identifiers are exactly as listed.

### 3.1 Diagnostic

| Tool | Purpose |
|---|---|
| `check_not_responding_apps` | Determine whether any currently running Windows application is in a "Not Responding" state, and identify which one(s). |

### 3.2 Fix

| Tool | Purpose |
|---|---|
| `close_unresponsive_app` | Close a verified unresponsive application. |

### 3.3 Control actions

| Tool | Purpose |
|---|---|
| `ask_user` | Request confirmation from the user (e.g., confirm which application is affected, approve closing it). |
| `escalate` | End L1 handling and create a ticket with gathered evidence. |
| `resolved` | End the session with status RESOLVED and produce the final report. |

---

## 4. PHASE 1 — VERIFY (`check_not_responding_apps`)

### 4.1 Purpose and principle

The user's statement that an application is frozen is a **symptom, not proof**. The first action of every session is to determine whether there is **actually** a currently running Windows application in a "Not Responding" state. Do **not** terminate anything merely because the user says an app is frozen. Do **not** assume which application is affected. Do **not** assume it is still frozen.

### 4.2 What the tool checks

`check_not_responding_apps` inspects the responsiveness state of the windows belonging to running user applications. Internally, this corresponds to how Windows itself marks a task: a window whose owning thread has stopped processing the Windows message queue (pumping messages) is flagged **(Not Responding)** in Task Manager and in the taskbar. The tool reports applications whose main window thread is in this state.

### 4.3 What does NOT count as "Not Responding"

An application must **not** be treated as unresponsive merely because:

- it is using CPU
- it is using a large amount of memory
- it has been running for a long time
- it takes several seconds to perform an operation
- the user says it "feels slow"
- the application is minimized
- the application is busy with a legitimate long task (e.g., compiling, rendering, large file copy)

**Only an actual Windows "Not Responding" state satisfies the verification condition.**

### 4.4 Result interpretation

| Result | Meaning | Next action |
|---|---|---|
| **No applications** marked Not Responding | The reported condition **cannot currently be reproduced** | Go to Phase 2 — stop, no fix, resolved |
| **Exactly one application** marked Not Responding | Problem verified; single affected application identified | Go to Phase 3 |
| **Multiple applications** marked Not Responding | Problem verified; possible system-wide condition | Go to Phase 3, then Section 4.5 |

### 4.5 Captured information

For every application reported Not Responding, the diagnostic captures, where available:

| Field | Description |
|---|---|
| `process_name` | Application/process name (e.g., `outlook.exe`, `app.exe`) |
| `window_title` | Title of the unresponsive window, for user confirmation |
| `process_id` | PID of the unresponsive process |
| `responsiveness_state` | Confirmed value: `Not Responding` |

This information is recorded as diagnostic evidence and used to identify the affected application.

### 4.6 Multiple unresponsive applications

If **two or more** applications are simultaneously Not Responding:

1. Do **not** terminate every process blindly.
2. Present the list to the user with `ask_user` and confirm which application(s) they were working with.
3. Close confirmed unresponsive applications **one at a time**, re-verifying after each close.
4. If the count is high (e.g., most applications on the machine are frozen) or the whole desktop is unresponsive, this suggests a **wider system problem** (memory exhaustion, OS-level hang) rather than an isolated application problem. Document the evidence and escalate — do not mass-terminate processes.

---

## 5. PHASE 2 — NO PROBLEM FOUND

If `check_not_responding_apps` returns **no** applications currently marked Not Responding:

**STOP.**

- Do not attempt to close anything.
- Do not run additional unnecessary diagnostics.
- Do not create a ticket.
- Use `resolved` with a report stating that the reported condition could not be reproduced at the time of troubleshooting:
  - `problem_verified = false`
  - `affected_application = null`
  - `fix_attempted = null`
  - `ticket_required = false`
  - `diagnosis`: "No application was detected in a Not Responding state."

The user may be informed that no currently unresponsive application was detected, and that if the problem recurs they should report it while the application is still frozen.

---

## 6. PHASE 3 — PROBLEM CONFIRMED

If the diagnostic identifies one or more applications that are actually Not Responding:

1. **Record the evidence:** affected application name, window title, process ID, responsiveness state.
2. **Select the affected application** — the one actually reported Not Responding. When the user's report names an application, match it against the diagnostic list. When the report is ambiguous and several applications are listed, use `ask_user` to confirm which window the user means (read the window titles back).
3. **Never terminate unrelated applications.** Only the confirmed unresponsive application may be closed.

---

## 7. PHASE 4 — L1 FIX (`close_unresponsive_app`)

### 7.1 Fix specification

| Field | Value |
|---|---|
| **Purpose** | Close the verified unresponsive application. This is the primary (and only) L1 remediation for this KB. |
| **Preconditions** | `check_not_responding_apps` has **positively identified** the specific application as Not Responding (Phase 3 complete). The target process is a **user application**, not a system-critical Windows process. |
| **Required evidence** | Captured record from Phase 3: process name, window title, PID, `Not Responding` state. |
| **What may be closed** | Only the application identified by the diagnostic. Never close an application merely because the user mentioned it. Never close applications not flagged Not Responding. Never close unrelated applications. Never terminate system-critical Windows processes (e.g., `csrss.exe`, `wininit.exe`, `services.exe`, `lsass.exe`, `svchost.exe` system instances, `dwm.exe`, `explorer.exe` unless explicitly identified as a safe target by the tool definition) — if the "unresponsive" process is a system process, stop and escalate. |
| **Expected behavior** | The application is asked to close gracefully first; if it does not respond to the graceful close within the tool's timeout, the process is force-terminated. |
| **Risk level** | **Medium — user data loss possible.** Unsaved work in the frozen application will be lost. This must be communicated before closing. |
| **User approval** | **Required (`ask_user`).** The approval message must warn the user that unsaved work in the application will be lost. |
| **If graceful closing fails** | The tool escalates internally to force termination of the same process. |
| **If the application cannot be terminated** | Access denied, process protected, or termination fails → do not retry in a loop. Go to Phase 5 (verification) and then escalate with the evidence. |

### 7.2 Hard prohibitions

- Never run this fix simply because the user mentioned an application.
- Never close an application that the diagnostic has not identified as unresponsive.
- Never close multiple applications at once.
- Never attempt the close twice on the same application in one session. One attempt per verified instance.

---

## 8. PHASE 5 — VERIFY THE FIX (MANDATORY)

After `close_unresponsive_app` executes (regardless of its own return status), the agent MUST re-run `check_not_responding_apps`.

**Do NOT assume the fix worked because the close operation returned success.**

The verification must determine whether the previously identified unresponsive application (by process identity) is no longer running in a Not Responding state.

### 8.1 Outcome: SUCCESS

- The affected application is no longer present in the Not Responding list (it was closed).
- Use `resolved` with status **RESOLVED**. The report states that the unresponsive application was identified and successfully closed.

### 8.2 Outcome: FAILURE

Any of the following:

- The application remains Not Responding after the close attempt.
- The application could not be closed (access denied / termination failed).
- The close succeeded but the verification is inconclusive.

Do **not** claim resolution. Proceed to escalation (Section 9). Do not retry the close, and do not loop back to re-diagnosis without new evidence.

---

## 9. IMPORTANT DISTINCTION — WHAT "RESOLVED" MEANS HERE

For this KB, resolution means:

> **"The reported frozen/unresponsive application condition has been cleared by closing the affected application."**

Do **NOT** claim that the underlying software defect has been repaired.

| Correct | Incorrect |
|---|---|
| "The unresponsive application was closed and the unresponsive condition was cleared." | "The application has been permanently fixed." |
| "The application was successfully closed and verified as no longer running." | "The application will no longer freeze." |

If the same application freezes repeatedly, that is evidence of an underlying defect and belongs in the escalation/ticket reasoning (see Section 10).

---

## 10. ESCALATION / TICKET CONDITIONS

Raise a ticket (with `escalate`) when **any** of the following is true. The ticket reason must reference actual gathered evidence.

| Condition | Typical evidence |
|---|---|
| The application remains unresponsive after the L1 fix | post-fix `check_not_responding_apps` still shows the app Not Responding |
| The application cannot be closed | close returned failure / access denied |
| The close operation fails | termination error recorded |
| The application immediately becomes unresponsive again during verification | same PID or relaunched instance back in Not Responding state — indicates a deeper software defect |
| A safe L1 action cannot be completed | tool failure, permissions, protected process |
| The application appears to have a deeper software/system issue | recurring freezes, multiple apps frozen, system-wide unresponsiveness |
| The affected process cannot be safely terminated | system-critical process flagged Not Responding |
| The problem is outside documented L1 scope | crash dialogs, OS freeze, install/update issues |

**Do NOT raise a ticket:**

- Simply because the user initially reported a frozen application — verify first.
- When `check_not_responding_apps` shows no unresponsive application and no further issue is supported by evidence.

**Recurring freeze escalation note:** if the user reports this is the Nth occurrence of the same application freezing, include that history in the ticket reason (e.g., "third occurrence this week; underlying application defect suspected; recommend L2/vendor investigation").

---

## 11. NO INFINITE LOOPING

- Do not repeatedly run `check_not_responding_apps` without reason.
- Do not repeatedly attempt `close_unresponsive_app` on the same application — **one attempt maximum per session**.
- The expected flow is strictly: **VERIFY → FIX → VERIFY**.
- If verification after the fix fails, stop repeated L1 attempts and raise a ticket. This KB documents no other safe L1 action after a failed close.

---

## 12. TEST SCENARIOS (REPRODUCIBLE ON A DEV MACHINE)

All scenarios are safe and reversible.

### TEST 1 — No frozen applications
- **Condition:** The Windows machine has no applications currently marked Not Responding.
- **Expected flow:** `check_not_responding_apps` → no problem found → `resolved`.
- **Expected result:** `problem_verified = false`, no fix attempted, no ticket. No process is terminated, no extra diagnostics run.

### TEST 2 — One frozen application
- **Condition:** Create a safe unresponsive application. Options: (a) run a small test program with a UI thread that sleeps/blocks (a simple loop in a button handler); (b) use an already-running harmless app and suspend its main thread briefly via Resource Monitor/Process Explorer (resume it afterward as cleanup if the close fails).
- **Expected flow:** `check_not_responding_apps` → app detected (name/title/PID recorded) → `ask_user` approval → `close_unresponsive_app` → `check_not_responding_apps` again → app no longer unresponsive → `resolved`.
- **Expected result:** RESOLVED, `problem_verified = true`, `fix_successful = true`.

### TEST 3 — Close operation fails
- **Condition:** Simulate a close failure — e.g., run the test app under a different, non-terminable context, or mock the tool to return a termination failure. (On a dev machine, a protected/elevated process owned by SYSTEM serves as a realistic close-failure target.)
- **Expected flow:** `check_not_responding_apps` → app detected → approval → `close_unresponsive_app` → close fails → verification still shows unresponsive → `escalate`.
- **Expected result:** TICKET_REQUIRED with the close-failure evidence. No retry loop.

### TEST 4 — Application remains problematic after close
- **Condition:** The close action reports failure, or the application immediately re-enters the Not Responding state (e.g., a test app that blocks its UI thread again on restart).
- **Expected flow:** `check_not_responding_apps` → app detected → approval → `close_unresponsive_app` → `check_not_responding_apps` → still Not Responding → `escalate`.
- **Expected result:** TICKET_REQUIRED; reason: "application remained unresponsive after L1 remediation."

### TEST 5 — Multiple applications frozen
- **Condition:** Start two or more test apps and block all their UI threads simultaneously.
- **Expected flow:** `check_not_responding_apps` → multiple apps listed → `ask_user` to confirm which app(s) the user means → close confirmed app(s) **one at a time** with re-verification after each → resolved per app.
- **System-problem variant:** if essentially every application is frozen / the desktop is unresponsive, document the evidence and escalate as a suspected system-wide condition — do not mass-terminate.

---

## 13. FINAL REPORT REQUIREMENTS

After every session, the application must produce a JSON report clearly communicating: whether the problem was verified, which application was affected, what evidence was found, what fix was attempted, whether it succeeded, whether the result was verified, and whether a ticket is required.

**Successfully cleared:**

```json
{
  "status": "RESOLVED",
  "problem_verified": true,
  "affected_application": "notepad_test.exe",
  "affected_window_title": "Untitled - Test App",
  "affected_process_id": 4212,
  "diagnosis": "Application was confirmed to be Not Responding.",
  "fix_attempted": "close_unresponsive_app",
  "fix_successful": true,
  "verification_successful": true,
  "actions_taken": ["check_not_responding_apps", "ask_user",
                    "close_unresponsive_app", "check_not_responding_apps", "resolved"],
  "ticket_required": false,
  "reason": "Unresponsive application was identified, approved by user, closed, and re-verified as no longer running."
}
```

**Could not be reproduced:**

```json
{
  "status": "RESOLVED",
  "problem_verified": false,
  "affected_application": null,
  "diagnosis": "No application was detected in a Not Responding state.",
  "fix_attempted": null,
  "fix_successful": false,
  "verification_successful": true,
  "actions_taken": ["check_not_responding_apps", "resolved"],
  "ticket_required": false,
  "reason": "Reported frozen application could not be reproduced at the time of troubleshooting; no unresponsive application detected."
}
```

**Unresolved (ticket required):**

```json
{
  "status": "TICKET_REQUIRED",
  "problem_verified": true,
  "affected_application": "outlook.exe",
  "affected_window_title": "Inbox - Outlook",
  "affected_process_id": 5104,
  "diagnosis": "Application was confirmed to be Not Responding.",
  "fix_attempted": "close_unresponsive_app",
  "fix_successful": false,
  "verification_successful": false,
  "actions_taken": ["check_not_responding_apps", "ask_user",
                    "close_unresponsive_app", "check_not_responding_apps", "escalate"],
  "ticket_required": true,
  "ticket_reason": "The application remained unresponsive after the L1 remediation (close failed / still Not Responding on re-check)."
}
```

---

## 14. SAFETY REQUIREMENTS

1. **Verify before acting** — no termination without a confirmed Not Responding state.
2. **Only close a confirmed unresponsive application** — identified by the diagnostic, not by assumption.
3. **Never terminate unrelated processes.**
4. **Avoid system-critical processes** — if a system process is the unresponsive one, escalate instead of closing.
5. **Warn about data loss** — unsaved work will be lost; approval is mandatory.
6. **Do not claim an underlying application defect is fixed** — resolution means the frozen condition was cleared by closing the app.
7. **Verify after the L1 action** — re-run the diagnostic; never assume success from the close result.
8. **Do not loop indefinitely** — one close attempt maximum; verify once; then escalate.
9. **Raise a ticket when the supported L1 remediation fails** — with evidence, never fabricated.

---

## 15. COMMON MISTAKES THE AGENT MUST AVOID

| Mistake | Why it's wrong | Correct behavior |
|---|---|---|
| Closing an app because the user said it's frozen | The freeze may have resolved already, or the wrong app may be named | Run `check_not_responding_apps` first |
| Treating high CPU/memory as "Not Responding" | A busy app is not a frozen app | Only the Windows Not Responding state counts |
| Closing all suspicious processes | Unrelated work is destroyed | Close only the diagnostic-confirmed app |
| Closing several apps at once | Same risk, plus harder to verify | One app at a time, verify between |
| Assuming success from the close result | The close can return success while the process survives | Always re-run `check_not_responding_apps` |
| Retrying the close repeatedly | Looping; no new evidence | One attempt, then escalate |
| Claiming the app is "permanently fixed" | The underlying defect is untouched | Report: "unresponsive condition cleared by closing the application" |
| Ticket on a bare complaint | No verified problem | Not reproducible → resolved, `problem_verified: false` |
| Killing system-critical processes | Can destabilize/crash Windows | Escalate instead |
| Mass-terminating when many apps are frozen | Signals a system problem, not app problems | Escalate with evidence |
