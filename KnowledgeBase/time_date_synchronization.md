# time_date_synchronization.md — L1 Troubleshooting Knowledge Base: Time / Date Synchronization Problem

**Applies to:** Windows 10 / Windows 11 workstations
**Agent role:** IT Helpdesk L1 automated agent
**Category:** TIME_DATE_SYNCHRONIZATION
**Technical basis:** Verified against Microsoft Learn Windows Time (w32time) documentation (see References).

---

## 1. SCOPE

This knowledge base covers L1 handling of end-user reports about **incorrect or unsynchronized workstation time/date**, such as:

- "My computer time is wrong."
- "My system clock is incorrect."
- "Windows time is not syncing."
- "The date on my PC is wrong."
- "My clock keeps drifting."
- "My PC time is several minutes behind."
- "Windows says the time cannot be synchronized."
- "My computer has the wrong date/time."

**In scope:**

- Verifying whether the system clock/date is actually incorrect (objective evidence, not the user's wording).
- Distinguishing the three related-but-different conditions: **system clock time**, **time synchronization**, **time zone**.
- Diagnosing Windows Time service state, synchronization state, and time-source validity.
- Forcing a synchronization attempt (`fix_sync_time`) and restarting the Windows Time service (`fix_restart_time_service`) when evidence justifies them.
- Re-verifying after every fix; escalating with evidence when L1 scope is exhausted.

**Out of scope (escalate instead):**

- Domain time hierarchy problems (domain controllers, PDC emulator, GPO-enforced time policy).
- Changing an organization's configured time source (policy decision, never arbitrary).
- CMOS/RTC hardware failure or a dead CMOS battery (clock resets to a past date on every boot).
- Hypervisor/VM host time-sync interference.
- Firewall/proxy infrastructure blocking NTP (UDP 123) network-wide.
- Setting time manually with large corrections (see the "time change too big" condition in Section 6.3 — the available L1 fix tools cannot perform it).

---

## 2. THE THREE-WAY DISTINCTION (CRITICAL)

**System clock time**, **time synchronization**, and **time zone** are related but are NOT the same problem:

| Condition | What it means | How it looks |
|---|---|---|
| **System clock time wrong** | The hardware/OS clock itself is set to the wrong moment | Time wrong by minutes/hours/days regardless of zone |
| **Synchronization failing** | Windows cannot correct the clock against its configured source | `w32tm /query /source` shows `Local CMOS Clock`; sync errors recorded |
| **Time zone wrong** | The underlying UTC/system time is CORRECT; only the displayed local time is shifted | Clock off by exactly a whole number of hours (e.g., UTC shown instead of UTC+5:30); date may appear off by one near midnight |

**Rules that follow:**

- A wrong **displayed local time** does NOT automatically prove synchronization is broken — check the time zone first.
- A failed synchronization command does NOT automatically prove the Windows Time **service** is broken — check service state separately.
- A **running** Windows Time service does NOT automatically prove the clock is synchronized — check status/source.
- Do not change time zone settings merely because synchronization failed.
- Do not restart the time service merely because the user reported a wrong clock.

---

## 3. MANDATORY LIFECYCLE

```
USER REPORT
    ↓
VERIFY ACTUAL TIME/DATE PROBLEM (check_time_status)
    ↓
┌──────────────────────────┐
│ Is the problem real?     │
└──────────────────────────┘
       │             │
      NO            YES
       │             │
RESOLVED          DIAGNOSE
NOT REPRODUCED       ↓
(check_time_service, check_time_source)
                 FIND CAUSE
                     ↓
               L1 FIX AVAILABLE?
                  │         │
                 NO        YES
                  │         │
                TICKET   APPLY FIX
                (escalate)   ↓
                       VERIFY AGAIN
                             ↓
                    ┌────────┴────────┐
                    │                 │
                  WORKED           FAILED
                    │                 │
                 RESOLVED       MORE L1 ACTION?
                                     │
                                ┌────┴────┐
                               YES       NO
                                │         │
                             FIX+VERIFY  TICKET
                               (once)

```

**Forbidden flows (never use):**

```
USER COMPLAINT → IMMEDIATE TIME SYNC
USER COMPLAINT → RESTART WINDOWS TIME SERVICE
USER COMPLAINT → CHANGE TIMEZONE
FIX COMPLETED → RESOLVED          (never resolve without re-verification)
```

The correct lifecycle is always: **VERIFY → DIAGNOSE → FIX → VERIFY AGAIN → RESOLVE OR TICKET.**

---

## 4. AVAILABLE TOOLS

The agent may use **only** these tools. Commands appear only inside tool descriptions as documented mechanics; the canonical identifiers are exactly as listed.

### 4.1 Diagnostics

| Tool | Purpose |
|---|---|
| `check_time_status` | Determine whether the workstation's current date/time is actually incorrect and whether Windows reports a synchronization problem. |
| `check_time_service` | Determine whether the Windows Time service (`w32time`) is running and behaving normally. |
| `check_time_source` | Determine what time source Windows is configured to use and whether that source appears available/usable. |

### 4.2 Fixes

| Tool | Purpose |
|---|---|
| `fix_sync_time` | Force a Windows time synchronization attempt when evidence proves sync is failing or the clock is incorrect. |
| `fix_restart_time_service` | Restart the Windows Time service when diagnostics show it stopped, stuck, or malfunctioning. |

### 4.3 Control actions

| Tool | Purpose |
|---|---|
| `ask_user` | Request information or approval (confirm the reported symptom, confirm the user's expected time zone, approve a fix). |
| `escalate` | End L1 handling and create a ticket with gathered evidence. |
| `resolved` | End the session with status RESOLVED and produce the final report. |

**Toolset gap (documented, not worked around):** the available fix list contains **no time-zone-changing tool and no manual clock-setting tool**. The KB never invents one. Time-zone handling follows Section 9.

---

## 5. PHASE 1 — VERIFY (`check_time_status`)

### 5.1 Principle

The user's statement is a reported symptom. "My computer time is wrong" does **not** prove the clock is currently incorrect. Before forcing sync, restarting the service, changing clock/timezone, or modifying configuration, the agent must establish objective state. Do **NOT** immediately synchronize, restart `w32time`, change the clock, or change the time zone.

### 5.2 What the tool gathers

| Field | Meaning |
|---|---|
| `current_local_date` / `current_local_time` | The workstation's current local date/time. |
| `timezone` | Configured Windows time zone (e.g., `UTC`, `India Standard Time`). |
| `sync_state` | Windows-reported synchronization state (synchronized / not synchronized / never synced). |
| `last_successful_sync` | Timestamp of the last successful synchronization, where available. |
| `time_source` | Current source as reported by Windows (verified signature: a healthy source is a real NTP server name or domain source; `Local CMOS Clock` = fallback, see Section 6.3). |
| `sync_error_state` | Any recorded synchronization failure ("no time data available", "time change too big", etc.). |

### 5.3 Trusted reference comparison

Where possible, compare the workstation's time against a **trustworthy reference** before declaring a problem:

- **Preferred:** query the configured/configurable NTP source directly and measure the offset (documented mechanics: `w32tm /stripchart /computer:<source> /samples:3 /dataonly` returns the offset in seconds).
- **Acceptable secondary:** a trusted network time endpoint retrievable over the existing connectivity (HTTPS time API), used only when NTP querying is unavailable.
- **Not acceptable:** the user's own statement; another application on the same machine; a wall clock read by the user.

**Tolerance rules — what counts as a real discrepancy:**

| Finding | Interpretation |
|---|---|
| Offset ≤ 2 seconds from reference | **Normal.** Network latency and normal clock discipline make sub-second-to-2-second differences routine. NEVER treated as a failure. |
| Offset 2–60 seconds with healthy sync state | Notable but not an L1 failure; note it, re-check after a normal sync cycle; user-visible only in rare cases. |
| Offset > 60 seconds | **Meaningful discrepancy → problem candidate.** Proceed with full verification. |
| Date wrong (wrong day/month/year) by any amount | **Always a problem candidate** — even "one day off" (typical of UTC-vs-local-zone display near midnight, or CMOS battery failure). Check time zone interpretation first (Section 2). |
| Sync state = not synchronized AND source = `Local CMOS Clock` | **Problem candidate** regardless of offset (the machine is running on its hardware clock with no discipline). |

### 5.4 Result classification

**HEALTHY — no verified problem (ALL of):**
- Date correct and time within tolerance (≤ 2 s from reference, or 2–60 s with healthy sync and a recent successful sync).
- Configured time zone is appropriate for the user's location (confirm with `ask_user` if the zone looks implausible).
- Sync state = synchronized, source = real NTP/domain source, `last_successful_sync` recent.
- No recorded synchronization failure.

→ STOP. Do not fix. Return `resolved`, `problem_verified = false`.

**PROBLEM VERIFIED (ANY of):**
- Time discrepancy > 60 seconds from reference.
- Date incorrect (after ruling out pure time-zone display shift — see 5.5).
- Sync state = not synchronized with `Local CMOS Clock` fallback or a recorded sync error.
- Time zone demonstrably wrong for the user's location (confirmed with the user), even if the underlying clock is fine — this IS a verified problem, but of type "timezone", not "sync" (Section 9).

**INCONCLUSIVE:**
- Reference comparison unavailable (no reachable source, no secondary reference) AND Windows reports no sync state.
- Tool output incomplete/unreadable.

→ Perform the minimum additional diagnostic (`check_time_service`, `check_time_source`) to establish state. Never guess from the complaint alone.

### 5.5 The time-zone trap in verification

Before declaring the clock "wrong", apply this check:

1. If the displayed local time is off by a **whole number of hours** (or the date flips near midnight), suspect time zone first.
2. If the machine's UTC-equivalent time (displayed time ± zone offset) matches the reference, **the system clock is correct** — the problem is time-zone configuration (Section 9), not synchronization.
3. Only when the underlying time itself is wrong proceed to synchronization diagnosis.

---

## 6. PHASE 2 — NO PROBLEM FOUND

If `check_time_status` shows the system time correct within tolerance, the date correct, the time zone appropriate, and synchronization functioning with no recorded failure:

**STOP.**

- Do not perform further fixes.
- Do not force synchronization.
- Do not restart the time service.
- Do not modify any time setting.
- Do not create a ticket.

Return `resolved` with `problem_verified = false`, diagnosis "System time and synchronization are currently healthy", `fix_attempted = null`, `ticket_required = false`. The report must state clearly that the reported condition could not be reproduced.

---

## 7. PHASE 3 — DIAGNOSE

Diagnosis begins **only after** verification. The agent must distinguish between:

| # | Condition | Typical evidence |
|---|---|---|
| 1 | Incorrect system clock | offset > 60 s from reference; underlying (UTC) time wrong |
| 2 | Incorrect system date | wrong day/month/year not explained by zone display |
| 3 | Incorrect time zone | UTC-equivalent time correct; local display shifted by whole hours |
| 4 | Windows Time service not running (when needed) | service Stopped/Disabled **at a moment sync is required** — see 7.1 caveat |
| 5 | Windows Time service malfunction | service Running but errors recorded; will not stay running |
| 6 | Synchronization failure | sync errors ("no time data available"); source = `Local CMOS Clock` |
| 7 | Invalid/unavailable time source | configured source blank/typo'd/unreachable (UDP 123 blocked, DNS failure) |
| 8 | Persistent clock drift / hardware | clock resets after every reboot to a past date; drift returns quickly after sync |
| 9 | Outside L1 scope | domain/GPO-enforced config, CMOS battery, VM host sync, large manual correction needed |

### 7.1 `check_time_service`

**Purpose:** verify the Windows Time service (`w32time`).

**Verified default behavior (important):** on Windows 10/11 the Windows Time service is **Manual (Trigger Start)** by default. On domain-joined machines it starts on a domain-join trigger; on workgroup machines it is normally **Stopped while idle** and is started on demand (including by a built-in weekly scheduled synchronization task). **A stopped service by itself is therefore NOT evidence of failure** — the same rule as trigger-start services generally.

| Result | Meaning | Next action |
|---|---|---|
| Running, no errors | Healthy (or idle) | Continue with `check_time_source` / `check_time_status` interpretation |
| Stopped, but "Set time automatically" is OFF (user disabled sync) | User/system policy disabled automatic time — not a service fault | Do not restart. Ask the user (`ask_user`) whether automatic time should be enabled; changing that toggle is a user action, not an L1 fix tool → handle per Section 9 (no invented tool) |
| Stopped/Disabled **and** a sync attempt or scheduled sync just failed because of it | Verified service problem (type 4) | `fix_restart_time_service` eligible |
| Running but stops again immediately, or fails to start (error on start) | Malfunction (type 5) | One `fix_restart_time_service` attempt; if it fails again → escalate |
| Access denied / service cannot be controlled | Privilege problem | Escalate |

**When restarting is appropriate:** only with the evidence above, and only after the problem is verified. **Never restart the service merely because the user reported an incorrect clock.**

### 7.2 `check_time_source`

**Purpose:** determine what source Windows is configured to use and whether it appears usable.

| Finding | Interpretation | Next action |
|---|---|---|
| Source = real NTP server (e.g., `time.windows.com`) on a non-domain machine; `Type: NTP` | Normal workgroup configuration | Healthy source; sync failure (if any) is reachability — see below |
| Source = a domain controller on a domain-joined machine; `Type: NT5DS` | Normal domain configuration | Domain path must not be replaced with arbitrary NTP servers → if the DC source fails, escalate (domain team) |
| Source = `Local CMOS Clock`, `Stratum: 0`, `Last Successful Sync Time: unspecified` | **Verified failure signature** — Windows has fallen back to the hardware clock because synchronization is failing | Diagnosis type 6 → `fix_sync_time` eligible (with source check) |
| `Type: NT5DS` but machine is NOT domain-joined (Entra/workgroup) | Wrong sync model configured by policy/image | Outside L1 fix tools (reconfiguration of sync model is policy-level) → escalate |
| Configured source blank, typo'd, or unreachable: sync error "The computer did not resync because no time data was available" | Source invalid/unreachable (type 7). Documented causes: DNS failure on the source name, **UDP port 123 blocked** (local firewall or network firewall), or the target not advertising as an NTP server | If the configured source is the **organization's approved source** and it is unreachable → escalate (network/firewall or source outage). **Do NOT replace an organization's configured time source with an arbitrary one** — that is never an approved L1 action. |
| Error "The computer did not resync because the required time change was too big" | Clock is off by more than the maximum phase correction (documented default: 15 hours, `MaxPosPhaseCorrection`/`MaxNegPhaseCorrection`) | The available L1 fix tools (sync / service restart) **cannot** perform a large manual step correction — outside L1 scope → escalate |

### 7.3 Synchronization error messages (documented interpretations only)

The agent may only use these documented meanings:

| Message | Documented meaning |
|---|---|
| "The computer did not resync because no time data was available." | No usable NTP response: source name/DNS problem, UDP 123 blocked, or source not advertising NTP. |
| "The computer did not resync because the required time change was too big." | Offset exceeds the maximum allowed phase correction (default 15 h). Needs manual/intervention correction — escalate. |
| "The computer did not resync because the time service was shutting down." | Transient; retry after service settles. |
| Service starts and source later shows a real server | Sync succeeded. |

---

## 8. PHASE 4 — L1 FIXES

General rules for all fixes:

1. **Never apply a fix without satisfying its documented preconditions.**
2. Both fixes require **admin (elevated) privileges** and **user approval via `ask_user`**.
3. After EVERY fix, re-run `check_time_status` (Section 10). **A successful command is not proof of a fix.**
4. Never repeat a failed fix. One attempt per fix per session.

### 8.1 `fix_sync_time`

| Field | Value |
|---|---|
| **Purpose** | Force a Windows time synchronization attempt against the **currently configured, appropriate** time source. |
| **Applicable conditions** | Verified problem (Phase 1) of type 1/2/6: clock/date wrong, or sync failing with a healthy service and a valid configured source. |
| **Preconditions (ALL required)** | 1. Problem verified. 2. `check_time_service` shows the service Running or successfully startable (if the service is the fault, use `fix_restart_time_service` first). 3. `check_time_source` shows the configured source is **valid and appropriate** (real NTP source on non-domain machines; domain source on domain machines; NOT `Local CMOS Clock` as the *configured* source, and not a blank/typo'd source). |
| **Evidence required** | Status record, service record, source record. |
| **What the fix changes** | Issues one immediate resynchronization against the configured source (documented mechanics: `w32tm /resync`; service restart first if the service was just restarted). No configuration is changed. |
| **Risk level** | Low. A visible clock jump of up to the tolerance occurs if the clock was off — warn the user that the displayed time will change and timestamps on new documents may shift. |
| **Admin required** | Yes. |
| **User approval** | Required (`ask_user`). |
| **Expected result** | Sync succeeds; source shows the real server; clock corrected. |
| **Verification procedure** | Re-run `check_time_status` and compare against the trusted reference: the original symptom (wrong time/date, failed sync) must be **demonstrated corrected** — offset within tolerance, date correct, sync state healthy. A "sync command completed" message is NOT verification. |
| **Failure condition** | Resync returns an error (see 7.3 table), or post-check still shows wrong time/`Local CMOS Clock`. |
| **Next step if unsuccessful** | Interpret the error: transient → one `fix_restart_time_service` then re-attempt sync (the only allowed second action, and only if the service evidence supports it). "No time data available" on an org-approved source → escalate. "Time change too big" → escalate. |

### 8.2 `fix_restart_time_service`

| Field | Value |
|---|---|
| **Purpose** | Restart a Windows Time service proven stopped (when sync is required), stuck, or malfunctioning. |
| **Applicable conditions** | Verified problem (Phase 1) with service evidence from `check_time_service`: service Disabled while auto-time is on, service stopped at the moment of a failed sync, or service running-but-malfunctioning. |
| **Preconditions** | Problem verified AND service evidence documented. **Do not restart blindly.** On a healthy-idle (stopped) trigger-start service with no sync failure, this fix is NOT applicable. |
| **Evidence required** | Service state record, sync error record (if any). |
| **What the fix changes** | Stops and restarts `w32time` (documented mechanics: `net stop w32time` / `net start w32time`). No configuration is modified; startup type is left unchanged. |
| **Risk level** | Low. Brief gap in clock discipline. |
| **Admin required** | Yes. |
| **User approval** | Required (`ask_user`). |
| **Expected result** | Service Running and stable; subsequent sync proceeds. |
| **Verification procedure** | Re-run `check_time_service` (Running) then `check_time_status`/`fix_sync_time` per Section 8.1 flow: the original symptom must be demonstrated corrected. A restarted service is NOT proof of a synchronized clock. |
| **Failure condition** | Service will not start, stops again immediately, or sync still fails after restart. |
| **Next step if unsuccessful** | If sync now yields a documented source-reachability error → escalate. If the service itself is broken beyond restart (e.g., unregister/register territory — documented L2 procedure) → escalate. **Do not** use `w32tm /unregister` or `/register`: those are outside the available fix tools. |

---

## 9. TIMEZONE HANDLING

### 9.1 Distinguishing

| Check | Time-zone problem | Sync/clock problem |
|---|---|---|
| Offset from reference | UTC-equivalent time **correct**; local display shifted by whole hours | Underlying time itself wrong (any offset) |
| `w32tm /query /status` | Sync healthy, source valid | Not synchronized / `Local CMOS Clock` |
| User context | Recently traveled, DST change just occurred, image deployed with wrong zone | Clock drifts or is stuck |

### 9.2 Procedure (no timezone tool exists — documented, not invented)

1. **Confirm with the user (`ask_user`)**: "What time zone should this PC show?" (e.g., after travel, or a DST change.)
2. If the zone is wrong, the KB contains **no tool to change it**. Do NOT improvise one. The agent:
   - Informs the user how to correct it themselves: **Settings → Time & Language → Date & Time → Time zone** (or the organization documents an approved self-service path).
   - Records the verified diagnosis ("incorrect time zone; system time correct; synchronization healthy") and ends with `resolved` (no system modification performed) — OR
   - If the environment requires admin-controlled zone changes (kiosk, shared device, GPO-managed), `escalate` with the diagnosis.
3. **Never change timezone settings merely because synchronization failed.** Zone changes and sync repairs are independent actions.

---

## 10. MANDATORY FIX → VERIFY

After ANY fix executes:

```
FIX
 ↓
CHECK TIME STATUS AGAIN (check_time_status against trusted reference;
check_time_service / check_time_source as relevant)
 ↓
Is the ORIGINAL problem gone?
 ↓
YES → RESOLVED
NO  → additional documented L1 action ONLY if newly justified
      (restart service → retry sync is the only allowed second action)
      otherwise → TICKET
```

**Verification must test the original reported symptom:**

- Original problem "My clock is five minutes behind" → verification must demonstrate the workstation's actual time is now within tolerance **and** synchronization is healthy — not merely that a sync command returned success.
- Original problem "The date is wrong" → verification must show the correct date.
- Original problem "Windows says the time cannot be synchronized" → verification must show a real source in the status and a recent successful sync.

**Do NOT declare RESOLVED merely because:**

- a diagnostic completed
- synchronization was attempted
- the service restarted
- a command returned success
- the clock changed or moved closer to the expected value
- the system reported that a sync command completed

---

## 11. MULTIPLE L1 ACTIONS

The agent may attempt a second L1 fix **only if all** of the following hold:

1. The first fix failed (post-fix verification unsuccessful).
2. The problem remains verified.
3. Current/new evidence supports the second fix.
4. The KB explicitly permits it — the **only** allowed second action is: `fix_restart_time_service` (or sync after a restart) when the first failure evidence indicates the service was the blocker.

Strictly forbidden:

- Blindly running both fixes back-to-back.
- Repeatedly synchronizing the clock (one `fix_sync_time` attempt per session).
- Repeatedly restarting the Windows Time service (one attempt per session).
- Cycling between the fixes.

Every action must be justified by evidence; the flow must move toward resolution or escalation.

---

## 12. ESCALATION / TICKET CONDITIONS

Raise a ticket (with `escalate`) when **any** of the following is true. The ticket reason must cite gathered evidence.

| Condition | Typical evidence |
|---|---|
| The appropriate L1 fix fails | post-fix verification still failing |
| Workstation remains incorrectly synchronized after remediation | action history + status records |
| Synchronization continues to fail | documented sync error per 7.3 |
| Configured time source is unavailable and cannot be corrected within L1 scope | "no time data available" against the org-approved source; UDP 123 blocked by network policy |
| Persistent clock drift suggests hardware/firmware issues | clock resets to a past date after every boot (classic CMOS battery/RTC signature); corrects on sync then drifts again within hours |
| Required administrative privileges are unavailable | access denied on service/sync |
| Condition related to domain/infrastructure policy beyond L1 tools | `NT5DS` misapplied to non-domain machine; GPO-enforced time config; domain DC source failing |
| Sync error "required time change was too big" | needs manual large correction — no tool exists for it |
| Problem is outside documented L1 scope | VM host time-sync override, hypervisor interference |
| No safe supported L1 remediation remains | all prerequisites exhausted |

**Do NOT create a ticket simply because:**

- the user reported the problem,
- the initial verification shows correct time,
- the clock is slow to update by a tiny amount (≤ 2 s is normal),
- the service is running,
- the model/application produced invalid tool output.

**An internal agent/application failure is NOT a user support problem.** Application errors are logged internally and never become ticket reasons.

---

## 13. NO FALSE RESOLUTION / NO INFINITE LOOPING

- Never return RESOLVED without post-fix evidence that the original problem is cleared (Section 10).
- Do not repeatedly run the same diagnostic without a reason.
- Do not repeatedly synchronize time.
- Do not repeatedly restart the time service.
- The normal flow is: **VERIFY → DIAGNOSE → FIX → VERIFY**.
- If post-fix verification fails and no additional documented L1 action is justified → **TICKET**. Do not troubleshoot indefinitely.

---

## 14. TEST SCENARIOS

All scenarios are safe and reversible on a dev machine/VM. Restore the original state after each test.

### TEST 1 — Time is already correct
- **Condition:** Workstation clock within tolerance, zone correct, sync healthy.
- **Reproduce:** Nothing — user simply reports a wrong clock.
- **Expected initial verification:** `check_time_status` → healthy.
- **Expected diagnostic path:** None.
- **Expected L1 fix:** **None.**
- **Expected post-fix verification:** N/A.
- **Expected final result:** RESOLVED / NOT REPRODUCED; `problem_verified = false`; no fix; no ticket.

### TEST 2 — Clock intentionally incorrect (controlled)
- **Condition:** Controlled time discrepancy on a VM/disposable machine.
- **Reproduce (admin):** `Set-Date` (or Date & Time settings) to shift the clock by a few minutes. Reversible: a successful sync restores it.
- **Expected initial verification:** Offset > 60 s → verified.
- **Expected diagnostic path:** `check_time_service` (Running) → `check_time_source` (valid source) → diagnosis type 1/6.
- **Expected L1 fix:** `fix_sync_time` (approval obtained).
- **Expected post-fix verification:** `check_time_status` — offset within tolerance, sync healthy.
- **Expected final result:** RESOLVED if corrected.

### TEST 3 — Windows Time service stopped
- **Condition:** `w32time` stopped in a context where sync is required.
- **Reproduce (admin):** `net stop w32time` (reversible: `net start w32time`; on trigger-start systems also confirm the "Set time automatically" toggle remains ON).
- **Expected initial verification:** Problem verified (sync failure recorded or source = `Local CMOS Clock`).
- **Expected diagnostic path:** `check_time_service` → Stopped at time of need.
- **Expected L1 fix:** `fix_restart_time_service` → then `fix_sync_time` (the allowed second action).
- **Expected post-fix verification:** Service Running; time within tolerance.
- **Expected final result:** RESOLVED if corrected.
- **Cleanup:** confirm trigger-start/startup type unchanged from original.

### TEST 4 — Synchronization fails (source unreachable)
- **Condition:** Sync cannot complete.
- **Reproduce (admin, lab VM):** Add a temporary Windows Firewall rule blocking **outbound UDP 123** (documented NTP port), or point the NTP source at a non-responsive address. Reversible: delete the rule / restore source.
- **Expected initial verification:** Verified (sync failing / `Local CMOS Clock`).
- **Expected diagnostic path:** `check_time_service` (Running) → `check_time_source` → error "no time data available" → source-reachability diagnosis (type 7).
- **Expected L1 fix:** `fix_sync_time` attempted (preconditions: service OK) → **fails** with the documented error. `fix_restart_time_service` does not repair a network block and is NOT a substitute — escalate.
- **Expected post-fix verification:** Still failing.
- **Expected final result:** **TICKET** with the reachability evidence (UDP 123 / source outage — outside L1 scope).

### TEST 5 — Wrong timezone, correct system time
- **Condition:** Time zone incorrect but underlying time valid.
- **Reproduce (admin):** `tzutil /s "UTC"` on a machine that should be in a local zone (or change via Settings). Reversible: `tzutil /s "<original zone>"`.
- **Expected initial verification:** Displayed local time off by whole hours; UTC-equivalent matches reference; sync state healthy.
- **Expected diagnostic path:** Diagnosis type 3 (time zone) — the agent must NOT classify this as a synchronization failure and must NOT reset/restart the time service or force sync.
- **Expected L1 fix:** **None available (no timezone tool).** `ask_user` confirms the intended zone → user instructed to correct via Settings → resolved (no system change) or escalate if admin-managed.
- **Expected post-fix verification:** N/A (no agent fix performed); user-side correction confirmed verbally/by re-check.
- **Expected final result:** RESOLVED (time-zone handling path) — or escalation for managed devices.

### TEST 6 — Time remains wrong after L1 remediation
- **Condition:** The allowed fixes fail to correct the clock.
- **Reproduce (admin, VM):** Shift the clock by **more than 15 hours** (exceeds the documented default maximum phase correction) → `w32tm /resync` returns "required time change was too big". Reversible: manually set the correct date/time afterward.
- **Expected initial verification:** Verified wrong time.
- **Expected diagnostic path:** `fix_sync_time` attempted → documented "too big" error → type 9 (outside L1 scope — no manual-correction tool exists).
- **Expected L1 fix:** fails; service restart does not help (not a service problem).
- **Expected post-fix verification:** Still wrong.
- **Expected final result:** **TICKET** citing the "time change too big" evidence.
- **Cleanup:** restore correct time manually.

### TEST 7 — Problem cannot be reproduced
- **Condition:** User reports wrong time, but verification shows healthy state (e.g., the weekly scheduled sync corrected it before the agent ran, or the user's reference was wrong).
- **Expected flow:** Verify → healthy → STOP.
- **Expected final result:** RESOLVED / NOT REPRODUCED; `problem_verified = false`; no fix; no ticket. Report notes current healthy state and the last successful sync time.

---

## 15. FINAL REPORT

After every session, the application must produce a JSON report clearly distinguishing: whether the problem was verified, actual time/date evidence, time zone state where relevant, synchronization state, diagnosed cause, the fix attempted, fix success, post-fix verification success, and whether a ticket is required.

**Resolved:**

```json
{
  "status": "RESOLVED",
  "problem_verified": true,
  "current_time_evidence": {"offset_seconds_from_reference": 412, "date_correct": true, "timezone": "India Standard Time"},
  "sync_state": "not synchronized (source: Local CMOS Clock)",
  "diagnosis": "Synchronization failure against configured source time.windows.com; service healthy.",
  "fix_attempted": "fix_sync_time",
  "fix_successful": true,
  "verification_successful": true,
  "actions_taken": ["check_time_status", "check_time_service", "check_time_source",
                    "ask_user", "fix_sync_time", "check_time_status", "resolved"],
  "ticket_required": false,
  "reason": "Clock was 412 seconds behind; forced synchronization succeeded; post-fix offset within tolerance and sync state healthy."
}
```

**Could not be reproduced:**

```json
{
  "status": "RESOLVED",
  "problem_verified": false,
  "current_time_evidence": {"offset_seconds_from_reference": 1, "date_correct": true, "timezone": "India Standard Time"},
  "sync_state": "synchronized",
  "diagnosis": "System time and synchronization are currently healthy.",
  "fix_attempted": null,
  "fix_successful": false,
  "verification_successful": true,
  "actions_taken": ["check_time_status", "resolved"],
  "ticket_required": false,
  "reason": "The reported condition could not be reproduced."
}
```

**Unresolved (ticket required):**

```json
{
  "status": "TICKET_REQUIRED",
  "problem_verified": true,
  "current_time_evidence": {"offset_seconds_from_reference": 903, "date_correct": true, "timezone": "India Standard Time"},
  "sync_state": "not synchronized (source: Local CMOS Clock)",
  "diagnosis": "Configured organizational NTP source unreachable; resync fails with 'no time data available'. Service healthy; UDP 123 suspected blocked on network path.",
  "fix_attempted": "fix_sync_time",
  "fix_successful": false,
  "verification_successful": false,
  "actions_taken": ["check_time_status", "check_time_service", "check_time_source",
                    "ask_user", "fix_sync_time", "check_time_status", "escalate"],
  "ticket_required": true,
  "ticket_reason": "Synchronization to the approved time source fails with 'no time data available' after the supported L1 fix; suspected network firewall block of UDP 123 or source outage. Escalating to network/L2."
}
```

---

## 16. SAFETY REQUIREMENTS

1. **Verify the actual clock state before changing anything** — no fix before Phase 1 completes.
2. **Distinguish time-zone problems from synchronization problems** — whole-hour offsets are zone suspects, not sync failures.
3. **Use the least invasive appropriate L1 remediation** — sync attempt before service restart; never registry edits (`MaxPosPhaseCorrection`, `SpecialPollInterval`), never `w32tm /config`, never `w32tm /unregister`/`/register` — none of these are available L1 fix tools.
4. **Do not replace approved organizational time sources arbitrarily** — if the org source is broken, escalate; pointing machines at arbitrary public servers silently breaks domain consistency.
5. **Do not make unsupported system changes** — no timezone changes via improvised tooling, no manual clock sets (no tool exists for them), no configuration writes.
6. **Verify after every fix** — a completed sync command is not a corrected clock.
7. **Do not claim permanent repair without evidence** — resolution means the current symptom is cleared and verified.
8. **Do not loop indefinitely** — one attempt per fix; then escalate.
9. **Preserve diagnostic evidence** — status records, service/source records, sync error text, and action history must be retained for the report and any ticket.
10. **Internal agent errors must not be treated as user problems** — application failures are logged internally and never become ticket reasons.

---

## 17. COMMON MISTAKES THE AGENT MUST AVOID

| Mistake | Why it's wrong | Correct behavior |
|---|---|---|
| Forcing a sync on first complaint | Problem not verified | Phase 1 verification first |
| Treating a stopped w32time as broken | Default is Manual (Trigger Start); stopped-when-idle is normal | Only stopped-at-need with sync failure is evidence |
| Treating "Local CMOS Clock" as the configured source | It is the fallback shown when sync has failed | Diagnose why sync fell back (source reachability) |
| Calling a whole-hour offset a sync failure | UTC time is correct; only the zone is wrong | Time-zone handling (Section 9); no service restart |
| Restarting the service to fix "no time data available" | The source is unreachable, not the service | Escalate with reachability evidence |
| Retrying sync repeatedly after failure | Looping; no new evidence | One attempt, interpret the error, escalate per 7.3 |
| Declaring RESOLVED after a successful resync command | Command success ≠ corrected clock | Compare against reference; check sync state |
| Pointing the machine at an arbitrary public NTP server | Violates org time policy; breaks domain consistency | Escalate; never change approved sources |
| Changing timezone because sync failed | Unrelated conditions | Fix sync only; handle zone separately |
| Editing registry/config to force a big correction | Outside available fix tools; risk of policy conflict | Escalate "time change too big" |
| Killing/ignoring the service trigger config | Startup type changes persist and surprise later | Leave startup type unchanged; one restart only |
| Ticket because the tool errored | Internal failure is not user evidence | Log internally; continue or restart the flow |

---

## 18. REFERENCES (VERIFIED TECHNICAL BASIS)

- Microsoft Learn — *W32Time doesn't start on a workgroup computer* (trigger-start behavior, domain-join trigger, `sc qtriggerinfo w32time`): https://learn.microsoft.com/en-us/troubleshoot/windows-client/active-directory/w32time-not-start-on-workgroup
- Microsoft Learn — *Windows Time Service Tools and Settings* (`w32tm`, phase-correction logic): https://learn.microsoft.com/en-us/windows-server/networking/windows-time-service/windows-time-service-tools-and-settings
- Microsoft Learn — *w32tm /resync fails: "no time data available"* (DNS, UDP 123 scenarios, resolution): https://learn.microsoft.com/en-us/troubleshoot/windows-server/active-directory/error-message-run-w32tm-resync-no-time-data-available
- Microsoft Q&A — Windows 11 time sync guidance (service restart, `regsvr32 w32time.dll`, UDP 123, `w32tm /unregister` + `/register` — all documented as L2-level, not in this KB's fix set): https://learn.microsoft.com/en-us/answers/questions/5639027/windows-11-time-synchronisation-fail
- Dell KB — Troubleshooting the Windows Time Service (source interpretation on domain vs. workgroup, resync procedure, unregister/register as reset-of-last-resort): https://www.dell.com/support/kbdoc/en-us/000134430/troubleshooting-the-windows-time-service
- Svetek — Fix Windows Time Sync on Entra ID joined devices (`Local CMOS Clock` + `Type: NT5DS` with `#Peers: 0` signature; `stripchart` proves reachability but not configuration): https://help.svetek.com/docs/Configuration/Azure/fix-windows-time-sync-entra-id/
- IBM — Troubleshoot time drift / failed sync (NT5DS vs NTP modes, VM host interference, UDP 123 blocks): https://www.ibm.com/support/pages/how-troubleshoot-time-drift-authentication-issues-or-failed-time-synchronization
