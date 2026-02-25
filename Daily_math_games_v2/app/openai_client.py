from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
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

NEAR_DUPLICATE_THRESHOLD = 0.9
RETRY_EXACT_RATIO_THRESHOLD = 0.25
RETRY_SIMILAR_RATIO_THRESHOLD = 0.5

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

PROMPT_DAILY_SET_DIVERSITY_RETRY = """
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
- Level2 and level3 must be materially different from the recent history window.
- Do NOT reuse or lightly rephrase the recent-window level2 or level3 questions listed below.

Recent-window level2 questions:
{history_level2}

Recent-window level3 questions:
{history_level3}

Return ONLY JSON.
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
    debug: dict[str, Any]


def _zero_usage() -> dict[str, int]:
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


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


def _normalize_question_text(text: str) -> str:
    value = re.sub(r"\s+", " ", text.strip().lower())
    value = re.sub(r"[^a-z0-9%+\-*/=()., ]", "", value)
    return value.strip()


def _tokenize_question(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9%]+", text))


def _question_similarity_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    sequence_ratio = SequenceMatcher(None, a, b).ratio()
    a_tokens = _tokenize_question(a)
    b_tokens = _tokenize_question(b)
    if not a_tokens or not b_tokens:
        return sequence_ratio

    intersection = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    jaccard_ratio = (intersection / union) if union else 0.0
    return max(sequence_ratio, jaccard_ratio)


def _extract_questions(payload: dict[str, Any], level: str) -> list[str]:
    raw = payload.get(level)
    if not isinstance(raw, list):
        return []

    questions: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        if not isinstance(question, str):
            continue
        cleaned = question.strip()
        if cleaned:
            questions.append(cleaned)
    return questions


def _similarity_summary_for_level(
    current_questions: list[str],
    previous_questions: list[str],
) -> dict[str, Any]:
    if not current_questions or not previous_questions:
        return {
            "count": len(current_questions),
            "exact_count": 0,
            "similar_count": 0,
            "exact_ratio": 0.0,
            "similar_ratio": 0.0,
        }

    previous_normalized = [
        q for q in (_normalize_question_text(q) for q in previous_questions) if q
    ]
    previous_set = set(previous_normalized)

    exact_count = 0
    similar_count = 0

    for question in current_questions:
        current_normalized = _normalize_question_text(question)
        if not current_normalized:
            continue

        if current_normalized in previous_set:
            exact_count += 1
            similar_count += 1
            continue

        best_score = 0.0
        for prev_normalized in previous_normalized:
            score = _question_similarity_score(current_normalized, prev_normalized)
            if score > best_score:
                best_score = score
            if best_score >= NEAR_DUPLICATE_THRESHOLD:
                break

        if best_score >= NEAR_DUPLICATE_THRESHOLD:
            similar_count += 1

    count = len(current_questions)
    return {
        "count": count,
        "exact_count": exact_count,
        "similar_count": similar_count,
        "exact_ratio": exact_count / count if count else 0.0,
        "similar_ratio": similar_count / count if count else 0.0,
    }


def _extract_history_questions(
    recent_sets: list[dict[str, Any]],
    level: str,
) -> list[str]:
    questions: list[str] = []
    for item in recent_sets:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        questions.extend(_extract_questions(payload, level))
    return questions


def _collect_similarity_metrics(
    current_payload: dict[str, Any],
    recent_sets: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    history_level2 = _extract_history_questions(recent_sets, "level2")
    history_level3 = _extract_history_questions(recent_sets, "level3")
    return {
        "level2": _similarity_summary_for_level(
            _extract_questions(current_payload, "level2"),
            history_level2,
        ),
        "level3": _similarity_summary_for_level(
            _extract_questions(current_payload, "level3"),
            history_level3,
        ),
    }


def _should_retry_for_similarity(metrics: dict[str, dict[str, Any]]) -> bool:
    for level_name in ("level2", "level3"):
        level = metrics.get(level_name, {})
        exact_count = int(level.get("exact_count", 0) or 0)
        exact_ratio = float(level.get("exact_ratio", 0.0) or 0.0)
        similar_ratio = float(level.get("similar_ratio", 0.0) or 0.0)
        if (
            exact_count > 0
            or
            exact_ratio >= RETRY_EXACT_RATIO_THRESHOLD
            or similar_ratio >= RETRY_SIMILAR_RATIO_THRESHOLD
        ):
            return True
    return False


def _similarity_rank(metrics: dict[str, dict[str, Any]]) -> float:
    level2 = metrics.get("level2", {})
    level3 = metrics.get("level3", {})
    max_exact = max(
        float(level2.get("exact_ratio", 0.0) or 0.0),
        float(level3.get("exact_ratio", 0.0) or 0.0),
    )
    max_similar = max(
        float(level2.get("similar_ratio", 0.0) or 0.0),
        float(level3.get("similar_ratio", 0.0) or 0.0),
    )
    return max_similar + (0.5 * max_exact)


def _format_questions_for_prompt(questions: list[str], *, limit: int = 40) -> str:
    if not questions:
        return "(none)"

    lines: list[str] = []
    for index, question in enumerate(questions[:limit], start=1):
        sanitized = re.sub(r"\s+", " ", question).strip()
        if not sanitized:
            continue
        lines.append(f"{index}. {sanitized}")
    return "\n".join(lines) if lines else "(none)"


def _compact_similarity(metrics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for level_name in ("level2", "level3"):
        level = metrics.get(level_name, {})
        compact[level_name] = {
            "exact_count": int(level.get("exact_count", 0) or 0),
            "similar_count": int(level.get("similar_count", 0) or 0),
            "count": int(level.get("count", 0) or 0),
            "exact_ratio": round(float(level.get("exact_ratio", 0.0) or 0.0), 3),
            "similar_ratio": round(float(level.get("similar_ratio", 0.0) or 0.0), 3),
        }
    return compact


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


def _generate_with_prompt(today_date: str, prompt: str) -> GenerationResult:
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    usage_total = _zero_usage()
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
                debug={},
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


def generate_daily_payload(
    today_date: str,
    *,
    recent_sets: list[dict[str, Any]] | None = None,
    repeat_window_days: int | None = None,
) -> GenerationResult:
    recent_sets = recent_sets or []
    recent_dates = [
        item["date"]
        for item in recent_sets
        if isinstance(item, dict) and isinstance(item.get("date"), str)
    ]

    first_result = _generate_with_prompt(
        today_date,
        PROMPT_DAILY_SET.format(date=today_date),
    )
    debug: dict[str, Any] = {
        "mode": "daily_diversity_window_v1",
        "repeat_window_days": repeat_window_days,
        "history_days_found": len(recent_dates),
        "history_dates": recent_dates,
        "retry_triggered": False,
        "selected_pass": "first",
    }

    if not recent_sets:
        first_result.debug = debug
        return first_result

    first_similarity = _collect_similarity_metrics(first_result.payload, recent_sets)
    debug["first_similarity"] = _compact_similarity(first_similarity)

    if not _should_retry_for_similarity(first_similarity):
        first_result.debug = debug
        return first_result
    debug["retry_triggered"] = True

    retry_prompt = PROMPT_DAILY_SET_DIVERSITY_RETRY.format(
        date=today_date,
        history_level2=_format_questions_for_prompt(
            _extract_history_questions(recent_sets, "level2")
        ),
        history_level3=_format_questions_for_prompt(
            _extract_history_questions(recent_sets, "level3")
        ),
    )

    try:
        second_result = _generate_with_prompt(today_date, retry_prompt)
    except OpenAIGenerationError:
        debug["retry_result"] = "failed_second_pass"
        first_result.debug = debug
        return first_result

    combined_usage = _add_usage(first_result.usage, second_result.usage)
    second_similarity = _collect_similarity_metrics(second_result.payload, recent_sets)
    debug["second_similarity"] = _compact_similarity(second_similarity)

    if _similarity_rank(second_similarity) <= _similarity_rank(first_similarity):
        debug["retry_result"] = "used_second_pass"
        debug["selected_pass"] = "second"
        return GenerationResult(
            payload=second_result.payload,
            usage=combined_usage,
            model=second_result.model,
            debug=debug,
        )

    debug["retry_result"] = "kept_first_pass"
    first_result.debug = debug
    return GenerationResult(
        payload=first_result.payload,
        usage=combined_usage,
        model=first_result.model,
        debug=debug,
    )
