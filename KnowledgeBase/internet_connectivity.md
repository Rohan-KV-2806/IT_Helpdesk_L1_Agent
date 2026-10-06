# Internet Connectivity

## Scope

Problems where a Windows workstation cannot reach internal or external network resources: no IP address, gateway unreachable, Internet unreachable by IP, DNS resolution failure. Covers workstation-level network diagnostics only. If evidence points to VPN, corporate network, or multi-user outage, escalate. A website failing to load is NOT automatically a DNS/Internet problem — verify before classifying.

## Diagnostic Tools

### check_ip_config
- Purpose: Verify adapter state, IP address, subnet, gateway, DNS servers.
- Command/tool: `ipconfig /all`
- What to look for:
  - Adapter status: media disconnected / disabled
  - IPv4 address: valid corporate range vs `169.254.x.x`
  - Default gateway: present and sane
  - DNS servers: present and corporate-approved
- Interpretation:
  - `169.254.x.x` → DHCP failure (no lease)
  - No gateway or no DNS → configuration problem
  - Media disconnected → physical/Wi-Fi problem
  - Valid config → proceed down the chain

### check_adapter_state
- Purpose: Detect disabled, missing, or malfunctioning network adapters without shell commands.
- Command/tool: predefined Python tool `get_network_adapters`
- What to look for: adapter present, enabled, connected; driver errors; adapter missing entirely
- Interpretation:
  - Adapter disabled → enable via approved tool (requires approval)
  - Adapter missing or driver error → escalate (driver/hardware)
  - Adapter OK but no link → cable/Wi-Fi issue

### check_gateway
- Purpose: Test local network reachability.
- Command/tool: `ping <default_gateway>` (gateway from check_ip_config)
- What to look for: replies, latency, packet loss
- Interpretation:
  - Replies → local network OK, continue
  - Timeout/destination unreachable → local network problem (cable, Wi-Fi, switch/VLAN)
  - High loss/latency → possible link quality problem, note and continue

### check_internet_ip
- Purpose: Test Internet reachability independent of DNS.
- Command/tool: `ping 8.8.8.8`
- What to look for: replies
- Interpretation:
  - Replies → Internet path OK; if domains fail, suspect DNS or application layer
  - Fails (but gateway OK) → upstream/Internet/proxy/VPN problem; check if VPN required by corporate policy

### check_dns
- Purpose: Test DNS name resolution.
- Command/tool: `nslookup example.com`
- What to look for: whether a DNS server responds and resolves the name to an address
- Interpretation:
  - Resolves → DNS OK; issue is likely browser/application/proxy
  - Server responded but name not found → external/service-side issue; verify with a second known-good domain before escalating
  - Timeout / "can't find server" → DNS server unreachable or wrong DNS config; run check_ip_config to inspect DNS servers
- Note: a single failed website is not DNS evidence. Confirm with ping by IP + nslookup.

## Decision Flow

User reports Internet problem
→ check_adapter_state
→ If adapter disabled → enable_adapter (with approval)
→ If adapter missing/driver error → ESCALATE
→ check_ip_config
→ If 169.254.x.x → DHCP failure → fix_renew_dhcp
→ If no gateway/DNS configured → fix_renew_dhcp, then re-check
→ check_gateway
→ If gateway fails → local network (cable/Wi-Fi/switch) → basic reseat/reconnect, then ESCALATE if unresolved
→ check_internet_ip
→ If public IP fails but gateway OK → upstream/VPN/proxy → verify VPN state → ESCALATE
→ check_dns
→ If DNS fails but IP works → DNS problem → fix_flush_dns, then fix_renew_dhcp
→ If DNS works but browser fails → application-level: check proxy settings, browser, specific site → escalate to application intent
→ Never classify as DNS based only on "website won't open".

## Safe Fixes

All commands below are executed by the Python application as predefined actions, never generated dynamically. Any state-changing action requires explicit user approval through the application. Diagnostics are read-only.

### fix_renew_dhcp
- Action: Release and renew the DHCP lease to obtain a valid IP, gateway, and DNS.
- Command: `ipconfig /release` then `ipconfig /renew`
- Requires administrator: Yes (renew/release on elevated context recommended)
- Risk: Low. Brief network interruption; VPN sessions may drop.
- When to use: 169.254.x.x address, missing gateway/DNS, after link recovery.
- Verify after action: re-run check_ip_config (expect non-169.254 address, gateway, DNS present), then check_gateway, check_internet_ip.

### fix_flush_dns
- Action: Clear the local DNS resolver cache to remove stale/negative records.
- Command: `ipconfig /flushdns`
- Requires administrator: No
- Risk: Very low. No outage; next lookups are slightly slower.
- When to use: DNS resolution failures after IP connectivity confirmed; specific domains failing that work elsewhere.
- Verify after action: re-run check_dns for the failing domain.

### fix_reset_winsock
- Action: Reset the Winsock catalog to repair corrupted network stack components.
- Command: `netsh winsock reset` (reboot required)
- Requires administrator: Yes
- Risk: Medium. Requires restart; some third-party VPN/filter software may need reconfiguration.
- When to use: IP and DNS configs look correct but all connectivity fails; browser/apps cannot connect though ping works.
- Verify after action: reboot, then re-run full diagnostic chain (check_ip_config → check_gateway → check_internet_ip → check_dns).

### fix_reset_tcpip
- Action: Reset TCP/IP stack (route table, interface config) to defaults.
- Command: `netsh int ip reset` (reboot required)
- Requires administrator: Yes
- Risk: Medium. Reboot required; static IP settings may be lost — note this to the user before approval.
- When to use: Persistent stack corruption after Winsock reset or when routing/interface behavior is clearly broken.
- Verify after action: reboot, re-run full diagnostic chain.

### fix_repair_network_stack (composite)
- Action: Sequential Winsock + TCP/IP reset.
- Command: `netsh winsock reset` then `netsh int ip reset` (reboot)
- Requires administrator: Yes
- Risk: Medium-High. Reboot required; may affect VPN clients and static settings. Requires explicit user approval.
- When to use: Multiple stack-repair attempts individually failed; connectivity broken at stack level.
- Verify after action: reboot, full diagnostic chain.

## Escalation

Stop troubleshooting and escalate when any of the following is true:

- Gateway unreachable after adapter and IP checks pass → local network/switch/VLAN issue.
- Network adapter missing, disabled and cannot be enabled, or driver error reported.
- Persistent failure after fix_repair_network_stack (safe network-stack repair exhausted).
- Corporate VPN, proxy, or network infrastructure appears involved (VPN down, proxy unreachable, authentication failures).
- Multiple users/devices report the same problem simultaneously (outage — do not keep repairing the workstation).
- Hardware failure suspected (NIC, cable plant, Wi-Fi card) or link/physical-layer errors persist.
- Network Reset (Settings > Network > Network Reset) would be required — last resort only, explicit approval, then escalate if it fails.
- Administrator privileges unavailable to execute required fixes.

## Tool Mapping

| Problem/Condition | Diagnostic Tool | Possible Fix |
|---|---|---|
| No IP / 169.254.x.x | check_ip_config | fix_renew_dhcp |
| Adapter disabled | check_adapter_state | enable_adapter (approval) |
| Adapter missing / driver error | check_adapter_state | escalate |
| Gateway unreachable | check_gateway | escalate (local network) |
| Public IP unreachable, gateway OK | check_internet_ip | verify VPN → escalate |
| DNS failure, IP OK | check_dns | fix_flush_dns → fix_renew_dhcp |
| Stack corruption suspected | check_ip_config + chain | fix_reset_winsock / fix_reset_tcpip / fix_repair_network_stack |
| Browser fails, all checks pass | check_dns (passed) | escalate (application intent) |

## Safety Rules

1. Never provide arbitrary PowerShell/CMD commands generated dynamically; only predefined tools/actions.
2. Diagnostics are read-only whenever possible.
3. Any action changing system state requires explicit user approval.
4. Do not recommend disabling firewall or antivirus.
5. Do not recommend changing DNS servers unless via an approved tool.
6. Do not recommend disabling IPv6.
7. Do not recommend uninstalling network drivers as a first-line fix.
8. Network Reset is last resort, requires explicit approval, and is followed by escalation if unsuccessful.
9. If evidence points outside the workstation (infrastructure, VPN, multi-user outage), escalate instead of guessing.
