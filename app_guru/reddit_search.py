"""
Reddit thread discovery via Reddit's official API (oauth.reddit.com),
using an app-only bearer token from a "script" app -- see reddit_api.py.

This replaced the earlier unauthenticated www.reddit.com/*.json approach,
which Reddit now blocks (403) for anonymous clients. The authenticated API
is Reddit's sanctioned path and returns the same search listings.

Reddit's search supports quoted phrases and OR, so we bias toward
venting/complaint threads with a disjunction of frustration phrases.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from app_guru.reddit_api import RedditClient

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
    """
    phrases = pain_phrases if pain_phrases is not None else DEFAULT_PAIN_PHRASES
    if not phrases:
        return market
    pain_clause = " OR ".join(f'"{p}"' for p in phrases)
    return f"{market} ({pain_clause})"


def _parse_listing(data: dict) -> list[SearchResult]:
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


def search_reddit_threads(
    client: RedditClient,
    market: str,
    subreddits: list[str] | None = None,
    pain_phrases: list[str] | None = None,
    total: int = 10,
    pause_seconds: float = 1.0,
) -> list[SearchResult]:
    """
    Find Reddit threads about `market` that read like complaints.

    - No subreddits: one site-wide `/search` query.
    - With subreddits: query each subreddit's `/r/<sub>/search` (restricted
      to that sub) and merge, deduped by URL, capped at `total`.
    """
    query = build_reddit_query(market, pain_phrases=pain_phrases)

    if not subreddits:
        data = client.get_json(
            "/search",
            {"q": query, "limit": total, "sort": "relevance", "type": "link"},
        )
        return _parse_listing(data)[:total]

    seen_urls: set[str] = set()
    merged: list[SearchResult] = []
    per_sub = max(1, -(-total // len(subreddits)))  # ceil division
    for i, sub in enumerate(subreddits):
        data = client.get_json(
            f"/r/{sub}/search",
            {"q": query, "limit": per_sub, "restrict_sr": 1, "sort": "relevance", "type": "link"},
        )
        for r in _parse_listing(data):
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                merged.append(r)
        if i < len(subreddits) - 1:
            time.sleep(pause_seconds)
    return merged[:total]
