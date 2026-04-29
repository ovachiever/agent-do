"""Small optional AI helpers for routing and hook gating."""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import anthropic
except ModuleNotFoundError:  # pragma: no cover - exercised through fallbacks
    anthropic = None


DEFAULT_FAST_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 64000
ADAPTIVE_THINKING_MODELS = {
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-opus-4-7",
    "claude-mythos-preview",
}


def _flag_value(name: str, override: str | None = None) -> str:
    value = override
    if value is None:
        value = os.environ.get(name)
    if value is None:
        value = os.environ.get("AGENT_DO_AI")
    return (value or "auto").strip().lower()


def ai_requested(name: str, override: str | None = None) -> bool:
    """Return whether an optional AI path should attempt a model call."""
    value = _flag_value(name, override)
    if value in {"0", "false", "no", "off", "never", "disabled"}:
        return False
    if anthropic is None:
        return False
    if value in {"1", "true", "yes", "on", "always"}:
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ai_model() -> str:
    return os.environ.get("AGENT_DO_AI_MODEL", DEFAULT_FAST_MODEL)


def ai_max_tokens() -> int:
    value = os.environ.get("AGENT_DO_AI_MAX_TOKENS")
    if value:
        try:
            parsed = int(value)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_MAX_TOKENS


def ai_effort() -> str:
    return os.environ.get("AGENT_DO_AI_EFFORT", "max")


def supports_adaptive_thinking(model: str) -> bool:
    return model in ADAPTIVE_THINKING_MODELS


def _message_text(response: Any) -> str:
    chunks = getattr(response, "content", None) or []
    texts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            text = chunk.get("text")
        else:
            text = getattr(chunk, "text", None)
        if text:
            texts.append(str(text))
    return "\n".join(texts)


def _extract_json(text: str) -> dict | None:
    stripped = text.strip()
    if "```json" in stripped:
        stripped = stripped.split("```json", 1)[1].split("```", 1)[0].strip()
    elif stripped.startswith("```") and "```" in stripped[3:]:
        stripped = stripped.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None

    return payload if isinstance(payload, dict) else None


def call_json_model(
    prompt: str,
    *,
    flag_name: str,
    flag_override: str | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
) -> dict | None:
    """Call the configured fast model and parse a JSON object, returning None on fallback-worthy failure."""
    if not ai_requested(flag_name, flag_override):
        return None

    try:
        client = anthropic.Anthropic()
        model = ai_model()
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens or ai_max_tokens(),
            "messages": [{"role": "user", "content": prompt}],
        }
        if supports_adaptive_thinking(model):
            kwargs["thinking"] = {"type": "adaptive", "display": "omitted"}
            kwargs["output_config"] = {"effort": ai_effort()}
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
    except Exception:
        return None

    payload = _extract_json(_message_text(response))
    if payload is not None:
        payload.setdefault("_model", ai_model())
    return payload
