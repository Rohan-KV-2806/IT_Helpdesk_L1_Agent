# IT Helpdesk L1 Agent

A lightweight Windows L1 IT Helpdesk agent with a PySide6 desktop UI, OpenAI-compatible cloud + LM Studio backends, Python-based declarative knowledge bases, controlled Windows capabilities, approval-gated fixes, verification, retry decisions, and ticket escalation.

## Architecture

```text
User
  ↓
KB classifier LLM
  ↓
Selected Python KB
  ↓
LLM orchestrator
  ↓
Choose exactly one documented capability
  ↓
Python executes capability
  ↓
Real result goes back to the LLM
  ↓
Repeat until RESOLVED / ASK USER / ESCALATE
```

The LLM is the troubleshooting orchestrator. Python is the safety and execution layer.

The KBs are declarative dictionaries under `helpdesk_agent/knowledge/`. They define:

- problem categories and descriptions
- `Testing`, `Diagnosis`, `Analysis`, `Fix`, `Verification`, `Retry`, and `Escalation`
- exact executable capability labels
- KB-specific safety rules

There is **no hardcoded category-to-KB mapping** and no Python decision tree such as `if category == internet: ...`.

## AI backends

The application no longer loads local model files itself. There is no `llama-cpp-python` dependency and no GGUF loading path.

Use **LM Studio** for local models: start the LM Studio server, point the agent to its OpenAI-compatible endpoint (default `http://localhost:1234/v1`), then select one of the models returned by `GET /v1/models`. LM Studio documents `/v1/models` as its OpenAI-compatible model-list endpoint and `/v1/chat/completions` for chat/tool use.

Cloud providers that expose an OpenAI-compatible chat endpoint can be configured the same way.

## AI Settings

Click **AI Settings** in the main window to configure:

- Cloud endpoint, API key, and model
- LM Studio endpoint, optional API token, and model
- model lists loaded directly from each provider
- temperature, top-p, max output tokens, and max agent steps

The model selector is editable, so a provider can still be used when its `/models` endpoint is unavailable by typing a known model ID manually.

Settings are stored in `settings.json`. For the packaged EXE, the application data directory defaults to `%APPDATA%\\L1Agent`, keeping mutable settings, reports, and tickets out of the bundled executable directory.

## Included knowledge bases

- `USB_ports.py`
- `audio_errors.py`
- `internet_issues.py`
- `cpu_memory_issue.py`
- `not_responding_apps_issue.py`
- `time_date_sync_problems.py`

Adding another KB only requires adding another Python module containing a valid `KNOWLEDGE_BASE` dictionary. The classifier discovers it at runtime.

## Agent workflow

```text
TEST
 ↓
DIAGNOSIS
 ↓
ANALYSIS
 ↓
FIX  ← GUI approval
 ↓
TEST / VERIFY
 ↓
 ┌───────────────┐
 │               │
FIXED         STILL BAD
 │               │
RESOLVED     another KB action?
                │
           ┌────┴────┐
          YES       NO
           │         │
        decision    ticket
         window
```

After a fix, a KB-defined verification diagnostic is required before the LLM can declare success.

## Decision window

For every state-changing fix, the existing UI shows:

- **Yes** — execute the exact approved fix.
- **No** — do not execute it; return the decision to the LLM for reconsideration.
- **Your idea** — send free-form troubleshooting instructions to the current LLM session. It never goes through KB classification.

An `ask_user` decision also opens the same interactive window immediately. The response returns directly to the existing troubleshooting session.

## Process/memory safety

The latest hardened version is retained:

- process-close fixes require an exact verified PID and process name
- the runtime re-checks the live process immediately before closing
- the agent and its parent are protected
- Windows/security processes are protected
- different verified PIDs are different FIX targets even when the same capability is reused
- a failed FIX is treated as **no system change** unless the tool result proves otherwise
- failed targets are remembered so the LLM can choose another documented path

## EXE layout

The project is intentionally packaged as a normal top-level Python package so PyInstaller can use `run.py` as a single entry point:

```text
L1Agent/
├── helpdesk_agent/
│   ├── agent/
│   ├── knowledge/
│   ├── llm/
│   ├── ticketing/
│   ├── tools/
│   └── ui/
├── tests/
├── run.py
├── L1Agent.spec
├── build_exe.bat
├── requirements.txt
└── .env.example
```

The PyInstaller spec bundles the declarative KB Python files as runtime data because the agent discovers them from the `knowledge` directory. PyInstaller supports explicitly bundling data files and building one-file or one-folder Windows applications.

Build on Windows:

```bat
python -m pip install -r requirements.txt
build_exe.bat
```

The generated executable is placed under `dist\\L1Agent\\` by the included spec.

## Run from source

```bat
python -m pip install -r requirements.txt
copy .env.example .env
python run.py
```

The AI Settings window is the recommended configuration method.

## Outputs

- Escalation tickets: `tickets/`
- Resolved/session reports: `reports/`

For a packaged EXE these writable outputs are placed under `%APPDATA%\\L1Agent` by default.

The application does not copy or upload model/API keys into tickets or reports.

## Testing

```bat
python -m compileall helpdesk_agent run.py tests
python -m pytest -q
```

The existing regression tests cover KB discovery/validation, classifier behavior, orchestration normalization, interactive user decisions, PID handling, failed-fix recovery, process safety, and required post-fix verification.


### Persistent AI settings
The AI Settings dialog persists endpoint, API key, model, backend, and generation settings in SQLite at `%APPDATA%\L1Agent\settings.db` for packaged builds (or the configured project root for source builds). A legacy `settings.json` is read once and migrated automatically when found. No model files are loaded by this application; local inference is provided through the LM Studio OpenAI-compatible endpoint.

### Final EXE packaging
The distribution root is `IT_Helpdesk_L1_Agent`. Run `build_exe.bat` from that folder to create `dist\L1Agent\L1Agent.exe`. Runtime-writable reports, tickets, and settings are kept outside the bundled application, under the per-user application data directory.
