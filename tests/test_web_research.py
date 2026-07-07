"""Tests for the web-search research step. The Anthropic client is mocked so
no real API call (and no real web search) happens."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app_guru import web_research
from app_guru.web_research import (
    ResearchResult,
    build_research_prompt,
    research_market,
)


def _block(**kwargs):
    return SimpleNamespace(**kwargs)


def _fake_response():
    """A response shaped like a web_search turn: a server_tool_use, a
    web_search_tool_result with two result URLs, and a final text block."""
    return SimpleNamespace(
        content=[
            _block(type="server_tool_use", name="web_search", input={"query": "co-parenting frustrated"}),
            _block(
                type="web_search_tool_result",
                content=[
                    _block(type="web_search_result", url="https://reddit.com/r/coparenting/a", title="a"),
                    _block(type="web_search_result", url="https://forum.example/b", title="b"),
                ],
            ),
            _block(type="text", text="Complaint 1 (r/coparenting): it's exhausting."),
        ]
    )


def test_build_research_prompt_includes_market_and_phrases():
    prompt = build_research_prompt("co-parenting", pain_phrases=["frustrated", "hate that"])
    assert "co-parenting" in prompt
    assert "frustrated" in prompt
    assert "hate that" in prompt


def test_build_research_prompt_mentions_subreddits():
    prompt = build_research_prompt("co-parenting", subreddits=["coparenting", "divorce"])
    assert "r/coparenting" in prompt
    assert "r/divorce" in prompt


def test_research_market_collects_text_sources_and_count():
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response()

    with patch.object(web_research.anthropic, "Anthropic", return_value=fake_client):
        result = research_market("co-parenting", api_key="sk-test")

    assert isinstance(result, ResearchResult)
    assert "it's exhausting" in result.text
    assert result.search_count == 1
    assert result.sources == ["https://reddit.com/r/coparenting/a", "https://forum.example/b"]
    assert not result.is_empty()


def test_research_market_passes_web_search_tool():
    fake_client = MagicMock()
    fake_client.messages.create.return_value = _fake_response()

    with patch.object(web_research.anthropic, "Anthropic", return_value=fake_client):
        research_market("co-parenting", api_key="sk-test", max_searches=7)

    kwargs = fake_client.messages.create.call_args.kwargs
    tools = kwargs["tools"]
    assert tools[0]["type"] == "web_search_20250305"
    assert tools[0]["max_uses"] == 7


def test_research_result_is_empty_on_blank_text():
    assert ResearchResult(text="   ").is_empty()
