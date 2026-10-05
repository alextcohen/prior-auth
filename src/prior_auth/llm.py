"""OpenAI calls for transcription and structured output."""

import os
from pathlib import Path

from prior_auth.errors import PriorAuthError

DEFAULT_MODEL = "gpt-4.1"


def load_prompt(name: str) -> str:
    path = Path(__file__).with_name("prompts") / name
    if not path.is_file():
        raise PriorAuthError(f"Missing prompt file: {name}")
    return path.read_text(encoding="utf-8")


def openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL


def openai_client():
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise PriorAuthError("Missing environment variable OPENAI_API_KEY.")
    from openai import OpenAI

    return OpenAI(api_key=api_key)


def parse_model(messages: list[dict[str, str]], schema):
    client = openai_client()
    model = openai_model()
    last_error: Exception | None = None
    for extra in _call_variants():
        try:
            completion = client.chat.completions.parse(
                model=model,
                messages=messages,
                response_format=schema,
                **extra,
            )
        except Exception as exc:
            last_error = exc
            if _retryable_parameter(exc):
                continue
            break
        choice = completion.choices[0].message
        parsed = choice.parsed
        if parsed is None:
            refusal = getattr(choice, "refusal", None) or "The model returned no structured result."
            last_error = PriorAuthError(refusal)
            continue
        return parsed

    raise PriorAuthError(f"OpenAI structured parse failed ({model}): {last_error}")


def complete_text(messages: list[dict], *, allow_empty: bool = False) -> str:
    """Plain-text completion. Used to transcribe a PDF page."""
    client = openai_client()
    model = openai_model()
    last_error: Exception | None = None
    for extra in _call_variants():
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                **extra,
            )
        except Exception as exc:
            last_error = exc
            if _retryable_parameter(exc):
                continue
            break
        choice = completion.choices[0].message
        text = (choice.content or "").strip()
        refusal = getattr(choice, "refusal", None)
        if text:
            return text
        if allow_empty and not refusal:
            return ""
        last_error = PriorAuthError(refusal or "The model returned no text.")
    raise PriorAuthError(f"OpenAI request failed ({model}): {last_error}")


def _call_variants() -> tuple[dict, ...]:
    return (
        {"temperature": 0, "max_completion_tokens": 16000},
        {"max_completion_tokens": 16000},
        {},
    )


def _retryable_parameter(exc: Exception) -> bool:
    message = str(exc).casefold()
    return "temperature" in message or "max_completion_tokens" in message or "max_tokens" in message
