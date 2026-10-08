from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..config import DEFAULT_MODEL_MAX_TOKENS, DEFAULT_TEMPERATURE, DEFAULT_TOP_P
from ..settings import normalize_backend, provider_settings, load_settings


@dataclass(frozen=True)
class ModelResult:
    content: str
    backend: str
    finish_reason: str = ""


class ModelProviderError(RuntimeError):
    pass


def _extract_json_candidate(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if len(lines) >= 3:
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    if cleaned.startswith("{") and cleaned.endswith("}"):
        return cleaned

    start = cleaned.find("{")
    if start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return cleaned[start:index + 1]
    raise ValueError(f"Model did not return a complete JSON object: {cleaned[:700]}")


def parse_json_object(text: str) -> dict[str, Any]:
    candidate = _extract_json_candidate(text)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned malformed JSON: {exc}: {candidate[:700]}") from exc
    if not isinstance(value, dict):
        raise ValueError("Model JSON root must be an object.")
    return value


class ModelProvider:
    """OpenAI-compatible provider for cloud APIs and LM Studio.

    LM Studio runs the local model; this application never loads GGUF or
    llama.cpp files itself.
    """

    def complete(self, system_prompt: str, user_prompt: str, backend: str, *, json_mode: bool = False) -> ModelResult:
        backend_name = normalize_backend(backend)
        if backend_name == "cloud":
            return self._complete_openai_compatible(system_prompt, user_prompt, "cloud", json_mode)
        return self._complete_openai_compatible(system_prompt, user_prompt, "lm_studio", json_mode)

    def list_models(self, backend: str) -> list[str]:
        settings = load_settings()
        cfg = provider_settings(settings, backend)
        return self.list_models_for_config(cfg.endpoint, cfg.api_key)

    @staticmethod
    def list_models_for_config(endpoint: str, api_key: str = "") -> list[str]:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ModelProviderError("The 'openai' package is not installed. Run pip install -r requirements.txt.") from exc

        client = OpenAI(
            api_key=api_key or "lm-studio",
            base_url=_normalize_openai_base_url(endpoint),
            timeout=15.0,
            max_retries=0,
        )
        try:
            result = client.models.list()
        except Exception as exc:
            raise ModelProviderError(f"Could not list models from {endpoint}: {exc}") from exc
        ids = sorted({str(item.id).strip() for item in getattr(result, "data", []) if getattr(item, "id", None)})
        if not ids:
            raise ModelProviderError("The endpoint responded successfully, but no model IDs were returned.")
        return ids

    def _complete_openai_compatible(
        self,
        system_prompt: str,
        user_prompt: str,
        backend_name: str,
        json_mode: bool,
    ) -> ModelResult:
        settings = load_settings()
        cfg = provider_settings(settings, backend_name)
        endpoint = _normalize_openai_base_url(cfg.endpoint)
        model = cfg.model.strip()
        if not model:
            raise ModelProviderError(
                f"{_display_backend(backend_name)} model is not configured. Open AI Settings and select a model."
            )
        if backend_name == "cloud" and not cfg.api_key:
            raise ModelProviderError("Cloud model is not configured: API key is empty.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ModelProviderError("The 'openai' package is not installed. Run pip install -r requirements.txt.") from exc

        client = OpenAI(
            api_key=cfg.api_key or "lm-studio",
            base_url=endpoint,
            timeout=90.0,
            max_retries=2,
        )

        generation = settings.generation
        request: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": generation.temperature if generation else DEFAULT_TEMPERATURE,
            "top_p": generation.top_p if generation else DEFAULT_TOP_P,
            "max_tokens": generation.max_tokens if generation else DEFAULT_MODEL_MAX_TOKENS,
            "stream": False,
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}

        try:
            return self._send(client, request, backend_name)
        except ModelProviderError:
            raise
        except Exception as first_exc:
            if json_mode and "response_format" in request:
                fallback = dict(request)
                fallback.pop("response_format", None)
                try:
                    return self._send(client, fallback, backend_name)
                except Exception as second_exc:
                    raise ModelProviderError(
                        f"{_display_backend(backend_name)} request failed with JSON mode and compatibility fallback: {second_exc}"
                    ) from second_exc
            raise ModelProviderError(f"{_display_backend(backend_name)} request failed: {first_exc}") from first_exc

    @staticmethod
    def _send(client: Any, request: dict[str, Any], backend_name: str) -> ModelResult:
        response = client.chat.completions.create(**request)
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ModelProviderError(f"{_display_backend(backend_name)} model returned no choices.")
        message = choices[0].message
        content = getattr(message, "content", None) or ""
        finish_reason = str(getattr(choices[0], "finish_reason", "") or "")
        if not content.strip():
            raise ModelProviderError(
                f"{_display_backend(backend_name)} model returned an empty response (finish_reason={finish_reason or 'unknown'})."
            )
        return ModelResult(content=content, backend=backend_name, finish_reason=finish_reason)


def _normalize_openai_base_url(endpoint: str) -> str:
    raw = (endpoint or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.endswith("/v1"):
        return raw
    return f"{raw}/v1"


def _display_backend(backend: str) -> str:
    return "LM Studio" if normalize_backend(backend) == "lm_studio" else "Cloud"
