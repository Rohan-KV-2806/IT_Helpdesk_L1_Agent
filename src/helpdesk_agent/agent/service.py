from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from ..config import CATEGORIES, MAX_AGENT_STEPS, REPORTS_ROOT, SYSTEM_PROMPT
from ..knowledge.store import load_kb
from ..llm.provider import ModelProvider, parse_json_object
from ..ticketing.service import create_ticket, save_report
from ..tools.registry import TOOLS, ToolResult


@dataclass
class AgentEvent:
    kind: str
    message: str
    payload: dict | None = None


class AgentService:
    def __init__(self, provider: ModelProvider | None = None) -> None:
        self.provider = provider or ModelProvider()

    def run(
        self,
        problem: str,
        backend: str,
        on_event: Callable[[AgentEvent], None],
        request_approval: Callable[[str, str, str], bool],
    ) -> None:
        history: list[dict] = []

        # Stage 1 is still LLM classification; there is no intent classifier.
        try:
            category, classify_result = self._classify(problem, backend)
            on_event(AgentEvent("classification", f"Category: {category}", {"category": category, "backend": classify_result.backend}))
        except UnsupportedRequest as exc:
            report = {
                "status": "TICKET_REQUIRED",
                "problem_verified": False,
                "category": None,
                "summary": problem,
                "reason": str(exc),
            }
            ticket_id, path = create_ticket(problem, None, history, str(exc))
            report["ticket_id"] = ticket_id
            save_report(report, REPORTS_ROOT)
            on_event(AgentEvent("unsupported", "I'm sorry, my Knowledge base is currently limited to Time / Date Synchronization Problem, Windows Update Stuck / Failing, Application Not Responding / Frozen App, and Internet.", {"ticket_id": ticket_id, "path": str(path)}))
            return
        except Exception as exc:
            # Internal agent error: never turn this into a user ticket.
            on_event(AgentEvent("internal_error", f"Agent classification failed: {exc}"))
            return

        try:
            kb = load_kb(category)
        except Exception as exc:
            on_event(AgentEvent("internal_error", str(exc)))
            return

        completed_tools: set[str] = set()

        for step in range(1, MAX_AGENT_STEPS + 1):
            on_event(AgentEvent("status", f"Step {step}: deciding next action…"))

            allowed = [name for name in TOOLS if name in kb]
            if not allowed:
                on_event(AgentEvent("internal_error", "The selected knowledge base does not reference any registered tools."))
                return

            context = self._build_context(category, kb, problem, history, completed_tools, allowed)
            try:
                result = self.provider.complete(SYSTEM_PROMPT, context, backend)
                data = parse_json_object(result.content)
                on_event(AgentEvent("model", f"{result.backend} decision received.", {"raw": result.content}))
            except Exception as exc:
                on_event(AgentEvent("internal_error", f"Agent decision failed: {exc}"))
                return

            status = str(data.get("status", "")).strip().upper()
            action_type = str(data.get("action_type", "")).strip().upper()
            action = str(data.get("action", "")).strip()
            message = str(data.get("message", "")).strip()
            reason = str(data.get("reason", "")).strip()

            if status == "UNSUPPORTED":
                # Category was already classified; treat a later unsupported response as model error.
                on_event(AgentEvent("internal_error", "Model changed a supported request to UNSUPPORTED during troubleshooting."))
                return

            if action_type == "ASK_USER":
                # Approval requests are handled by the GUI as a real Yes/No
                # dialog.  Small models sometimes emit ASK_USER instead of
                # FIX when they need permission for a state-changing action.
                # If exactly one currently-eligible L1 fix exists, treat this
                # ASK_USER response as an approval request for that fix.
                approval_candidates = [
                    name
                    for name in allowed
                    if TOOLS[name].category == "FIX"
                    and TOOLS[name].requires_approval
                    and self._fix_preconditions_met(name, history)
                ]

                approval_text = message.lower()
                approval_words = (
                    "approve", "approval", "allow", "permission",
                    "proceed", "authorize", "do you want", "would you like"
                )

                if len(approval_candidates) == 1 and any(word in approval_text for word in approval_words):
                    approval_action = approval_candidates[0]
                    definition = TOOLS[approval_action]
                    approved = request_approval(
                        approval_action,
                        message or definition.description,
                        reason,
                    )
                    if not approved:
                        on_event(AgentEvent("status", "Fix declined. No ticket was created."))
                        return

                    args = self._tool_args(approval_action, history)
                    on_event(AgentEvent("tool", f"Running {approval_action}…", {"tool": approval_action}))
                    result: ToolResult = definition.runner(args)
                    completed_tools.add(approval_action)
                    history.append({"tool": approval_action, "success": result.success, "output": result.output[:6000]})
                    on_event(AgentEvent("tool_result", result.output or "(no output)", {"tool": approval_action, "success": result.success}))
                    continue

                on_event(AgentEvent("ask", message or "Please provide more information."))
                return

            if action_type == "RESOLVED":
                report = {
                    "status": "RESOLVED",
                    "problem_verified": self._problem_verified(history),
                    "category": category,
                    "summary": problem,
                    "diagnosis": reason,
                    "actions_taken": history,
                    "verification_successful": True,
                    "message": message or "The issue appears to be resolved.",
                }
                path = save_report(report, REPORTS_ROOT)
                on_event(AgentEvent("resolved", message or "The issue appears to be resolved.", {"report_path": str(path), "report": report}))
                return

            if action_type == "ESCALATE":
                ticket_reason = reason or "The knowledge base requires escalation."
                ticket_id, path = create_ticket(problem, category, history, ticket_reason)
                report = {
                    "status": "TICKET_REQUIRED",
                    "problem_verified": self._problem_verified(history),
                    "category": category,
                    "summary": problem,
                    "diagnosis": reason,
                    "actions_taken": history,
                    "ticket_required": True,
                    "ticket_id": ticket_id,
                    "ticket_reason": ticket_reason,
                }
                save_report(report, REPORTS_ROOT)
                on_event(AgentEvent("ticket", f"Ticket created: {ticket_id}", {"ticket_id": ticket_id, "path": str(path), "report": report}))
                return

            # Python is the final authority on what the model may execute.
            if action not in allowed or action not in TOOLS:
                on_event(AgentEvent("internal_error", f"Model selected unavailable or KB-disallowed tool: {action}"))
                return

            definition = TOOLS[action]
            if action_type != definition.category:
                on_event(AgentEvent("internal_error", f"Action type mismatch for {action}: model={action_type}, tool={definition.category}"))
                return

            if action in completed_tools and definition.category == "DIAGNOSTIC":
                # A diagnostic that already ran normally must not be repeated.
                # Exception: immediately after a FIX, the workflow MUST verify
                # the original problem again. This is the post-fix verification
                # step, not an accidental duplicate diagnostic.
                last_tool = history[-1]["tool"] if history else None
                last_definition = TOOLS.get(last_tool) if last_tool else None
                if not (last_definition and last_definition.category == "FIX"):
                    on_event(AgentEvent("internal_error", f"Model repeated completed diagnostic: {action}"))
                    return

            if definition.category == "FIX" and not self._fix_preconditions_met(action, history):
                on_event(AgentEvent("internal_error", f"Model selected {action} without the evidence required by the troubleshooting state."))
                return

            if definition.requires_approval:
                approved = request_approval(action, message or definition.description, reason)
                if not approved:
                    on_event(AgentEvent("status", "Fix declined. No ticket was created."))
                    return

            # Some tool calls need structured target data. Extract only from the latest diagnostic output.
            args = self._tool_args(action, history)
            on_event(AgentEvent("tool", f"Running {action}…", {"tool": action}))
            result: ToolResult = definition.runner(args)
            completed_tools.add(action)
            history.append({"tool": action, "success": result.success, "output": result.output[:6000]})
            on_event(AgentEvent("tool_result", result.output or "(no output)", {"tool": action, "success": result.success}))

        ticket_reason = "Maximum troubleshooting steps reached without a confirmed resolution."
        ticket_id, path = create_ticket(problem, category, history, ticket_reason)
        report = {
            "status": "TICKET_REQUIRED",
            "problem_verified": self._problem_verified(history),
            "category": category,
            "summary": problem,
            "diagnosis": "Maximum troubleshooting steps reached without a confirmed resolution.",
            "actions_taken": history,
            "ticket_required": True,
            "ticket_id": ticket_id,
            "ticket_reason": ticket_reason,
        }
        save_report(report, REPORTS_ROOT)
        on_event(AgentEvent("ticket", f"Ticket created: {ticket_id}", {"ticket_id": ticket_id, "path": str(path), "report": report}))

    def _classify(self, problem: str, backend: str):
        prompt = f"""CLASSIFY THIS REQUEST.

Return ONLY ONE of these exact values:
Time / Date Synchronization Problem
Windows Update Stuck / Failing
Application Not Responding / Frozen App
Internet
UNSUPPORTED

Do not explain. Do not return JSON. Do not return anything else.

User request:
{problem}"""
        result = self.provider.complete(SYSTEM_PROMPT, prompt, backend, json_mode=False)
        raw = (result.content or "").strip()
        normalized = raw.lower().replace("\n", " ").strip().strip('`"')

        # Prefer an exact answer. Small models sometimes add punctuation or a
        # short wrapper despite the classification-only instruction.
        for category in CATEGORIES:
            if normalized == category.lower() or normalized.rstrip(".! ") == category.lower():
                return category, result

        if normalized == "unsupported" or "unsupported" in normalized[:80]:
            return self._unsupported_result(result)

        # Safe recovery for short model wrappers such as: "Category: Internet"
        # or "The answer is Internet.". Never infer from a long explanation.
        if len(raw) <= 80:
            for category in CATEGORIES:
                if category.lower() in normalized:
                    return category, result

        raise ValueError(f"Model returned an invalid classification: {raw[:300]}")

    @staticmethod
    def _unsupported_result(result):
        raise UnsupportedRequest("The user's request does not match a supported knowledge base.")

    @staticmethod
    def _build_context(category: str, kb: str, problem: str, history: list[dict], completed: set[str], allowed: list[str]) -> str:
        history_text = "None" if not history else "\n\n".join(
            f"Step {i}: {x['tool']} | success={x['success']}\n{x['output']}" for i, x in enumerate(history, 1)
        )
        completed_text = ", ".join(sorted(completed)) or "None"
        tools_text = "\n".join(f"- {name}: {TOOLS[name].category}; {TOOLS[name].description}" for name in allowed)
        return f'''SELECTED CATEGORY:
{category}

KNOWLEDGE BASE:
{kb}

AVAILABLE TOOLS FOR THIS KB:
{tools_text}

USER REQUEST:
{problem}

COMPLETED TOOLS:
{completed_text}

ACTUAL DIAGNOSTIC / TOOL HISTORY:
{history_text}

Choose exactly ONE next action. Follow the knowledge base. The Python application will execute only the exact action you return.'''

    @staticmethod
    def _fix_preconditions_met(action: str, history: list[dict]) -> bool:
        """Reject state-changing actions unless the observed evidence supports them.

        The KB remains the policy source; these checks are a second Python-side
        safety barrier against small-model mistakes such as jumping straight to
        DHCP renewal on a healthy connection.
        """
        outputs = {x["tool"]: x["output"] for x in history}
        if not any(x["tool"].startswith("check_") and x["success"] for x in history):
            return False

        if action == "enable_adapter":
            return "disabled" in outputs.get("check_adapter_state", "").lower()

        if action == "fix_renew_dhcp":
            text = outputs.get("check_ip_config", "")
            lower = text.lower()
            return "169.254." in lower or ("dhcp enabled" in lower and "ipv4 address" not in lower)

        if action == "fix_flush_dns":
            ip_ok = any(x["tool"] == "check_internet_ip" and x["success"] for x in history)
            dns_failed = any(x["tool"] == "check_dns" and not x["success"] for x in history)
            return ip_ok and dns_failed

        if action in {"fix_reset_winsock", "fix_reset_tcpip"}:
            return ("check_gateway" in outputs and "check_internet_ip" in outputs)

        if action == "close_unresponsive_app":
            return "not responding" in outputs.get("check_not_responding_apps", "").lower()

        if action == "fix_restart_update_services":
            text = outputs.get("check_windows_update_services", "").lower()
            return "stopped" in text or "stop" in text or "paused" in text

        if action == "fix_reset_windows_update_components":
            return "check_windows_update_error" in outputs or "check_windows_update_services" in outputs

        if action == "fix_sync_time":
            return "check_time_status" in outputs or "check_time_source" in outputs

        if action == "fix_restart_time_service":
            return "stopped" in outputs.get("check_time_service", "").lower()

        return False

    @staticmethod
    def _problem_verified(history: list[dict]) -> bool:
        return any(x["tool"].startswith("check_") and x["success"] for x in history)

    @staticmethod
    def _tool_args(action: str, history: list[dict]) -> dict:
        if action != "close_unresponsive_app":
            return {}
        # Use the most recent not-responding diagnostic to identify a target.
        for item in reversed(history):
            if item["tool"] == "check_not_responding_apps":
                text = item["output"]
                # PowerShell table: ProcessName Id MainWindowTitle Responding
                for line in text.splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and parts[1].isdigit():
                        return {"process_name": parts[0], "pid": parts[1]}
        return {}


class UnsupportedRequest(Exception):
    pass
