"""
Web-search research step for `mine`, replacing the old Reddit-API pipeline.

Instead of us wiring up a third-party data source (Reddit's OAuth API, which
now requires manual developer approval, or Google Custom Search, which needs
a billed Cloud project), we let Claude do the searching itself with its
built-in `web_search` server tool. Claude searches the open web -- Reddit
threads, forums, app-store reviews, Q&A sites -- and compiles the real,
verbatim complaints it finds into one document.

That document is then handed, unchanged, to `extract.py`, which turns it
into categorized, quote-backed, scored app suggestions. So the only
credential `mine` needs is ANTHROPIC_API_KEY -- the same key `trends`-free
users already have working. No Reddit app, no OAuth, no Cloud billing.

This mirrors the Gold Mining Framework's first move ("go where people
complain and collect the raw complaints") -- Claude just does the collecting.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import anthropic

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_MAX_SEARCHES = 5

DEFAULT_PAIN_PHRASES = [
    "frustrated",
    "hate that",
    "wish there was an app",
    "is there a way to",
    "annoying",
    "why is it so hard to",
]

RESEARCH_SYSTEM_PROMPT = (
    "You are a research assistant for app-idea sourcing. Your job is to find "
    "REAL people describing REAL frustrations about a given market, using web "
    "search, and to compile their actual words. Prioritize places where "
    "people vent honestly: Reddit threads, niche forums, app-store and "
    "software reviews, Q&A sites. Do NOT invent complaints, summarize away "
    "the specifics, or editorialize. Reproduce the complaints as close to "
    "verbatim as possible, each with a one-line note on where it came from "
    "(subreddit / forum / review site) so a later step can quote them. "
    "Favor concrete, repeated, everyday annoyances over big visionary "
    "problems -- the goal is to find boring, narrow problems a one-feature "
    "app could fix."
)


@dataclass
class ResearchResult:
    text: str
    sources: list[str] = field(default_factory=list)
    search_count: int = 0

    def is_empty(self) -> bool:
        return not self.text.strip()


def build_research_prompt(
    market: str,
    subreddits: list[str] | None = None,
    pain_phrases: list[str] | None = None,
) -> str:
    phrases = pain_phrases if pain_phrases else DEFAULT_PAIN_PHRASES
    lines = [
        f'Find real people complaining about problems in this market: "{market}".',
        "",
        "Run several web searches. Combine the market with frustration language "
        "like: " + ", ".join(f'"{p}"' for p in phrases) + ".",
    ]
    if subreddits:
        subs = ", ".join(f"r/{s}" for s in subreddits)
        lines += [
            "",
            f"Pay special attention to these subreddits if relevant: {subs}. "
            "You can bias searches with site:reddit.com or the subreddit name.",
        ]
    lines += [
        "",
        "Then compile everything you found into a single document. For each "
        "distinct complaint, give:",
        "  - the person's words, as close to verbatim as you can get them",
        "  - a one-line note on the source (which subreddit / forum / review site)",
        "",
        "Group nothing, score nothing, recommend nothing -- just gather the raw "
        "complaints. The more real, specific, quotable frustrations you collect, "
        "the better. If you genuinely find nothing, say so plainly.",
    ]
    return "\n".join(lines)


def _collect_text(response) -> str:
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _collect_sources(response) -> list[str]:
    urls: list[str] = []
    seen = set()
    for block in response.content:
        if getattr(block, "type", None) != "web_search_tool_result":
            continue
        content = getattr(block, "content", None) or []
        for item in content:
            url = getattr(item, "url", None)
            if url and url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _count_searches(response) -> int:
    count = 0
    for block in response.content:
        if getattr(block, "type", None) == "server_tool_use" and getattr(block, "name", None) == "web_search":
            count += 1
    return count


def research_market(
    market: str,
    subreddits: list[str] | None = None,
    pain_phrases: list[str] | None = None,
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    max_searches: int = DEFAULT_MAX_SEARCHES,
    max_tokens: int = 4096,
) -> ResearchResult:
    """
    Have Claude search the web for real complaints about `market` and return
    the compiled raw text (plus the source URLs it hit). Reads
    ANTHROPIC_API_KEY from the environment if api_key is not passed.
    """
    client = anthropic.Anthropic(api_key=api_key)
    prompt = build_research_prompt(market, subreddits=subreddits, pain_phrases=pain_phrases)

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=RESEARCH_SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}],
        messages=[{"role": "user", "content": prompt}],
    )

    return ResearchResult(
        text=_collect_text(response),
        sources=_collect_sources(response),
        search_count=_count_searches(response),
    )
