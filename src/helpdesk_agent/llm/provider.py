from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from llama_cpp import Llama

from ..config import (
    CLOUD_API_ENDPOINT,
    CLOUD_API_KEY,
    CLOUD_MODEL,
    LOCAL_MODEL,
    MODEL_CONTEXT,
    MODEL_THREADS,
)


@dataclass
class ModelResult:
    backend: str
    content: str


class ModelProvider:
    """Cloud-first provider with a lazy-loaded local fallback."""

    def __init__(self) -> None:
        self._cloud: OpenAI | None = None
        self._local: Llama | None = None

    def _cloud_client(self) -> OpenAI:
        if self._cloud is None:
            if not (CLOUD_API_ENDPOINT and CLOUD_API_KEY and CLOUD_MODEL):
                raise RuntimeError("Cloud model configuration is incomplete")
            self._cloud = OpenAI(
                base_url=CLOUD_API_ENDPOINT,
                api_key=CLOUD_API_KEY,
                timeout=30.0,
            )
        return self._cloud

    def _local_model(self) -> Llama:
        if self._local is None:
            if not LOCAL_MODEL:
                raise RuntimeError("LOCAL_MODEL is not configured")
            self._local = Llama(
                model_path=LOCAL_MODEL,
                n_ctx=MODEL_CONTEXT,
                n_threads=MODEL_THREADS,
                verbose=False,
            )
        return self._local

    def complete(self, system_prompt: str, user_prompt: str) -> ModelResult:
        """Call cloud first; fall back to local on any cloud failure."""
        cloud_error: Exception | None = None

        if CLOUD_API_ENDPOINT and CLOUD_API_KEY and CLOUD_MODEL:
            try:
                kwargs = {
                    "model": CLOUD_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 6000,
                }
                if "nemotron-3-ultra" in CLOUD_MODEL.lower():
                    kwargs["reasoning_effort"] = "none"
                response = self._cloud_client().chat.completions.create(**kwargs)
                return ModelResult("Cloud", response.choices[0].message.content or "")
            except Exception as exc:  # noqa: BLE001
                cloud_error = exc

        try:
            model = self._local_model()
            response = model.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                top_p=1.0,
                max_tokens=6000,
                # Safe for Qwen-style templates; ignored by templates that don't use it.
                # chat_template_kwargs={"enable_thinking": False},
            )
            content = response["choices"][0]["message"].get("content", "")
            return ModelResult("Local", _clean_thinking(content))
        except Exception as local_error:
            if cloud_error is not None:
                raise RuntimeError(
                    f"Cloud model failed ({cloud_error}); local model also failed ({local_error})"
                ) from local_error
            raise


def _clean_thinking(text: str) -> str:
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from a model response."""
    cleaned = _clean_thinking(text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Model did not return JSON: {cleaned[:300]}")
    return json.loads(match.group(0))
