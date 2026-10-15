"""Language-model client.

Development default is Google's Gemini free tier. Set LLM_PROVIDER=openai
and OPENAI_API_KEY later to switch to a paid model without changing code.
Groq is available the same way for another free-tier key.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import Settings
from app.services.catalog import RuleDraft, coerce_rule

SYSTEM_RULES = """You help domain experts define data quality checks for one database table.
Return JSON only, with this shape:
{"rules":[{"title":"","plain_language":"","expectation_type":"","kwargs":{},"severity":"critical","rationale":""}]}

Allowed expectation_type values and kwargs:
- expect_column_values_to_not_be_null: {"column"}
- expect_column_values_to_be_unique: {"column"}
- expect_column_values_to_be_in_set: {"column", "value_set": []}
- expect_column_values_to_be_between: {"column", "min_value", "max_value"}
- expect_column_value_lengths_to_be_between: {"column", "min_value", "max_value"}
- expect_column_values_to_match_regex: {"column", "regex"}
- expect_table_row_count_to_be_between: {"min_value", "max_value"}
- expect_compound_columns_to_be_unique: {"column_list": []}

Use only columns that exist. Prefer 4 to 10 high-value checks.
Write title and plain_language for someone who does not know Great Expectations.
Use severity "critical" when a bad value makes the row unusable, otherwise "warning".
If a pattern holds for most rows but a few values break it, write the check the few values will fail.
Do not invent columns or values that the profile does not support.
"""

SYSTEM_ONE = """You translate one plain-language data quality request into checks.
Return JSON only:
{"rules":[{"title":"","plain_language":"","expectation_type":"","kwargs":{},"severity":"critical"}]}

Allowed expectation_type values and kwargs:
- expect_column_values_to_not_be_null: {"column"}
- expect_column_values_to_be_unique: {"column"}
- expect_column_values_to_be_in_set: {"column", "value_set": []}
- expect_column_values_to_be_between: {"column", "min_value", "max_value"}
- expect_column_value_lengths_to_be_between: {"column", "min_value", "max_value"}
- expect_column_values_to_match_regex: {"column", "regex"}
- expect_table_row_count_to_be_between: {"min_value", "max_value"}
- expect_compound_columns_to_be_unique: {"column_list": []}

Use only columns from the profile. If the request implies several checks, return each one.
Keep the user's meaning. Do not add unrelated checks.
"""


class LlmError(RuntimeError):
    pass


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise LlmError("The model did not return JSON")
        payload = json.loads(cleaned[start : end + 1])
    if isinstance(payload, list):
        return {"rules": payload}
    if not isinstance(payload, dict):
        raise LlmError("The model response was not an object")
    if "rule" in payload and "rules" not in payload:
        payload = {"rules": [payload["rule"]]}
    return payload


def _rules_from_payload(payload: dict[str, Any], columns: set[str]) -> list[RuleDraft]:
    raw_rules = payload.get("rules") or []
    if not isinstance(raw_rules, list):
        raise LlmError("The model response did not include a list of checks")
    drafts = []
    for raw in raw_rules:
        try:
            drafts.append(coerce_rule(raw, columns))
        except ValueError:
            continue
    if not drafts:
        raise LlmError("The model did not return any checks that match this table")
    return drafts[:12]


def _gemini(settings: Settings, system: str, user: str) -> str:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_model}:generateContent"
    )
    response = httpx.post(
        url,
        headers={"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        },
        timeout=45,
    )
    if response.status_code >= 400:
        raise LlmError(f"Gemini returned {response.status_code}: {_safe_error(response)}")
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError("Gemini returned an empty response") from exc


def _openai_compatible(url: str, api_key: str, model: str, system: str, user: str, provider: str) -> str:
    body = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=45,
    )
    if response.status_code == 400:
        body.pop("response_format", None)
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=45,
        )
    if response.status_code >= 400:
        raise LlmError(f"{provider} returned {response.status_code}: {_safe_error(response)}")
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError(f"{provider} returned an empty response") from exc


def _safe_error(response: httpx.Response) -> str:
    text = response.text[:300].replace("\n", " ")
    return re.sub(r"key=[^&\s]+", "key=redacted", text)


def complete(settings: Settings, system: str, user: str) -> str:
    provider = settings.llm_provider.strip().lower()
    if provider == "openai":
        return _openai_compatible(
            "https://api.openai.com/v1/chat/completions",
            settings.openai_api_key,
            settings.openai_model,
            system,
            user,
            "OpenAI",
        )
    if provider == "groq":
        return _openai_compatible(
            "https://api.groq.com/openai/v1/chat/completions",
            settings.groq_api_key,
            settings.groq_model,
            system,
            user,
            "Groq",
        )
    if provider == "gemini":
        return _gemini(settings, system, user)
    raise LlmError(f"Unknown LLM provider: {settings.llm_provider}")


def suggest_with_llm(settings: Settings, profile: dict[str, Any], columns: set[str]) -> list[RuleDraft]:
    user = "Table profile:\n" + json.dumps(profile, default=str)
    text = complete(settings, SYSTEM_RULES, user)
    return _rules_from_payload(_extract_json(text), columns)


def translate_with_llm(
    settings: Settings, profile: dict[str, Any], columns: set[str], request: str
) -> list[RuleDraft]:
    user = (
        "Table profile:\n"
        + json.dumps(profile, default=str)
        + "\n\nDomain expert request:\n"
        + request.strip()
    )
    text = complete(settings, SYSTEM_ONE, user)
    return _rules_from_payload(_extract_json(text), columns)
