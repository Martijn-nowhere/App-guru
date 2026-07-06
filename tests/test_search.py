"""Unit tests for app_guru.search, mocking requests instead of hitting the
Google Custom Search API (which is also blocked in this dev sandbox's
egress policy)."""

from unittest.mock import MagicMock, patch

from app_guru.search import build_reddit_query, search_reddit_threads, search_reddit_threads_paged


def test_build_reddit_query_no_subreddits():
    q = build_reddit_query("co-parenting", pain_phrases=["I hate", "so frustrating"])
    assert q.startswith("(site:reddit.com)")
    assert "co-parenting" in q
    assert '"I hate"' in q
    assert '"so frustrating"' in q


def test_build_reddit_query_with_subreddits():
    q = build_reddit_query("co-parenting", subreddits=["coparenting", "blendedfamilies"], pain_phrases=["annoying"])
    assert "site:reddit.com/r/coparenting" in q
    assert "site:reddit.com/r/blendedfamilies" in q
    assert " OR " in q


def _fake_response(items):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"items": items}
    return resp


def test_search_reddit_threads_filters_non_reddit_links():
    items = [
        {"title": "A reddit thread", "link": "https://www.reddit.com/r/x/comments/1/a/", "snippet": "s1"},
        {"title": "Not reddit", "link": "https://example.com/page", "snippet": "s2"},
    ]
    with patch("app_guru.search.requests.get", return_value=_fake_response(items)) as mock_get:
        results = search_reddit_threads("query", "key", "cx")
    assert len(results) == 1
    assert results[0].url == "https://www.reddit.com/r/x/comments/1/a/"
    mock_get.assert_called_once()


def test_search_reddit_threads_paged_stops_on_short_batch():
    full_batch = [
        {"title": f"t{i}", "link": f"https://www.reddit.com/r/x/comments/{i}/a/", "snippet": ""}
        for i in range(10)
    ]
    short_batch = [
        {"title": "t10", "link": "https://www.reddit.com/r/x/comments/10/a/", "snippet": ""}
    ]

    responses = [_fake_response(full_batch), _fake_response(short_batch)]
    with patch("app_guru.search.requests.get", side_effect=responses) as mock_get, \
         patch("app_guru.search.time.sleep"):
        results = search_reddit_threads_paged("query", "key", "cx", total=15)

    assert len(results) == 11
    assert mock_get.call_count == 2


def test_search_reddit_threads_paged_respects_total_cap():
    full_batch = [
        {"title": f"t{i}", "link": f"https://www.reddit.com/r/x/comments/{i}/a/", "snippet": ""}
        for i in range(10)
    ]
    with patch("app_guru.search.requests.get", return_value=_fake_response(full_batch)), \
         patch("app_guru.search.time.sleep"):
        results = search_reddit_threads_paged("query", "key", "cx", total=5)

    assert len(results) == 5
