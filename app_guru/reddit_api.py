"""
Reddit API client using application-only OAuth (the client-credentials
grant). A Reddit "script" app gives you a client ID + secret; we exchange
those for a short-lived bearer token and use it against oauth.reddit.com.

This is Reddit's sanctioned path for programmatic read access -- reliable
and not subject to the 403 "Blocked" that hits the unauthenticated
www.reddit.com/*.json endpoints. No Reddit username/password needed; the
client-credentials grant gives app-only read access, which is all `mine`
needs (public search + public thread listings).

Create the app at https://www.reddit.com/prefs/apps ("script" type). Then
set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.
"""

from __future__ import annotations

import time

import requests

API_BASE = "https://oauth.reddit.com"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

# Reddit requires a unique, descriptive User-Agent for API access and will
# throttle generic/library ones. Overridable via REDDIT_USER_AGENT.
DEFAULT_USER_AGENT = "app-guru/0.1 (personal app-idea research script)"


class RedditAuthError(RuntimeError):
    """The client ID/secret were rejected, or no token came back."""


def get_access_token(client_id: str, client_secret: str, user_agent: str = DEFAULT_USER_AGENT) -> str:
    """Exchange a script app's client_id/secret for an app-only bearer token."""
    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={"grant_type": "client_credentials"},
        headers={"User-Agent": user_agent},
        timeout=15,
    )
    if resp.status_code == 401:
        raise RedditAuthError(
            "Reddit rejected the client ID/secret (401). Double-check "
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET (the app must be the "
            "'script' type)."
        )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RedditAuthError(f"No access_token in Reddit response: {resp.text[:200]}")
    return token


class RedditClient:
    """Holds a bearer token and makes authenticated GETs to oauth.reddit.com."""

    def __init__(self, client_id: str, client_secret: str, user_agent: str = DEFAULT_USER_AGENT):
        self.user_agent = user_agent
        self._token = get_access_token(client_id, client_secret, user_agent)

    def get_json(self, path: str, params: dict | None = None, retries: int = 2, pause_seconds: float = 1.0):
        """GET oauth.reddit.com<path> and return parsed JSON, with retries."""
        url = API_BASE + path
        merged = {"raw_json": 1}
        if params:
            merged.update(params)
        attempt = 0
        last_error: Exception | None = None
        while attempt <= retries:
            try:
                resp = requests.get(
                    url,
                    params=merged,
                    headers={
                        "Authorization": f"bearer {self._token}",
                        "User-Agent": self.user_agent,
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_error = exc
                attempt += 1
                if attempt <= retries:
                    time.sleep(pause_seconds * (attempt + 1))
        raise RuntimeError(f"Reddit API request to {path} failed: {last_error}")
