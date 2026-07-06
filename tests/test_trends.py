"""
Unit tests for the scoring logic in app_guru.trends, using fake pytrends
data. These don't touch the network -- they exist because this repo's dev
sandbox has Google Trends blocked at the egress-policy level, so the only
way to validate the scoring math here is against synthetic series.
"""

import pandas as pd
import pytest

from app_guru.trends import TrendResult, _slope_change_pct, _verdict_for, check_idea


class FakePytrends:
    def __init__(self, series):
        self._series = series
        self.built = None

    def build_payload(self, keywords, timeframe=None, geo=None):
        self.built = (keywords, timeframe, geo)

    def interest_over_time(self):
        keyword = self.built[0][0]
        return pd.DataFrame({keyword: self._series})

    def related_queries(self):
        keyword = self.built[0][0]
        rising = pd.DataFrame({"query": ["adjacent idea one", "adjacent idea two"], "value": [500, 200]})
        return {keyword: {"top": None, "rising": rising}}


def test_slope_change_pct_rising():
    values = [10, 12, 11, 13, 30, 32, 31, 34]
    assert _slope_change_pct(values) > 100  # second half roughly triples the first


def test_slope_change_pct_declining():
    values = [40, 42, 41, 39, 10, 9, 11, 8]
    assert _slope_change_pct(values) < -50


def test_slope_change_pct_flat():
    values = [20, 21, 19, 20, 21, 20, 19, 20]
    assert abs(_slope_change_pct(values)) < 8


def test_verdict_thresholds():
    assert _verdict_for(9.0) == "RISING"
    assert _verdict_for(-9.0) == "DECLINING"
    assert _verdict_for(0.0) == "FLAT"
    assert _verdict_for(8.0) == "RISING"  # boundary is inclusive


def test_check_idea_rising_with_related_queries():
    series = [5, 5, 6, 5, 20, 22, 21, 23]  # clear upward step
    fake = FakePytrends(series)

    result = check_idea("cancel subscription reminder", fake)

    assert result.ok
    assert result.keyword == "cancel subscription reminder"
    assert result.verdict == "RISING"
    assert result.rising_related == ["adjacent idea one", "adjacent idea two"]
    assert result.current_interest == pytest.approx(sum(series[-4:]) / 4, abs=0.1)


def test_check_idea_handles_empty_dataframe():
    class EmptyPytrends:
        def build_payload(self, *a, **k):
            pass

        def interest_over_time(self):
            return pd.DataFrame()

    result = check_idea("no data idea", EmptyPytrends())
    assert not result.ok
    assert result.error == "no data returned"


def test_check_idea_handles_exception():
    class BoomPytrends:
        def build_payload(self, *a, **k):
            raise RuntimeError("429 Too Many Requests")

    result = check_idea("rate limited idea", BoomPytrends())
    assert not result.ok
    assert "429" in result.error
