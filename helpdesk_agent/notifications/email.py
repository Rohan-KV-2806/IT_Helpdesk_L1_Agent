from __future__ import annotations

import json
import re
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any

from ..llm.provider import ModelProvider, ModelProviderError, parse_json_object
from ..settings import EmailSettings, load_settings


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class EmailDraft:
    subject: str
    to: str
    body: str


def is_valid_email(value: str) -> bool:
    address = (value or "").strip()
    if not _EMAIL_RE.match(address):
        return False
    _, parsed = parseaddr(address)
    return parsed.lower() == address.lower()


def generate_ticket_email(
    provider: ModelProvider,
    backend: str,
    *,
    recipient: str,
    ticket_id: str,
    problem: str,
    category: str | None,
    diagnosis: str,
    actions: list[dict[str, Any]],
    status: str,
    escalation_reason: str,
) -> EmailDraft:
    if not is_valid_email(recipient):
        raise ValueError("The support recipient email address is invalid.")

    action_text = json.dumps(actions[-10:], ensure_ascii=False, indent=2)
    if len(action_text) > 14000:
        action_text = action_text[-14000:]

    prompt = f"""
Create the email that will send an L1 IT Helpdesk ticket to the support team.

OUTPUT CONTRACT:
Return ONLY a JSON object with exactly these string fields:
- subject: professional, concise ticket subject
- to: EXACTLY the recipient supplied below; do not change it
- body: professional plain-text ticket description

RECIPIENT (must be copied exactly):
{recipient}

TICKET ID:
{ticket_id}

STATUS:
{status}

CATEGORY:
{category or "Unsupported / No matching L1 KB"}

USER PROBLEM:
{problem}

L1 DIAGNOSIS:
{diagnosis or "No conclusive L1 diagnosis was established."}

WHY THIS WAS ESCALATED:
{escalation_reason or "L1 could not safely complete the request."}

DIAGNOSTIC / ACTION HISTORY:
{action_text}

EMAIL BODY RULES:
- Clearly describe what the user reported.
- Summarize the useful diagnostics and any L1 actions already attempted.
- Include the diagnosis when one exists. Do not invent one.
- State why the ticket needs support-team attention.
- Include the ticket ID.
- Do not claim a fix succeeded unless the history shows it succeeded.
- Do not include secrets, API keys, SMTP passwords, or model configuration.
- Plain text only. No markdown tables.
- Do not add any recipient other than the exact supplied recipient.
""".strip()

    system_prompt = "You are the L1 Helpdesk email writer. Generate accurate ticket emails only."
    result = provider.complete(system_prompt, prompt, backend, json_mode=True)
    try:
        return _parse_draft(result.content, recipient)
    except Exception as first_error:
        repair = (
            f"{prompt}\n\nEMAIL DRAFT VALIDATION ERROR:\n{first_error}\n\n"
            "Return ONLY valid JSON with exactly the fields subject, to, body. "
            "The `to` value MUST exactly equal the recipient supplied above."
        )
        repaired = provider.complete(system_prompt, repair, backend, json_mode=True)
        return _parse_draft(repaired.content, recipient)


def _parse_draft(content: str, recipient: str) -> EmailDraft:
    data = parse_json_object(content)
    subject = str(data.get("subject", "")).strip()
    to = str(data.get("to", "")).strip()
    body = str(data.get("body", "")).strip()
    if not subject:
        raise ValueError("The LLM email draft is missing a subject.")
    if not body:
        raise ValueError("The LLM email draft is missing a body.")
    if to.lower() != recipient.strip().lower():
        raise ValueError("The LLM email recipient did not exactly match the recipient entered during chat.")
    if not is_valid_email(to):
        raise ValueError("The LLM email recipient is not a valid email address.")
    return EmailDraft(subject=subject, to=to, body=body)


def send_email(settings: EmailSettings, draft: EmailDraft) -> None:
    sender = settings.sender_email.strip()
    password = settings.smtp_password.strip()
    host = settings.smtp_host.strip() or "smtp.gmail.com"
    port = int(settings.smtp_port)
    security = settings.security.strip().lower()

    if not is_valid_email(sender):
        raise ValueError("Support email settings are incomplete: enter a valid sender email address.")
    if not password:
        raise ValueError("Support email settings are incomplete: enter the SMTP/app password.")
    if not host:
        raise ValueError("Support email settings are incomplete: SMTP host is empty.")
    if port <= 0 or port > 65535:
        raise ValueError("Support email settings contain an invalid SMTP port.")
    if security not in {"ssl", "starttls"}:
        raise ValueError("Support email settings contain an invalid security mode.")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = draft.to
    message["Subject"] = draft.subject
    message.set_content(draft.body)

    context = ssl.create_default_context()
    if security == "ssl":
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
            smtp.login(sender, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(sender, password)
            smtp.send_message(message)
