"""
Reddit thread discovery via Google Programmable Search (Custom Search JSON
API), instead of the Reddit API. Mirrors the "Gold Mining Framework" step:

    "In step three, we go on Google to find Reddit threads. But we will
     use a special query with advanced search on Google to surface the
     Reddit threads where people are talking about their problem,
     expressing their pain."

Requires a Google Cloud API key and a Programmable Search Engine
(https://programmablesearchengine.google.com/) configured to search the
entire web. Free tier: 100 queries/day.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

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


def build_reddit_query(
    market: str,
    subreddits: list[str] | None = None,
    pain_phrases: list[str] | None = None,
) -> str:
    """
    Build a Google query scoped to reddit.com (optionally to specific
    subreddits) plus a disjunction of frustration phrases, so results skew
    toward threads where people are venting about `market` rather than
    neutral discussion.
    """
    if subreddits:
        site_clause = " OR ".join(f"site:reddit.com/r/{s}" for s in subreddits)
    else:
        site_clause = "site:reddit.com"

    phrases = pain_phrases if pain_phrases is not None else DEFAULT_PAIN_PHRASES
    pain_clause = " OR ".join(f'"{p}"' if " " in p else p for p in phrases)

    return f"({site_clause}) {market} ({pain_clause})"


def search_reddit_threads(
    query: str,
    api_key: str,
    cx: str,
    num: int = 10,
    start: int = 1,
    retries: int = 2,
    pause_seconds: float = 1.0,
) -> list[SearchResult]:
    """
    Run the query against the Custom Search JSON API. `num` is capped at 10
    per request by the API itself; use `start` (1-indexed) to page beyond
    that, or call search_reddit_threads_paged for that automatically.
    """
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": min(num, 10),
        "start": start,
    }

    attempt = 0
    last_error: Exception | None = None
    while attempt <= retries:
        try:
            resp = requests.get(SEARCH_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            return [
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                )
                for item in items
                if "reddit.com" in item.get("link", "")
            ]
        except Exception as exc:  # network errors, 4xx/5xx, bad JSON
            last_error = exc
            attempt += 1
            if attempt <= retries:
                time.sleep(pause_seconds * attempt)

    raise RuntimeError(f"Google Custom Search request failed: {last_error}")


def search_reddit_threads_paged(
    query: str,
    api_key: str,
    cx: str,
    total: int = 10,
    pause_seconds: float = 1.0,
) -> list[SearchResult]:
    """
    Page through results in batches of 10 (the API's per-request cap) until
    `total` results are collected or the API stops returning items.
    """
    results: list[SearchResult] = []
    start = 1
    while len(results) < total:
        batch = search_reddit_threads(
            query,
            api_key,
            cx,
            num=min(10, total - len(results)),
            start=start,
            pause_seconds=pause_seconds,
        )
        if not batch:
            break
        results.extend(batch)
        if len(batch) < 10:
            break
        start += 10
        time.sleep(pause_seconds)
    return results[:total]
