# IT Helpdesk L1 Agent

A lightweight Windows L1 IT Helpdesk agent with a PySide6 desktop UI, local/cloud LLM support, Python-based declarative knowledge bases, controlled Windows capabilities, approval-gated fixes, verification, retry decisions, and ticket escalation.

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

The KBs are declarative dictionaries under `src/helpdesk_agent/knowledge/`. They define:

- problem categories and descriptions
- `Testing`, `Diagnosis`, `Analysis`, `Fix`, `Verification`, `Retry`, and `Escalation`
- exact executable capability labels
- KB-specific safety rules

There is **no hardcoded category-to-KB mapping** and no Python decision tree such as `if category == internet: ...`.

The executable capability layer is deliberately separate from troubleshooting knowledge. Its job is only to implement controlled OS operations and validate inputs.

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

The LLM decides whether the idea corresponds to a safe documented diagnostic/fix, or whether it should reject the request and continue safely.

## Error handling

The runtime is fail-closed:

- invalid classifier output is repaired once; the classifier also accepts accidental legacy JSON containing a valid KB ID
- malformed orchestration JSON gets a bounded repair attempt
- unknown tools, unavailable KB tools, invalid arguments, premature fixes, skipped verification, repeated tool loops, and repeated fixes are blocked
- tool execution failures are returned to the LLM as factual tool results so the agent can choose another documented action or escalate
- user denial does not become a new classification request
- internal LLM/application failures never create support tickets
- only unsupported user requests and explicit LLM escalation create tickets
- the agent has a hard maximum-step limit to prevent infinite loops

## Run

```bat
python -m pip install -r requirements.txt
copy .env.example .env
python -m src.helpdesk_agent.main
```

Configure `.env` for either backend.

Example cloud configuration:

```text
CLOUD_API_ENDPOINT=https://integrate.api.nvidia.com/v1
CLOUD_API_KEY=YOUR_KEY_HERE
CLOUD_MODEL=YOUR_MODEL_HERE
```

Example local configuration:

```text
LOCAL_MODEL=models/your-model.gguf
```

The local model path may be absolute or relative to the project directory.

## Outputs

- Escalation tickets: `tickets/`
- Resolved/session reports: `reports/`

The application does not copy or upload model/API keys into tickets or reports.

## Testing

Static validation:

```bat
python -m compileall src
python -m pytest -q
```

The tests cover KB discovery/validation, the classifier's legacy-JSON compatibility path, orchestration decision normalization, and the required post-fix verification guard without executing Windows-changing commands.


## Guardrails added
- The LLM classifier decides whether a message is a supported IT problem, GENERAL_CHAT, or UNSUPPORTED.
- GENERAL_CHAT never creates tickets or reports and receives a fixed L1 helpdesk response.
- A technical resolution is never finalized until the user confirms the original problem is actually solved.
- If the user selects No or Your idea in the resolution decision window, the instruction is returned to the LLM orchestrator; classification is not repeated.
