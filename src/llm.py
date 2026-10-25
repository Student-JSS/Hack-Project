"""Provider-agnostic LLM access.

``LLM_PROVIDER`` selects Google Gemini (default, free tier), OpenAI or Anthropic.
Every function returns ``None`` instead of raising when a key is missing, a
package is absent or a call fails - the pipeline then falls back to the
deterministic templates in :mod:`src.graph.deterministic`.

Privacy: prompts contain the survivor's own words. Story text is never logged;
only the provider/model name is. With ``LANGSMITH_TRACING=true`` plus a key,
LangChain sends traces to LangSmith (documented in ARCHITECTURE.md).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from src.config import Settings, get_logger, get_settings

LOGGER = get_logger("llm")
SchemaT = TypeVar("SchemaT", bound=BaseModel)

SYSTEM_PROMPT = (
    "You are Saakshya, a careful assistant for women in India who are dealing with "
    "harassment, domestic violence or cyber abuse. Use plain, calm, non-judgemental "
    "language. Never promise legal outcomes, never invent section numbers, and never "
    "add facts the user did not provide. Always remind the user that this is general "
    "information and that a lawyer or free legal aid clinic should confirm it. "
    "If the user mentions immediate danger, prioritise safety instructions first."
)


def _extract_json(text: str) -> str:
    """Return the outermost JSON object found in a model response."""
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


def _build_llm(provider: str, model: str, temperature: float, api_key: str) -> Any | None:
    """Instantiate the chat model for one provider, or ``None`` on failure."""
    try:
        if provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(model=model, api_key=api_key, temperature=temperature)
        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=model, api_key=api_key, temperature=temperature)
        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=model, api_key=api_key, temperature=temperature)
    except Exception as exc:  # missing package or bad config
        LOGGER.warning("Could not initialise %s model %s: %s", provider, model, exc)
        return None
    LOGGER.warning("Unsupported LLM provider: %s", provider)
    return None


@lru_cache(maxsize=8)
def _get_llm_cached(provider: str, model: str, temperature: float, api_key: str) -> Any | None:
    """Cached model factory (reads no env directly, so tests can override)."""
    settings = get_settings()
    if settings.demo_mode:
        LOGGER.info("Demo Mode is on: using deterministic templates, not the LLM.")
        return None
    if not settings.llm_enabled:
        LOGGER.info("LLM_ENABLED=false: using deterministic templates.")
        return None
    if not api_key:
        LOGGER.info("No API key for %s: using deterministic templates.", provider)
        return None
    llm = _build_llm(provider, model, temperature, api_key)
    if llm is not None:
        LOGGER.info("LLM ready: provider=%s model=%s", provider, model)
    return llm


def get_llm(temperature: float | None = None, settings: Settings | None = None) -> Any | None:
    """Return a chat model for the configured provider, or ``None``."""
    settings = settings or get_settings()
    return _get_llm_cached(
        settings.llm_provider,
        settings.model_name,
        float(settings.llm_temperature if temperature is None else temperature),
        settings.provider_api_key,
    )


def llm_available() -> bool:
    """True when a model will actually be called (not demo / not keyless)."""
    return get_llm() is not None


def provider_label() -> str:
    """Short UI label such as ``google:gemini-2.5-flash``."""
    settings = get_settings()
    return f"{settings.llm_provider}:{settings.model_name}" if settings.llm_ready else "offline templates"


def invoke_text(prompt: str, system: str | None = None, temperature: float | None = None) -> str | None:
    """Send a single prompt and return plain text, or ``None`` on failure."""
    llm = get_llm(temperature)
    if llm is None:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [SystemMessage(content=system or SYSTEM_PROMPT), HumanMessage(content=prompt)]
        response = llm.invoke(messages)
        content = getattr(response, "content", "")
        if isinstance(content, list):
            content = "\n".join(
                block.get("text", "") if isinstance(block, dict) else str(block) for block in content
            )
        text = str(content).strip()
        return text or None
    except Exception as exc:
        LOGGER.warning("LLM text call failed: %s", exc)
        return None


def invoke_structured(
    prompt: str, schema: type[SchemaT], system: str | None = None
) -> SchemaT | None:
    """Ask for a Pydantic-validated object, falling back to JSON-in-text parsing."""
    llm = get_llm()
    if llm is None:
        return None
    if hasattr(llm, "with_structured_output"):
        try:
            structured = llm.with_structured_output(schema)
            result = structured.invoke(
                [
                    ("system", system or SYSTEM_PROMPT),
                    ("human", prompt),
                ]
            )
            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                return schema.model_validate(result)
        except Exception as exc:
            LOGGER.info("Structured output unavailable (%s); trying JSON parsing.", type(exc).__name__)
    raw = invoke_text(
        f"{prompt}\n\nReply with a single JSON object that matches this schema:\n"
        f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}\n"
        "Output JSON only, no prose.",
        system=system,
    )
    if not raw:
        return None
    try:
        return schema.model_validate_json(_extract_json(raw))
    except (ValidationError, ValueError) as exc:
        LOGGER.warning("Could not parse a structured LLM reply: %s", type(exc).__name__)
        return None


def reset_llm_cache() -> None:
    """Drop cached models (tests and settings changes)."""
    _get_llm_cached.cache_clear()
