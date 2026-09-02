from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.infra.errors import ModelError

TSchema = TypeVar("TSchema", bound=BaseModel)


def parse_structured_output(text: str, schema: type[TSchema]) -> TSchema:
    """Parse model text into a Pydantic schema. Does not apply domain rules."""
    try:
        payload = json.loads(_extract_json_object(text))
        return schema.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as e:
        raise ModelError("Malformed structured output") from e


def _extract_json_object(text: str) -> str:
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("structured output is not a JSON object")
    return stripped[start : end + 1]


async def generate_structured_from(
    llm: object,
    prompt: str,
    schema: type[TSchema],
) -> TSchema:
    """Call provider generate_structured when present; otherwise parse generate()."""
    method = getattr(llm, "generate_structured", None)
    if callable(method):
        return await method(prompt, schema)
    generate = getattr(llm, "generate", None)
    if not callable(generate):
        raise ModelError("LLM client cannot generate structured output")
    text = await generate(prompt)
    return parse_structured_output(text, schema)
