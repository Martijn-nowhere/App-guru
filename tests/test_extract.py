"""Unit tests for app_guru.extract, mocking the Anthropic client (api.anthropic.com
is reachable from this sandbox, but we don't want real API calls/costs in unit
tests)."""

import json
from unittest.mock import MagicMock, patch

from app_guru.extract import extract_pain_points, join_threads


def _fake_anthropic_response(pain_points):
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps({"pain_points": pain_points})

    response = MagicMock()
    response.content = [block]
    return response


def test_join_threads_uses_separator():
    joined = join_threads(["thread one", "thread two"])
    assert joined == "thread one\n\n--- NEXT THREAD ---\n\nthread two"


def test_extract_pain_points_parses_structured_response():
    fake_data = [
        {
            "category": "co-parenting with an abuser",
            "pain_point": "Parents feel unsafe negotiating with an abusive ex.",
            "quotes": ["it's hard to co-parent with your abuser"],
        }
    ]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = _fake_anthropic_response(fake_data)

    with patch("app_guru.extract.anthropic.Anthropic", return_value=mock_client) as mock_anthropic:
        result = extract_pain_points("some thread text", model="claude-opus-4-8")

    mock_anthropic.assert_called_once_with(api_key=None)
    assert len(result) == 1
    assert result[0].category == "co-parenting with an abuser"
    assert result[0].quotes == ["it's hard to co-parent with your abuser"]

    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4-8"
    assert call_kwargs["output_config"]["format"]["type"] == "json_schema"
    assert call_kwargs["messages"][0]["content"] == "some thread text"


def test_extract_pain_points_empty_list():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _fake_anthropic_response([])

    with patch("app_guru.extract.anthropic.Anthropic", return_value=mock_client):
        result = extract_pain_points("nothing interesting here")

    assert result == []
