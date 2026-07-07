"""
Reddit thread discovery via Reddit's own public search endpoint --
NO API key, no Google Cloud, no billing. Just `reddit.com/search.json`
(and the per-subreddit `/r/<sub>/search.json`), which Reddit serves
publicly to any client with a real User-Agent.

This replaces the earlier Google Custom Search approach. The Gold Mining
Framework used a Google `site:reddit.com` query only because that's how you
do it from a browser; hitting Reddit's own search directly gets the same
complaint threads with none of the credential setup.

Reddit's search supports quoted phrases and OR, so we can still bias toward
venting/complaint threads with a disjunction of frustration phrases.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

DEFAULT_USER_AGENT = "app-guru/0.1 (idea-research script; contact via github.com/Martijn-nowhere/app-guru)"

DEFAULT_PAIN_PHRASES = [
    "I wish it did",
    "why can't it just",
    "so frustrating",
    "hate that",
    "annoying that",
    "doesn't work the way I want",
]


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def build_reddit_query(market: str, pain_phrases: list[str] | None = None) -> str:
    """
    Build a Reddit search query string. Reddit's search is Lucene-based and
    supports quoted phrases and OR, so we AND the market term with a
    parenthesized OR-group of frustration phrases to bias toward complaints.
    No `site:` operator -- we're already searching only Reddit.
    """
    phrases = pain_phrases if pain_phrases is not None else DEFAULT_PAIN_PHRASES
    if not phrases:
        return market
    pain_clause = " OR ".join(f'"{p}"' for p in phrases)
    return f"{market} ({pain_clause})"


def _search_once(
    url: str,
    params: dict,
    user_agent: str,
    retries: int = 2,
    pause_seconds: float = 1.0,
) -> list[SearchResult]:
    """One request to a Reddit search endpoint, with a couple of retries.
    Reddit rate-limits anonymous clients, so we back off and retry."""
    attempt = 0
    last_error: Exception | None = None
    while attempt <= retries:
        try:
            resp = requests.get(
                url, params=params, headers={"User-Agent": user_agent}, timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            results = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                permalink = post.get("permalink")
                if not permalink:
                    continue
                results.append(
                    SearchResult(
                        title=post.get("title", ""),
                        url="https://www.reddit.com" + permalink,
                        snippet=(post.get("selftext", "") or "")[:200],
                    )
                )
            return results
        except Exception as exc:  # network, rate-limit, bad JSON
            last_error = exc
            attempt += 1
            if attempt <= retries:
                time.sleep(pause_seconds * (attempt + 1))
    raise RuntimeError(f"Reddit search request failed: {last_error}")


def search_reddit_threads(
    market: str,
    subreddits: list[str] | None = None,
    pain_phrases: list[str] | None = None,
    total: int = 10,
    user_agent: str = DEFAULT_USER_AGENT,
    pause_seconds: float = 1.0,
) -> list[SearchResult]:
    """
    Find Reddit threads about `market` that read like complaints.

    - No subreddits: one site-wide `reddit.com/search.json` query.
    - With subreddits: query each subreddit's `/r/<sub>/search.json`
      (restricted to that sub) and merge the results, deduped by URL,
      capped at `total`.
    """
    query = build_reddit_query(market, pain_phrases=pain_phrases)

    if not subreddits:
        return _search_once(
            "https://www.reddit.com/search.json",
            {"q": query, "limit": total, "sort": "relevance", "type": "link"},
            user_agent,
            pause_seconds=pause_seconds,
        )[:total]

    seen_urls: set[str] = set()
    merged: list[SearchResult] = []
    per_sub = max(1, -(-total // len(subreddits)))  # ceil division
    for i, sub in enumerate(subreddits):
        batch = _search_once(
            f"https://www.reddit.com/r/{sub}/search.json",
            {"q": query, "limit": per_sub, "restrict_sr": 1, "sort": "relevance", "type": "link"},
            user_agent,
            pause_seconds=pause_seconds,
        )
        for r in batch:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                merged.append(r)
        if i < len(subreddits) - 1:
            time.sleep(pause_seconds)
    return merged[:total]
