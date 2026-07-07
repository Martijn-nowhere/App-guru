"""Unit tests for app_guru.reddit_fetch, using a fake RedditClient (the
client.get_json call is what would hit oauth.reddit.com)."""

from unittest.mock import MagicMock

from app_guru.reddit_fetch import _thread_path, fetch_thread, fetch_threads


def test_thread_path_strips_domain_and_trailing_slash():
    url = "https://www.reddit.com/r/coparenting/comments/abc123/some_title/"
    assert _thread_path(url) == "/r/coparenting/comments/abc123/some_title"


def test_thread_path_handles_no_trailing_slash():
    url = "https://www.reddit.com/r/coparenting/comments/abc123/some_title"
    assert _thread_path(url) == "/r/coparenting/comments/abc123/some_title"


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
    client = MagicMock()
    client.get_json.return_value = _fake_thread_payload()

    thread = fetch_thread(
        client, "https://www.reddit.com/r/coparenting/comments/abc123/x/", max_comments=15
    )

    assert thread.subreddit == "coparenting"
    assert "hate co-parenting" in thread.title
    assert thread.post_body == "Ranting about my ex here."
    # deleted comment and "more" stub excluded; sorted by score desc
    assert thread.top_comments == ["It's hard to co-parent with your abuser", "low score comment"]

    # fetched via the permalink path, no domain, no ".json"
    assert client.get_json.call_args.args[0] == "/r/coparenting/comments/abc123/x"


def test_fetch_thread_as_text_block_includes_everything():
    client = MagicMock()
    client.get_json.return_value = _fake_thread_payload()

    thread = fetch_thread(client, "https://www.reddit.com/r/coparenting/comments/abc123/x/")

    text = thread.as_text_block()
    assert "Subreddit: r/coparenting" in text
    assert "Title:" in text
    assert "Post: Ranting" in text
    assert "Comment 1:" in text


def test_fetch_threads_collects_errors_without_aborting():
    client = MagicMock()

    def side_effect(path, *a, **k):
        if "bad" in path:
            raise RuntimeError("404 not found")
        return _fake_thread_payload()

    client.get_json.side_effect = side_effect

    threads, errors = fetch_threads(
        client,
        [
            "https://www.reddit.com/r/coparenting/comments/good1/x/",
            "https://www.reddit.com/r/coparenting/comments/bad/x/",
        ],
    )

    assert len(threads) == 1
    assert len(errors) == 1
    assert errors[0][0].endswith("/bad/x/")
    assert "404" in errors[0][1]
