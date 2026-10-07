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

The UI was left unchanged.

## KB-driven architecture

There is intentionally **no hardcoded category list** and **no hardcoded category-to-file mapping** in the agent.

At runtime:

```text
KnowledgeBase/*.md
        ↓
discover filenames dynamically
        ↓
LLM classification chooses one exact filename
        ↓
Load that exact Markdown KB
        ↓
LLM reads the KB and chooses one exact tool documented by that KB
        ↓
Python validates that the tool exists and is referenced by the KB
        ↓
Python executes the registered implementation
        ↓
Actual result returns to the LLM
        ↓
LLM follows the KB to the next step
        ↓
RESOLVED or ESCALATE
```

Python does **not** encode rules such as "Internet → internet_connectivity.md" or "USB → usb_device_port_problem.md".

To add another knowledge base, place another `.md` file in `KnowledgeBase/`. The classifier will discover the new filename automatically. The KB should document its own troubleshooting workflow and exact tool names.

## Tool registry

`helpdesk_agent/tools/registry.py` contains the real Python implementations of executable tools. This registry is a capability layer, not a troubleshooting decision tree.

A tool is executable for a session only when its exact identifier is documented in the selected KB and the same identifier exists in the registry.

State-changing tools require the existing GUI Yes/No approval dialog. The LLM must return the FIX action itself; it must not request fix approval through ASK_USER.

## Internal failures

Invalid model output, missing tools, malformed arguments, and similar application/model errors are reported as internal agent errors. They are not converted into user tickets.

## Knowledge bases

The source does not bundle a hardcoded list of KB files. Copy your `.md` files into the project-root `KnowledgeBase/` directory.
