from __future__ import annotations

import tempfile
from pathlib import Path

from helpdesk_agent.agent.service import AgentService, AgentEvent, ApprovalResponse
from helpdesk_agent.knowledge.store import discover_kbs
from helpdesk_agent.llm.provider import parse_json_object
from helpdesk_agent.ticketing import service as ticketing_service
from helpdesk_agent.tools.capabilities import ToolDefinition, ToolResult


class FakeProvider:
    def __init__(self):
        self.calls = 0

    def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
        from helpdesk_agent.llm.provider import ModelResult

        self.calls += 1
        if "classification gate" in system_prompt:
            content = "internet_issues"
        else:
            sequence = [
                '{"decision":"tool_call","phase":"TEST","tool":"check_adapter_state","arguments":{},"message":"Checking adapters.","reason":"Testing the local network state."}',
                '{"decision":"tool_call","phase":"DIAGNOSIS","tool":"check_ip_config","arguments":{},"message":"Checking IP configuration.","reason":"Looking for a usable local address."}',
                '{"decision":"tool_call","phase":"FIX","tool":"fix_flush_dns","arguments":{},"message":"I found a DNS-related symptom and propose flushing the DNS cache.","reason":"The KB permits this fix when DNS evidence supports it."}',
                '{"decision":"tool_call","phase":"VERIFY","tool":"check_dns","arguments":{},"message":"Re-checking DNS after the fix.","reason":"Post-fix verification is required."}',
                '{"decision":"resolved","phase":"RESOLVED","status":"RESOLVED","problem_verified":true,"verification_successful":true,"message":"The network issue is resolved.","reason":"Post-fix DNS verification succeeded."}',
            ]
            content = sequence[min(self.calls - 2, len(sequence) - 1)]
        return ModelResult(content, backend)


def test_kb_discovery_and_capability_coverage():
    kbs = discover_kbs()
    expected = {
        "USB_ports",
        "audio_errors",
        "internet_issues",
        "cpu_memory_issue",
        "not_responding_apps_issue",
        "time_date_sync_problems",
    }
    assert set(kbs) == expected

    service = AgentService(provider=FakeProvider())
    missing = {
        tool
        for kb in kbs.values()
        for labels in kb["tool_labels"].values()
        for tool in labels
        if tool not in service.capabilities
    }
    assert missing == set()


def test_classifier_accepts_accidental_old_agent_json():
    service = AgentService(provider=FakeProvider())
    kbs = discover_kbs()
    old_response = (
        '{"status":"ACTION_REQUIRED","phase":"TEST","category":"internet_issues",'
        '"action_type":"NONE","action":"","arguments":{},"problem_verified":false,'
        '"verification_successful":false,"message":"","reason":""}'
    )
    assert service._extract_kb_id(old_response, kbs) == "internet_issues"


def test_json_parser_handles_fenced_and_surrounded_json():
    assert parse_json_object('```json\n{"decision":"resolved"}\n```')["decision"] == "resolved"
    assert parse_json_object('model text\n{"decision":"resolved"}\nmore text')["decision"] == "resolved"


def test_full_orchestrator_loop_requires_approval_and_verification():
    fake = FakeProvider()
    service = AgentService(provider=fake)

    def ok(_):
        return ToolResult(True, "OK")

    for name in ("check_adapter_state", "check_ip_config", "fix_flush_dns", "check_dns"):
        original = service.capabilities[name]
        service.capabilities[name] = ToolDefinition(
            original.name,
            original.category,
            original.description,
            original.requires_approval,
            ok,
            original.argument_schema,
        )

    events: list[AgentEvent] = []
    approvals: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        reports_root = Path(tmp) / "reports"
        original_reports = ticketing_service.TICKETS_ROOT
        # The service imports its own REPORTS_ROOT constant, so patch it there too.
        import helpdesk_agent.agent.service as agent_service_module
        original_agent_reports = agent_service_module.REPORTS_ROOT
        agent_service_module.REPORTS_ROOT = reports_root
        ticketing_service.TICKETS_ROOT = Path(tmp) / "tickets"
        try:
            service.run(
                "My internet has a DNS problem",
                "cloud",
                events.append,
                lambda action, message, reason: (approvals.append(action) or ApprovalResponse("yes", "")),
            )
        finally:
            agent_service_module.REPORTS_ROOT = original_agent_reports
            ticketing_service.TICKETS_ROOT = original_reports

    assert approvals == ["fix_flush_dns", "CONFIRM_RESOLUTION"]
    assert any(event.kind == "resolved" for event in events)
    assert not any(event.kind == "internal_error" for event in events)



def test_classifier_handles_general_chat_without_ticketing():
    from helpdesk_agent.llm.provider import ModelResult

    class GeneralChatProvider(FakeProvider):
        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            if "classification gate" in system_prompt:
                return ModelResult("GENERAL_CHAT", backend)
            return super().complete(system_prompt, user_prompt, backend, json_mode=json_mode)

    service = AgentService(provider=GeneralChatProvider())
    events: list[AgentEvent] = []
    service.run(
        "hello",
        "cloud",
        events.append,
        lambda action, message, reason: ApprovalResponse("no", ""),
    )
    assert any(event.kind == "general_chat" for event in events)
    assert not any(event.kind in {"ticket", "unsupported", "resolved"} for event in events)
    assert not any(event.kind == "internal_error" for event in events)


def test_resolution_requires_user_confirmation_and_no_means_continue():
    from helpdesk_agent.llm.provider import ModelResult

    class ConfirmationProvider(FakeProvider):
        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            if "classification gate" in system_prompt:
                return ModelResult("internet_issues", backend)
            seq = [
                '{"decision":"tool_call","phase":"TEST","tool":"check_adapter_state","arguments":{},"message":"Checking the adapter.","reason":"Initial test."}',
                '{"decision":"resolved","phase":"RESOLVED","status":"RESOLVED","problem_verified":true,"verification_successful":true,"message":"The network appears healthy.","reason":"Verification succeeded."}',
                '{"decision":"tool_call","phase":"TEST","tool":"check_dns","arguments":{},"message":"Checking DNS again.","reason":"The user says the problem remains."}',
                '{"decision":"resolved","phase":"RESOLVED","status":"RESOLVED","problem_verified":true,"verification_successful":true,"message":"The network is now verified again.","reason":"The second verification succeeded."}',
            ]
            index = min(self.calls - 1, len(seq)-1)
            self.calls += 1
            return ModelResult(seq[index], backend)

    fake = ConfirmationProvider()
    service = AgentService(provider=fake)
    for name in ("check_adapter_state", "check_dns"):
        original = service.capabilities[name]
        service.capabilities[name] = ToolDefinition(
            original.name, original.category, original.description,
            original.requires_approval, lambda _args: ToolResult(True, "OK"), original.argument_schema
        )
    events: list[AgentEvent] = []
    confirmations = []
    with tempfile.TemporaryDirectory() as tmp:
        import helpdesk_agent.agent.service as agent_service_module
        original_reports = agent_service_module.REPORTS_ROOT
        agent_service_module.REPORTS_ROOT = Path(tmp) / "reports"
        try:
            def decision(action, message, reason):
                confirmations.append(action)
                if action == "CONFIRM_RESOLUTION" and len(confirmations) == 1:
                    return ApprovalResponse("no", "")
                return ApprovalResponse("yes", "")
            service.run("my internet is still not working", "cloud", events.append, decision)
        finally:
            agent_service_module.REPORTS_ROOT = original_reports
    assert confirmations == ["CONFIRM_RESOLUTION", "CONFIRM_RESOLUTION"]
    assert any(event.kind == "resolved" for event in events)
    assert not any(event.kind == "internal_error" for event in events)


def test_ask_user_opens_interactive_decision_and_stays_in_same_session():
    from helpdesk_agent.llm.provider import ModelResult

    class AskProvider:
        def __init__(self):
            self.calls = 0

        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            if "classification gate" in system_prompt:
                return ModelResult("cpu_memory_issue", backend)
            self.calls += 1
            if self.calls == 1:
                return ModelResult(
                    '{"decision":"ask_user","phase":"ANALYSIS",'
                    '"message":"Firefox is the safest user application candidate to close. Should I use that option?",'
                    '"reason":"The latest memory diagnostic shows Firefox as the largest user-space consumer."}',
                    backend,
                )
            if self.calls == 2:
                return ModelResult(
                    '{"decision":"tool_call","phase":"TEST","tool":"check_named_process",'
                    '"arguments":{"name":"Teams"},"message":"Checking Teams first.","reason":"The user identified Teams as the intended app."}',
                    backend,
                )
            return ModelResult(
                '{"decision":"escalate","phase":"ESCALATE","status":"TICKET_REQUIRED",'
                '"message":"Escalating.","reason":"No safe L1 action remains."}',
                backend,
            )

    service = AgentService(provider=AskProvider())
    events: list[AgentEvent] = []
    user_decisions: list[ApprovalResponse] = []

    # Replace the selected diagnostics so this test never depends on Windows.
    original = service.capabilities["check_named_process"]
    service.capabilities["check_named_process"] = ToolDefinition(
        original.name, original.category, original.description,
        original.requires_approval,
        lambda _args: ToolResult(True, "No running process matched: Teams"),
        original.argument_schema,
    )

    service.run(
        "My memory is too full",
        "cloud",
        events.append,
        lambda action, message, reason: ApprovalResponse("no", ""),
        lambda action, message, reason: (
            user_decisions.append(ApprovalResponse("idea", "Check Teams instead."))
            or (ApprovalResponse("idea", "support@example.com") if action == "EMAIL_RECIPIENT" else ApprovalResponse("idea", "Check Teams instead."))
        ),
    )

    assert sum(1 for item in user_decisions if item.instruction == "Check Teams instead.") >= 1
    assert user_decisions[0].instruction == "Check Teams instead."
    assert any(event.kind == "tool" and event.payload and event.payload.get("tool") == "check_named_process" for event in events)
    assert not any(event.kind == "internal_error" for event in events)


def test_pid_arguments_accept_json_numbers_from_llm():
    service = AgentService(provider=FakeProvider())
    definition = service.capabilities["close_high_resource_process"]
    assert service._validate_arguments({"pid": 34888, "process_name": "firefox"}, definition)
    assert service._validate_arguments({"pid": "34888", "process_name": "firefox"}, definition)
    assert not service._validate_arguments({"pid": 0, "process_name": "firefox"}, definition)
    assert not service._validate_arguments({"pid": 34888, "process_name": ""}, definition)


def test_numeric_pid_does_not_trigger_protocol_repair_failure():
    from helpdesk_agent.llm.provider import ModelResult

    class NumericPidProvider(FakeProvider):
        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            if "classification gate" in system_prompt:
                return ModelResult("cpu_memory_issue", backend)
            sequence = [
                '{"decision":"tool_call","phase":"TEST","tool":"check_system_performance","arguments":{},"message":"Checking memory pressure.","reason":"Initial evidence."}',
                '{"decision":"tool_call","phase":"TEST","tool":"check_top_memory_processes","arguments":{},"message":"Identifying the main memory consumer.","reason":"Need process evidence."}',
                '{"decision":"tool_call","phase":"FIX","tool":"close_high_resource_process","arguments":{"pid":34888,"process_name":"firefox"},"message":"Firefox is the verified user-space consumer.","reason":"The PID and process name came from the latest diagnostic evidence."}',
                '{"decision":"tool_call","phase":"VERIFY","tool":"check_system_performance","arguments":{},"message":"Verifying memory after the approved fix.","reason":"Post-fix verification is required."}',
                '{"decision":"resolved","phase":"RESOLVED","status":"RESOLVED","problem_verified":true,"verification_successful":true,"message":"Memory pressure improved.","reason":"The post-fix verification succeeded."}',
            ]
            self.calls += 1
            return ModelResult(sequence[min(self.calls - 1, len(sequence) - 1)], backend)

    service = AgentService(provider=NumericPidProvider())
    for name in ("check_system_performance", "check_top_memory_processes", "close_high_resource_process"):
        original = service.capabilities[name]
        service.capabilities[name] = ToolDefinition(
            original.name, original.category, original.description, original.requires_approval,
            lambda _args: ToolResult(True, "OK"), original.argument_schema
        )

    events: list[AgentEvent] = []
    approvals: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        import helpdesk_agent.agent.service as agent_service_module
        original_reports = agent_service_module.REPORTS_ROOT
        agent_service_module.REPORTS_ROOT = Path(tmp) / "reports"
        try:
            service.run(
                "My memory is too full",
                "cloud",
                events.append,
                lambda action, message, reason: (approvals.append(action) or ApprovalResponse("yes", "")),
            )
        finally:
            agent_service_module.REPORTS_ROOT = original_reports

    assert approvals == ["close_high_resource_process", "CONFIRM_RESOLUTION"]
    assert any(event.kind == "resolved" for event in events)
    assert not any(event.kind == "internal_error" for event in events)



def test_failed_fix_does_not_trigger_post_fix_verification_and_allows_different_target():
    from helpdesk_agent.llm.provider import ModelResult

    class FailedThenDifferentTargetProvider:
        def __init__(self):
            self.calls = 0

        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            if "classification gate" in system_prompt:
                return ModelResult("cpu_memory_issue", backend)
            self.calls += 1
            seq = [
                '{"decision":"tool_call","phase":"TEST","tool":"check_system_performance","arguments":{},"message":"Checking memory.","reason":"Initial evidence."}',
                '{"decision":"tool_call","phase":"TEST","tool":"check_top_memory_processes","arguments":{},"message":"Finding the largest user process.","reason":"Need process evidence."}',
                '{"decision":"tool_call","phase":"FIX","tool":"close_high_resource_process","arguments":{"pid":111,"process_name":"Code"},"message":"I can close the verified Code process.","reason":"It is a user-space memory consumer."}',
                '{"decision":"tool_call","phase":"FIX","tool":"close_high_resource_process","arguments":{"pid":222,"process_name":"firefox"},"message":"The first target failed, so I propose the next verified user app target.","reason":"The user requested a different app and this target is from the same diagnostics."}',
                '{"decision":"tool_call","phase":"VERIFY","tool":"check_system_performance","arguments":{},"message":"Verifying memory after the successful close.","reason":"Post-fix verification is required."}',
                '{"decision":"resolved","phase":"RESOLVED","status":"RESOLVED","problem_verified":true,"verification_successful":true,"message":"Memory pressure improved.","reason":"Post-fix verification succeeded."}',
            ]
            return ModelResult(seq[min(self.calls-1, len(seq)-1)], backend)

    service = AgentService(provider=FailedThenDifferentTargetProvider())
    calls = []
    original = service.capabilities["close_high_resource_process"]
    service.capabilities["close_high_resource_process"] = ToolDefinition(
        original.name, original.category, original.description, original.requires_approval,
        lambda args: (calls.append(dict(args)) or (ToolResult(False, "simulated close failure") if int(str(args["pid"])) == 111 else ToolResult(True, "closed"))),
        original.argument_schema,
    )
    for name in ("check_system_performance", "check_top_memory_processes"):
        original_diag = service.capabilities[name]
        service.capabilities[name] = ToolDefinition(
            original_diag.name, original_diag.category, original_diag.description, original_diag.requires_approval,
            lambda _args: ToolResult(True, "diagnostic ok"), original_diag.argument_schema
        )

    events: list[AgentEvent] = []
    approvals: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        import helpdesk_agent.agent.service as agent_service_module
        original_reports = agent_service_module.REPORTS_ROOT
        agent_service_module.REPORTS_ROOT = Path(tmp) / "reports"
        try:
            def approve(action, message, reason):
                approvals.append(action)
                if action == "CONFIRM_RESOLUTION":
                    return ApprovalResponse("yes", "")
                return ApprovalResponse("yes", "")
            service.run("My memory is over full", "cloud", events.append, approve)
        finally:
            agent_service_module.REPORTS_ROOT = original_reports

    assert calls == [{"pid": 111, "process_name": "Code"}, {"pid": 222, "process_name": "firefox"}]
    assert approvals[:2] == ["close_high_resource_process", "close_high_resource_process"]
    assert any(event.kind == "resolved" for event in events)
    assert not any(event.kind == "internal_error" for event in events)
    assert not any("mandatory post-fix verification" in event.message for event in events)


def test_close_high_resource_process_builds_script_without_missing_agent_pid():
    import helpdesk_agent.tools.capabilities as capabilities_module

    original_ps = capabilities_module._ps
    try:
        capabilities_module._ps = lambda script, timeout=30: ToolResult(True, script)
        result = capabilities_module.close_high_resource_process({"pid": 1234, "process_name": "Code"})
    finally:
        capabilities_module._ps = original_ps
    assert result.success
    assert "Get-Process -Id 1234" in result.output
    assert "-eq " in result.output
    assert "$protected" in result.output
    assert "agent_pid" not in result.output


def test_same_fix_capability_with_different_arguments_is_not_blocked_as_repeat():
    service = AgentService(provider=FakeProvider())
    definition = service.capabilities["close_high_resource_process"]
    first = {"pid": 111, "process_name": "Code"}
    second = {"pid": 222, "process_name": "firefox"}
    assert service._validate_arguments(first, definition)
    assert service._validate_arguments(second, definition)
    first_key = ("close_high_resource_process", __import__('json').dumps(first, sort_keys=True, ensure_ascii=False))
    second_key = ("close_high_resource_process", __import__('json').dumps(second, sort_keys=True, ensure_ascii=False))
    assert first_key != second_key


def test_ai_settings_round_trip_and_backend_aliases(tmp_path, monkeypatch):
    from helpdesk_agent import config
    from helpdesk_agent.settings import AISettings, GenerationSettings, ProviderSettings, load_settings, normalize_backend, save_settings

    settings_file = tmp_path / "settings.json"
    settings_db = tmp_path / "settings.db"
    monkeypatch.setattr(config, "SETTINGS_PATH", settings_file)
    monkeypatch.setattr(config, "SETTINGS_DB_PATH", settings_db)
    value = AISettings(
        active_backend="local",
        cloud=ProviderSettings("https://cloud.example/v1", "secret", "cloud-model"),
        lm_studio=ProviderSettings("http://localhost:1234/v1", "lm-token", "qwen-model"),
        generation=GenerationSettings(0.2, 0.8, 1500, 20, 2),
    )
    save_settings(value)
    loaded = load_settings()
    assert loaded.active_backend == "lm_studio"
    assert loaded.cloud.model == "cloud-model"
    assert loaded.lm_studio.endpoint.endswith("/v1")
    assert loaded.generation.max_tokens == 1500
    assert normalize_backend("LM Studio") == "lm_studio"
    assert normalize_backend("local") == "lm_studio"


def test_local_backend_is_only_a_compatibility_alias_for_lm_studio(monkeypatch):
    from helpdesk_agent.llm.provider import ModelProvider, ModelResult

    provider = ModelProvider()
    captured = {}

    def fake_complete(system_prompt, user_prompt, backend_name, json_mode):
        captured["backend"] = backend_name
        return ModelResult("{}", backend_name)

    monkeypatch.setattr(provider, "_complete_openai_compatible", fake_complete)
    result = provider.complete("system", "user", "local", json_mode=True)
    assert result.backend == "lm_studio"
    assert captured["backend"] == "lm_studio"


def test_ai_settings_persist_in_sqlite_and_migrate_without_json(monkeypatch, tmp_path):
    from helpdesk_agent import config
    from helpdesk_agent.settings import AISettings, GenerationSettings, ProviderSettings, load_settings, save_settings

    db_path = tmp_path / "settings.db"
    json_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_DB_PATH", db_path)
    monkeypatch.setattr(config, "SETTINGS_PATH", json_path)

    value = AISettings(
        active_backend="lm_studio",
        cloud=ProviderSettings("https://cloud.example/v1", "secret", "cloud-model"),
        lm_studio=ProviderSettings("http://localhost:1234/v1", "lm-token", "qwen-model"),
        generation=GenerationSettings(0.25, 0.85, 1600, 18, 2),
    )
    saved_path = save_settings(value)
    assert saved_path == db_path
    assert db_path.exists()

    loaded = load_settings()
    assert loaded.active_backend == "lm_studio"
    assert loaded.cloud.api_key == "secret"
    assert loaded.lm_studio.model == "qwen-model"
    assert loaded.generation.max_tokens == 1600


def test_legacy_json_is_migrated_to_sqlite(monkeypatch, tmp_path):
    from helpdesk_agent import config
    from helpdesk_agent.settings import AISettings, ProviderSettings, save_settings, load_settings

    db_path = tmp_path / "settings.db"
    json_path = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_DB_PATH", db_path)
    monkeypatch.setattr(config, "SETTINGS_PATH", json_path)

    legacy = AISettings(
        active_backend="cloud",
        cloud=ProviderSettings("https://example/v1", "legacy-key", "legacy-model"),
        lm_studio=ProviderSettings("http://localhost:1234/v1", "", "local-model"),
    )
    json_path.write_text(__import__('json').dumps(__import__('dataclasses').asdict(legacy)), encoding='utf-8')

    loaded = load_settings()
    assert loaded.cloud.model == "legacy-model"
    assert db_path.exists()

    # Remove the JSON source; the migrated SQLite copy remains authoritative.
    json_path.unlink()
    loaded_again = load_settings()
    assert loaded_again.cloud.api_key == "legacy-key"
    assert loaded_again.lm_studio.model == "local-model"

def test_ticket_email_draft_requires_exact_user_recipient():
    from helpdesk_agent.notifications.email import generate_ticket_email
    from helpdesk_agent.llm.provider import ModelResult

    class EmailProvider:
        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            return ModelResult(
                '{"subject":"Ticket TKT-1: Memory pressure","to":"support@example.com","body":"User reports high memory usage. Diagnosis: memory pressure remains."}',
                backend,
            )

    draft = generate_ticket_email(
        EmailProvider(),
        "cloud",
        recipient="support@example.com",
        ticket_id="TKT-1",
        problem="memory is full",
        category="cpu_memory_issue",
        diagnosis="Memory pressure remains.",
        actions=[{"category":"DIAGNOSTIC","tool":"check_system_performance","success":True,"output":"92% memory"}],
        status="TICKET_REQUIRED",
        escalation_reason="No safe L1 action remains.",
    )
    assert draft.to == "support@example.com"
    assert "memory pressure" in draft.body.lower()


def test_ticket_email_draft_rejects_llm_recipient_change():
    import pytest
    from helpdesk_agent.notifications.email import generate_ticket_email
    from helpdesk_agent.llm.provider import ModelResult

    class BadEmailProvider:
        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            return ModelResult(
                '{"subject":"Ticket","to":"attacker@example.com","body":"Ticket body"}',
                backend,
            )

    with pytest.raises(ValueError, match="recipient"):
        generate_ticket_email(
            BadEmailProvider(),
            "cloud",
            recipient="support@example.com",
            ticket_id="TKT-1",
            problem="problem",
            category="internet_issues",
            diagnosis="DNS issue",
            actions=[],
            status="TICKET_REQUIRED",
            escalation_reason="Escalation required.",
        )


def test_send_email_uses_configured_smtp_and_does_not_log_password(monkeypatch):
    from helpdesk_agent.notifications.email import EmailDraft, send_email
    from helpdesk_agent.settings import EmailSettings

    events = []

    class FakeSMTP:
        def __init__(self, host, port, **kwargs):
            events.append(("init", host, port, kwargs))
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            events.append(("exit",))
        def login(self, username, password):
            events.append(("login", username, password))
        def send_message(self, message):
            events.append(("send", message["To"], message["Subject"], message.get_content()))

    monkeypatch.setattr("smtplib.SMTP_SSL", FakeSMTP)
    secret = "test-app-password"
    send_email(
        EmailSettings(sender_email="sender@gmail.com", smtp_password=secret, smtp_host="smtp.gmail.com", smtp_port=465, security="ssl"),
        EmailDraft("Ticket subject", "support@example.com", "Diagnosis: test"),
    )
    assert events[0][0] == "init"
    assert events[1] == ("login", "sender@gmail.com", secret)
    assert events[2][0] == "send"


def test_escalation_asks_recipient_and_sends_email_in_same_session(monkeypatch):
    from helpdesk_agent.llm.provider import ModelResult

    class EscalationProvider:
        def __init__(self):
            self.calls = 0
        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            if "classification gate" in system_prompt:
                return ModelResult("internet_issues", backend)
            self.calls += 1
            if self.calls == 1:
                return ModelResult(
                    '{"decision":"tool_call","phase":"TEST","tool":"check_adapter_state","arguments":{},"message":"Checking adapter.","reason":"Initial connectivity test."}',
                    backend,
                )
            if self.calls == 2:
                return ModelResult(
                    '{"decision":"escalate","phase":"ESCALATE","status":"TICKET_REQUIRED","problem_verified":true,"verification_successful":false,"message":"Escalating to support.","reason":"No safe L1 remediation remains."}',
                    backend,
                )
            return ModelResult(
                '{"subject":"Ticket TKT: Internet issue","to":"support@example.com","body":"User reports an Internet issue. Diagnosis: No safe L1 remediation remains."}',
                backend,
            )

    import helpdesk_agent.agent.service as agent_service_module
    import helpdesk_agent.ticketing.service as ticketing_service_module
    from helpdesk_agent.settings import EmailSettings
    from pathlib import Path

    service = AgentService(provider=EscalationProvider())
    original = service.capabilities["check_adapter_state"]
    service.capabilities["check_adapter_state"] = ToolDefinition(
        original.name, original.category, original.description, original.requires_approval,
        lambda _args: ToolResult(True, "adapter ok"), original.argument_schema
    )
    monkeypatch.setattr(agent_service_module, "REPORTS_ROOT", Path(monkeypatch.tmpdir if hasattr(monkeypatch, 'tmpdir') else '/tmp'))
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        monkeypatch.setattr(agent_service_module, "REPORTS_ROOT", tmp_path / "reports")
        monkeypatch.setattr(ticketing_service_module, "TICKETS_ROOT", tmp_path / "tickets")
        original_settings_loader = agent_service_module.load_settings
        class E:
            pass
        dummy = E(); dummy.email = EmailSettings(sender_email="sender@gmail.com", smtp_password="secret")
        dummy.generation = None
        monkeypatch.setattr(agent_service_module, "load_settings", lambda: dummy)
        sent = []
        monkeypatch.setattr("helpdesk_agent.agent.service.send_email", lambda settings, draft: sent.append((draft.to, draft.subject, draft.body)))

        events = []
        answers = []
        def ask(action, message, reason):
            answers.append(action)
            if action == "EMAIL_RECIPIENT":
                return ApprovalResponse("idea", "support@example.com")
            return ApprovalResponse("no", "")

        service.run("internet is broken", "cloud", events.append, ask, ask)

        assert "EMAIL_RECIPIENT" in answers
        assert sent and sent[0][0] == "support@example.com"
        assert any(e.kind == "ticket" for e in events)
        assert not any(e.kind == "internal_error" for e in events)



def test_email_settings_round_trip_in_sqlite(monkeypatch, tmp_path):
    from helpdesk_agent import config
    from helpdesk_agent.settings import AISettings, EmailSettings, load_settings, save_settings

    monkeypatch.setattr(config, "SETTINGS_DB_PATH", tmp_path / "settings.db")
    monkeypatch.setattr(config, "SETTINGS_PATH", tmp_path / "legacy.json")
    value = AISettings(email=EmailSettings(
        sender_email="sender@gmail.com",
        smtp_password="secret",
        smtp_host="smtp.gmail.com",
        smtp_port=465,
        security="ssl",
    ))
    save_settings(value)
    loaded = load_settings()
    assert loaded.email.sender_email == "sender@gmail.com"
    assert loaded.email.smtp_password == "secret"
    assert loaded.email.smtp_port == 465


def test_ticket_email_llm_draft_repair_preserves_recipient():
    from helpdesk_agent.notifications.email import generate_ticket_email
    from helpdesk_agent.llm.provider import ModelResult

    class RepairProvider:
        def __init__(self):
            self.calls = 0
        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            self.calls += 1
            if self.calls == 1:
                return ModelResult('{"subject":"bad","to":"other@example.com"}', backend)
            return ModelResult('{"subject":"Ticket fixed","to":"support@example.com","body":"Diagnosis: DNS issue."}', backend)

    provider = RepairProvider()
    draft = generate_ticket_email(
        provider,
        "cloud",
        recipient="support@example.com",
        ticket_id="TKT-1",
        problem="internet broken",
        category="internet_issues",
        diagnosis="DNS issue",
        actions=[],
        status="TICKET_REQUIRED",
        escalation_reason="No safe L1 remediation remains.",
    )
    assert provider.calls == 2
    assert draft.to == "support@example.com"
    assert draft.subject == "Ticket fixed"


def test_general_support_routes_directly_to_ticket_without_local_troubleshooting():
    from helpdesk_agent.llm.provider import ModelResult
    import helpdesk_agent.agent.service as agent_service_module

    class SupportProvider(FakeProvider):
        def complete(self, system_prompt, user_prompt, backend, *, json_mode=False):
            if "classification gate" in system_prompt:
                return ModelResult("GENERAL_SUPPORT", backend)
            if "collect_device_identity" in user_prompt:
                return ModelResult('{"collect_device_identity":false}', backend)
            return ModelResult('{"subject":"Support request","to":"support@example.com","body":"Support request."}', backend)

    service = AgentService(provider=SupportProvider())
    events: list[AgentEvent] = []
    with tempfile.TemporaryDirectory() as tmp:
        original_reports = agent_service_module.REPORTS_ROOT
        original_tickets = ticketing_service.TICKETS_ROOT
        agent_service_module.REPORTS_ROOT = Path(tmp) / "reports"
        ticketing_service.TICKETS_ROOT = Path(tmp) / "tickets"
        try:
            service.run(
                "My company subscription has disappeared.",
                "cloud",
                events.append,
                lambda action, message, reason: ApprovalResponse("no", ""),
                lambda action, message, reason: ApprovalResponse("no", ""),
            )
        finally:
            agent_service_module.REPORTS_ROOT = original_reports
            ticketing_service.TICKETS_ROOT = original_tickets
    assert any(event.kind == "ticket" for event in events)
    assert not any(event.kind == "classification" and "UNSUPPORTED" in event.message for event in events)
    assert not any(event.kind == "internal_error" for event in events)


def test_device_identity_capability_is_exposed_and_safe_metadata_is_defined():
    service = AgentService(provider=FakeProvider())
    assert "get_device_identity" in service.capabilities
    tool = service.capabilities["get_device_identity"]
    assert tool.category == "DIAGNOSTIC"
    assert tool.requires_approval is False
