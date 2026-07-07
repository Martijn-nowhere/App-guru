"""
LLM-based pain-point extraction, mirroring the Gold Mining Framework step:

    "Now we process the data. For that we have three major prompts that we
     use one after the other. The first one will extract all the pain
     points and refine them... categories and quotes from the people
     attached to the specific pain point."

Extended with two scores per pain point, per the "boring, one-feature apps
win" thesis from the sourcing videos (Puff Count: one screen, one feature;
a $10M/month QR reader): opportunity (is this a real, common, painful
complaint) and buildability (can it be solved with one narrow feature, or
does it need a complex multi-part product).

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
                    "search_term": {
                        "type": "string",
                        "description": (
                            "a SHORT, real phrase an actual person would type into Google when "
                            "looking for an app in this space -- 2-4 words, the kind of query that "
                            "has real search volume. Think product category, not the specific "
                            "complaint. e.g. for a co-parent messaging gripe: 'co parenting app', "
                            "not 'unreliable notifications'. This is what gets trend-checked, so it "
                            "MUST be something people genuinely search, not a description of the bug."
                        ),
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
                    "simplest_fix": {
                        "type": "string",
                        "description": (
                            "the narrowest possible single-feature app that addresses just this "
                            "pain point -- one sentence, no 'and'. If it can't be stated without "
                            "an 'and', say so instead of forcing it."
                        ),
                    },
                    "opportunity_score": {
                        "type": "integer",
                        "description": (
                            "1-10: how painful and how common this complaint looks from the "
                            "evidence alone (number of quotes/threads, intensity of language). "
                            "This is NOT a claim about validated market demand -- only trends "
                            "data or real signups can confirm that."
                        ),
                    },
                    "buildability_score": {
                        "type": "integer",
                        "description": (
                            "1-10: how simple the simplest_fix is to actually build. 10 = a "
                            "trivial single-feature app, no backend/auth/payments complexity, "
                            "buildable with no-code AI tools in hours. 1 = needs a complex "
                            "multi-sided product, deep integrations, or regulatory hurdles."
                        ),
                    },
                },
                "required": [
                    "category",
                    "search_term",
                    "pain_point",
                    "quotes",
                    "simplest_fix",
                    "opportunity_score",
                    "buildability_score",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["pain_points"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You extract customer pain points from raw forum/review text for app idea "
    "research, and score them as potential app ideas. For each distinct "
    "problem people describe, produce: a category label; a real-world "
    "search_term (a short phrase people actually Google when looking for an "
    "app in this space -- the product category, NOT the specific complaint, "
    "so it has real search volume); a one-to-two "
    "sentence description; the verbatim quotes that support it; the "
    "simplest possible single-feature fix (one sentence, no 'and' -- if you "
    "can't state it without one, say the pain point is too broad instead of "
    "forcing a fix); an opportunity_score (1-10) for how painful/common the "
    "complaint looks from the evidence alone; and a buildability_score "
    "(1-10) for how simple that fix would be to actually build. Favor "
    "boring, narrow, single-feature ideas over ambitious or clever ones -- "
    "the most profitable apps are usually the simplest ones solving one "
    "real problem well, not the most impressive-sounding. Merge duplicate "
    "or near-duplicate complaints into a single pain point rather than "
    "repeating them. Only include pain points that have at least one "
    "supporting quote from the provided text -- do not invent or infer "
    "problems that aren't actually expressed."
)

THREAD_SEPARATOR = "\n\n--- NEXT THREAD ---\n\n"


@dataclass
class PainPoint:
    category: str
    description: str
    quotes: list[str] = field(default_factory=list)
    simplest_fix: str = ""
    opportunity_score: int = 0
    buildability_score: int = 0
    search_term: str = ""


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
    structured, quote-backed, scored app-idea suggestions. Reads
    ANTHROPIC_API_KEY from the environment if api_key is not passed.
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
        PainPoint(
            category=p["category"],
            description=p["pain_point"],
            quotes=p["quotes"],
            simplest_fix=p["simplest_fix"],
            opportunity_score=p["opportunity_score"],
            buildability_score=p["buildability_score"],
            search_term=p["search_term"],
        )
        for p in data["pain_points"]
    ]
