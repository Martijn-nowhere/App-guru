"""End-to-end CLI wiring tests, with every network/LLM call mocked out.

`append_to_ledger` is auto-patched for every test in this module so tests
never write to the real repo-committed ledger file -- tests that care about
what gets logged assert on the mock's call args directly.
"""

import pytest
from unittest.mock import patch

import app_guru.cli as cli
from app_guru.extract import PainPoint
from app_guru.reddit_fetch import RedditThread
from app_guru.reddit_search import SearchResult
from app_guru.trends import TrendResult


@pytest.fixture(autouse=True)
def no_real_ledger():
    with patch.object(cli, "append_to_ledger") as mock_append:
        yield mock_append


@pytest.fixture(autouse=True)
def fake_reddit_creds(monkeypatch):
    """Provide Reddit creds and stub the client so cmd_mine never makes a
    real token/API call. Tests that exercise the missing-creds path unset
    these explicitly."""
    monkeypatch.setenv("REDDIT_CLIENT_ID", "cid")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "csecret")
    with patch.object(cli, "RedditClient") as mock_client_cls:
        yield mock_client_cls


def test_trends_subcommand(no_real_ledger):
    fake_results = [
        TrendResult(keyword="quit vaping", ok=True, current_interest=31.0, change_pct=9.0, verdict="RISING"),
    ]
    with patch.object(cli, "check_ideas", return_value=fake_results) as mock_check:
        rc = cli.main(["trends", "quit vaping"])
    assert rc == 0
    mock_check.assert_called_once()

    no_real_ledger.assert_called_once()
    logged_entries = no_real_ledger.call_args.args[0]
    assert logged_entries[0].station == "trends"
    assert logged_entries[0].subject == "quit vaping"
    assert logged_entries[0].verdict == "RISING"


def _fake_mine_dependencies():
    search_results = [
        SearchResult(title="t1", url="https://www.reddit.com/r/coparenting/comments/1/x/", snippet="s"),
    ]
    thread = RedditThread(
        url=search_results[0].url,
        subreddit="coparenting",
        title="t1",
        post_body="body",
        top_comments=["it's hard to co-parent with your abuser"],
    )
    pain_points = [
        PainPoint(
            category="hostile co-parent communication",
            description="Parents feel pressure to stay friendly with an abusive ex.",
            quotes=["it's hard to co-parent with your abuser"],
            simplest_fix="A one-tap button that generates a neutral, drama-free message.",
            opportunity_score=7,
            buildability_score=9,
        ),
        PainPoint(
            category="scheduling conflicts",
            description="Parents argue over swap requests via text.",
            quotes=["we always fight about who has them on holidays"],
            simplest_fix="A shared calendar with one-tap swap requests.",
            opportunity_score=9,
            buildability_score=6,
        ),
    ]
    return search_results, thread, pain_points


def test_mine_missing_creds_returns_2(capsys, monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    rc = cli.main(["mine", "co-parenting"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "Reddit API credentials required" in err


def test_mine_auth_error_returns_2(capsys, fake_reddit_creds):
    from app_guru.reddit_api import RedditAuthError
    fake_reddit_creds.side_effect = RedditAuthError("bad client id/secret (401)")
    rc = cli.main(["mine", "co-parenting"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "401" in err


def test_mine_no_results_exits_cleanly():
    with patch.object(cli, "search_reddit_threads", return_value=[]), \
         patch.object(cli, "extract_pain_points") as mock_extract:
        rc = cli.main(["mine", "co-parenting"])
    assert rc == 0
    mock_extract.assert_not_called()


def test_mine_search_error_returns_1(capsys):
    with patch.object(cli, "search_reddit_threads", side_effect=RuntimeError("429 Too Many Requests")):
        rc = cli.main(["mine", "co-parenting"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "429" in err


def test_mine_subcommand_without_check_trends():
    search_results, thread, pain_points = _fake_mine_dependencies()

    with patch.object(cli, "search_reddit_threads", return_value=search_results), \
         patch.object(cli, "fetch_threads", return_value=([thread], [])), \
         patch.object(cli, "extract_pain_points", return_value=pain_points) as mock_extract, \
         patch.object(cli, "check_ideas") as mock_check:
        rc = cli.main(["mine", "co-parenting"])

    assert rc == 0
    mock_extract.assert_called_once()
    mock_check.assert_not_called()


def test_mine_passes_subreddits_and_phrases_to_search():
    search_results, thread, pain_points = _fake_mine_dependencies()

    with patch.object(cli, "search_reddit_threads", return_value=search_results) as mock_search, \
         patch.object(cli, "fetch_threads", return_value=([thread], [])), \
         patch.object(cli, "extract_pain_points", return_value=pain_points), \
         patch.object(cli, "check_ideas"):
        rc = cli.main(
            ["mine", "co-parenting", "--subreddit", "coparenting", "--subreddit", "blendedfamilies"]
        )

    assert rc == 0
    # search_reddit_threads(client, market, ...) -- client is args[0], market args[1]
    kwargs = mock_search.call_args.kwargs
    assert mock_search.call_args.args[1] == "co-parenting"
    assert kwargs["subreddits"] == ["coparenting", "blendedfamilies"]


def test_mine_ranks_by_opportunity_score(capsys):
    search_results, thread, pain_points = _fake_mine_dependencies()

    with patch.object(cli, "search_reddit_threads", return_value=search_results), \
         patch.object(cli, "fetch_threads", return_value=([thread], [])), \
         patch.object(cli, "extract_pain_points", return_value=pain_points), \
         patch.object(cli, "check_ideas"):
        rc = cli.main(["mine", "co-parenting"])

    assert rc == 0
    out = capsys.readouterr().out
    # "scheduling conflicts" has the higher opportunity score (9 vs 7) so it
    # should be ranked #1 even though it was extracted second.
    first_idx = out.index("#1")
    second_idx = out.index("#2")
    assert out.index("scheduling conflicts") < out.index("hostile co-parent communication")
    assert first_idx < out.index("scheduling conflicts") < second_idx
    assert "Opportunity 9/10" in out
    assert "Buildability 6/10" in out
    assert "App idea: A shared calendar with one-tap swap requests." in out
    assert "only a RISING trends verdict" in out or "counts as validated" in out


def test_mine_logs_pain_points_with_null_verdict(no_real_ledger):
    search_results, thread, pain_points = _fake_mine_dependencies()

    with patch.object(cli, "search_reddit_threads", return_value=search_results), \
         patch.object(cli, "fetch_threads", return_value=([thread], [])), \
         patch.object(cli, "extract_pain_points", return_value=pain_points), \
         patch.object(cli, "check_ideas"):
        rc = cli.main(["mine", "co-parenting"])

    assert rc == 0
    no_real_ledger.assert_called_once()
    logged_entries = no_real_ledger.call_args.args[0]
    assert all(e.station == "mine" for e in logged_entries)
    assert all(e.verdict is None for e in logged_entries)
    assert {e.subject for e in logged_entries} == {"hostile co-parent communication", "scheduling conflicts"}
    assert logged_entries[0].data["market"] == "co-parenting"


def test_mine_subcommand_with_check_trends(capsys):
    search_results, thread, pain_points = _fake_mine_dependencies()
    trend_results = [
        TrendResult(keyword="hostile co-parent communication", ok=True, current_interest=20.0, change_pct=14.0, verdict="RISING"),
        TrendResult(keyword="scheduling conflicts", ok=True, current_interest=10.0, change_pct=1.0, verdict="FLAT"),
    ]

    with patch.object(cli, "search_reddit_threads", return_value=search_results), \
         patch.object(cli, "fetch_threads", return_value=([thread], [])), \
         patch.object(cli, "extract_pain_points", return_value=pain_points), \
         patch.object(cli, "check_ideas", return_value=trend_results) as mock_check:
        rc = cli.main(["mine", "co-parenting", "--check-trends"])

    assert rc == 0
    mock_check.assert_called_once()
    called_categories = mock_check.call_args.args[0]
    assert set(called_categories) == {"hostile co-parent communication", "scheduling conflicts"}

    out = capsys.readouterr().out
    assert "Trend: UP (+14.0%)" in out
    assert "Trend: FLAT (+1.0%)" in out
    assert "cleared the trend gate" in out


def test_mine_csv_includes_scores_and_rank(tmp_path):
    search_results, thread, pain_points = _fake_mine_dependencies()
    trend_results = [
        TrendResult(keyword="hostile co-parent communication", ok=True, current_interest=20.0, change_pct=14.0, verdict="RISING"),
        TrendResult(keyword="scheduling conflicts", ok=True, current_interest=10.0, change_pct=1.0, verdict="FLAT"),
    ]
    csv_path = tmp_path / "report.csv"

    with patch.object(cli, "search_reddit_threads", return_value=search_results), \
         patch.object(cli, "fetch_threads", return_value=([thread], [])), \
         patch.object(cli, "extract_pain_points", return_value=pain_points), \
         patch.object(cli, "check_ideas", return_value=trend_results):
        rc = cli.main(["mine", "co-parenting", "--check-trends", "--csv", str(csv_path)])

    assert rc == 0
    content = csv_path.read_text()
    assert "opportunity_score" in content
    assert "buildability_score" in content
    assert "trend_verdict" in content
    assert "RISING" in content
    # highest opportunity score (scheduling conflicts, 9) should be rank 1
    lines = content.splitlines()
    assert lines[1].startswith("1,scheduling conflicts")
