"""Unit tests for app_guru.reddit_search, mocking requests (reddit.com is
blocked in this dev sandbox's egress policy, and we don't want real network
calls in unit tests anyway)."""

from unittest.mock import MagicMock, patch

from app_guru.reddit_search import build_reddit_query, search_reddit_threads


def test_build_reddit_query_with_phrases():
    q = build_reddit_query("co-parenting", pain_phrases=["I hate", "so frustrating"])
    assert q.startswith("co-parenting")
    assert '"I hate"' in q
    assert '"so frustrating"' in q
    assert " OR " in q


def test_build_reddit_query_no_phrases_is_just_market():
    assert build_reddit_query("co-parenting", pain_phrases=[]) == "co-parenting"


def _fake_search_response(posts):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "data": {"children": [{"data": p} for p in posts]}
    }
    return resp


def test_search_sitewide_builds_full_urls():
    posts = [
        {"title": "Rant", "permalink": "/r/coparenting/comments/1/rant/", "selftext": "ugh"},
        {"title": "No link", "selftext": "x"},  # missing permalink -> skipped
    ]
    with patch("app_guru.reddit_search.requests.get", return_value=_fake_search_response(posts)) as mock_get:
        results = search_reddit_threads("co-parenting", total=10)

    assert len(results) == 1
    assert results[0].url == "https://www.reddit.com/r/coparenting/comments/1/rant/"
    assert results[0].title == "Rant"
    # site-wide search hits the top-level search endpoint
    assert mock_get.call_args.args[0] == "https://www.reddit.com/search.json"


def test_search_subreddits_queries_each_and_dedupes():
    post_a = {"title": "A", "permalink": "/r/coparenting/comments/1/a/", "selftext": ""}
    dupe = {"title": "A dup", "permalink": "/r/coparenting/comments/1/a/", "selftext": ""}
    post_b = {"title": "B", "permalink": "/r/blendedfamilies/comments/2/b/", "selftext": ""}

    responses = [
        _fake_search_response([post_a]),
        _fake_search_response([dupe, post_b]),
    ]
    with patch("app_guru.reddit_search.requests.get", side_effect=responses) as mock_get, \
         patch("app_guru.reddit_search.time.sleep"):
        results = search_reddit_threads(
            "co-parenting", subreddits=["coparenting", "blendedfamilies"], total=10
        )

    urls = [r.url for r in results]
    assert urls == [
        "https://www.reddit.com/r/coparenting/comments/1/a/",
        "https://www.reddit.com/r/blendedfamilies/comments/2/b/",
    ]
    # one request per subreddit, each scoped to that subreddit
    assert mock_get.call_count == 2
    first_url = mock_get.call_args_list[0].args[0]
    assert first_url == "https://www.reddit.com/r/coparenting/search.json"
    assert mock_get.call_args_list[0].kwargs["params"]["restrict_sr"] == 1


def test_search_respects_total_cap():
    posts = [
        {"title": f"t{i}", "permalink": f"/r/x/comments/{i}/a/", "selftext": ""}
        for i in range(10)
    ]
    with patch("app_guru.reddit_search.requests.get", return_value=_fake_search_response(posts)):
        results = search_reddit_threads("x", total=3)
    assert len(results) == 3


def test_search_retries_then_raises():
    with patch("app_guru.reddit_search.requests.get", side_effect=RuntimeError("boom")), \
         patch("app_guru.reddit_search.time.sleep"):
        try:
            search_reddit_threads("x", total=5)
        except RuntimeError as exc:
            assert "Reddit search request failed" in str(exc)
        else:
            raise AssertionError("expected RuntimeError")
