from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import (
    CLOUD_API_ENDPOINT,
    CLOUD_API_KEY,
    CLOUD_MODEL,
    LOCAL_CHAT_TEMPLATE_THINKING,
    LOCAL_MODEL,
    LOCAL_N_GPU_LAYERS,
    MODEL_CONTEXT,
    MODEL_MAX_TOKENS,
    MODEL_THREADS,
    TEMPERATURE,
    TOP_P,
)


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
    def __init__(self):
        self._local = None
        self._cloud = None

    def complete(self, system_prompt: str, user_prompt: str, backend: str, *, json_mode: bool = False) -> ModelResult:
        backend_name = backend.lower().strip()
        if backend_name == "cloud":
            return self._cloud_complete(system_prompt, user_prompt, json_mode)
        if backend_name == "local":
            return self._local_complete(system_prompt, user_prompt, json_mode)
        raise ModelProviderError(f"Unknown backend '{backend}'. Use cloud or local.")

    def _cloud_complete(self, system_prompt: str, user_prompt: str, json_mode: bool) -> ModelResult:
        if not CLOUD_API_KEY:
            raise ModelProviderError("Cloud model is not configured: CLOUD_API_KEY is empty.")
        if not CLOUD_MODEL:
            raise ModelProviderError("Cloud model is not configured: CLOUD_MODEL is empty.")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ModelProviderError("The 'openai' package is not installed. Run pip install -r requirements.txt.") from exc

        if self._cloud is None:
            self._cloud = OpenAI(
                api_key=CLOUD_API_KEY,
                base_url=CLOUD_API_ENDPOINT,
                timeout=90.0,
                max_retries=2,
            )

        request: dict[str, Any] = {
            "model": CLOUD_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_tokens": MODEL_MAX_TOKENS,
            "stream": False,
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}

        try:
            return self._send_cloud(request)
        except ModelProviderError:
            raise
        except Exception as first_exc:
            # Some OpenAI-compatible endpoints reject response_format even
            # though normal chat completions work. Retry once without it; the
            # orchestrator still enforces JSON in its prompt and parser.
            if json_mode and "response_format" in request:
                fallback = dict(request)
                fallback.pop("response_format", None)
                try:
                    return self._send_cloud(fallback)
                except Exception as second_exc:
                    raise ModelProviderError(
                        f"Cloud model request failed with JSON mode and compatibility fallback: {second_exc}"
                    ) from second_exc
            raise ModelProviderError(f"Cloud model request failed: {first_exc}") from first_exc

    def _send_cloud(self, request: dict[str, Any]) -> ModelResult:
        response = self._cloud.chat.completions.create(**request)
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise ModelProviderError("Cloud model returned no choices.")
        message = choices[0].message
        content = getattr(message, "content", None) or ""
        finish_reason = str(getattr(choices[0], "finish_reason", "") or "")
        if not content.strip():
            raise ModelProviderError(
                f"Cloud model returned an empty response (finish_reason={finish_reason or 'unknown'})."
            )
        return ModelResult(content=content, backend="cloud", finish_reason=finish_reason)

    def _local_complete(self, system_prompt: str, user_prompt: str, json_mode: bool) -> ModelResult:
        model_path = self._resolve_local_model()
        if not model_path:
            raise ModelProviderError("Local model is not configured: LOCAL_MODEL is empty.")

        if self._local is None:
            try:
                from llama_cpp import Llama
            except ImportError as exc:
                raise ModelProviderError(
                    "The 'llama-cpp-python' package is not installed. Run pip install -r requirements.txt."
                ) from exc
            try:
                self._local = Llama(
                    model_path=model_path,
                    n_ctx=MODEL_CONTEXT,
                    n_threads=MODEL_THREADS,
                    n_gpu_layers=LOCAL_N_GPU_LAYERS,
                    verbose=False,
                )
            except Exception as exc:
                raise ModelProviderError(f"Local model could not be loaded from '{model_path}': {exc}") from exc

        base_kwargs: dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": TEMPERATURE,
            "top_p": TOP_P,
            "max_tokens": MODEL_MAX_TOKENS,
        }
        if not LOCAL_CHAT_TEMPLATE_THINKING:
            base_kwargs["chat_template_kwargs"] = {"enable_thinking": False}

        attempts = []
        if json_mode:
            attempts.append({"response_format": {"type": "json_object"}})
        attempts.append({})

        last_error: Exception | None = None
        for extra in attempts:
            kwargs = dict(base_kwargs)
            kwargs.update(extra)
            try:
                response = self._local.create_chat_completion(**kwargs)
                choices = response.get("choices") or []
                if not choices:
                    raise ModelProviderError("Local model returned no choices.")
                message = choices[0].get("message") or {}
                content = str(message.get("content") or "")
                finish_reason = str(choices[0].get("finish_reason") or "")
                if not content.strip():
                    raise ModelProviderError(
                        f"Local model returned an empty response (finish_reason={finish_reason or 'unknown'})."
                    )
                return ModelResult(content=content, backend="local", finish_reason=finish_reason)
            except TypeError as exc:
                last_error = exc
                # Older llama-cpp builds can reject response_format or
                # chat_template_kwargs. Try the compatibility path below.
                if "chat_template_kwargs" in kwargs:
                    fallback = dict(kwargs)
                    fallback.pop("chat_template_kwargs", None)
                    try:
                        response = self._local.create_chat_completion(**fallback)
                        choices = response.get("choices") or []
                        if not choices:
                            raise ModelProviderError("Local model returned no choices.")
                        message = choices[0].get("message") or {}
                        content = str(message.get("content") or "")
                        finish_reason = str(choices[0].get("finish_reason") or "")
                        if content.strip():
                            return ModelResult(content=content, backend="local", finish_reason=finish_reason)
                    except Exception as nested:
                        last_error = nested
            except Exception as exc:
                last_error = exc

        raise ModelProviderError(f"Local model request failed: {last_error}") from last_error

    @staticmethod
    def _resolve_local_model() -> str:
        raw = LOCAL_MODEL.strip()
        if not raw:
            return ""
        path = Path(raw).expanduser()
        if path.is_absolute() and path.exists():
            return str(path)
        candidate = Path.cwd() / path
        if candidate.exists():
            return str(candidate.resolve())
        project_candidate = Path(__file__).resolve().parents[3] / path
        if project_candidate.exists():
            return str(project_candidate.resolve())
        return str(path)
