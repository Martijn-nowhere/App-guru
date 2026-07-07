"""
Fetch a single Reddit thread's post + top comments via Reddit's public,
unauthenticated JSON endpoint (append ".json" to any thread URL). No
Reddit API app/OAuth credentials needed for read access, but Reddit does
require a real-looking User-Agent or it will 429/403 generic clients.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import requests

# Reddit blocks (403) automated-looking User-Agents on its public .json;
# a browser-like UA gets served. Kept in sync with reddit_search.py.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REMOVED_BODIES = {"[deleted]", "[removed]", ""}


@dataclass
class RedditThread:
    url: str
    subreddit: str
    title: str
    post_body: str
    top_comments: list[str] = field(default_factory=list)

    def as_text_block(self) -> str:
        lines = [f"Subreddit: r/{self.subreddit}", f"Title: {self.title}"]
        if self.post_body:
            lines.append(f"Post: {self.post_body}")
        for i, comment in enumerate(self.top_comments, start=1):
            lines.append(f"Comment {i}: {comment}")
        return "\n".join(lines)


def _json_url(thread_url: str) -> str:
    parts = urlsplit(thread_url)
    path = parts.path.rstrip("/")
    if not path.endswith(".json"):
        path += ".json"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def fetch_thread(
    thread_url: str,
    max_comments: int = 15,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 15,
) -> RedditThread:
    resp = requests.get(
        _json_url(thread_url),
        headers={"User-Agent": user_agent, "Accept": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()

    if not isinstance(payload, list) or len(payload) < 2:
        raise ValueError(f"unexpected response shape for {thread_url}")

    post = payload[0]["data"]["children"][0]["data"]
    comment_nodes = payload[1]["data"]["children"]

    comments = []
    for node in comment_nodes:
        if node.get("kind") != "t1":  # skip "more" stubs etc.
            continue
        body = node.get("data", {}).get("body", "")
        if body in REMOVED_BODIES:
            continue
        comments.append((node["data"].get("score", 0), body))

    comments.sort(key=lambda pair: pair[0], reverse=True)
    top_comments = [body for _, body in comments[:max_comments]]

    return RedditThread(
        url=thread_url,
        subreddit=post.get("subreddit", ""),
        title=post.get("title", ""),
        post_body=post.get("selftext", ""),
        top_comments=top_comments,
    )


def fetch_threads(
    thread_urls: list[str],
    max_comments: int = 15,
    user_agent: str = DEFAULT_USER_AGENT,
) -> tuple[list[RedditThread], list[tuple[str, str]]]:
    """Fetch several threads, collecting (url, error) pairs for failures
    instead of aborting the whole batch on one bad thread."""
    threads: list[RedditThread] = []
    errors: list[tuple[str, str]] = []
    for url in thread_urls:
        try:
            threads.append(fetch_thread(url, max_comments=max_comments, user_agent=user_agent))
        except Exception as exc:
            errors.append((url, str(exc)))
    return threads, errors
