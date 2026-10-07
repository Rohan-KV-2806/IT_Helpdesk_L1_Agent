# L1 Agent — `src`

Minimal PySide6 desktop client for the Windows L1 Helpdesk agent.

## Run

From the project root:

```bat
pip install -r requirements.txt
python -m src.helpdesk_agent.main
```

The application reads `.env`, `KnowledgeBase/`, and writes `tickets/` and `reports/` relative to the directory from which it is launched.

## Model selector

The top-right dropdown selects `cloud` or `local` for each request.

- `cloud`: OpenAI-compatible Chat Completions endpoint using `CLOUD_API_ENDPOINT`, `CLOUD_API_KEY`, and `CLOUD_MODEL`.
- `local`: GGUF model using `LOCAL_MODEL` and `llama-cpp-python`.

The system prompt is kept as one string in `helpdesk_agent/config.py`.

## Knowledge bases

The app currently supports:

- `KnowledgeBase/time_date_synchronization.md`
- `KnowledgeBase/windows_update_stuck_failing.md`
- `KnowledgeBase/application_not_responding.md`
- `KnowledgeBase/internet_connectivity.md`

A few filename aliases are accepted for development convenience.

## Important architecture

The LLM proposes one action. Python validates that the action is an exact registered tool, is referenced by the selected KB, and is not a repeated diagnostic. Python executes the tool. Model/application errors are not converted into user tickets.


Post-fix verification: a diagnostic that already ran may be run once again immediately after a FIX so the original problem can be verified. Other duplicate diagnostics remain blocked.
