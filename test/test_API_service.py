import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# =========================================================
# Load environment variables
# =========================================================

load_dotenv()

API_ENDPOINT = os.getenv("CLOUD_API_ENDPOINT")
API_KEY = os.getenv("CLOUD_API_KEY")
MODEL = os.getenv("CLOUD_MODEL")


if not API_ENDPOINT:
    raise ValueError("CLOUD_API_ENDPOINT is not set")

if not API_KEY:
    raise ValueError("CLOUD_API_KEY is not set")

if not MODEL:
    raise ValueError("CLOUD_MODEL is not set")


# =========================================================
# Load Knowledge Base
# =========================================================

KB_PATH = Path("KnowledgeBase/internet_connectivity.md")

if not KB_PATH.exists():
    raise FileNotFoundError(f"Knowledge base not found: {KB_PATH}")

knowledge_base = KB_PATH.read_text(encoding="utf-8")


# =========================================================
# Create Cloud Client
# =========================================================

client = OpenAI(
    api_key=API_KEY,
    base_url=API_ENDPOINT
)


# =========================================================
# System Prompt
# =========================================================

SYSTEM_PROMPT = """
You are an IT Helpdesk L1 diagnostic agent.

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

USER_PROBLEM = "There is something wrong with my internet."


# =========================================================
# Build Input
# =========================================================

user_input = f"""
KNOWLEDGE BASE:

{knowledge_base}

USER PROBLEM:

{USER_PROBLEM}

Determine the next action.
"""


# =========================================================
# Call Cloud Model
# =========================================================

response = client.responses.create(
    model=MODEL,
    instructions=SYSTEM_PROMPT,
    input=user_input,
    temperature=0,
    extra_body={"chat_template_kwargs":{"enable_thinking":False}}
)


# =========================================================
# Display Result
# =========================================================

print("\n==============================")
print("USER PROBLEM")
print("==============================")
print(USER_PROBLEM)

print("\n==============================")
print("CLOUD MODEL")
print("==============================")
print(MODEL)

print("\n==============================")
print("AGENT DECISION")
print("==============================")
print(response.output_text)