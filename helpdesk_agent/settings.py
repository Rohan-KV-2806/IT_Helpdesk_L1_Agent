from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import config


@dataclass
class ProviderSettings:
    endpoint: str
    api_key: str = ""
    model: str = ""


@dataclass
class GenerationSettings:
    temperature: float = config.DEFAULT_TEMPERATURE
    top_p: float = config.DEFAULT_TOP_P
    max_tokens: int = config.DEFAULT_MODEL_MAX_TOKENS
    max_agent_steps: int = config.DEFAULT_MAX_AGENT_STEPS
    max_protocol_repairs: int = config.DEFAULT_MAX_PROTOCOL_REPAIRS


@dataclass
class AISettings:
    active_backend: str = "cloud"
    cloud: ProviderSettings | None = None
    lm_studio: ProviderSettings | None = None
    generation: GenerationSettings | None = None

    def __post_init__(self) -> None:
        if self.cloud is None:
            self.cloud = ProviderSettings(
                endpoint=config.DEFAULT_CLOUD_API_ENDPOINT,
                api_key=config.DEFAULT_CLOUD_API_KEY,
                model=config.DEFAULT_CLOUD_MODEL,
            )
        if self.lm_studio is None:
            self.lm_studio = ProviderSettings(
                endpoint=config.DEFAULT_LM_STUDIO_ENDPOINT,
                api_key=config.DEFAULT_LM_STUDIO_API_KEY,
                model=config.DEFAULT_LM_STUDIO_MODEL,
            )
        if self.generation is None:
            self.generation = GenerationSettings()
        self.active_backend = normalize_backend(self.active_backend)


def normalize_backend(value: str) -> str:
    raw = (value or "").strip().lower().replace("-", "_")
    if raw in {"local", "lmstudio", "lm_studio", "lm studio"}:
        return "lm_studio"
    return "cloud"


def settings_path() -> Path:
    """Return the legacy JSON path kept for backward compatibility."""
    return config.SETTINGS_PATH


def settings_db_path() -> Path:
    """Return the SQLite database used for persistent AI settings."""
    return config.SETTINGS_DB_PATH


def _settings_to_json(settings: AISettings) -> str:
    return json.dumps(asdict(settings), ensure_ascii=False, separators=(",", ":"))


def _settings_from_json(raw_text: str, defaults: AISettings) -> AISettings:
    raw = json.loads(raw_text)
    if not isinstance(raw, dict):
        return defaults
    return AISettings(
        active_backend=normalize_backend(str(raw.get("active_backend", defaults.active_backend))),
        cloud=_provider_from_mapping(raw.get("cloud"), defaults.cloud),
        lm_studio=_provider_from_mapping(raw.get("lm_studio"), defaults.lm_studio),
        generation=_generation_from_mapping(raw.get("generation")),
    )


def _ensure_settings_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _load_legacy_json(defaults: AISettings) -> AISettings | None:
    path = settings_path()
    try:
        if not path.exists():
            return None
        return _settings_from_json(path.read_text(encoding="utf-8"), defaults)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _load_sqlite(defaults: AISettings) -> AISettings | None:
    db = settings_db_path()
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db) as conn:
            _ensure_settings_db(conn)
            row = conn.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?",
                ("ai_settings",),
            ).fetchone()
        if not row:
            return None
        return _settings_from_json(str(row[0]), defaults)
    except (OSError, sqlite3.Error, ValueError, TypeError, json.JSONDecodeError):
        return None


def _provider_from_mapping(raw: Any, default: ProviderSettings) -> ProviderSettings:
    if not isinstance(raw, dict):
        return default
    return ProviderSettings(
        endpoint=str(raw.get("endpoint", default.endpoint) or default.endpoint).strip(),
        api_key=str(raw.get("api_key", default.api_key) or "").strip(),
        model=str(raw.get("model", default.model) or "").strip(),
    )


def _generation_from_mapping(raw: Any) -> GenerationSettings:
    defaults = GenerationSettings()
    if not isinstance(raw, dict):
        return defaults
    try:
        temperature = float(raw.get("temperature", defaults.temperature))
    except (TypeError, ValueError):
        temperature = defaults.temperature
    try:
        top_p = float(raw.get("top_p", defaults.top_p))
    except (TypeError, ValueError):
        top_p = defaults.top_p
    try:
        max_tokens = int(raw.get("max_tokens", defaults.max_tokens))
    except (TypeError, ValueError):
        max_tokens = defaults.max_tokens
    try:
        max_agent_steps = int(raw.get("max_agent_steps", defaults.max_agent_steps))
    except (TypeError, ValueError):
        max_agent_steps = defaults.max_agent_steps
    try:
        max_protocol_repairs = int(raw.get("max_protocol_repairs", defaults.max_protocol_repairs))
    except (TypeError, ValueError):
        max_protocol_repairs = defaults.max_protocol_repairs

    return GenerationSettings(
        temperature=min(2.0, max(0.0, temperature)),
        top_p=min(1.0, max(0.0, top_p)),
        max_tokens=max(256, max_tokens),
        max_agent_steps=max(4, max_agent_steps),
        max_protocol_repairs=max(1, max_protocol_repairs),
    )


def _legacy_defaults() -> AISettings:
    return AISettings(
        active_backend="cloud",
        cloud=ProviderSettings(
            endpoint=config.DEFAULT_CLOUD_API_ENDPOINT,
            api_key=config.DEFAULT_CLOUD_API_KEY,
            model=config.DEFAULT_CLOUD_MODEL,
        ),
        lm_studio=ProviderSettings(
            endpoint=config.DEFAULT_LM_STUDIO_ENDPOINT,
            api_key=config.DEFAULT_LM_STUDIO_API_KEY,
            model=config.DEFAULT_LM_STUDIO_MODEL,
        ),
        generation=GenerationSettings(),
    )


def load_settings() -> AISettings:
    """Load settings from SQLite, migrating the legacy JSON file when present."""
    defaults = _legacy_defaults()

    loaded = _load_sqlite(defaults)
    if loaded is not None:
        return loaded

    legacy = _load_legacy_json(defaults)
    if legacy is not None:
        try:
            save_settings(legacy)
        except OSError:
            pass
        return legacy

    return defaults


def save_settings(settings: AISettings) -> Path:
    """Persist the complete AI configuration in SQLite in one transaction."""
    db = settings_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    payload = _settings_to_json(settings)
    try:
        with sqlite3.connect(db, timeout=10) as conn:
            _ensure_settings_db(conn)
            conn.execute(
                """
                INSERT INTO app_settings(setting_key, setting_value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                ("ai_settings", payload),
            )
            conn.commit()
    except sqlite3.Error as exc:
        raise OSError(f"Could not save AI settings to SQLite: {exc}") from exc
    return db

def provider_settings(settings: AISettings, backend: str) -> ProviderSettings:
    backend_name = normalize_backend(backend)
    return settings.lm_studio if backend_name == "lm_studio" else settings.cloud
