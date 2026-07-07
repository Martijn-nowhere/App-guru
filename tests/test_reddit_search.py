"""Unit tests for app_guru.reddit_search, using a fake RedditClient (no
network, no real token)."""

from unittest.mock import MagicMock

from app_guru.reddit_search import build_reddit_query, search_reddit_threads


def test_build_reddit_query_with_phrases():
    q = build_reddit_query("co-parenting", pain_phrases=["I hate", "so frustrating"])
    assert q.startswith("co-parenting")
    assert '"I hate"' in q
    assert '"so frustrating"' in q
    assert " OR " in q


def test_build_reddit_query_no_phrases_is_just_market():
    assert build_reddit_query("co-parenting", pain_phrases=[]) == "co-parenting"


def _listing(posts):
    return {"data": {"children": [{"data": p} for p in posts]}}


def test_search_sitewide_builds_full_urls():
    posts = [
        {"title": "Rant", "permalink": "/r/coparenting/comments/1/rant/", "selftext": "ugh"},
        {"title": "No link", "selftext": "x"},  # missing permalink -> skipped
    ]
    client = MagicMock()
    client.get_json.return_value = _listing(posts)

    results = search_reddit_threads(client, "co-parenting", total=10)

    assert len(results) == 1
    assert results[0].url == "https://www.reddit.com/r/coparenting/comments/1/rant/"
    assert results[0].title == "Rant"
    # site-wide search hits the /search endpoint
    assert client.get_json.call_args.args[0] == "/search"


def test_search_subreddits_queries_each_and_dedupes():
    post_a = {"title": "A", "permalink": "/r/coparenting/comments/1/a/", "selftext": ""}
    dupe = {"title": "A dup", "permalink": "/r/coparenting/comments/1/a/", "selftext": ""}
    post_b = {"title": "B", "permalink": "/r/blendedfamilies/comments/2/b/", "selftext": ""}

    client = MagicMock()
    client.get_json.side_effect = [_listing([post_a]), _listing([dupe, post_b])]

    with_sleep = MagicMock()
    import app_guru.reddit_search as rs
    orig_sleep = rs.time.sleep
    rs.time.sleep = with_sleep
    try:
        results = search_reddit_threads(
            client, "co-parenting", subreddits=["coparenting", "blendedfamilies"], total=10
        )
    finally:
        rs.time.sleep = orig_sleep

    urls = [r.url for r in results]
    assert urls == [
        "https://www.reddit.com/r/coparenting/comments/1/a/",
        "https://www.reddit.com/r/blendedfamilies/comments/2/b/",
    ]
    assert client.get_json.call_count == 2
    first_call = client.get_json.call_args_list[0]
    assert first_call.args[0] == "/r/coparenting/search"
    assert first_call.args[1]["restrict_sr"] == 1


def test_search_respects_total_cap():
    posts = [
        {"title": f"t{i}", "permalink": f"/r/x/comments/{i}/a/", "selftext": ""}
        for i in range(10)
    ]
    client = MagicMock()
    client.get_json.return_value = _listing(posts)

    results = search_reddit_threads(client, "x", total=3)
    assert len(results) == 3
