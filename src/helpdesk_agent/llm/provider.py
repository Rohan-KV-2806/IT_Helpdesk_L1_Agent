from __future__ import annotations

import json
from dataclasses import dataclass
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
    PROMPT_TEMPERATURE,
    PROMPT_TOP_P,
)


@dataclass
class ModelResult:
    content: str
    backend: str


def parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "", 1).replace("```", "", 1).strip()
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    # Recover a JSON object when a model adds a small amount of text.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        value = json.loads(text[start : end + 1])
        if isinstance(value, dict):
            return value
    raise ValueError(f"Model did not return valid JSON: {text[:500]}")


class ModelProvider:
    def __init__(self) -> None:
        self._local = None
        self._cloud = None

    def complete(self, system_prompt: str, user_prompt: str, backend: str, json_mode: bool = True) -> ModelResult:
        backend = backend.lower().strip()
        if backend == "cloud":
            return self._cloud_complete(system_prompt, user_prompt, json_mode)
        if backend == "local":
            return self._local_complete(system_prompt, user_prompt, json_mode)
        raise ValueError(f"Unknown backend: {backend}")

    def _cloud_complete(self, system_prompt: str, user_prompt: str, json_mode: bool) -> ModelResult:
        if not CLOUD_API_KEY or not CLOUD_MODEL:
            raise RuntimeError("Cloud model is not configured. Check CLOUD_API_KEY and CLOUD_MODEL in .env.")
        from openai import OpenAI

        if self._cloud is None:
            self._cloud = OpenAI(api_key=CLOUD_API_KEY, base_url=CLOUD_API_ENDPOINT, timeout=90.0, max_retries=1)

        response = self._cloud.chat.completions.create(
            model=CLOUD_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=PROMPT_TEMPERATURE,
            top_p=PROMPT_TOP_P,
            max_tokens=MODEL_MAX_TOKENS,
            stream=False,
        )
        content = response.choices[0].message.content or ""
        return ModelResult(content=content, backend="cloud")

    def _load_local(self):
        if not LOCAL_MODEL:
            raise RuntimeError("Local model is not configured. Check LOCAL_MODEL in .env.")
        from llama_cpp import Llama

        self._local = Llama(
            model_path=LOCAL_MODEL,
            n_ctx=MODEL_CONTEXT,
            n_threads=MODEL_THREADS,
            n_gpu_layers=LOCAL_N_GPU_LAYERS,
            verbose=False,
        )
        return self._local

    def _local_complete(self, system_prompt: str, user_prompt: str, json_mode: bool) -> ModelResult:
        llm = self._local or self._load_local()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        kwargs = dict(
            messages=messages,
            temperature=PROMPT_TEMPERATURE,
            top_p=PROMPT_TOP_P,
            max_tokens=MODEL_MAX_TOKENS,
            **({"response_format": {"type": "json_object"}} if json_mode else {}),
        )
        if not LOCAL_CHAT_TEMPLATE_THINKING:
            kwargs["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            response = llm.create_chat_completion(**kwargs)
        except TypeError:
            kwargs.pop("chat_template_kwargs", None)
            response = llm.create_chat_completion(**kwargs)
        content = response["choices"][0]["message"].get("content", "") or ""
        return ModelResult(content=content, backend="local")
