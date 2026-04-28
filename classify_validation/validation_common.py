from __future__ import annotations

import json
import re
from dataclasses import dataclass


SYSTEM_PROMPT = (
    "You are an expert code reviewer. Given a code comment and its context, "
    "determine if the context uses LLM APIs or libraries, and if the comment "
    "is a self-admitted technical debt (SATD) such as TODO, FIXME, HACK, BUG, "
    "or XXX, related to the implementation and functionality surrounding the "
    "use of the LLM."
)

USER_PROMPT_TEMPLATE = (
    "Comment: {comment}\n"
    "Context: {context}\n\n"
    "Return only a JSON object with exactly these keys:\n"
    '{{"is_context_llm": true|false, "is_comment_satd": true|false, "explanation": "short explanation"}}'
)


@dataclass(frozen=True)
class ClassificationResult:
    is_context_llm: bool
    is_comment_satd: bool
    explanation: str


def extract_json_object(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    start = stripped.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in response: {text!r}")

    depth = 0
    for index in range(start, len(stripped)):
        char = stripped[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : index + 1]

    raise ValueError(f"Incomplete JSON object found in response: {text!r}")


def parse_classification_response(text: str) -> ClassificationResult:
    payload = json.loads(extract_json_object(text))
    return ClassificationResult(
        is_context_llm=bool(payload["is_context_llm"]),
        is_comment_satd=bool(payload["is_comment_satd"]),
        explanation=str(payload["explanation"]).strip(),
    )
