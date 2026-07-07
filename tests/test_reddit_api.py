"""Unit tests for the Reddit OAuth client, mocking requests (no real
token exchange, and oauth.reddit.com is blocked in this dev sandbox anyway)."""

from unittest.mock import MagicMock, patch

import pytest

from app_guru.reddit_api import RedditAuthError, RedditClient, get_access_token


def _token_response(status=200, token="tok123", text="{}"):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = {"access_token": token} if token else {}
    resp.text = text
    resp.raise_for_status.return_value = None
    return resp


def test_get_access_token_returns_token():
    with patch("app_guru.reddit_api.requests.post", return_value=_token_response(token="abc")) as mock_post:
        token = get_access_token("cid", "secret")
    assert token == "abc"
    # client-credentials grant, HTTP basic auth
    assert mock_post.call_args.kwargs["data"] == {"grant_type": "client_credentials"}
    assert mock_post.call_args.kwargs["auth"] == ("cid", "secret")


def test_get_access_token_401_raises_auth_error():
    with patch("app_guru.reddit_api.requests.post", return_value=_token_response(status=401)):
        with pytest.raises(RedditAuthError):
            get_access_token("bad", "creds")


def test_get_access_token_no_token_raises():
    with patch("app_guru.reddit_api.requests.post", return_value=_token_response(token=None)):
        with pytest.raises(RedditAuthError):
            get_access_token("cid", "secret")


def test_client_get_json_sends_bearer_and_raw_json():
    api_resp = MagicMock()
    api_resp.raise_for_status.return_value = None
    api_resp.json.return_value = {"ok": True}

    with patch("app_guru.reddit_api.requests.post", return_value=_token_response(token="tok")), \
         patch("app_guru.reddit_api.requests.get", return_value=api_resp) as mock_get:
        client = RedditClient("cid", "secret")
        data = client.get_json("/search", {"q": "x"})

    assert data == {"ok": True}
    call = mock_get.call_args
    assert call.args[0] == "https://oauth.reddit.com/search"
    assert call.kwargs["headers"]["Authorization"] == "bearer tok"
    assert call.kwargs["params"]["raw_json"] == 1
    assert call.kwargs["params"]["q"] == "x"
