"""
LLM-based pain-point extraction, mirroring the Gold Mining Framework step:

    "Now we process the data. For that we have three major prompts that we
     use one after the other. The first one will extract all the pain
     points and refine them... categories and quotes from the people
     attached to the specific pain point."

Uses the Anthropic Messages API with a JSON schema output format so the
result is always valid, parseable JSON -- no free-text parsing needed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import anthropic

DEFAULT_MODEL = "claude-opus-4-8"

PAIN_POINT_SCHEMA = {
    "type": "object",
    "properties": {
        "pain_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "short label for the theme, e.g. 'onboarding friction'",
                    },
                    "pain_point": {
                        "type": "string",
                        "description": "one to two sentence description of the problem",
                    },
                    "quotes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "verbatim supporting quotes from the source threads",
                    },
                },
                "required": ["category", "pain_point", "quotes"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["pain_points"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You extract customer pain points from raw forum/review text for app idea "
    "research. For each distinct problem people describe, produce a category "
    "label, a one-to-two sentence description, and the verbatim quotes that "
    "support it. Merge duplicate or near-duplicate complaints into a single "
    "pain point rather than repeating them. Only include pain points that "
    "have at least one supporting quote from the provided text -- do not "
    "invent or infer problems that aren't actually expressed."
)

THREAD_SEPARATOR = "\n\n--- NEXT THREAD ---\n\n"


@dataclass
class PainPoint:
    category: str
    description: str
    quotes: list[str] = field(default_factory=list)


def join_threads(thread_texts: list[str]) -> str:
    return THREAD_SEPARATOR.join(thread_texts)


def extract_pain_points(
    source_text: str,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4096,
) -> list[PainPoint]:
    """
    Send raw thread text (see join_threads) to Claude and get back
    structured, quote-backed pain points. Reads ANTHROPIC_API_KEY from the
    environment if api_key is not passed.
    """
    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": PAIN_POINT_SCHEMA}},
        messages=[{"role": "user", "content": source_text}],
    )

    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)

    return [
        PainPoint(category=p["category"], description=p["pain_point"], quotes=p["quotes"])
        for p in data["pain_points"]
    ]
