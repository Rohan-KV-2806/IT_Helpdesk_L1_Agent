from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..config import INTENTS, MAX_AGENT_STEPS
from ..knowledge.store import load_kb
from ..llm.provider import ModelProvider, parse_json_object
from ..ticketing.service import create_ticket
from ..tools.registry import TOOLS, ToolResult

SYSTEM_PROMPT = """
You are a STRICT Windows IT Helpdesk L1 decision engine.

Your job is to choose exactly ONE next action using ONLY the
knowledge base and the AVAILABLE TOOLS supplied in the input.

ABSOLUTE RULES:

1. The action MUST be copied EXACTLY from AVAILABLE TOOLS.
2. NEVER invent, rename, abbreviate, or guess a tool name.
3. NEVER output a command, shell command, PowerShell command,
   function name, or description as the action.
4. NEVER choose a tool that is not listed in AVAILABLE TOOLS.
5. Choose ONLY ONE action per response.
6. Do NOT skip required diagnostic steps from the knowledge base.
7. Diagnostics are read-only and may run automatically.
8. FIX actions change the computer and require user approval.
9. Do not claim that a tool has already been executed.
10. Do not assume diagnostic results.
11. Use previous diagnostic results when deciding the next step.
12. If the KB requires information that is missing, use ASK_USER.
13. Use ESCALATE only when the KB says to escalate or there is
    no safe supported L1 action.
14. Use RESOLVED only when previous evidence confirms the issue
    is fixed.
15. If no valid tool is appropriate, use ASK_USER or ESCALATE.
16. The value of "action" MUST be empty for ASK_USER, ESCALATE,
    and RESOLVED.

OUTPUT ONLY VALID JSON.

EXACT FORMAT:

{
  "action_type": "DIAGNOSTIC|FIX|ESCALATE|RESOLVED|ASK_USER",
  "action": "EXACT_TOOL_NAME_OR_EMPTY",
  "message": "SHORT_MESSAGE",
  "reason": "SHORT_REASON"
}

FINAL CHECK BEFORE ANSWERING:

- Is action_type valid?
- If action_type is DIAGNOSTIC or FIX, is action an EXACT
  character-for-character match of one item in AVAILABLE TOOLS?
- If not, DO NOT invent another name. Use ASK_USER or ESCALATE.
- Return JSON only.
""".strip()

INTENT_PROMPT = """
Classify this employee's IT problem into exactly ONE of these intents:
{intents}

Return ONLY JSON:
{{"intent":"EXACT_INTENT"}}

User problem:
{problem}
""".strip()


@dataclass
class AgentEvent:
    kind: str
    message: str
    payload: dict | None = None


class AgentService:
    def __init__(self, provider: ModelProvider | None = None) -> None:
        self.provider = provider or ModelProvider()

    def infer_intent(self, problem: str) -> tuple[str, str]:
        prompt = INTENT_PROMPT.format(intents="\n".join(f"- {x}" for x in INTENTS), problem=problem)
        result = self.provider.complete(SYSTEM_PROMPT, prompt)
        data = parse_json_object(result.content)
        intent = str(data.get("intent", "")).strip()
        if intent not in INTENTS:
            raise ValueError(f"Unknown intent from model: {intent}")
        return intent, result.backend

    def run(
        self,
        problem: str,
        forced_intent: str | None,
        on_event: Callable[[AgentEvent], None],
        request_approval: Callable[[str, str, str], bool],
    ) -> None:
        history: list[dict] = []

        # Resolve intent only when the debug menu has not forced one.
        if forced_intent:
            intent = forced_intent
            backend = "Debug"
        else:
            try:
                intent, backend = self.infer_intent(problem)
                on_event(AgentEvent("intent", f"Intent detected: {intent}", {"intent": intent, "backend": backend}))
            except Exception as exc:  # noqa: BLE001
                on_event(AgentEvent("error", f"Could not determine intent: {exc}"))
                self._make_ticket(problem, forced_intent or "OTHER_UNKNOWN", history, "Intent could not be determined safely.", on_event)
                return

        try:
            kb = load_kb(intent)
        except FileNotFoundError as exc:
            on_event(AgentEvent("error", str(exc)))
            self._make_ticket(problem, intent, history, "No knowledge-base playbook is available for this intent.", on_event)
            return

        for step in range(1, MAX_AGENT_STEPS + 1):
            on_event(AgentEvent("status", f"Planning step {step}…"))
            kb_tool_names = [name for name in TOOLS if name in kb]
            tool_list = "\n".join(
                f"- {name}: {TOOLS[name].category}; approval={TOOLS[name].requires_approval}"
                for name in kb_tool_names
            ) or "- No allowlisted tool is referenced by this KB."
            context = f"""
INTENT: {intent}

KNOWLEDGE BASE:
{kb}

AVAILABLE TOOLS:
{tool_list}

USER PROBLEM:
{problem}

PREVIOUS STEPS:
{_history_text(history)}

Choose the next action now.
""".strip()

            try:
                model_result = self.provider.complete(SYSTEM_PROMPT, context)
                data = parse_json_object(model_result.content)
                on_event(AgentEvent("model", f"{model_result.backend} decision received.", {"backend": model_result.backend, "raw": model_result.content}))
            except Exception as exc:  # noqa: BLE001
                on_event(AgentEvent("error", f"Agent decision failed: {exc}"))
                self._make_ticket(problem, intent, history, "The agent could not produce a safe structured decision.", on_event)
                return

            action_type = str(data.get("action_type", "")).upper().strip()
            action = str(data.get("action", "")).strip()
            message = str(data.get("message", "")).strip()
            reason = str(data.get("reason", "")).strip()

            if action_type == "ASK_USER":
                on_event(AgentEvent("ask", message or "Please provide more information."))
                return

            if action_type == "RESOLVED":
                on_event(AgentEvent("resolved", message or "The issue appears to be resolved."))
                return

            if action_type == "ESCALATE":
                self._make_ticket(problem, intent, history, reason or "Outside safe L1 scope.", on_event)
                return

            if action not in TOOLS:
                on_event(AgentEvent("error", f"Model selected unavailable tool: {action}"))
                self._make_ticket(problem, intent, history, "Model selected a tool that is not allowlisted.", on_event)
                return

            definition = TOOLS[action]
            if action_type != definition.category:
                on_event(AgentEvent("error", f"Action type mismatch for {action}."))
                self._make_ticket(problem, intent, history, "Unsafe action type mismatch.", on_event)
                return

            if definition.requires_approval:
                approved = request_approval(action, message or definition.description, reason)
                if not approved:
                    on_event(AgentEvent("status", "Fix declined by user. No ticket was created."))
                    return

            on_event(AgentEvent("tool", f"Running {action}…", {"tool": action, "category": definition.category}))
            result: ToolResult = definition.runner({})
            history.append({
                "tool": action,
                "success": result.success,
                "output": result.output[:5000],
            })
            on_event(AgentEvent(
                "tool_result",
                result.output or "(no output)",
                {"tool": action, "success": result.success}
            ))

            if action_type == "FIX" and not result.success:
                on_event(AgentEvent("status", "The attempted fix failed; evaluating the next safe step."))

        self._make_ticket(problem, intent, history, "Maximum troubleshooting steps reached without a confirmed resolution.", on_event)

    @staticmethod
    def _make_ticket(problem: str, intent: str, history: list[dict], reason: str, on_event: Callable[[AgentEvent], None]) -> None:
        ticket_id, path = create_ticket(problem, intent, history, reason)
        on_event(AgentEvent("ticket", f"Ticket created: {ticket_id}", {"ticket_id": ticket_id, "path": str(path)}))


def _history_text(history: list[dict]) -> str:
    if not history:
        return "None"
    chunks = []
    for i, item in enumerate(history, start=1):
        chunks.append(f"Step {i}: {item['tool']} | success={item['success']}\n{item['output']}")
    return "\n\n".join(chunks)
