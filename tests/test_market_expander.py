"""Tests for market-idea expansion, mocking the Anthropic client (same
pattern as test_extract.py -- no real API calls in unit tests)."""

import json
from unittest.mock import MagicMock, patch

from app_guru.market_expander import CORE_MARKETS, expand_market


def _fake_response(niches):
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps({"niches": niches})
    response = MagicMock()
    response.content = [block]
    return response


def test_core_markets_are_the_frameworks_three():
    assert CORE_MARKETS == ["health", "wealth", "relationships"]


def test_expand_market_parses_structured_response():
    fake_niches = [
        {"name": "co-parenting", "rationale": "recurring conflict and demonstrated app spend"},
        {"name": "freelance invoicing", "rationale": "real recurring pain, people already pay for tools"},
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _fake_response(fake_niches)

    with patch("app_guru.market_expander.anthropic.Anthropic", return_value=mock_client) as mock_anthropic:
        result = expand_market(["relationships"], model="claude-opus-4-8")

    mock_anthropic.assert_called_once_with(api_key=None)
    assert len(result) == 2
    assert result[0].name == "co-parenting"
    assert result[0].parent_category == "relationships"
    assert result[1].name == "freelance invoicing"

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-8"
    assert call_kwargs["output_config"]["format"]["type"] == "json_schema"
    assert "relationships" in call_kwargs["messages"][0]["content"]


def test_expand_market_calls_once_per_category():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _fake_response(
        [{"name": "niche a", "rationale": "r"}]
    )

    with patch("app_guru.market_expander.anthropic.Anthropic", return_value=mock_client):
        result = expand_market(["health", "wealth"], count_per_category=3)

    assert mock_client.messages.create.call_count == 2
    assert {c.parent_category for c in result} == {"health", "wealth"}


def test_expand_market_empty_niches():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _fake_response([])

    with patch("app_guru.market_expander.anthropic.Anthropic", return_value=mock_client):
        result = expand_market(["wealth"])

    assert result == []
