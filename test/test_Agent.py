from llama_cpp import Llama
from pathlib import Path


# =========================================================
# Configuration
# =========================================================

MODEL_PATH = "LocalLLMs/Falcon-H1-0.5B-Instruct-Q4_K_M.gguf"
KB_PATH = "KnowledgeBase/internet_connectivity.md"


# =========================================================
# Load Knowledge Base
# =========================================================

def load_knowledge_base(path: str) -> str:
    kb_path = Path(path)

    if not kb_path.exists():
        raise FileNotFoundError(
            f"Knowledge base not found: {kb_path}"
        )

    return kb_path.read_text(
        encoding="utf-8"
    )


knowledge_base = load_knowledge_base(KB_PATH)


# =========================================================
# Load Local LLM
# =========================================================

llm = Llama(
    model_path=MODEL_PATH,
    n_ctx=12000,
    n_threads=2,
    verbose=False
)


# =========================================================
# System Prompt
# =========================================================

SYSTEM_PROMPT = """You are an IT Helpdesk L1 diagnostic agent.

Your task is to determine the SINGLE NEXT ACTION required to
diagnose or resolve the user's current problem.

You MUST use the supplied Knowledge Base as the source of truth.

RULES:

1. Select exactly ONE action.
2. The action MUST exist in the Knowledge Base.
3. Never invent a tool, command, action, or diagnostic.
4. Do NOT provide a troubleshooting plan.
5. Do NOT describe future steps.
6. Do NOT list multiple actions.
7. Do NOT assume the result of a diagnostic.
8. A diagnostic must be performed before choosing a fix when
   the cause is unknown.
9. Prefer read-only diagnostics over system-changing actions.
10. Never claim that an action has already been executed.
11. System-changing actions require user approval.
12. If the Knowledge Base requires escalation, select ESCALATE.
13. If there is insufficient information to choose a fix,
    select the most appropriate diagnostic.
14. Base the decision only on:
    - the user's problem
    - the supplied Knowledge Base
    - diagnostic results provided by the system
15. Do not use your general knowledge to invent procedures.
16. Keep the reason to ONE short sentence.

CRITICAL:

You are NOT responsible for creating a complete troubleshooting
procedure.

You are only responsible for choosing the NEXT action.

After selecting the action, STOP.

Never output:
- a second action
- future actions
- a troubleshooting sequence
- "then"
- "next"
- "after that"
- additional recommendations

OUTPUT FORMAT:

ACTION_TYPE: <DIAGNOSTIC | FIX | ESCALATE>
ACTION: <exact action name from Knowledge Base>
REASON: <one short sentence>

OUTPUT ONLY THESE THREE LINES.

Do not output Markdown.
Do not output explanations.
Do not output anything before or after these three lines.
"""


# =========================================================
# User Problem
# =========================================================

USER_PROBLEM = """
There is something wrong with my internet.
"""


# =========================================================
# Build Prompt
# =========================================================

prompt = f"""
KNOWLEDGE BASE:

{knowledge_base}

USER PROBLEM:

{USER_PROBLEM}

Determine the next action.
"""


# =========================================================
# Ask Model
# =========================================================

response = llm.create_chat_completion(
    messages=[
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0.3,
    max_tokens=1500,
)


# =========================================================
# Get Response
# =========================================================

result = response["choices"][0]["message"]["content"].strip()


# Remove Qwen thinking block if the template still produces one
if "</think>" in result:
    result = result.split("</think>", 1)[1].strip()


print("\n==============================")
print("USER PROBLEM")
print("==============================")
print(USER_PROBLEM.strip())

print("\n==============================")
print("AGENT DECISION")
print("==============================")
print(result)