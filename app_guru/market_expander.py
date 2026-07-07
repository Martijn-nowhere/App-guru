"""
Market idea expansion -- the Gold Mining Framework's actual step one.

Per the source video: "the idea is to start with what you have some edge
[on] or what you are interested in within the three core markets which are
health, wealth and relationship... you are already reducing the risk."
Their own walkthrough example narrows relationship -> family relationship
-> parenting -> co-parenting, specifically because the presenter says
"one that I have explored previously and that I found there is a lot of
demand is co-parenting" -- a deliberate narrowing into ONE niche, not a
market-agnostic scan of everything.

This module automates that narrowing step: give it one broad area (or
nothing, to expand all three core markets), and it proposes concrete,
narrower candidate niches -- so you never have to invent a niche name
yourself, but the search stays focused instead of drowning in noise. The
niches it proposes are then meant to be run through `trends` (to see which
are actually growing) and `mine` (to find real pain points within the
winner).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

DEFAULT_MODEL = "claude-opus-4-8"

# The framework's own three "safe" markets -- chosen because people are
# demonstrably willing to spend money in each.
CORE_MARKETS = ["health", "wealth", "relationships"]

NICHE_SCHEMA = {
    "type": "object",
    "properties": {
        "niches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "a short (2-4 word), specific, real market/niche name -- "
                            "narrow enough that a single-feature app could plausibly serve "
                            "it (e.g. 'co-parenting', 'postpartum recovery', 'freelance "
                            "invoicing'), NOT a broad category like 'health' or 'parenting'"
                        ),
                    },
                    "rationale": {
                        "type": "string",
                        "description": (
                            "one sentence: why this niche plausibly has real, recurring "
                            "pain and people already spend money in it"
                        ),
                    },
                },
                "required": ["name", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["niches"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You help narrow a broad market category into concrete, specific candidate "
    "niches for app-idea research, mirroring how a market idea expander works: "
    "given a broad category (health, wealth, relationships, or similar), propose "
    "narrower niches within it. Each niche must be specific enough that a single "
    "narrow-feature app could plausibly serve it -- not a broad category restated "
    "(reject things like 'fitness' or 'parenting'), and not a dead micro-niche with "
    "no realistic audience or spending behavior. Favor niches where people are "
    "demonstrably already spending money (subscriptions, services, courses) and "
    "where a recurring, specific frustration plausibly exists -- these are the "
    "niches worth trend-checking and then mining for real complaints. Do not "
    "repeat near-duplicate niches."
)


@dataclass
class NicheCandidate:
    name: str
    rationale: str = ""
    parent_category: str = ""


def expand_market(
    categories: list[str],
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    count_per_category: int = 8,
    max_tokens: int = 2048,
) -> list[NicheCandidate]:
    """
    Expand one or more broad categories into concrete candidate niches.
    Reads ANTHROPIC_API_KEY from the environment if api_key is not passed.
    """
    client = anthropic.Anthropic(api_key=api_key)
    results: list[NicheCandidate] = []

    for category in categories:
        prompt = (
            f'Broad category: "{category}"\n\n'
            f"Propose {count_per_category} specific, narrower candidate niches within "
            f"this category for app-idea research."
        )
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            output_config={"format": {"type": "json_schema", "schema": NICHE_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )

        text = next(block.text for block in response.content if block.type == "text")
        data = json.loads(text)

        for n in data["niches"]:
            results.append(NicheCandidate(name=n["name"], rationale=n["rationale"], parent_category=category))

    return results
