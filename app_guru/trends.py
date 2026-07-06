"""
Google Trends signal for a candidate app idea / problem keyword.

Implements the validation rule from the sourcing framework:
    "Type it into Google search. Is it going up and to the right?
     If it is, that's a great sign."

Also used per the "Google Trends, plug in your core keyword ... if it's flat
or declining, skip it. If it's trending up, then it's worth exploring" step.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np
from pytrends.request import TrendReq

RISING_THRESHOLD = 8.0   # % growth (recent vs. older half of window) to call it RISING
DECLINING_THRESHOLD = -8.0  # % growth below this is DECLINING


@dataclass
class TrendResult:
    keyword: str
    ok: bool
    current_interest: float = 0.0
    change_pct: float = 0.0
    verdict: str = "UNKNOWN"
    rising_related: list[str] = field(default_factory=list)
    error: str | None = None


def _verdict_for(change_pct: float) -> str:
    if change_pct >= RISING_THRESHOLD:
        return "RISING"
    if change_pct <= DECLINING_THRESHOLD:
        return "DECLINING"
    return "FLAT"


def _slope_change_pct(values: list[float]) -> float:
    """
    Compare the mean of the second half of the window to the mean of the
    first half, expressed as a % change. Cheap and robust to weekly noise
    (more forgiving than a raw linear-regression slope on Trends' 0-100
    index, which spikes on single events).
    """
    n = len(values)
    if n < 4:
        return 0.0
    mid = n // 2
    first, second = values[:mid], values[mid:]
    first_mean = float(np.mean(first)) if first else 0.0
    second_mean = float(np.mean(second)) if second else 0.0
    if first_mean == 0:
        return 100.0 if second_mean > 0 else 0.0
    return ((second_mean - first_mean) / first_mean) * 100.0


def check_idea(
    keyword: str,
    pytrends: TrendReq,
    timeframe: str = "today 12-m",
    geo: str = "",
) -> TrendResult:
    """Fetch and score a single keyword. One network round-trip."""
    try:
        pytrends.build_payload([keyword], timeframe=timeframe, geo=geo)
        df = pytrends.interest_over_time()

        if df is None or df.empty or keyword not in df:
            return TrendResult(keyword=keyword, ok=False, error="no data returned")

        series = df[keyword].astype(float).tolist()
        current = float(np.mean(series[-4:])) if len(series) >= 4 else series[-1]
        change_pct = _slope_change_pct(series)

        rising_related: list[str] = []
        try:
            related = pytrends.related_queries()
            rising_df = related.get(keyword, {}).get("rising")
            if rising_df is not None and not rising_df.empty:
                rising_related = rising_df["query"].head(5).tolist()
        except Exception:
            pass  # related queries are a bonus signal, never fatal

        return TrendResult(
            keyword=keyword,
            ok=True,
            current_interest=round(current, 1),
            change_pct=round(change_pct, 1),
            verdict=_verdict_for(change_pct),
            rising_related=rising_related,
        )
    except Exception as exc:  # pytrends raises on 429 / malformed responses
        return TrendResult(keyword=keyword, ok=False, error=str(exc))


def check_ideas(
    keywords: list[str],
    timeframe: str = "today 12-m",
    geo: str = "",
    pause_seconds: float = 1.5,
    retries: int = 2,
) -> list[TrendResult]:
    """
    Score a batch of keywords, one request at a time, with a pause between
    calls and a couple of retries on failure. Google Trends' unofficial
    endpoint rate-limits aggressively when hit back-to-back.
    """
    pytrends = TrendReq(hl="en-US", tz=0)
    results: list[TrendResult] = []

    for i, keyword in enumerate(keywords):
        attempt = 0
        result = None
        while attempt <= retries:
            result = check_idea(keyword, pytrends, timeframe=timeframe, geo=geo)
            if result.ok:
                break
            attempt += 1
            if attempt <= retries:
                time.sleep(pause_seconds * (attempt + 1))
        results.append(result)

        if i < len(keywords) - 1:
            time.sleep(pause_seconds)

    return results
