# internet_connectivity.md — L1 Troubleshooting Knowledge Base: Internet Connectivity

**Applies to:** Windows 10 / Windows 11 workstations
**Agent role:** IT Helpdesk L1 automated agent
**Category:** INTERNET_CONNECTIVITY

---

## 1. SCOPE

This knowledge base covers L1 diagnosis and remediation of end-user reports of **general Internet connectivity failure** on a single Windows workstation, where the user reports symptoms such as:

- "My internet is not working."
- "I can't open any websites."
- "Nothing loads in the browser."
- "Teams/Outlook says I'm offline."

**In scope:**

- Verifying whether Internet connectivity is genuinely broken (objective pre-check).
- Diagnosing the cause using supported diagnostics.
- Applying safe, documented L1 fixes when evidence justifies them.
- Re-verifying connectivity after every fix.
- Escalating with evidence when L1 scope is exhausted.

**Out of scope (escalate instead):**

- Corporate VPN-only connectivity problems where general Internet works (use the VPN KB).
- Proxy configuration, firewall policy, or corporate web-filter issues.
- Router, switch, Wi-Fi access point, or ISP outages (infrastructure).
- Network adapter hardware failure or driver corruption requiring driver installation.
- Problems affecting multiple users or an entire site simultaneously.
- Any condition requiring changes outside the local workstation.

---

## 2. MANDATORY LIFECYCLE

Every troubleshooting session MUST follow this exact sequence:

```
USER REPORTS INTERNET PROBLEM
        ↓
1. VERIFY THE PROBLEM ACTUALLY EXISTS
        ↓
2. DIAGNOSE THE CAUSE
        ↓
3. SELECT AN APPLICABLE L1 FIX
        ↓
4. EXECUTE THE FIX
        ↓
5. VERIFY WHETHER THE FIX WORKED
        ↓
      ┌───────────────┐
      │               │
     YES              NO
      │               │
   RESOLVED       MORE JUSTIFIED L1 ACTION?
                     │
                ┌────┴────┐
               YES       NO
                │         │
             FIX+TEST  TICKET
```

**Forbidden flows (never use):**

```
USER COMPLAINT → GUESS THE CAUSE → RUN A FIX
USER COMPLAINT → RUN DHCP RENEW
USER COMPLAINT → RUN DNS FLUSH
FIX EXECUTED → RESOLVED          (never declare resolved without re-verification)
```

The correct lifecycle is always: **VERIFY → DIAGNOSE → FIX → VERIFY AGAIN → RESOLVE OR TICKET.**

---

## 3. AVAILABLE TOOLS

The agent may use **only** these tools. Commands are documented inside tool descriptions for reference; the canonical tool identifier is the name listed here.

### 3.1 Diagnostics

| Tool | Reference commands (informational) | Purpose |
|---|---|---|
| `check_adapter_state` | `Get-NetAdapter` / `netsh interface show interface` | Determine whether a network adapter exists, is enabled, and has link (media connected). |
| `check_ip_config` | `ipconfig /all` | Inspect IPv4 address, DHCP state, and default gateway assigned to the active adapter. |
| `check_gateway` | `ping <default-gateway-IP>` | Test reachability of the local default gateway. |
| `check_internet_ip` | `ping 1.1.1.1` (a public IP address, no DNS involved) | Test end-to-end Internet reachability by IP only. |
| `check_dns` | `nslookup example.com` | Test whether DNS name resolution works. |

### 3.2 Fixes

| Tool | Reference command (informational) | Purpose |
|---|---|---|
| `enable_adapter` | `Enable-NetAdapter -Name "<adapter>"` | Enable a disabled network adapter. |
| `fix_renew_dhcp` | `ipconfig /release` then `ipconfig /renew` | Obtain a fresh IP configuration from DHCP. |
| `fix_flush_dns` | `ipconfig /flushdns` | Clear the local DNS resolver cache. |
| `fix_reset_winsock` | `netsh winsock reset` | Repair a corrupted Winsock (Windows socket) layer. |
| `fix_reset_tcpip` | `netsh int ip reset` | Reset the TCP/IP stack to a clean state. |

### 3.3 Control actions

| Tool | Purpose |
|---|---|
| `ask_user` | Request information or confirmation from the user (e.g., approval for a fix, which network they use, whether others nearby are affected). |
| `escalate` | End L1 handling and create a ticket with gathered evidence. |
| `resolved` | End the session with status RESOLVED and produce the final report. |

---

## 4. PHASE 1 — INITIAL CONNECTIVITY VERIFICATION

### 4.1 Principle

The user's statement is a **reported symptom, not evidence**. "My internet is not working" does not prove connectivity is broken. The agent must first establish objective evidence. Do **not** renew DHCP, flush DNS, reset Winsock, reset TCP/IP, restart adapters, or apply any other fix before verification is complete.

**Not accepted as proof of working Internet, on their own:**

- "Wi-Fi connected" or "Ethernet connected" (only proves local link).
- Having an IP address (only proves local configuration).
- Having a default gateway (only proves configuration, not reachability).

### 4.2 Verification procedure

Run the diagnostics in this order. Stop as soon as a conclusive answer is reached.

**Step V1 — `check_adapter_state`**

| Result | Meaning | Next action |
|---|---|---|
| At least one adapter Enabled, with Media/Link "Connected" | Local link present | Go to V2 |
| Adapter exists but is **Disabled** | Disabled adapter — a verified local connectivity problem | Skip to Diagnosis D1 (adapter problem). Do NOT claim "Internet is down" yet; verify after enabling. |
| Adapter Enabled but **Media Disconnected / no link** | Cable unplugged, Wi-Fi off, or hardware problem | Use `ask_user` to confirm cable/Wi-Fi state. If user confirms everything is plugged in and Wi-Fi is on → hardware/local-link failure → escalate. Do not run IP/DNS fixes. |
| No network adapter present at all | Hardware/driver problem | Escalate (no supported L1 remediation). |

**Step V2 — `check_ip_config`**

| Result | Meaning | Next action |
|---|---|---|
| Valid IPv4 (e.g., `192.168.x.x`, `10.x.x.x`, `172.16–31.x.x`) with a default gateway listed | Plausible local configuration | Go to V3 |
| No IPv4 address, or address starting with `169.254.x.x` | DHCP failure — verified connectivity problem | Go to Diagnosis D3 (DHCP failure). |
| Valid IPv4 but **no default gateway** | Invalid local configuration | Treat as DHCP/configuration failure → Diagnosis D3. |

**Step V3 — `check_gateway`** (ping the default gateway IP obtained in V2)

| Result | Meaning | Next action |
|---|---|---|
| Gateway replies | Local network path works | Go to V4 |
| Gateway does not reply | Local network/gateway failure — verified problem | Diagnosis D4. Do NOT run DNS fixes. |

**Step V4 — `check_internet_ip`** (ping a public IP by address, e.g., `1.1.1.1` — no DNS involved)

| Result | Meaning | Next action |
|---|---|---|
| Public IP replies | **Internet path is working.** The machine has Internet connectivity. | Go to V5 to confirm DNS. |
| No reply | Either Internet path failure OR ICMP blocked by a firewall | Go to V5 to disambiguate. |

**Step V5 — `check_dns`** (`nslookup` a known public name)

| Result | Meaning | Next action |
|---|---|---|
| Name resolves successfully | **Internet connectivity is confirmed working** (DNS also works). The reported outage **cannot be reproduced**. | Do NOT diagnose, do NOT fix. Inform the user via the report: "The reported Internet outage could not be reproduced; end-to-end connectivity and DNS are working." Mark `problem_verified: false`, status `RESOLVED`, reason "not reproducible." |
| `nslookup` fails (timeout / cannot resolve) while V1–V3 were healthy | **Verified problem.** If V4 also failed → Internet path failure (Diagnosis D5). If V4 succeeded → DNS resolution failure (Diagnosis D6). | Continue to Phase 2. |

> **Inconclusive handling:** If a test cannot complete (tool error, unknown output), perform the minimum additional diagnostic needed to establish connectivity status — never guess. If verification cannot be established with the supported tools, escalate with `problem_verified` set to the closest evidence-supported value and note the inconclusive step in `ticket_reason`.

---

## 5. PHASE 2 — DIAGNOSTIC DECISION TREE

Each diagnosis below is reached **only** by the evidence path shown. Never assume a cause before evidence proves it.

```
V1 check_adapter_state
   ├─ Disabled ───────────────► D1 Adapter disabled ──────► enable_adapter
   ├─ No link / hardware ─────► D8 Out of L1 scope ───────► escalate
   └─ Link OK
        V2 check_ip_config
           ├─ No IP / 169.254.x.x ─► D3 DHCP failure ─────► fix_renew_dhcp
           ├─ No gateway ───────────► D3 DHCP failure ─────► fix_renew_dhcp
           └─ Valid IP + gateway
                V3 check_gateway
                   ├─ Unreachable ──► D4 Gateway/local network ─► escalate
                   └─ Reachable
                        V4 check_internet_ip
                           ├─ OK ──► V5 check_dns
                           │           ├─ OK ──► Internet WORKS (not reproducible) ─► resolved
                           │           └─ FAIL ► D6 DNS resolution failure ─► fix_flush_dns
                           └─ FAIL ► V5 check_dns
                                           ├─ OK ──► ICMP blocked; Internet WORKS ─► resolved (not reproducible)
                                           └─ FAIL ► D5 Internet path failure
                                                       ├─ After justified stack evidence ► fix_reset_winsock / fix_reset_tcpip
                                                       └─ Otherwise ────────────────────► escalate
```

### D1 — Adapter disabled
**Evidence:** `check_adapter_state` shows the relevant adapter Disabled.
**Meaning:** The workstation cannot use that adapter. This is a local connectivity problem.
**Eligible fix:** `enable_adapter`
**Not appropriate:** `fix_flush_dns`, `fix_renew_dhcp` (they cannot help a disabled adapter).

### D2 — Missing/invalid IP configuration
**Evidence:** `check_ip_config` shows no IPv4 address, an APIPA address (`169.254.x.x`), or a missing gateway.
**Meaning:** The workstation never obtained (or lost) a valid DHCP lease.
**Eligible fix:** `fix_renew_dhcp`
**Not appropriate:** `fix_flush_dns` (DNS is irrelevant without IP connectivity).

### D3 — DHCP failure
Same evidence family as D2; reached when the IP configuration is demonstrably absent or invalid and the adapter/link are healthy. Eligible fix: `fix_renew_dhcp`.

### D4 — Default gateway / local network failure
**Evidence:** valid IP **and** `check_gateway` fails (gateway does not reply).
**Meaning:** the workstation's own network segment or gateway is down/unreachable.
**Eligible fixes:** **none of the supported L1 fixes repair a dead gateway.**
**Not appropriate:** `fix_flush_dns` (a DNS-only fix applied here is a classic misdiagnosis and is **forbidden**), `fix_renew_dhcp` (a normal valid IPv4 address must NOT by itself justify DHCP renewal).
**Action:** `escalate` with evidence: valid IP, gateway IP, gateway ping failure. Optionally use `ask_user` to ask whether other users on the same site are affected (indicates infrastructure outage).

### D5 — Internet path failure
**Evidence:** gateway reachable, `check_internet_ip` fails, `check_dns` also fails (see V4/V5 disambiguation — if `check_dns` succeeds while ping fails, the issue is ICMP blocking, not connectivity).
**Meaning:** traffic leaves the local network but cannot reach the Internet — ISP edge, upstream outage, or a corrupted local network stack.
**First consideration:** this is usually **outside L1 scope** (infrastructure). Escalate with evidence.
**Stack-problem exception:** if evidence of local stack corruption also exists (e.g., a Winsock problem documented under D7), the stack fixes become eligible. Do not apply them blindly to an Internet path failure.

### D6 — DNS resolution failure
**Evidence:** Internet reachable by IP (`check_internet_ip` replies) **but** `check_dns` cannot resolve a known public name.
**Meaning:** the transport works; name resolution is broken (stale/poisoned resolver cache most commonly at L1).
**Eligible fix:** `fix_flush_dns`
**Not appropriate:** `fix_renew_dhcp` (a valid IP plus working Internet path does NOT justify DHCP renewal), `fix_reset_tcpip`, `fix_reset_winsock` (too invasive as a first-line DNS fix).

### D7 — TCP/IP or Winsock stack problem
**Evidence (all required):** adapter enabled, valid IP, gateway reachable, `check_internet_ip` succeeds, `check_dns` succeeds — yet the user's applications still cannot reach the Internet. This pattern (raw network tests pass, applications fail) indicates Winsock layer corruption.
**Meaning:** the OS socket layer used by applications is damaged.
**Eligible fixes (in order, one at a time, each followed by re-verification):** `fix_reset_winsock` first; `fix_reset_tcpip` second if Winsock reset did not restore application connectivity.
**Not appropriate:** `fix_flush_dns`, `fix_renew_dhcp` (all basic diagnostics are healthy).

### D8 — Conditions outside normal L1 scope
**Evidence:** hardware failure indications (no adapter, media disconnected despite user confirming cabling, device errors), infrastructure outage indications, VPN/corporate-path dependency, or any condition the supported diagnostics cannot characterize.
**Action:** `escalate` with the evidence gathered. Never fabricate a diagnosis.

---

## 6. PHASE 3 — L1 FIXES

General rules for all fixes:

1. **Never apply a fix whose prerequisite evidence has not been satisfied** (per Section 5).
2. Before any fix that changes system state, use `ask_user` to obtain user approval (all fixes below require approval).
3. After EVERY fix, re-run the verification path (V1→V5 as applicable). **A successful command exit is NOT a fix success.** Only restored connectivity counts.
4. If a fix fails, do not retry the same fix. Move to the next *evidence-justified* action or escalate.
5. Never cycle between fixes without new diagnostic evidence.

### 6.1 `enable_adapter`

| Field | Value |
|---|---|
| **Purpose** | Re-enable a disabled network adapter. |
| **Preconditions / evidence required** | `check_adapter_state` proves the relevant adapter is Disabled (D1). Enable only the adapter the workstation actually uses. Do not enable unrelated adapters. |
| **Risk level** | Low |
| **Admin privileges** | Usually required on managed/domain machines. |
| **User approval** | Required (`ask_user`). |
| **Expected effect** | Adapter transitions to Enabled and negotiates link. |
| **Verification procedure** | Re-run `check_adapter_state` (enabled + link), then continue V2→V5. The original connectivity problem is resolved only when V5 confirms working Internet. |
| **Failure condition** | Adapter will not enable, or enables but has no link/media disconnected. |
| **Next action if unsuccessful** | If media disconnected with cabling confirmed → escalate (hardware). If adapter will not enable → escalate. |

### 6.2 `fix_renew_dhcp`

| Field | Value |
|---|---|
| **Purpose** | Obtain a fresh, valid IP configuration from the DHCP server. |
| **Preconditions / evidence required** | D2/D3 evidence: no IPv4 address, `169.254.x.x`, or missing gateway — with a healthy, enabled adapter. **A normal valid IPv4 address must NOT by itself justify DHCP renewal.** |
| **Risk level** | Low. Brief network drop; active VPN sessions will disconnect. |
| **Admin privileges** | Not required for standard renew in most environments. |
| **User approval** | Required (`ask_user`). |
| **Expected effect** | `check_ip_config` shows a valid IPv4 address and default gateway. |
| **Verification procedure** | Re-run V2→V5: confirm valid IP, gateway reachable, Internet reachable, DNS resolves. |
| **Failure condition** | Renew returns `169.254.x.x` again, times out, or no gateway is offered. |
| **Next action if unsuccessful** | One repeat is NOT permitted. Escalate with DHCP evidence (likely DHCP server/scope problem — infrastructure). |

### 6.3 `fix_flush_dns`

| Field | Value |
|---|---|
| **Purpose** | Clear a stale or poisoned local DNS resolver cache. |
| **Preconditions / evidence required** | D6 evidence ONLY: `check_internet_ip` succeeds but `check_dns` fails. Do not flush merely because a user says a website does not open. |
| **Risk level** | Very low (cache is rebuilt automatically). |
| **Admin privileges** | Not required. |
| **User approval** | Required (`ask_user`). |
| **Expected effect** | Subsequent name resolutions re-query real DNS servers instead of the bad cached entry. |
| **Verification procedure** | Re-run `check_dns`; if it resolves, re-run `check_internet_ip` and confirm end-to-end Internet access. |
| **Failure condition** | DNS still fails after the flush. |
| **Next action if unsuccessful** | The problem is beyond the DNS cache (e.g., wrong DNS server config, corporate DNS outage) — outside the supported L1 fixes → escalate with evidence. Do not escalate to Winsock/TCP-IP resets for a DNS-only problem. |

### 6.4 `fix_reset_winsock`

| Field | Value |
|---|---|
| **Purpose** | Rebuild the Winsock catalog (the socket layer applications use) when it is corrupted. |
| **Preconditions / evidence required** | D7 evidence: ALL basic diagnostics pass (adapter, IP, gateway, Internet-by-IP, DNS) yet applications cannot access the network. Not for adapter, DHCP, DNS, or Internet-path problems. |
| **Risk level** | **Medium — more invasive.** Removes third-party LSPs; some security/filtering software may need reconfiguration. |
| **Admin privileges** | Required. |
| **User approval** | Required (`ask_user`) — explicitly warn a restart is required and third-party network software may be affected. |
| **Expected effect** | Winsock catalog reset to default; applications regain network access after restart. |
| **Verification procedure** | After the required **restart**, re-run V1→V5 AND confirm the user's original application-level symptom is gone. |
| **Failure condition** | Applications still cannot reach the network after restart. |
| **Next action if unsuccessful** | If the full D7 evidence pattern still holds → `fix_reset_tcpip` (once). Otherwise → escalate. |

### 6.5 `fix_reset_tcpip`

| Field | Value |
|---|---|
| **Purpose** | Reset the TCP/IP stack to a clean default state. |
| **Preconditions / evidence required** | D7 evidence pattern persists **after** a Winsock reset and restart failed, OR `check_ip_config` repeatedly shows invalid configuration even after a justified DHCP renewal. Never a first-line fix. |
| **Risk level** | **Medium–High.** Removes static IP/DNS configuration — any static settings must be recorded first so they can be restored. |
| **Admin privileges** | Required. |
| **User approval** | Required (`ask_user`) — explicitly warn about restart and loss of static network configuration. |
| **Expected effect** | TCP/IP stack reinitialized; configuration re-obtained (via DHCP) or restored manually. |
| **Verification procedure** | After the required **restart**, re-run V1→V5 fully. |
| **Failure condition** | Connectivity still broken after restart and reconfiguration. |
| **Next action if unsuccessful** | Escalate — L1 remediation exhausted. |

---

## 7. MULTIPLE FIXES RULE

The agent may attempt another documented L1 fix **only when new diagnostic evidence justifies it** after re-verification. Strictly forbidden:

- Blindly executing every fix in sequence.
- Repeating a fix that already failed.
- Cycling between fixes.
- Applying a fix without the evidence prerequisites of Section 5/6.

Valid pattern:

```
Initial verification → Diagnosis → Fix A → Verification
   → still broken → additional diagnosis if needed
   → Fix B (only if newly justified) → Verification
   → still broken → ESCALATE
```

---

## 8. ESCALATION CONDITIONS

Escalate (with `escalate`) when **any** of the following is true. The escalation reason must reference actual gathered evidence — never fabricate a reason.

| Condition | Typical evidence |
|---|---|
| No safe L1 fix is applicable to the verified problem | e.g., D4 gateway failure, D5 pure Internet path failure |
| Required permissions are unavailable | admin rights denied for `enable_adapter`, `fix_reset_winsock`, `fix_reset_tcpip` |
| Problem persists after all evidence-justified L1 fixes | post-fix verification still fails |
| Diagnostics indicate hardware failure | no adapter, media disconnected with cabling confirmed, device errors |
| Diagnostics indicate infrastructure/network outage | gateway dead; ask_user confirms multiple users affected |
| VPN/corporate network dependency is involved | general Internet healthy but corporate resources unreachable |
| Condition is outside documented L1 scope | proxy, firewall policy, driver installation, multi-user outage |
| Further remediation would be risky or require higher privileges | static-config loss, domain policy changes |
| Problem cannot be established or resolved with supported diagnostics/tools | inconclusive verification with no further test available |

**Critical rule:** a ticket is **never** created merely because the agent application made an invalid tool selection or hit an internal error. An application/model failure is NOT evidence that the user's Internet is broken. Application errors are logged internally; only user-facing evidence justifies a ticket.

---

## 9. POST-FIX VERIFICATION (MANDATORY)

After ANY fix executes successfully (command exit success):

```
FIX EXECUTED
     ↓
RUN CONNECTIVITY VERIFICATION AGAIN (V1→V5 as applicable)
     ↓
Original symptom resolved?
     ↓
  YES ──► resolved (status RESOLVED)
  NO  ──► next justified L1 action, or escalate
```

**Do NOT declare RESOLVED merely because:**

- the command exited successfully
- the adapter became enabled
- an IP address appeared
- a DNS cache was flushed
- Winsock reset completed
- TCP/IP reset completed

The verification must test the **actual original failing symptom**: end-to-end Internet access (and, where relevant, DNS resolution). Only demonstrated restoration counts.

---

## 10. TEST SCENARIOS (REPRODUCIBLE ON A DEV MACHINE)

All scenarios are safe and reversible. Use a test machine/VPN-free lab connection.

### TS-1: Reported problem, but Internet is actually working
- **Reproduce:** Do nothing to the machine. User simply reports "internet is down."
- **Expected initial verification:** V1–V5 all healthy.
- **Expected diagnostic path:** None after V5.
- **Expected L1 fix:** **None.** No DHCP renew, no flush, no resets.
- **Expected post-fix verification:** N/A.
- **Expected final result:** `resolved`, `problem_verified: false`, reason "reported outage could not be reproduced; end-to-end connectivity and DNS confirmed working."

### TS-2: DHCP/IP configuration failure
- **Reproduce (admin):** `ipconfig /release` (reversible — a renew restores it).
- **Expected initial verification:** V2 shows no IPv4 address.
- **Expected diagnostic path:** D2/D3.
- **Expected L1 fix:** `fix_renew_dhcp` (with approval).
- **Expected post-fix verification:** V2→V5 pass.
- **Expected final result:** `resolved`.

### TS-3: DNS resolution failure
- **Reproduce (admin):** Add a line to `C:\Windows\System32\drivers\etc\hosts` mapping a test domain (e.g., `internal-test.example`) to a dead IP (e.g., `10.255.255.10`), resolve it once (`nslookup`/`ping`), then **delete** the line. The stale cached answer still resolves to the dead IP until the cache is cleared.
- **Expected initial verification:** V4 succeeds (ping `1.1.1.1` OK); V5 fails for the test domain.
- **Expected diagnostic path:** D6.
- **Expected L1 fix:** `fix_flush_dns`.
- **Expected post-fix verification:** `check_dns` resolves the test domain correctly.
- **Expected final result:** `resolved`.
- **Cleanup:** confirm the hosts file line is removed (the scenario depends on it).

### TS-4: Adapter disabled
- **Reproduce:** Settings → Network → Change adapter options → right-click the active adapter → Disable.
- **Expected initial verification:** V1 shows adapter Disabled.
- **Expected diagnostic path:** D1.
- **Expected L1 fix:** `enable_adapter` (with approval).
- **Expected post-fix verification:** V1 enabled + link, then V2→V5 pass.
- **Expected final result:** `resolved`.
- **Cleanup:** none — the fix itself restores the state.

### TS-5: Local gateway failure (must NOT receive a DNS-only fix)
- **Reproduce (admin):** Set a static IPv4 with the **wrong** default gateway (e.g., real gateway is `.1`, set `.254`). Note the real settings first.
- **Expected initial verification:** V2 shows valid IP; V3 gateway ping fails.
- **Expected diagnostic path:** D4.
- **Expected L1 fix:** **None available.** The agent must NOT run `fix_flush_dns` and must NOT run `fix_renew_dhcp` (valid IP present).
- **Expected post-fix verification:** N/A.
- **Expected final result:** `escalate` with gateway-failure evidence.
- **Cleanup:** restore the original static settings (or switch back to DHCP).

### TS-6: Internet remains unavailable after the justified L1 fix
- **Reproduce (admin, lab only):** Disconnect the lab's uplink (or block the lab VLAN's Internet path at the test router) so DHCP still works but Internet is dead, then renew the lease to prove DHCP health. Alternatively leave a `169.254.x.x` state that the DHCP server cannot fix.
- **Expected initial verification:** V3 passes, V4 fails, V5 fails.
- **Expected diagnostic path:** D5.
- **Expected L1 fix:** none applicable (or a justified stack fix that still fails); after re-verification the Internet is still down.
- **Expected post-fix verification:** still failing.
- **Expected final result:** `escalate` (ticket) — agent performed verification after the fix and the issue remains unresolved.

### TS-7: Problem with no supported L1 remediation
- **Reproduce:** Disable the network adapter in Device Manager, or unplug the Ethernet cable and confirm Wi-Fi is off (media disconnected state).
- **Expected initial verification:** V1 shows media disconnected / adapter unavailable.
- **Expected diagnostic path:** D8 (hardware/local-link).
- **Expected L1 fix:** **None.**
- **Expected post-fix verification:** N/A.
- **Expected final result:** `escalate` with hardware evidence.
- **Cleanup:** re-enable in Device Manager / replug cable.

---

## 11. EXAMPLE TROUBLESHOOTING FLOWS

### Flow A — Full success (DNS)
```
User: "No website opens."
V1 adapter OK → V2 valid IP + gateway → V3 gateway OK
→ V4 ping 1.1.1.1 OK → V5 nslookup FAILS
Diagnosis: D6 DNS resolution failure
ask_user approval → fix_flush_dns → V5 again: nslookup OK → V4 still OK
resolved: RESOLVED, problem_verified true, diagnosis "DNS resolution failure",
fix "fix_flush_dns", verification successful
```

### Flow B — Not reproducible
```
User: "Internet is down."
V1–V5 all healthy
resolved: problem_verified FALSE, no fixes run,
reason "reported outage could not be reproduced"
```

### Flow C — Escalation after justified fix fails
```
User: "Internet is down."
V2: 169.254.x.x → Diagnosis D3 → approval → fix_renew_dhcp
→ V2 again: still 169.254.x.x
No repeat permitted; no other fix justified by evidence
escalate: ticket_reason "DHCP renewal returned APIPA address;
likely DHCP infrastructure issue"
```

### Flow D — Wrong-fix prevention
```
User: "Internet is down."
V2 valid IP, V3 gateway UNREACHABLE
→ D4: NO fix applicable. fix_flush_dns is FORBIDDEN here (not a DNS problem).
escalate with gateway evidence.
```

---

## 12. FINAL RESULT / REPORT FORMAT

After every session, the application must produce a JSON report distinguishing: whether the problem was verified, the evidence-based diagnosis, the fix attempted, fix success, post-fix verification success, and whether a ticket is required.

**Resolved:**

```json
{
  "status": "RESOLVED",
  "problem_verified": true,
  "diagnosis": "DNS resolution failure",
  "fix_attempted": "fix_flush_dns",
  "fix_successful": true,
  "verification_successful": true,
  "actions_taken": ["check_adapter_state", "check_ip_config", "check_gateway",
                    "check_internet_ip", "check_dns",
                    "ask_user", "fix_flush_dns", "check_dns", "resolved"],
  "reason": "DNS cache flushed; name resolution and end-to-end Internet access restored."
}
```

**Not resolved (ticket required):**

```json
{
  "status": "TICKET_REQUIRED",
  "problem_verified": true,
  "diagnosis": "DHCP failure",
  "fix_attempted": "fix_renew_dhcp",
  "fix_successful": false,
  "verification_successful": false,
  "actions_taken": ["check_adapter_state", "check_ip_config", "check_gateway",
                    "check_internet_ip", "check_dns",
                    "ask_user", "fix_renew_dhcp", "check_ip_config", "escalate"],
  "ticket_reason": "DHCP renewal returned a 169.254.x.x address after fix_renew_dhcp; likely DHCP server or scope problem. Escalating to L2/network team."
}
```

**Not reproducible:**

```json
{
  "status": "RESOLVED",
  "problem_verified": false,
  "diagnosis": "none - connectivity healthy",
  "fix_attempted": "none",
  "fix_successful": false,
  "verification_successful": true,
  "actions_taken": ["check_adapter_state", "check_ip_config", "check_gateway",
                    "check_internet_ip", "check_dns", "resolved"],
  "reason": "Reported Internet outage could not be reproduced; adapter, IP, gateway, Internet-by-IP and DNS all verified working."
}
```

---

## 13. SAFETY RULES

1. **Verify before anything else.** No diagnosis, no fixes, before Phase 1 completes.
2. **Evidence before fixes.** Every fix requires its documented evidence prerequisites. Never fix on a guess.
3. **Approval before state-changing fixes.** All five fixes require explicit user approval via `ask_user`, including warnings about restarts and configuration loss where applicable.
4. **Re-verify after every fix.** Command success ≠ problem solved. Only demonstrated restoration of the original symptom counts.
5. **Least invasive first.** Never jump to `fix_reset_winsock` or `fix_reset_tcpip` when a targeted fix (`enable_adapter`, `fix_renew_dhcp`, `fix_flush_dns`) matches the evidence.
6. **Record before resetting.** Before `fix_reset_tcpip`, record any static IP/DNS configuration so it can be restored.
7. **No blind adapter enabling.** Enable only the adapter proven disabled and relevant.
8. **No repeat failures.** A failed fix is never immediately retried.
9. **Honest tickets only.** Escalation reasons must cite gathered evidence; agent-internal errors never justify a ticket.
10. **Stay in scope.** Proxy, firewall, VPN, driver, and infrastructure problems are escalate-only.

---

## 14. COMMON MISTAKES THE AGENT MUST AVOID

| Mistake | Why it's wrong | Correct behavior |
|---|---|---|
| Running `fix_renew_dhcp` immediately after the complaint | The complaint is not proof of a DHCP problem | Run Phase 1 verification first |
| Flushing DNS because "a website doesn't open" | The failure may be link, IP, gateway, or Internet path — not DNS | Flush only on D6 evidence (IP reachable, DNS failing) |
| Treating "Wi-Fi connected" as working Internet | Link ≠ Internet access | Complete V1→V5 |
| Treating any valid IP as proof of health, or as DHCP failure by itself | A valid 192.168.x.x is healthy; it neither proves Internet access nor indicates DHCP failure | Interpret each diagnostic in sequence |
| Applying a DNS fix to a gateway failure | DNS fixes cannot repair a dead gateway | D4 → escalate |
| Declaring RESOLVED after a successful command | Commands can succeed while the problem persists | Re-verify the original symptom |
| Re-running the same failed fix | No new evidence, no new outcome | Diagnose again or escalate |
| Running all fixes in sequence "to be safe" | Invasive resets with real risk, applied without justification | One fix per evidence, verify between each |
| Resetting Winsock/TCP-IP as a first response | Requires restart, removes LSPs/static config | Only on D7 evidence, after simpler paths |
| Creating a ticket because the agent errored | Application failure is not user evidence | Log internally; continue or restart the flow |
| Enabling every disabled adapter | May enable unused/harmful interfaces | Enable only the proven-relevant adapter |
