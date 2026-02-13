from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from .schemas import DailySetPayload

OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

DAILY_SET_JSON_SCHEMA = {
    "type": "object",
    "required": ["date", "level1", "level2", "level3"],
    "additionalProperties": False,
    "properties": {
        "date": {"type": "string"},
        "level1": {
            "type": "array",
            "minItems": 40,
            "items": {
                "type": "object",
                "required": ["question", "answer"],
                "additionalProperties": False,
                "properties": {
                    "question": {"type": "string", "minLength": 1},
                    "answer": {"type": "string", "minLength": 1},
                },
            },
        },
        "level2": {
            "type": "array",
            "minItems": 8,
            "items": {
                "type": "object",
                "required": ["question", "answer"],
                "additionalProperties": False,
                "properties": {
                    "question": {"type": "string", "minLength": 1},
                    "answer": {"type": "string", "minLength": 1},
                },
            },
        },
        "level3": {
            "type": "array",
            "minItems": 8,
            "items": {
                "type": "object",
                "required": ["question", "answer"],
                "additionalProperties": False,
                "properties": {
                    "question": {"type": "string", "minLength": 1},
                    "answer": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

SYSTEM_PROMPT = (
    "You generate daily math game content. "
    "Return only valid JSON matching the requested schema with no extra text."
)

PROMPT_DAILY_SET = """
Create a daily math game set as ONE JSON object only.
No markdown, no explanation, no code fences.

Required schema:
{{
  "date": "{date}",
  "level1": [{{"question": "...", "answer": "..."}}],
  "level2": [{{"question": "...", "answer": "..."}}],
  "level3": [{{"question": "...", "answer": "..."}}]
}}

Rules:
- level1: 40 short arithmetic questions, all unique.
- level2: 8 medium difficulty word problems and geometry-style questions.
- level3: 8 algebra/equation solving problems.
- Keep answers short and unambiguous.
- Prefer plain numeric answers when possible.
- Do not make level2 a copy of level1-style single-step arithmetic.
- Level2 should include variety: area/perimeter, fractions, percentages, ratios, units, and short real-world scenarios.
- Level2 questions must be self-contained and mathematically consistent.
- Level3 should focus on solving for x or evaluating algebraic expressions.
- Return ONLY JSON.
""".strip()

FIX_JSON_PROMPT = """
Your previous output failed strict parsing or schema validation.
Fix it into one valid JSON object matching this exact schema:
{{
  "date": "{date}",
  "level1": [{{"question": "...", "answer": "..."}}],
  "level2": [{{"question": "...", "answer": "..."}}],
  "level3": [{{"question": "...", "answer": "..."}}]
}}

Raw invalid output:
{raw_output}

Validation/parsing error:
{error}

Return ONLY corrected JSON.
Keep level2 as medium word/geometry problems, not basic level1 arithmetic.
""".strip()


class OpenAIGenerationError(Exception):
    pass


@dataclass
class GenerationResult:
    payload: dict[str, Any]
    usage: dict[str, int]
    model: str


def _add_usage(total: dict[str, int], delta: dict[str, int]) -> dict[str, int]:
    return {
        "input_tokens": total.get("input_tokens", 0) + delta.get("input_tokens", 0),
        "output_tokens": total.get("output_tokens", 0) + delta.get("output_tokens", 0),
        "total_tokens": total.get("total_tokens", 0) + delta.get("total_tokens", 0),
    }


def _extract_message_content(choice: dict[str, Any]) -> str:
    message = choice.get("message")
    if not isinstance(message, dict):
        raise OpenAIGenerationError("OpenAI response missing message object.")

    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        raise OpenAIGenerationError(f"Model refused request: {refusal[:220]}")

    content = message.get("content")
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_value = part.get("text")
                if isinstance(text_value, str):
                    text_parts.append(text_value)
        if text_parts:
            return "".join(text_parts)

    raise OpenAIGenerationError("OpenAI response message content is missing.")


def _parse_single_json_object(raw_text: str) -> dict[str, Any]:
    stripped = raw_text.strip()
    decoder = json.JSONDecoder()

    try:
        parsed, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        raise OpenAIGenerationError(
            f"Model output was not valid JSON: {exc.msg} (char {exc.pos})."
        ) from exc

    if end != len(stripped):
        raise OpenAIGenerationError(
            "Model output contained text outside of a single JSON object."
        )

    if not isinstance(parsed, dict):
        raise OpenAIGenerationError("Model output must be one JSON object.")

    return parsed


def _request_openai(messages: list[dict[str, str]]) -> tuple[str, dict[str, int], str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise OpenAIGenerationError(
            "OPENAI_API_KEY is missing. Set it in your environment before running /generate."
        )

    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"

    body = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "daily_math_set",
                "strict": True,
                "schema": DAILY_SET_JSON_SCHEMA,
            },
        },
        "temperature": 0,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = httpx.Timeout(connect=5.0, read=90.0, write=30.0, pool=10.0)

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=body, headers=headers)
    except httpx.ConnectError as exc:
        raise OpenAIGenerationError("Could not connect to OpenAI API endpoint.") from exc
    except httpx.TimeoutException as exc:
        raise OpenAIGenerationError("Timed out waiting for OpenAI response.") from exc
    except httpx.HTTPError as exc:
        raise OpenAIGenerationError(f"HTTP error contacting OpenAI: {exc}") from exc

    if response.status_code != 200:
        preview = response.text.strip().replace("\n", " ")[:300]
        raise OpenAIGenerationError(
            f"OpenAI returned status {response.status_code}: {preview}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise OpenAIGenerationError("OpenAI response was not valid JSON.") from exc

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenAIGenerationError("OpenAI response did not include choices.")

    content = _extract_message_content(choices[0])

    usage_raw = data.get("usage")
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    if isinstance(usage_raw, dict):
        usage = {
            "input_tokens": int(usage_raw.get("prompt_tokens", 0) or 0),
            "output_tokens": int(usage_raw.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage_raw.get("total_tokens", 0) or 0),
        }

    model_name = str(data.get("model") or OPENAI_MODEL)
    return content, usage, model_name


def generate_daily_payload(today_date: str) -> GenerationResult:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": PROMPT_DAILY_SET.format(date=today_date)},
    ]

    usage_total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    last_error = "unknown"
    last_output = ""
    last_model = OPENAI_MODEL

    for attempt in range(3):
        raw_output, usage, model_name = _request_openai(messages)
        usage_total = _add_usage(usage_total, usage)
        last_output = raw_output
        last_model = model_name

        try:
            parsed = _parse_single_json_object(raw_output)
            parsed["date"] = today_date
            validated = DailySetPayload.model_validate(parsed)
            return GenerationResult(
                payload=validated.model_dump(),
                usage=usage_total,
                model=last_model,
            )
        except (OpenAIGenerationError, ValidationError) as exc:
            last_error = str(exc)
            if attempt == 2:
                break
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": FIX_JSON_PROMPT.format(
                        date=today_date,
                        raw_output=last_output,
                        error=last_error,
                    ),
                },
            ]

    raise OpenAIGenerationError(
        "Failed to produce valid daily JSON after 3 attempts. "
        f"Last error: {last_error}. "
        f"Last output preview: {last_output[:220]!r}"
    )
