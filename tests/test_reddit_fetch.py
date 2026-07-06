"""Unit tests for app_guru.reddit_fetch, mocking the reddit .json endpoint
(reddit.com is blocked in this dev sandbox's egress policy, same as Trends
and the search APIs)."""

from unittest.mock import MagicMock, patch

from app_guru.reddit_fetch import _json_url, fetch_thread, fetch_threads


def test_json_url_appends_json_and_strips_trailing_slash():
    url = "https://www.reddit.com/r/coparenting/comments/abc123/some_title/"
    assert _json_url(url) == "https://www.reddit.com/r/coparenting/comments/abc123/some_title.json"


def test_json_url_handles_no_trailing_slash():
    url = "https://www.reddit.com/r/coparenting/comments/abc123/some_title"
    assert _json_url(url) == "https://www.reddit.com/r/coparenting/comments/abc123/some_title.json"


def _fake_thread_payload():
    return [
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "subreddit": "coparenting",
                            "title": "I hate co-parenting but it's so damn necessary",
                            "selftext": "Ranting about my ex here.",
                        }
                    }
                ]
            }
        },
        {
            "data": {
                "children": [
                    {"kind": "t1", "data": {"body": "It's hard to co-parent with your abuser", "score": 42}},
                    {"kind": "t1", "data": {"body": "[deleted]", "score": 5}},
                    {"kind": "t1", "data": {"body": "low score comment", "score": 1}},
                    {"kind": "more", "data": {}},
                ]
            }
        },
    ]


def test_fetch_thread_parses_post_and_top_comments():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = _fake_thread_payload()

    with patch("app_guru.reddit_fetch.requests.get", return_value=resp) as mock_get:
        thread = fetch_thread("https://www.reddit.com/r/coparenting/comments/abc123/x/", max_comments=15)

    assert thread.subreddit == "coparenting"
    assert "hate co-parenting" in thread.title
    assert thread.post_body == "Ranting about my ex here."
    # deleted comment and "more" stub excluded; sorted by score desc
    assert thread.top_comments == ["It's hard to co-parent with your abuser", "low score comment"]

    called_url = mock_get.call_args[0][0]
    assert called_url.endswith(".json")


def test_fetch_thread_as_text_block_includes_everything():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = _fake_thread_payload()

    with patch("app_guru.reddit_fetch.requests.get", return_value=resp):
        thread = fetch_thread("https://www.reddit.com/r/coparenting/comments/abc123/x/")

    text = thread.as_text_block()
    assert "Subreddit: r/coparenting" in text
    assert "Title:" in text
    assert "Post: Ranting" in text
    assert "Comment 1:" in text


def test_fetch_threads_collects_errors_without_aborting():
    ok_resp = MagicMock()
    ok_resp.raise_for_status.return_value = None
    ok_resp.json.return_value = _fake_thread_payload()

    def side_effect(url, **kwargs):
        if "bad" in url:
            raise RuntimeError("404 not found")
        return ok_resp

    with patch("app_guru.reddit_fetch.requests.get", side_effect=side_effect):
        threads, errors = fetch_threads(
            [
                "https://www.reddit.com/r/coparenting/comments/good1/x/",
                "https://www.reddit.com/r/coparenting/comments/bad/x/",
            ]
        )

    assert len(threads) == 1
    assert len(errors) == 1
    assert errors[0][0].endswith("/bad/x/")
    assert "404" in errors[0][1]
