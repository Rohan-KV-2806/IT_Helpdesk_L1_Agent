from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Literal

from ..config import (
    CLASSIFIER_SYSTEM_PROMPT,
    KB_ROOT,
    ORCHESTRATOR_SYSTEM_PROMPT,
    PROTOCOL_REPAIR_PROMPT,
    REPORTS_ROOT,
)
from ..settings import load_settings
from ..knowledge.store import build_kb_catalog, discover_kbs, load_kb
from ..llm.provider import ModelProvider, ModelProviderError, parse_json_object
from ..ticketing.service import create_ticket, save_report, update_ticket_email
from ..notifications.email import EmailDraft, generate_ticket_email, is_valid_email, send_email
from ..tools.capabilities import ToolDefinition, ToolResult, get_capabilities


@dataclass(frozen=True)
class ApprovalResponse:
    choice: Literal["yes", "no", "idea"]
    instruction: str = ""


@dataclass(frozen=True)
class AgentEvent:
    kind: str
    message: str
    payload: dict[str, Any] | None = None


class UnsupportedRequest(Exception):
    pass


class AgentService:
    """KB-guided L1 agent with an LLM-controlled tool loop.

    Python is deliberately responsible for safety, validation, permissions,
    and execution. The LLM decides the next troubleshooting action.
    """

    def __init__(self, provider: ModelProvider | None = None):
        self.provider = provider or ModelProvider()
        self.capabilities = get_capabilities()

    def run(
        self,
        problem: str,
        backend: str,
        on_event: Callable[[AgentEvent], None],
        request_approval: Callable[[str, str, str], ApprovalResponse],
        request_user_decision: Callable[[str, str, str], ApprovalResponse] | None = None,
    ) -> None:
        problem = problem.strip()
        if not problem:
            on_event(AgentEvent("internal_error", "The request was empty."))
            return

        try:
            kb_id = self._classify(problem, backend)
            on_event(AgentEvent("classification", f"Classification: {kb_id}", {"category": kb_id, "backend": backend}))
            if kb_id == "GENERAL_CHAT":
                on_event(
                    AgentEvent(
                        "general_chat",
                        "Hello. I'm your L1 IT Helpdesk Agent. Please tell me the IT problem you'd like me to check or troubleshoot.",
                        {"backend": backend},
                    )
                )
                return
            if kb_id == "GENERAL_SUPPORT":
                self._handle_general_support(
                    problem, backend, request_user_decision, on_event
                )
                return
            kb = load_kb(kb_id)
        except UnsupportedRequest as exc:
            self._handle_unsupported(problem, str(exc), backend, request_user_decision, on_event)
            return
        except Exception as exc:
            on_event(AgentEvent("internal_error", f"Agent startup failed: {exc}"))
            return

        try:
            allowed = self._kb_capabilities(kb)
        except Exception as exc:
            on_event(AgentEvent("internal_error", f"Invalid selected knowledge base: {exc}"))
            return

        missing = sorted(name for name in allowed if name not in self.capabilities)
        if missing:
            on_event(
                AgentEvent(
                    "internal_error",
                    "The selected knowledge base references unavailable executable capabilities: " + ", ".join(missing),
                )
            )
            return

        # Session state is deliberately explicit. The LLM remains the
        # orchestrator; these values are hard safety/integrity guards.
        history: list[dict[str, Any]] = []
        user_feedback: list[str] = []
        attempted_fixes: set[tuple[str, str]] = set()
        declined_fixes: set[tuple[str, str]] = set()
        failed_fixes: set[tuple[str, str]] = set()
        repeated_tools: dict[tuple[str, str], int] = {}
        fixes_executed: list[str] = []
        post_fix_verification_required = False
        last_verification_success = True
        last_diagnostic_success = False
        resolution_declined = False

        runtime_settings = load_settings()
        max_agent_steps = runtime_settings.generation.max_agent_steps if runtime_settings.generation else 14
        for step in range(1, max_agent_steps + 1):
            on_event(AgentEvent("status", f"Step {step}: LLM deciding next action…"))
            context = self._build_orchestrator_context(
                kb_id=kb_id,
                kb=kb,
                problem=problem,
                history=history,
                allowed=allowed,
                user_feedback=user_feedback,
                attempted_fixes=attempted_fixes,
                failed_fixes=failed_fixes,
                post_fix_verification_required=post_fix_verification_required,
            )

            try:
                decision = self._get_decision_with_repair(context, backend)
            except Exception as exc:
                on_event(AgentEvent("internal_error", f"Agent decision failed: {exc}"))
                return

            try:
                normalized = self._normalize_decision(decision, kb_id)
            except ValueError as exc:
                # Give the LLM a bounded opportunity to repair a structurally
                # invalid decision without executing anything unsafe.
                repaired = self._repair_decision(context, backend, str(exc))
                if repaired is None:
                    on_event(AgentEvent("internal_error", f"LLM returned an invalid decision: {exc}"))
                    return
                try:
                    normalized = self._normalize_decision(repaired, kb_id)
                except ValueError as second_exc:
                    on_event(AgentEvent("internal_error", f"LLM returned an invalid decision after repair: {second_exc}"))
                    return

            on_event(AgentEvent("model", "LLM decision received.", {"decision": normalized}))
            decision_type = normalized["decision"]

            if decision_type == "resolved":
                # The LLM cannot close a session before it has at least one
                # successful diagnostic execution.
                if not any(entry["category"] == "DIAGNOSTIC" for entry in history) or not last_diagnostic_success:
                    repaired = self._repair_decision(
                        context,
                        backend,
                        "A RESOLVED decision is not allowed yet. At least one diagnostic capability must execute successfully first. Select a KB-defined TEST/DIAGNOSIS capability.",
                    )
                    if repaired is None:
                        on_event(AgentEvent("internal_error", "LLM attempted to resolve before usable diagnostic evidence."))
                        return
                    try:
                        normalized = self._normalize_decision(repaired, kb_id)
                    except ValueError as exc:
                        on_event(AgentEvent("internal_error", f"LLM could not repair the missing diagnostic step: {exc}"))
                        return
                    if normalized["decision"] != "tool_call":
                        on_event(AgentEvent("internal_error", "LLM repair did not select a diagnostic capability."))
                        return
                    decision_type = "tool_call"
                else:
                    # After every state-changing action, the next useful
                    # evidence must come from a KB-defined verification tool.
                    if fixes_executed and (post_fix_verification_required or not last_verification_success):
                        repaired = self._repair_decision(
                            context,
                            backend,
                            "A FIX was executed but the latest required verification is missing or failed. Select a KB-defined Verification diagnostic before resolving.",
                        )
                        if repaired is None:
                            on_event(AgentEvent("internal_error", "LLM attempted to declare success before successful verification."))
                            return
                        try:
                            normalized = self._normalize_decision(repaired, kb_id)
                        except ValueError as exc:
                            on_event(AgentEvent("internal_error", f"LLM could not repair the missing verification step: {exc}"))
                            return
                        if normalized["decision"] != "tool_call":
                            on_event(AgentEvent("internal_error", "LLM repair did not select the required verification capability."))
                            return
                        decision_type = "tool_call"
                    else:
                        # Do not assume that successful technical verification means
                        # the human's original symptom is gone. Give the user the final
                        # say through the same decision window used for state changes.
                        if resolution_declined:
                            repaired = self._repair_decision(
                                context,
                                backend,
                                "The user explicitly said the problem is NOT solved. Do not declare RESOLVED again. Choose another KB-supported diagnostic/fix, ask for the required user test, or escalate.",
                            )
                            if repaired is None:
                                on_event(AgentEvent("internal_error", "LLM could not continue after the user reported that the problem remains."))
                                return
                            try:
                                normalized = self._normalize_decision(repaired, kb_id)
                            except ValueError as exc:
                                on_event(AgentEvent("internal_error", f"LLM returned an invalid recovery decision: {exc}"))
                                return
                            if normalized["decision"] == "resolved":
                                on_event(AgentEvent("internal_error", "LLM attempted to resolve again after the user said the problem remains."))
                                return
                            decision_type = normalized["decision"]
                        else:
                            confirmation = request_approval(
                                "CONFIRM_RESOLUTION",
                                normalized["message"],
                                normalized["reason"],
                            )
                            if confirmation.choice == "yes":
                                report = self._make_resolved_report(
                                    problem=problem,
                                    kb_id=kb_id,
                                    history=history,
                                    decision=normalized,
                                )
                                save_report(report, REPORTS_ROOT)
                                on_event(AgentEvent("resolved", normalized["message"], {"report": report}))
                                return
                            if confirmation.choice == "no":
                                resolution_declined = True
                                user_feedback.append(
                                    "USER CONFIRMED THE PROBLEM IS NOT SOLVED. Do not declare resolved. Reconsider the KB evidence and choose another supported action, required user test, or escalation."
                                )
                                on_event(AgentEvent("status", "Thanks. I’ll continue troubleshooting instead of marking the issue resolved."))
                                continue
                            instruction = confirmation.instruction.strip()
                            if instruction:
                                user_feedback.append(f"USER DECISION INSTRUCTION AFTER PROPOSED RESOLUTION: {instruction}")
                            else:
                                user_feedback.append("The user chose Your idea but supplied no additional instruction. Continue troubleshooting without making a system change.")
                            resolution_declined = True
                            on_event(AgentEvent("status", "Your instruction was sent to the LLM. I’ll continue troubleshooting."))
                            continue

                # A repair converted a premature RESOLVED decision into a
                # tool call. Continue through the normal safety/execution path.

            if decision_type == "escalate":
                self._handle_escalation(problem, kb_id, history, normalized, backend, request_user_decision, on_event)
                return

            if decision_type == "ask_user":
                # User-input decisions are interactive checkpoints, not dead ends.
                # Keep them inside the same session so the answer goes directly back
                # to the orchestrator instead of being classified as a new request.
                if request_user_decision is None:
                    on_event(AgentEvent("ask", normalized["message"], {"reason": normalized["reason"]}))
                    return
                response = request_user_decision("ASK_USER", normalized["message"], normalized["reason"])
                if response.choice == "yes":
                    user_feedback.append(
                        f"USER CONFIRMED THE PROPOSED USER DECISION: {normalized['message']}"
                    )
                elif response.choice == "no":
                    user_feedback.append(
                        f"USER DECLINED THE PROPOSED USER DECISION: {normalized['message']}"
                    )
                else:
                    instruction = response.instruction.strip()
                    if instruction:
                        user_feedback.append(f"USER DECISION INSTRUCTION: {instruction}")
                    else:
                        user_feedback.append("The user chose Your idea but supplied no instruction.")
                on_event(AgentEvent("status", "Your response was sent to the LLM. Continuing the current troubleshooting session…"))
                continue

            tool_name = normalized["tool"]
            arguments = normalized["arguments"]
            phase = normalized["phase"]
            definition = self.capabilities.get(tool_name)
            if definition is None:
                on_event(AgentEvent("internal_error", f"LLM selected unavailable capability '{tool_name}'."))
                return

            if tool_name not in allowed:
                repaired = self._repair_decision(
                    context,
                    backend,
                    f"Capability '{tool_name}' is not documented by the selected KB. Choose only a capability from the supplied KB tool list.",
                )
                if repaired is None:
                    on_event(AgentEvent("internal_error", f"LLM selected a capability not documented by the selected KB: {tool_name}"))
                    return
                normalized = self._normalize_decision(repaired, kb_id)
                if normalized["decision"] != "tool_call":
                    # Process a valid non-tool repaired decision on the next
                    # loop iteration so every turn still has one clear action.
                    if normalized["decision"] == "resolved":
                        on_event(AgentEvent("internal_error", "LLM repair attempted to resolve without executing the required tool."))
                    elif normalized["decision"] == "escalate":
                        self._handle_escalation(problem, kb_id, history, normalized, backend, request_user_decision, on_event)
                    else:
                        on_event(AgentEvent("ask", normalized.get("message", "More user information is required.")))
                    return
                tool_name = normalized["tool"]
                arguments = normalized["arguments"]
                phase = normalized["phase"]
                definition = self.capabilities.get(tool_name)
                if definition is None or tool_name not in allowed:
                    on_event(AgentEvent("internal_error", "LLM could not select a valid KB capability after protocol repair."))
                    return

            if definition.category != "DIAGNOSTIC" and definition.category != "FIX":
                on_event(AgentEvent("internal_error", f"Capability '{tool_name}' has an unsupported execution category."))
                return

            if not self._validate_arguments(arguments, definition):
                reason = f"Arguments for '{tool_name}' do not match the declared capability schema."
                repaired = self._repair_decision(context, backend, reason)
                if repaired is None:
                    on_event(AgentEvent("internal_error", reason))
                    return
                normalized = self._normalize_decision(repaired, kb_id)
                if normalized["decision"] != "tool_call":
                    on_event(AgentEvent("internal_error", "LLM repair did not return the required capability call."))
                    return
                tool_name = normalized["tool"]
                arguments = normalized["arguments"]
                phase = normalized["phase"]
                definition = self.capabilities.get(tool_name)
                if definition is None or tool_name not in allowed or not self._validate_arguments(arguments, definition):
                    on_event(AgentEvent("internal_error", "LLM returned invalid capability arguments after protocol repair."))
                    return

            fingerprint = (tool_name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))
            repeated_tools[fingerprint] = repeated_tools.get(fingerprint, 0) + 1

            verification_tools_for_repeat_guard = set(self._tool_group(kb, "Verification"))
            repeat_limit = 3 if post_fix_verification_required and tool_name in verification_tools_for_repeat_guard else 2
            if repeated_tools[fingerprint] > repeat_limit:
                on_event(
                    AgentEvent(
                        "internal_error",
                        f"LLM entered a repeated tool loop with '{tool_name}'. No ticket was created because this is an agent-loop failure.",
                    )
                )
                return

            if definition.category == "DIAGNOSTIC":
                if post_fix_verification_required:
                    verification_tools = set(self._tool_group(kb, "Verification"))
                    if tool_name not in verification_tools:
                        repaired = self._repair_decision(
                            context,
                            backend,
                            f"The previous action was a FIX. The next action must be a verification/test capability from this KB: {sorted(verification_tools)}.",
                        )
                        if repaired is None:
                            on_event(AgentEvent("internal_error", "LLM could not select the mandatory post-fix verification."))
                            return
                        normalized = self._normalize_decision(repaired, kb_id)
                        if normalized["decision"] != "tool_call" or normalized["tool"] not in verification_tools:
                            on_event(AgentEvent("internal_error", "LLM repeatedly skipped mandatory post-fix verification."))
                            return
                        tool_name = normalized["tool"]
                        arguments = normalized["arguments"]
                        phase = normalized["phase"]
                        definition = self.capabilities[tool_name]

            if definition.category == "FIX":
                diagnostic_history = [entry for entry in history if entry["category"] == "DIAGNOSTIC"]
                if not diagnostic_history or not last_diagnostic_success:
                    repaired = self._repair_decision(
                        context,
                        backend,
                        "A FIX cannot run yet. At least one diagnostic tool must execute first and provide evidence.",
                    )
                    if repaired is None:
                        on_event(AgentEvent("internal_error", "LLM attempted a FIX before diagnostics."))
                        return
                    normalized = self._normalize_decision(repaired, kb_id)
                    if normalized["decision"] != "tool_call":
                        on_event(AgentEvent("internal_error", "LLM repair did not select a diagnostic."))
                        return
                    tool_name = normalized["tool"]
                    arguments = normalized["arguments"]
                    phase = normalized["phase"]
                    definition = self.capabilities.get(tool_name)
                    if definition is None or definition.category != "DIAGNOSTIC" or tool_name not in allowed:
                        on_event(AgentEvent("internal_error", "LLM returned a non-diagnostic after FIX-order repair."))
                        return

                fix_key = (tool_name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))
                if fix_key in declined_fixes and not self._feedback_explicitly_retries(user_feedback, tool_name):
                    repaired = self._repair_decision(
                        context,
                        backend,
                        f"The exact FIX '{tool_name}' with these exact arguments was already declined. Do not propose the same target again unless the user's latest instruction explicitly asks for that same retry. You MAY use the same FIX capability with a DIFFERENT verified target, choose another supported FIX, ask the user, or escalate.",
                    )
                    if repaired is None:
                        on_event(AgentEvent("internal_error", "LLM repeatedly proposed a declined fix."))
                        return
                    normalized = self._normalize_decision(repaired, kb_id)
                    if normalized["decision"] != "tool_call":
                        # A diagnostic, user question, or escalation can be a
                        # legitimate response after a declined FIX. Handle it
                        # on the next loop rather than treating it as a protocol
                        # failure.
                        user_feedback.append(
                            "The previous FIX target was declined. Continue with the repaired decision without repeating that exact target."
                        )
                        if normalized["decision"] == "ask_user":
                            if request_user_decision is None:
                                on_event(AgentEvent("ask", normalized["message"], {"reason": normalized["reason"]}))
                                return
                            response = request_user_decision("ASK_USER", normalized["message"], normalized["reason"])
                            if response.choice == "yes":
                                user_feedback.append(f"USER CONFIRMED THE PROPOSED USER DECISION: {normalized['message']}")
                            elif response.choice == "no":
                                user_feedback.append(f"USER DECLINED THE PROPOSED USER DECISION: {normalized['message']}")
                            elif response.instruction.strip():
                                user_feedback.append(f"USER DECISION INSTRUCTION: {response.instruction.strip()}")
                            on_event(AgentEvent("status", "Your response was sent to the LLM. Continuing the current troubleshooting session…"))
                            continue
                        if normalized["decision"] == "escalate":
                            self._handle_escalation(problem, kb_id, history, normalized, backend, request_user_decision, on_event)
                            return
                        on_event(AgentEvent("internal_error", "LLM returned an unsupported repaired decision after a declined FIX."))
                        return
                    tool_name = normalized["tool"]
                    arguments = normalized["arguments"]
                    phase = normalized["phase"]
                    definition = self.capabilities.get(tool_name)
                    if definition is None or tool_name not in allowed or definition.category != "FIX":
                        on_event(AgentEvent("internal_error", "LLM did not select another valid FIX after a declined target."))
                        return
                    fix_key = (tool_name, json.dumps(arguments, sort_keys=True, ensure_ascii=False))
                    if fix_key in declined_fixes:
                        on_event(AgentEvent("internal_error", "LLM repeated the same declined FIX target after repair."))
                        return

                if fix_key in attempted_fixes and not self._feedback_explicitly_retries(user_feedback, tool_name):
                    repaired = self._repair_decision(
                        context,
                        backend,
                        f"The exact FIX '{tool_name}' with these exact arguments was already attempted. Do not repeat that exact target automatically. You MAY use the same FIX capability with DIFFERENT verified arguments (for example a different application PID), choose another supported action, ask the user, or escalate.",
                    )
                    if repaired is None:
                        on_event(AgentEvent("internal_error", "LLM entered a repeated-fix loop."))
                        return
                    normalized = self._normalize_decision(repaired, kb_id)
                    if normalized["decision"] != "tool_call":
                        # This is not necessarily an error: after an attempted
                        # FIX, the LLM may reasonably ask for a new test, ask the
                        # user, or escalate. Allow those decisions to proceed
                        # instead of converting them into an internal error.
                        if normalized["decision"] == "ask_user":
                            if request_user_decision is None:
                                on_event(AgentEvent("ask", normalized["message"], {"reason": normalized["reason"]}))
                                return
                            response = request_user_decision("ASK_USER", normalized["message"], normalized["reason"])
                            if response.choice == "yes":
                                user_feedback.append(f"USER CONFIRMED THE PROPOSED USER DECISION: {normalized['message']}")
                            elif response.choice == "no":
                                user_feedback.append(f"USER DECLINED THE PROPOSED USER DECISION: {normalized['message']}")
                            elif response.instruction.strip():
                                user_feedback.append(f"USER DECISION INSTRUCTION: {response.instruction.strip()}")
                            on_event(AgentEvent("status", "Your response was sent to the LLM. Continuing the current troubleshooting session…"))
                            continue
                        if normalized["decision"] == "escalate":
                            self._handle_escalation(problem, kb_id, history, normalized, backend, request_user_decision, on_event)
                            return
                        on_event(AgentEvent("internal_error", "LLM returned an unsupported repaired decision after a repeated FIX."))
                        return
                    new_tool_name = normalized["tool"]
                    new_arguments = normalized["arguments"]
                    new_fix_key = (new_tool_name, json.dumps(new_arguments, sort_keys=True, ensure_ascii=False))
                    if new_fix_key == fix_key:
                        on_event(AgentEvent("internal_error", "LLM repeated the exact same FIX target after repair."))
                        return
                    tool_name = new_tool_name
                    arguments = new_arguments
                    phase = normalized["phase"]
                    definition = self.capabilities.get(tool_name)
                    if definition is None or tool_name not in allowed or definition.category != "FIX":
                        on_event(AgentEvent("internal_error", "LLM did not select another valid FIX target after repair."))
                        return
                    fix_key = new_fix_key

                if not definition.requires_approval:
                    on_event(AgentEvent("internal_error", f"State-changing capability '{tool_name}' is not approval-gated."))
                    return

                dialog_reason = normalized.get("reason") or definition.description
                dialog_message = normalized.get("message") or definition.description
                approval = request_approval(tool_name, dialog_message, dialog_reason)

                if approval.choice == "no":
                    declined_fixes.add(fix_key)
                    user_feedback.append(
                        f"The user declined the proposed fix '{tool_name}'. Do not execute it. Reconsider the same KB and evidence."
                    )
                    on_event(AgentEvent("status", "Fix declined. The LLM will reconsider the evidence and remaining KB actions…"))
                    continue

                if approval.choice == "idea":
                    instruction = approval.instruction.strip()
                    if not instruction:
                        user_feedback.append("The user chose Your idea but supplied no text. Continue without changing the system.")
                    else:
                        user_feedback.append(f"USER DECISION INSTRUCTION: {instruction}")
                    on_event(AgentEvent("status", "Your idea was sent to the LLM for analysis. No system change was made."))
                    continue

                attempted_fixes.add(fix_key)

            on_event(
                AgentEvent(
                    "tool",
                    f"Running {tool_name}…",
                    {"tool": tool_name, "arguments": arguments, "phase": phase},
                )
            )

            try:
                result: ToolResult = definition.runner(arguments)
            except Exception as exc:
                result = ToolResult(False, f"Executable capability '{tool_name}' raised an unexpected error: {exc}")

            output = (result.output or "(no output)").strip()
            if len(output) > 6000:
                output = output[:6000] + "\n[tool output truncated by agent runtime]"

            history.append(
                {
                    "step": step,
                    "tool": tool_name,
                    "category": definition.category,
                    "phase": phase,
                    "success": bool(result.success),
                    "arguments": arguments,
                    "output": output,
                }
            )
            on_event(
                AgentEvent(
                    "tool_result",
                    output,
                    {"tool": tool_name, "success": result.success, "phase": phase},
                )
            )

            # New evidence makes another resolution confirmation meaningful.
            # A prior "No" only blocks an immediate repeated resolution claim.
            resolution_declined = False

            if definition.category == "FIX":
                if result.success:
                    fixes_executed.append(tool_name)
                    post_fix_verification_required = True
                    last_verification_success = False
                    user_feedback.append(
                        f"Tool result for FIX '{tool_name}': success=true. A verification/test is now mandatory before resolution."
                    )
                else:
                    # A failed executable FIX did not change the system, so
                    # mandatory post-fix verification would be misleading.
                    # Keep the failed target blocked, but let the orchestrator
                    # choose another verified target, another supported fix, a
                    # new diagnostic, or escalation.
                    failed_fixes.add(fix_key)
                    post_fix_verification_required = False
                    last_verification_success = False
                    user_feedback.append(
                        f"Tool result for FIX '{tool_name}': success=false. No system change is confirmed. Do not treat this as a completed fix; choose another evidence-based action, another verified target, or escalate."
                    )
            else:
                last_diagnostic_success = bool(result.success)
                user_feedback.append(
                    f"Tool result for DIAGNOSTIC '{tool_name}': success={result.success}. Interpret the actual output; tool success only means the diagnostic ran."
                )
                if post_fix_verification_required and tool_name in set(self._tool_group(kb, "Verification")):
                    post_fix_verification_required = False
                    last_verification_success = bool(result.success)

        on_event(
            AgentEvent(
                "internal_error",
                f"The LLM agent loop reached the maximum of {max_agent_steps} steps. No ticket was created because this is an internal agent-loop limit.",
            )
        )

    def _classify(self, problem: str, backend: str) -> str:
        candidates = discover_kbs()
        if not candidates:
            raise RuntimeError(f"No Python knowledge bases were found in {KB_ROOT}")

        prompt = (
            "AVAILABLE KNOWLEDGE BASES:\n"
            f"{build_kb_catalog()}\n\n"
            "SPECIAL CLASSIFICATION: GENERAL_CHAT / GENERAL_SUPPORT\n"
            "Use GENERAL_CHAT for greetings, thanks, small talk, or questions about the agent itself that are not an IT support request.\n"
            "Use GENERAL_SUPPORT for legitimate IT/workplace support matters outside the discovered KBs that should be sent to the support team without local troubleshooting.\n\n"
            "USER REQUEST:\n"
            f"{problem}\n\n"
            "RETURN ONLY ONE EXACT KB ID, GENERAL_CHAT, GENERAL_SUPPORT, OR UNSUPPORTED."
        )
        result = self.provider.complete(CLASSIFIER_SYSTEM_PROMPT, prompt, backend, json_mode=False)
        kb_id = self._extract_kb_id(result.content, candidates)
        if kb_id:
            return kb_id

        # One cheap protocol retry handles models that accidentally emit the
        # troubleshooting JSON envelope during classification.
        repair_prompt = (
            "CLASSIFICATION FORMAT ERROR.\n"
            f"The candidates are: {', '.join(candidates)}. You may also return GENERAL_CHAT, GENERAL_SUPPORT, or UNSUPPORTED.\n"
            f"The previous model response was:\n{result.content[:1200]}\n\n"
            "Return ONLY the exact KB ID, GENERAL_CHAT, GENERAL_SUPPORT, or UNSUPPORTED."
        )
        repaired = self.provider.complete(CLASSIFIER_SYSTEM_PROMPT, repair_prompt, backend, json_mode=False)
        kb_id = self._extract_kb_id(repaired.content, candidates)
        if kb_id:
            return kb_id

        if (result.content or "").strip().upper() == "UNSUPPORTED" or (repaired.content or "").strip().upper() == "UNSUPPORTED":
            raise UnsupportedRequest("The user's request does not match any discovered knowledge base.")
        raise ValueError(f"Model returned invalid KB ID: {(repaired.content or '')[:500]}")

    @staticmethod
    def _extract_kb_id(raw: str, candidates: dict[str, dict[str, Any]]) -> str | None:
        text = (raw or "").strip()
        if not text:
            return None

        aliases = {kb_id.lower(): kb_id for kb_id in candidates}
        aliases["general_chat"] = "GENERAL_CHAT"
        aliases["general_support"] = "GENERAL_SUPPORT"
        aliases["support_request"] = "GENERAL_SUPPORT"
        aliases["unsupported"] = "UNSUPPORTED"
        cleaned = text.strip("` \"'\t\r\n")
        for prefix in ("kb:", "kb_id:", "knowledge_base:", "category:"):
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip().strip("` \"'")
                break
        if cleaned.lower() in aliases:
            return aliases[cleaned.lower()]

        try:
            data = parse_json_object(text)
        except Exception:
            data = None
        if isinstance(data, dict):
            for key in ("kb_id", "knowledge_base", "category", "id"):
                value = str(data.get(key, "")).strip()
                if value.lower() in aliases:
                    return aliases[value.lower()]

        # Accept a single exact ID embedded in a short accidental wrapper such
        # as "The best KB is internet_issues" but never fuzzy-match long text.
        lower = text.lower()
        matches = [canonical for alias, canonical in aliases.items() if alias in lower]
        if len(matches) == 1 and len(text) <= 250:
            return matches[0]
        return None

    def _get_decision_with_repair(self, context: str, backend: str) -> dict[str, Any]:
        result = self.provider.complete(ORCHESTRATOR_SYSTEM_PROMPT, context, backend, json_mode=True)
        try:
            return parse_json_object(result.content)
        except Exception as first_exc:
            repair_prompt = (
                f"{context}\n\n{PROTOCOL_REPAIR_PROMPT}\n"
                f"RUNTIME PARSE ERROR: {first_exc}"
            )
            repaired = self.provider.complete(ORCHESTRATOR_SYSTEM_PROMPT, repair_prompt, backend, json_mode=True)
            try:
                return parse_json_object(repaired.content)
            except Exception as second_exc:
                raise ValueError(f"Model returned invalid orchestration JSON after one repair: {second_exc}") from second_exc

    def _repair_decision(self, context: str, backend: str, runtime_issue: str) -> dict[str, Any] | None:
        generation = load_settings().generation
        max_repairs = generation.max_protocol_repairs if generation else 2
        for _ in range(max_repairs):
            prompt = f"{context}\n\n{PROTOCOL_REPAIR_PROMPT}\nRUNTIME VALIDATION ERROR:\n{runtime_issue}"
            try:
                result = self.provider.complete(ORCHESTRATOR_SYSTEM_PROMPT, prompt, backend, json_mode=True)
                return parse_json_object(result.content)
            except Exception:
                continue
        return None

    @staticmethod
    def _normalize_decision(raw: dict[str, Any], kb_id: str) -> dict[str, Any]:
        """Normalize the new protocol and the previous build's protocol.

        This is intentionally a compatibility layer so an older model prompt
        cannot crash the entire session just because it used the old fields.
        """
        decision = str(raw.get("decision", "")).strip().lower()
        if not decision:
            status = str(raw.get("status", "")).strip().upper()
            action_type = str(raw.get("action_type", "")).strip().upper()
            action = str(raw.get("action", "")).strip()
            if action_type in {"DIAGNOSTIC", "FIX"} and action:
                decision = "tool_call"
            elif action_type == "ASK_USER":
                decision = "ask_user"
            elif action_type == "RESOLVED" or status == "RESOLVED":
                decision = "resolved"
            elif action_type == "ESCALATE" or status == "TICKET_REQUIRED":
                decision = "escalate"

        phase = str(raw.get("phase", "")).strip().upper() or "ANALYSIS"
        message = str(raw.get("message", "")).strip()
        reason = str(raw.get("reason", "")).strip()

        if decision == "tool_call":
            tool = str(raw.get("tool", raw.get("action", ""))).strip()
            arguments = raw.get("arguments", {})
            if not isinstance(arguments, dict):
                raise ValueError("tool_call arguments must be an object")
            if not tool:
                raise ValueError("tool_call is missing tool")
            if phase not in {"TEST", "DIAGNOSIS", "ANALYSIS", "FIX", "VERIFY", "RETRY"}:
                raise ValueError(f"invalid tool_call phase '{phase}'")
            return {
                "decision": "tool_call",
                "phase": phase,
                "tool": tool,
                "arguments": arguments,
                "message": message,
                "reason": reason,
            }

        if decision == "ask_user":
            if not message:
                raise ValueError("ask_user requires message")
            return {"decision": "ask_user", "phase": phase, "message": message, "reason": reason}

        if decision == "resolved":
            problem_verified = bool(raw.get("problem_verified", False))
            verification_successful = bool(raw.get("verification_successful", False))
            if not verification_successful:
                raise ValueError("resolved requires verification_successful=true")
            return {
                "decision": "resolved",
                "phase": "RESOLVED",
                "status": "RESOLVED",
                "problem_verified": problem_verified,
                "verification_successful": verification_successful,
                "message": message or "The issue is resolved or could not be reproduced.",
                "reason": reason,
            }

        if decision in {"escalate", "ticket_required"}:
            return {
                "decision": "escalate",
                "phase": "ESCALATE",
                "status": "TICKET_REQUIRED",
                "problem_verified": bool(raw.get("problem_verified", False)),
                "verification_successful": bool(raw.get("verification_successful", False)),
                "message": message or "This issue requires escalation to a higher support level.",
                "reason": reason or "L1 knowledge-base remediation is exhausted or out of scope.",
            }

        raise ValueError(f"unknown decision type '{decision}' for KB '{kb_id}'")

    @staticmethod
    def _kb_capabilities(kb: dict[str, Any]) -> set[str]:
        labels = kb.get("tool_labels", {})
        if not isinstance(labels, dict):
            raise ValueError("tool_labels must be a dictionary")
        found: set[str] = set()
        for values in labels.values():
            if not isinstance(values, list):
                raise ValueError("every tool_labels group must be a list")
            found.update(str(value).strip() for value in values if str(value).strip())
        if not found:
            raise ValueError("knowledge base has no executable capabilities")
        return found

    @staticmethod
    def _tool_group(kb: dict[str, Any], group: str) -> list[str]:
        values = kb.get("tool_labels", {}).get(group, [])
        return [str(x).strip() for x in values if str(x).strip()]

    @staticmethod
    def _validate_arguments(arguments: dict[str, Any], definition: ToolDefinition) -> bool:
        if not definition.argument_schema:
            return arguments == {}
        if not isinstance(arguments, dict):
            return False
        allowed = set(definition.argument_schema)
        if any(key not in allowed for key in arguments):
            return False

        # Most Windows capability arguments are evidence strings. A common
        # JSON-model variation is returning a PID as a JSON number instead of
        # a string (for example, 34888 rather than "34888"). Accept that
        # safe representation for PID arguments because the executable runner
        # already validates the PID and re-checks the live process before a fix.
        for key, value in arguments.items():
            if isinstance(value, str):
                if not value.strip():
                    return False
                continue
            if key == "pid" and isinstance(value, int) and not isinstance(value, bool) and value > 0:
                continue
            return False
        return True

    @staticmethod
    def _feedback_explicitly_retries(user_feedback: list[str], tool_name: str) -> bool:
        text = " ".join(user_feedback[-3:]).lower()
        tool = tool_name.lower()
        retry_words = ("retry", "try again", "run it again", "repeat", "do it again")
        return tool in text and any(word in text for word in retry_words)

    @staticmethod
    def _build_orchestrator_context(
        *,
        kb_id: str,
        kb: dict[str, Any],
        problem: str,
        history: list[dict[str, Any]],
        allowed: set[str],
        user_feedback: list[str],
        attempted_fixes: set[tuple[str, str]],
        failed_fixes: set[tuple[str, str]],
        post_fix_verification_required: bool,
    ) -> str:
        tool_metadata = []
        capabilities = get_capabilities()
        for name in sorted(allowed):
            tool = capabilities[name]
            tool_metadata.append(
                {
                    "name": tool.name,
                    "type": tool.category,
                    "description": tool.description,
                    "requires_approval": tool.requires_approval,
                    "arguments": tool.argument_schema,
                }
            )

        trimmed_history = history[-8:]
        history_text = json.dumps(trimmed_history, ensure_ascii=False, indent=2)
        if len(history_text) > 18000:
            history_text = history_text[-18000:]
        feedback_text = "\n".join(user_feedback[-8:]) or "None"
        if len(feedback_text) > 5000:
            feedback_text = feedback_text[-5000:]

        attempted_text = json.dumps(sorted(attempted_fixes), ensure_ascii=False)
        failed_text = json.dumps(sorted(failed_fixes), ensure_ascii=False)

        return (
            "SESSION STATE\n"
            f"Selected KB: {kb_id}\n"
            f"Post-fix verification required: {post_fix_verification_required}\n"
            f"Attempted FIX targets: {attempted_text}\n"
            f"FIX targets that failed to execute: {failed_text}\n\n"
            "SELECTED KNOWLEDGE BASE (AUTHORITATIVE):\n"
            f"{json.dumps(kb, ensure_ascii=False, indent=2)}\n\n"
            "EXACT EXECUTABLE CAPABILITIES EXPOSED FOR THIS KB:\n"
            f"{json.dumps(tool_metadata, ensure_ascii=False, indent=2)}\n\n"
            "ORIGINAL USER REQUEST:\n"
            f"{problem}\n\n"
            "ACTUAL TOOL HISTORY (NOT ASSUMPTIONS):\n"
            f"{history_text}\n\n"
            "USER DECISION / RETRY INSTRUCTIONS:\n"
            f"{feedback_text}\n\n"
            "Choose exactly one next decision. Do not return a tool that is not in the capability list."
        )

    def _make_resolved_report(
        self,
        *,
        problem: str,
        kb_id: str,
        history: list[dict[str, Any]],
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "RESOLVED",
            "problem_verified": bool(decision["problem_verified"]),
            "category": kb_id,
            "summary": problem,
            "diagnosis": decision["reason"],
            "actions_taken": history,
            "verification_successful": True,
            "message": decision["message"],
        }

    def _request_ticket_recipient(
        self,
        request_user_decision: Callable[[str, str, str], ApprovalResponse] | None,
        on_event: Callable[[AgentEvent], None],
    ) -> str | None:
        if request_user_decision is None:
            on_event(AgentEvent("internal_error", "Ticket email recipient input is unavailable in this UI."))
            return None
        on_event(
            AgentEvent(
                "ask",
                "I need the support team's email address before I can send this ticket. Please enter the recipient email in the prompt.",
                {"action": "EMAIL_RECIPIENT"},
            )
        )
        response = request_user_decision(
            "EMAIL_RECIPIENT",
            "Enter the support team's email address that should receive this ticket.",
            "The recipient is required for this ticket email and will not be guessed or taken from settings.",
        )
        if response.choice != "idea":
            on_event(AgentEvent("status", "No recipient was provided. The ticket will still be saved locally."))
            return None
        recipient = response.instruction.strip()
        if not is_valid_email(recipient):
            on_event(AgentEvent("internal_error", "The support recipient email address is invalid. The ticket was saved locally, but the email was not sent."))
            return None
        return recipient

    def _send_ticket_email(
        self,
        *,
        problem: str,
        category: str | None,
        history: list[dict[str, Any]],
        diagnosis: str,
        status: str,
        escalation_reason: str,
        ticket_id: str,
        ticket_path,
        backend: str,
        recipient: str,
        on_event: Callable[[AgentEvent], None],
    ) -> dict[str, Any]:
        settings = load_settings()
        try:
            draft = generate_ticket_email(
                self.provider,
                backend,
                recipient=recipient,
                ticket_id=ticket_id,
                problem=problem,
                category=category,
                diagnosis=diagnosis,
                actions=history,
                status=status,
                escalation_reason=escalation_reason,
            )
            send_email(settings.email, draft)
            email_info = {
                "status": "SENT",
                "recipient": draft.to,
                "subject": draft.subject,
            }
            update_ticket_email(ticket_path, email_info)
            on_event(
                AgentEvent(
                    "email",
                    f"Ticket {ticket_id} was emailed to {draft.to}.",
                    {"ticket_id": ticket_id, "recipient": draft.to, "subject": draft.subject, "body": draft.body},
                )
            )
            return email_info
        except Exception as exc:
            email_info = {
                "status": "FAILED",
                "recipient": recipient,
                "error": str(exc),
            }
            try:
                update_ticket_email(ticket_path, email_info)
            except Exception:
                pass
            on_event(
                AgentEvent(
                    "email_error",
                    f"Ticket {ticket_id} was saved, but the email could not be sent: {exc}",
                    {"ticket_id": ticket_id, "recipient": recipient, "error": str(exc)},
                )
            )
            return email_info

    def _should_collect_device_identity(self, problem: str, backend: str) -> bool:
        """Ask the LLM only whether a device identity is useful for this ticket.

        This is deliberately a tiny bounded decision: it cannot run arbitrary
        commands and the only executable identity capability is collected below.
        Explicit device-ID requests are handled without relying on the model.
        """
        text = problem.lower()
        explicit = (
            "device id" in text
            or "device uuid" in text
            or "serial number" in text
            or "machine id" in text
            or "computer id" in text
            or "asset id" in text
        )
        if explicit:
            return True
        try:
            prompt = (
                "Decide whether collecting the Windows device identity would materially help a support-team ticket for this request. "
                'Return ONLY JSON: {"collect_device_identity":true|false}. '
                "Choose true only when device identity is useful for identifying the affected machine or service account/device. "
                "Do not collect it merely because it exists.\n\nUSER REQUEST:\n" + problem
            )
            result = self.provider.complete(
                "You are a narrowly scoped IT support triage gate. Do not troubleshoot and do not invent tools.",
                prompt,
                backend,
                json_mode=True,
            )
            data = parse_json_object(result.content)
            return bool(data.get("collect_device_identity", False))
        except Exception:
            return False

    def _handle_general_support(
        self,
        problem: str,
        backend: str,
        request_user_decision: Callable[[str, str, str], ApprovalResponse] | None,
        on_event: Callable[[AgentEvent], None],
    ) -> None:
        """Route legitimate non-KB support requests directly to the support team.

        No fake troubleshooting is performed. A narrowly scoped device identity
        diagnostic may be collected when the request or LLM indicates it is
        useful, then the normal ticket/email pipeline is used.
        """
        try:
            history: list[dict[str, Any]] = []
            if self._should_collect_device_identity(problem, backend):
                tool = self.capabilities.get("get_device_identity")
                if tool is None:
                    on_event(AgentEvent("internal_error", "Device identity capability is unavailable."))
                    return
                on_event(AgentEvent("status", "Collecting device identity for the support ticket…"))
                result = tool.runner({})
                history.append({
                    "category": tool.category,
                    "tool": tool.name,
                    "success": result.success,
                    "output": result.output,
                })
                on_event(AgentEvent("tool", f"Running {tool.name}…"))
                on_event(AgentEvent("tool_result", result.output, {"tool": tool.name, "success": result.success}))

            reason = "The request is a legitimate support-team matter outside the local L1 troubleshooting knowledge bases."
            ticket_id, path = create_ticket(problem, "GENERAL_SUPPORT", history, reason)
            recipient = self._request_ticket_recipient(request_user_decision, on_event)
            email_info = None
            if recipient:
                email_info = self._send_ticket_email(
                    problem=problem,
                    category="GENERAL_SUPPORT",
                    history=history,
                    diagnosis="No local troubleshooting was required for this support-team request.",
                    status="TICKET_REQUIRED",
                    escalation_reason=reason,
                    ticket_id=ticket_id,
                    ticket_path=path,
                    backend=backend,
                    recipient=recipient,
                    on_event=on_event,
                )
            report_path = save_report(
                {
                    "status": "TICKET_REQUIRED",
                    "problem_verified": False,
                    "category": "GENERAL_SUPPORT",
                    "summary": problem,
                    "diagnosis": "No local troubleshooting was required; routed directly to the support team.",
                    "actions_taken": history,
                    "reason": reason,
                    "ticket_id": ticket_id,
                    "email": email_info,
                },
                REPORTS_ROOT,
            )
            on_event(
                AgentEvent(
                    "ticket",
                    f"This request was routed directly to the support team. Ticket: {ticket_id}",
                    {"ticket_id": ticket_id, "path": str(path), "report_path": str(report_path), "email": email_info},
                )
            )
        except Exception as exc:
            on_event(AgentEvent("internal_error", f"Could not create the general support ticket: {exc}"))

    def _handle_unsupported(
        self,
        problem: str,
        reason: str,
        backend: str,
        request_user_decision: Callable[[str, str, str], ApprovalResponse] | None,
        on_event: Callable[[AgentEvent], None],
    ) -> None:
        try:
            ticket_id, path = create_ticket(problem, None, [], reason)
            recipient = self._request_ticket_recipient(request_user_decision, on_event)
            email_info = None
            if recipient:
                email_info = self._send_ticket_email(
                    problem=problem,
                    category=None,
                    history=[],
                    diagnosis="",
                    status="TICKET_REQUIRED",
                    escalation_reason=reason,
                    ticket_id=ticket_id,
                    ticket_path=path,
                    backend=backend,
                    recipient=recipient,
                    on_event=on_event,
                )
            report_path = save_report(
                {
                    "status": "TICKET_REQUIRED",
                    "problem_verified": False,
                    "category": None,
                    "summary": problem,
                    "reason": reason,
                    "ticket_id": ticket_id,
                    "email": email_info,
                },
                REPORTS_ROOT,
            )
            titles = [kb.get("title", kb_id) for kb_id, kb in discover_kbs().items()]
            supported = ", ".join(titles) if titles else "No knowledge bases are currently available."
            message = f"I can only troubleshoot the supported L1 knowledge bases. Supported areas: {supported}."
            on_event(
                AgentEvent(
                    "unsupported",
                    message,
                    {"ticket_id": ticket_id, "path": str(path), "report_path": str(report_path), "email": email_info},
                )
            )
        except Exception as exc:
            on_event(AgentEvent("internal_error", f"Could not create the unsupported-request ticket: {exc}"))

    def _handle_escalation(
        self,
        problem: str,
        kb_id: str,
        history: list[dict[str, Any]],
        decision: dict[str, Any],
        backend: str,
        request_user_decision: Callable[[str, str, str], ApprovalResponse] | None,
        on_event: Callable[[AgentEvent], None],
    ) -> None:
        try:
            ticket_id, path = create_ticket(problem, kb_id, history, decision["reason"])
            recipient = self._request_ticket_recipient(request_user_decision, on_event)
            email_info = None
            if recipient:
                email_info = self._send_ticket_email(
                    problem=problem,
                    category=kb_id,
                    history=history,
                    diagnosis=decision.get("reason", ""),
                    status="TICKET_REQUIRED",
                    escalation_reason=decision.get("reason", ""),
                    ticket_id=ticket_id,
                    ticket_path=path,
                    backend=backend,
                    recipient=recipient,
                    on_event=on_event,
                )
            report = {
                "status": "TICKET_REQUIRED",
                "problem_verified": bool(decision.get("problem_verified", False)),
                "category": kb_id,
                "summary": problem,
                "diagnosis": decision.get("reason", ""),
                "actions_taken": history,
                "verification_successful": bool(decision.get("verification_successful", False)),
                "message": decision.get("message", ""),
                "ticket_id": ticket_id,
                "email": email_info,
            }
            report_path = save_report(report, REPORTS_ROOT)
            on_event(
                AgentEvent(
                    "ticket",
                    decision["message"],
                    {
                        "ticket_id": ticket_id,
                        "path": str(path),
                        "report": report,
                        "report_path": str(report_path),
                        "email": email_info,
                    },
                )
            )
        except Exception as exc:
            on_event(AgentEvent("internal_error", f"Could not create escalation ticket: {exc}"))

