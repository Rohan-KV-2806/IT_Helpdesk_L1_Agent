# IT Helpdesk L1 Agent — `src`

This `src` folder is intended to sit directly inside the project root.

## Run

From the project root:

```bat
python -m src.helpdesk_agent.main
```

Required packages in the existing environment include:

```text
PySide6
openai
python-dotenv
llama-cpp-python
```

The application reads `.env` from the project root. It tries the cloud OpenAI-compatible endpoint first and falls back to `LOCAL_MODEL` if the cloud call fails.

## Runtime behavior

- Normal mode: the model infers the intent, then loads that intent's Markdown KB.
- Debug mode: selecting an intent bypasses intent classification and loads the mapped KB directly.
- The model can only select allowlisted Python tools.
- Diagnostics run automatically.
- System-changing fixes require approval.
- When the issue is unresolved, outside L1 scope, the KB is missing, or the agent becomes unsafe/uncertain, a local triaged JSON ticket is created in `data/tickets/`.
- Commands run with `cwd=Path.cwd()`, i.e. the directory from which the application is launched.
