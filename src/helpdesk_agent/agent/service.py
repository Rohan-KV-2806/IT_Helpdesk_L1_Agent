from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..config import KB_ROOT, MAX_AGENT_STEPS, REPORTS_ROOT, SYSTEM_PROMPT
from ..knowledge.store import build_kb_catalog, discover_kbs, load_kb
from ..llm.provider import ModelProvider, parse_json_object
from ..ticketing.service import create_ticket, save_report
from ..tools.actions import ToolResult, resolve_tool


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

        try:
            kb_filename, classify_result = self._classify(problem, backend)
            on_event(
                AgentEvent(
                    "classification",
                    f"Knowledge base: {kb_filename}",
                    {"category": kb_filename, "backend": classify_result.backend},
                )
            )
        except UnsupportedRequest as exc:
            message = self._unsupported_message()
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
            on_event(AgentEvent("unsupported", message, {"ticket_id": ticket_id, "path": str(path)}))
            return
        except Exception as exc:
            on_event(AgentEvent("internal_error", f"Agent classification failed: {exc}"))
            return

        try:
            kb = load_kb(kb_filename)
        except Exception as exc:
            on_event(AgentEvent("internal_error", str(exc)))
            return

        # The KB defines the executable action names and whether each one is a
        # diagnostic or a fix. Python does not maintain a category-specific map.
        kb_tools = self._parse_kb_tools(kb)
        if not kb_tools:
            on_event(AgentEvent("internal_error", f"The selected KB '{kb_filename}' does not define any executable diagnostic or fix tools."))
            return

        completed_tools: list[str] = []

        for step in range(1, MAX_AGENT_STEPS + 1):
            on_event(AgentEvent("status", f"Step {step}: deciding next action…"))

            context = self._build_context(kb_filename, kb, problem, history, kb_tools)
            try:
                result = self.provider.complete(SYSTEM_PROMPT, context, backend)
                try:
                    data = parse_json_object(result.content)
                except Exception:
                    retry_context = context + (
                        "\n\nFORMAT CORRECTION: Your previous response was not valid JSON. "
                        "Return exactly one complete JSON object matching the troubleshooting output contract. "
                        "Do not include prose, markdown, or reasoning outside the JSON object."
                    )
                    retry_result = self.provider.complete(SYSTEM_PROMPT, retry_context, backend)
                    data = parse_json_object(retry_result.content)
                    on_event(AgentEvent("model", f"{retry_result.backend} corrected decision received.", {"raw": retry_result.content}))
                else:
                    on_event(AgentEvent("model", f"{result.backend} decision received.", {"raw": result.content}))
            except Exception as exc:
                on_event(AgentEvent("internal_error", f"Agent decision failed: {exc}"))
                return

            status = str(data.get("status", "")).strip().upper()
            action_type = str(data.get("action_type", "")).strip().upper()
            action = str(data.get("action", "")).strip()
            message = str(data.get("message", "")).strip()
            reason = str(data.get("reason", "")).strip()
            arguments = data.get("arguments", {})

            if not isinstance(arguments, dict):
                on_event(AgentEvent("internal_error", "Model returned malformed tool arguments."))
                return

            if status == "UNSUPPORTED":
                on_event(AgentEvent("internal_error", "Model returned UNSUPPORTED after a supported KB was selected."))
                return

            if action_type == "ASK_USER":
                if action:
                    on_event(AgentEvent("internal_error", "ASK_USER must not contain a tool action."))
                    return
                retry_context = context + (
                    "\n\nPROTOCOL CORRECTION: ASK_USER is only for information or a user/physical test "
                    "explicitly required by the knowledge base. It must never be used to request approval for a FIX. "
                    "The application handles FIX approval through its Yes/No dialog. Reconsider the next action "
                    "and return exactly one JSON decision."
                )
                try:
                    retry_result = self.provider.complete(SYSTEM_PROMPT, retry_context, backend)
                    data = parse_json_object(retry_result.content)
                    on_event(AgentEvent("model", f"{retry_result.backend} corrected decision received.", {"raw": retry_result.content}))
                    status = str(data.get("status", "")).strip().upper()
                    action_type = str(data.get("action_type", "")).strip().upper()
                    action = str(data.get("action", "")).strip()
                    message = str(data.get("message", "")).strip()
                    reason = str(data.get("reason", "")).strip()
                    arguments = data.get("arguments", {})
                    if not isinstance(arguments, dict):
                        raise ValueError("Corrected decision returned malformed tool arguments.")
                except Exception as exc:
                    on_event(AgentEvent("internal_error", f"Agent decision failed after ASK_USER correction: {exc}"))
                    return
                if action_type == "ASK_USER":
                    on_event(AgentEvent("internal_error", "Model continued to use ASK_USER where the application protocol requires a direct FIX action for approval."))
                    return

            if action_type == "RESOLVED":
                if action:
                    on_event(AgentEvent("internal_error", "RESOLVED must not contain a tool action."))
                    return
                problem_verified = data.get("problem_verified")
                verification_successful = data.get("verification_successful")
                if not isinstance(problem_verified, bool) or not isinstance(verification_successful, bool):
                    on_event(AgentEvent("internal_error", "RESOLVED decision must include boolean problem_verified and verification_successful fields."))
                    return
                report = {
                    "status": "RESOLVED",
                    "problem_verified": problem_verified,
                    "category": kb_filename,
                    "summary": problem,
                    "diagnosis": reason,
                    "actions_taken": history,
                    "verification_successful": verification_successful,
                    "message": message or "The issue appears to be resolved.",
                }
                path = save_report(report, REPORTS_ROOT)
                on_event(AgentEvent("resolved", report["message"], {"report_path": str(path), "report": report}))
                return

            if action_type == "ESCALATE":
                if action:
                    on_event(AgentEvent("internal_error", "ESCALATE must not contain a tool action."))
                    return
                problem_verified = data.get("problem_verified")
                verification_successful = data.get("verification_successful")
                if not isinstance(problem_verified, bool) or not isinstance(verification_successful, bool):
                    on_event(AgentEvent("internal_error", "ESCALATE decision must include boolean problem_verified and verification_successful fields."))
                    return
                ticket_reason = reason or "The knowledge base requires escalation."
                ticket_id, path = create_ticket(problem, kb_filename, history, ticket_reason)
                report = {
                    "status": "TICKET_REQUIRED",
                    "problem_verified": problem_verified,
                    "category": kb_filename,
                    "summary": problem,
                    "diagnosis": reason,
                    "actions_taken": history,
                    "verification_successful": verification_successful,
                    "ticket_required": True,
                    "ticket_id": ticket_id,
                    "ticket_reason": ticket_reason,
                }
                save_report(report, REPORTS_ROOT)
                on_event(AgentEvent("ticket", f"Ticket created: {ticket_id}", {"ticket_id": ticket_id, "path": str(path), "report": report}))
                return

            if status != "ACTION_REQUIRED":
                on_event(AgentEvent("internal_error", f"Unsupported model status: {status}"))
                return

            if action_type not in {"DIAGNOSTIC", "FIX"}:
                on_event(AgentEvent("internal_error", f"Unsupported action type: {action_type}"))
                return

            # Action permission comes from the selected KB, not from Python.
            if action not in kb_tools:
                on_event(AgentEvent("internal_error", f"Model selected a tool not documented by the selected KB: {action}"))
                return

            kb_action_type = kb_tools[action]
            if kb_action_type != action_type:
                on_event(AgentEvent("internal_error", f"Action type mismatch for KB tool '{action}'."))
                return

            # Resolve the exact tool name to a Python function. There is no
            # central tool registry; the function name itself is the binding.
            runner = resolve_tool(action)
            if runner is None:
                on_event(AgentEvent("internal_error", f"The selected KB requires tool '{action}', but no Python implementation exists for that exact tool name."))
                return

            if kb_action_type == "DIAGNOSTIC" and action in completed_tools:
                previous_tool = history[-1]["tool"] if history else None
                previous_type = kb_tools.get(previous_tool) if previous_tool else None
                if previous_type != "FIX":
                    on_event(AgentEvent("internal_error", f"The diagnostic '{action}' was already completed and is not a valid repeated step."))
                    return

            if kb_action_type == "FIX" and not self._has_successful_diagnostic(history, kb_tools):
                on_event(AgentEvent("internal_error", "A state-changing tool was selected before a successful diagnostic."))
                return

            if action in completed_tools and kb_action_type == "FIX":
                on_event(AgentEvent("internal_error", f"The same fix was already attempted: {action}"))
                return

            # Every KB-defined FIX is treated as state-changing. The GUI owns
            # the approval interaction and returns only True/False here.
            if kb_action_type == "FIX":
                approved = request_approval(action, message or f"Run KB-defined fix: {action}", reason)
                if not approved:
                    on_event(AgentEvent("status", "Fix declined. No ticket was created."))
                    return

            on_event(AgentEvent("tool", f"Running {action}…", {"tool": action, "arguments": arguments}))
            try:
                tool_result: ToolResult = runner(arguments)
            except Exception as exc:
                on_event(AgentEvent("internal_error", f"Tool '{action}' failed inside the application: {exc}"))
                return

            completed_tools.append(action)
            history.append(
                {
                    "tool": action,
                    "success": tool_result.success,
                    "arguments": arguments,
                    "output": tool_result.output[:6000],
                }
            )
            on_event(AgentEvent("tool_result", tool_result.output or "(no output)", {"tool": action, "success": tool_result.success}))

        on_event(AgentEvent("internal_error", f"The agent reached the maximum of {MAX_AGENT_STEPS} reasoning steps without a final KB decision. No ticket was created because this is an internal agent failure."))

    def _classify(self, problem: str, backend: str):
        candidates = discover_kbs()
        if not candidates:
            raise RuntimeError(f"No Markdown knowledge-base files were found in {KB_ROOT}")

        prompt = f"""CLASSIFY THIS USER REQUEST.

Return EXACTLY ONE of the candidate filenames below, or UNSUPPORTED.

CANDIDATE KNOWLEDGE-BASE FILES:
{build_kb_catalog()}

USER REQUEST:
{problem}
"""
        result = self.provider.complete(SYSTEM_PROMPT, prompt, backend, json_mode=False)
        raw = (result.content or "").strip()
        normalized = self._normalize_classifier_output(raw)

        if normalized in candidates:
            return normalized, result
        if normalized == "UNSUPPORTED":
            raise UnsupportedRequest("The user's request does not match any discovered knowledge-base file.")

        raise ValueError(f"Model returned an invalid knowledge-base filename: {raw[:500]}")

    @staticmethod
    def _normalize_classifier_output(raw: str) -> str:
        value = (raw or "").strip().strip("`\"'")
        if value.lower().startswith("kb:"):
            value = value[3:].strip()
        if value.lower().startswith("knowledge base:"):
            value = value[len("knowledge base:") :].strip()
        return value.rstrip(".! ")

    @staticmethod
    def _parse_kb_tools(kb: str) -> dict[str, str]:
        """Parse executable tool names directly from the KB's AVAILABLE TOOLS section."""
        match = re.search(r"(?ms)^##\s+\d+\.\s+AVAILABLE TOOLS\b(.*?)(?=^##\s+|\Z)", kb)
        section = match.group(1) if match else kb
        tools: dict[str, str] = {}
        current_type: str | None = None

        for line in section.splitlines():
            heading = re.match(r"^###\s+(.+?)\s*$", line)
            if heading:
                title = heading.group(1).lower()
                if "diagnostic" in title:
                    current_type = "DIAGNOSTIC"
                elif "fix" in title or "l1 action" in title or "l1 fix" in title:
                    current_type = "FIX"
                else:
                    current_type = None
                continue

            if current_type is None:
                continue

            cell = re.match(r"^\|\s*`([A-Za-z_][A-Za-z0-9_]*)`\s*\|", line)
            if cell:
                tools[cell.group(1)] = current_type

        return tools

    @staticmethod
    def _build_context(
        kb_filename: str,
        kb: str,
        problem: str,
        history: list[dict],
        kb_tools: dict[str, str],
    ) -> str:
        history_text = "None" if not history else "\n\n".join(
            f"Step {i}: {item['tool']} | success={item['success']}\n"
            f"Arguments: {item.get('arguments', {})}\n"
            f"{item['output']}"
            for i, item in enumerate(history, 1)
        )
        tool_names = "\n".join(f"- {name}: {tool_type}" for name, tool_type in sorted(kb_tools.items()))

        return f'''SELECTED KNOWLEDGE-BASE FILE:
{kb_filename}

KNOWLEDGE BASE (SOURCE OF TRUTH):
{kb}

EXECUTABLE ACTION NAMES DISCOVERED FROM THIS KB:
{tool_names}

USER REQUEST:
{problem}

ACTUAL TOOL HISTORY:
{history_text}

Choose exactly ONE next action. Follow the knowledge base exactly. The Python application will execute only an exact action name documented by this selected KB and for which a Python implementation exists. For any FIX action, the application will show its Yes/No approval dialog automatically. Do not use ASK_USER to request FIX approval.'''

    @staticmethod
    def _has_successful_diagnostic(history: list[dict], kb_tools: dict[str, str]) -> bool:
        return any(
            item.get("success") and kb_tools.get(item.get("tool")) == "DIAGNOSTIC"
            for item in history
        )

    @staticmethod
    def _unsupported_message() -> str:
        filenames = sorted(discover_kbs())
        if not filenames:
            return "I'm sorry, my knowledge base is currently unavailable because no Markdown knowledge-base files were found."
        joined = ", ".join(filenames)
        return f"I'm sorry, my Knowledge base is currently limited to: {joined}."


class UnsupportedRequest(Exception):
    pass
