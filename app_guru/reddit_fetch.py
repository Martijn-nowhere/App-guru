"""
Fetch a single Reddit thread's post + top comments via Reddit's official
API (oauth.reddit.com), using the authenticated client from reddit_api.py.

Reddit blocks the old unauthenticated www.reddit.com/*.json endpoints, so
we hit the same thread listing through the authenticated API instead: GET
oauth.reddit.com<permalink> returns the [post, comments] pair.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from app_guru.reddit_api import RedditClient

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


def _thread_path(thread_url: str) -> str:
    """The API path for a thread is just its permalink path (no domain,
    no trailing '.json')."""
    return urlsplit(thread_url).path.rstrip("/")


def fetch_thread(client: RedditClient, thread_url: str, max_comments: int = 15) -> RedditThread:
    payload = client.get_json(_thread_path(thread_url))

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
    client: RedditClient,
    thread_urls: list[str],
    max_comments: int = 15,
) -> tuple[list[RedditThread], list[tuple[str, str]]]:
    """Fetch several threads, collecting (url, error) pairs for failures
    instead of aborting the whole batch on one bad thread."""
    threads: list[RedditThread] = []
    errors: list[tuple[str, str]] = []
    for url in thread_urls:
        try:
            threads.append(fetch_thread(client, url, max_comments=max_comments))
        except Exception as exc:
            errors.append((url, str(exc)))
    return threads, errors
