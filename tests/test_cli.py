"""End-to-end CLI wiring tests, with every network/LLM call mocked out.

`append_to_ledger` is auto-patched for every test in this module so tests
never write to the real repo-committed ledger file -- tests that care about
what gets logged assert on the mock's call args directly.
"""

import pytest
from unittest.mock import patch

import anthropic

import app_guru.cli as cli
from app_guru.extract import PainPoint
from app_guru.market_expander import NicheCandidate
from app_guru.trends import TrendResult
from app_guru.web_research import ResearchResult


@pytest.fixture(autouse=True)
def no_real_ledger():
    with patch.object(cli, "append_to_ledger") as mock_append:
        yield mock_append


@pytest.fixture(autouse=True)
def fake_api_key(monkeypatch):
    """Give cmd_mine an API key so it gets past the credential check. Tests
    that exercise the missing-key path unset it explicitly."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


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
    research = ResearchResult(
        text="Raw complaints compiled from the web...",
        sources=["https://www.reddit.com/r/coparenting/comments/1/x/"],
        search_count=3,
    )
    pain_points = [
        PainPoint(
            category="hostile co-parent communication",
            search_term="co parenting app",
            description="Parents feel pressure to stay friendly with an abusive ex.",
            quotes=["it's hard to co-parent with your abuser"],
            simplest_fix="A one-tap button that generates a neutral, drama-free message.",
            opportunity_score=7,
            buildability_score=9,
        ),
        PainPoint(
            category="scheduling conflicts",
            search_term="custody calendar app",
            description="Parents argue over swap requests via text.",
            quotes=["we always fight about who has them on holidays"],
            simplest_fix="A shared calendar with one-tap swap requests.",
            opportunity_score=9,
            buildability_score=6,
        ),
    ]
    return research, pain_points


def test_mine_missing_key_returns_2(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = cli.main(["mine", "co-parenting"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ANTHROPIC_API_KEY required" in err


def test_mine_api_error_returns_1(capsys):
    err = anthropic.APIError("boom", request=None, body=None)
    with patch.object(cli, "research_market", side_effect=err):
        rc = cli.main(["mine", "co-parenting"])
    assert rc == 1
    assert "research failed" in capsys.readouterr().err


def test_mine_no_results_exits_cleanly():
    empty = ResearchResult(text="", sources=[], search_count=1)
    with patch.object(cli, "research_market", return_value=empty), \
         patch.object(cli, "extract_pain_points") as mock_extract:
        rc = cli.main(["mine", "co-parenting"])
    assert rc == 0
    mock_extract.assert_not_called()


def test_mine_subcommand_without_check_trends():
    research, pain_points = _fake_mine_dependencies()

    with patch.object(cli, "research_market", return_value=research), \
         patch.object(cli, "extract_pain_points", return_value=pain_points) as mock_extract, \
         patch.object(cli, "check_ideas") as mock_check:
        rc = cli.main(["mine", "co-parenting"])

    assert rc == 0
    mock_extract.assert_called_once()
    # the compiled research text is what gets extracted
    assert mock_extract.call_args.args[0] == research.text
    mock_check.assert_not_called()


def test_mine_passes_subreddits_and_phrases_to_research():
    research, pain_points = _fake_mine_dependencies()

    with patch.object(cli, "research_market", return_value=research) as mock_research, \
         patch.object(cli, "extract_pain_points", return_value=pain_points), \
         patch.object(cli, "check_ideas"):
        rc = cli.main(
            ["mine", "co-parenting", "--subreddit", "coparenting", "--subreddit", "blendedfamilies"]
        )

    assert rc == 0
    # research_market(market, ...) -- market is args[0]
    assert mock_research.call_args.args[0] == "co-parenting"
    assert mock_research.call_args.kwargs["subreddits"] == ["coparenting", "blendedfamilies"]


def test_mine_ranks_by_opportunity_score(capsys):
    research, pain_points = _fake_mine_dependencies()

    with patch.object(cli, "research_market", return_value=research), \
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
    research, pain_points = _fake_mine_dependencies()

    with patch.object(cli, "research_market", return_value=research), \
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
    research, pain_points = _fake_mine_dependencies()
    trend_results = [
        TrendResult(keyword="co parenting app", ok=True, current_interest=20.0, change_pct=14.0, verdict="RISING"),
        TrendResult(keyword="custody calendar app", ok=True, current_interest=10.0, change_pct=1.0, verdict="FLAT"),
    ]

    with patch.object(cli, "research_market", return_value=research), \
         patch.object(cli, "extract_pain_points", return_value=pain_points), \
         patch.object(cli, "check_ideas", return_value=trend_results) as mock_check:
        rc = cli.main(["mine", "co-parenting", "--check-trends"])

    assert rc == 0
    mock_check.assert_called_once()
    # trend-checks the real search terms, not the category labels
    called_terms = mock_check.call_args.args[0]
    assert set(called_terms) == {"co parenting app", "custody calendar app"}
    # never displayed by mine's report, so skip the extra related-queries request
    assert mock_check.call_args.kwargs["fetch_related"] is False

    out = capsys.readouterr().out
    assert 'Trend for "co parenting app": UP (+14.0%)' in out
    assert 'Trend for "custody calendar app": FLAT (+1.0%)' in out
    assert "cleared the trend gate" in out


def test_mine_csv_includes_scores_and_rank(tmp_path):
    research, pain_points = _fake_mine_dependencies()
    trend_results = [
        TrendResult(keyword="co parenting app", ok=True, current_interest=20.0, change_pct=14.0, verdict="RISING"),
        TrendResult(keyword="custody calendar app", ok=True, current_interest=10.0, change_pct=1.0, verdict="FLAT"),
    ]
    csv_path = tmp_path / "report.csv"

    with patch.object(cli, "research_market", return_value=research), \
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


def _fake_explore_dependencies():
    candidates = [
        NicheCandidate(name="co-parenting", rationale="recurring conflict, real spend", parent_category="relationships"),
        NicheCandidate(name="blended families", rationale="growing niche, less crowded", parent_category="relationships"),
    ]
    trend_results = [
        TrendResult(keyword="co-parenting", ok=True, current_interest=30.0, change_pct=13.0, verdict="RISING"),
        TrendResult(keyword="blended families", ok=True, current_interest=10.0, change_pct=1.0, verdict="FLAT"),
    ]
    return candidates, trend_results


def test_explore_missing_key_returns_2(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = cli.main(["explore"])
    assert rc == 2
    assert "ANTHROPIC_API_KEY required" in capsys.readouterr().err


def test_explore_defaults_to_core_markets():
    candidates, trend_results = _fake_explore_dependencies()
    with patch.object(cli, "expand_market", return_value=candidates) as mock_expand, \
         patch.object(cli, "check_ideas", return_value=trend_results):
        rc = cli.main(["explore"])

    assert rc == 0
    assert mock_expand.call_args.args[0] == cli.CORE_MARKETS


def test_explore_uses_given_category():
    candidates, trend_results = _fake_explore_dependencies()
    with patch.object(cli, "expand_market", return_value=candidates) as mock_expand, \
         patch.object(cli, "check_ideas", return_value=trend_results):
        rc = cli.main(["explore", "relationships"])

    assert rc == 0
    assert mock_expand.call_args.args[0] == ["relationships"]


def test_explore_api_error_returns_1(capsys):
    err = anthropic.APIError("boom", request=None, body=None)
    with patch.object(cli, "expand_market", side_effect=err):
        rc = cli.main(["explore"])
    assert rc == 1
    assert "market expansion failed" in capsys.readouterr().err


def test_explore_ranks_rising_first_and_reports_trend(capsys):
    candidates, trend_results = _fake_explore_dependencies()
    with patch.object(cli, "expand_market", return_value=candidates), \
         patch.object(cli, "check_ideas", return_value=trend_results):
        rc = cli.main(["explore"])

    assert rc == 0
    out = capsys.readouterr().out
    assert out.index("co-parenting") < out.index("blended families")
    assert "UP (+13.0%, interest 30.0/100)" in out
    assert "FLAT (+1.0%, interest 10.0/100)" in out
    assert "cleared the trend gate" in out


def test_explore_logs_niches_with_real_verdict(no_real_ledger):
    candidates, trend_results = _fake_explore_dependencies()
    with patch.object(cli, "expand_market", return_value=candidates), \
         patch.object(cli, "check_ideas", return_value=trend_results):
        rc = cli.main(["explore"])

    assert rc == 0
    no_real_ledger.assert_called_once()
    logged = no_real_ledger.call_args.args[0]
    assert all(e.station == "explore" for e in logged)
    by_subject = {e.subject: e for e in logged}
    assert by_subject["co-parenting"].verdict == "RISING"
    assert by_subject["blended families"].verdict == "FLAT"


def test_explore_csv_includes_rank_and_rationale(tmp_path):
    candidates, trend_results = _fake_explore_dependencies()
    csv_path = tmp_path / "niches.csv"
    with patch.object(cli, "expand_market", return_value=candidates), \
         patch.object(cli, "check_ideas", return_value=trend_results):
        rc = cli.main(["explore", "--csv", str(csv_path)])

    assert rc == 0
    content = csv_path.read_text()
    assert "rationale" in content
    lines = content.splitlines()
    assert lines[1].startswith("1,co-parenting")


def test_explore_auto_mine_chains_into_top_rising_niche():
    candidates, trend_results = _fake_explore_dependencies()
    research = ResearchResult(text="raw complaints", sources=["https://example.com"], search_count=2)
    pain_points = [
        PainPoint(
            category="hostile communication",
            search_term="co parenting app",
            description="desc",
            quotes=["q"],
            simplest_fix="fix",
            opportunity_score=7,
            buildability_score=8,
        )
    ]

    with patch.object(cli, "expand_market", return_value=candidates), \
         patch.object(cli, "check_ideas", return_value=trend_results), \
         patch.object(cli, "research_market", return_value=research) as mock_research, \
         patch.object(cli, "extract_pain_points", return_value=pain_points):
        rc = cli.main(["explore", "--auto-mine"])

    assert rc == 0
    # auto-mine should target the top RISING candidate, not the FLAT one
    assert mock_research.call_args.args[0] == "co-parenting"


def test_explore_auto_mine_skips_when_nothing_rising(capsys):
    candidates = [
        NicheCandidate(name="blended families", rationale="r", parent_category="relationships"),
    ]
    trend_results = [
        TrendResult(keyword="blended families", ok=True, current_interest=10.0, change_pct=1.0, verdict="FLAT"),
    ]
    with patch.object(cli, "expand_market", return_value=candidates), \
         patch.object(cli, "check_ideas", return_value=trend_results), \
         patch.object(cli, "research_market") as mock_research:
        rc = cli.main(["explore", "--auto-mine"])

    assert rc == 0
    mock_research.assert_not_called()
    assert "skipping --auto-mine" in capsys.readouterr().out
