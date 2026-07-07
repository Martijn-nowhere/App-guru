"""
app-guru: a monthly idea-search assistant.

Three stations so far, run in the order the "Gold Mining Framework" video
actually describes it -- narrow to a market first, validate demand, then
mine that one market for pain points. It is NOT a market-agnostic "scan
everything, whatever's trending" tool; the source material is explicit
that narrowing first is what keeps the mined results specific and
buildable instead of generic internet noise:

  explore Market idea expansion -- the framework's own step one. Give it
          one broad area (health / wealth / relationships, or your own),
          and Claude proposes concrete, narrower candidate niches, which
          are then trend-checked so you see which ones have real, rising
          demand -- so you never have to invent a niche name yourself,
          but the search stays focused. `--auto-mine` chains straight
          into `mine` on the top RISING candidate.

  trends  Google Trends validation -- is anyone actually searching for this
          problem? ("If it's flat or declining, skip it. If it's trending
          up, then it's worth exploring.")

  mine    Pain-point mining -- Claude searches the open web (Reddit,
          forums, reviews) for real complaints about a market with its
          built-in web_search tool, then extracts categorized,
          quote-backed, SCORED app suggestions from them (opportunity +
          buildability), favoring boring single-feature ideas over
          ambitious ones. Only needs ANTHROPIC_API_KEY -- no Reddit app
          or Cloud billing.

Every run of any station appends to a shared, append-only history file
(app_guru/ledger.py) so results compound across months instead of living
only in a one-off CSV. `mine` entries never claim validated demand on
their own -- only `trends` and `explore` write a real verdict (both are
backed by actual Google Trends data); `mine` always logs verdict=None,
because a pain point is a lead to investigate, not proof.

Usage:
    app-guru explore
    app-guru explore "wealth" --auto-mine

    app-guru trends "quit vaping" "ai sales rep"
    app-guru trends --file ideas.txt

    app-guru mine "co-parenting" --subreddit coparenting --subreddit blendedfamilies
    app-guru mine "co-parenting" --check-trends
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

import anthropic

from app_guru.extract import PainPoint, extract_pain_points
from app_guru.ledger import LedgerEntry, append_to_ledger
from app_guru.market_expander import CORE_MARKETS, NicheCandidate, expand_market
from app_guru.trends import TrendResult, check_ideas
from app_guru.web_research import DEFAULT_PAIN_PHRASES, research_market

VERDICT_MARK = {
    "RISING": "UP",
    "FLAT": "FLAT",
    "DECLINING": "DOWN",
    "UNKNOWN": "N/A",
}


# ---------------------------------------------------------------------------
# trends
# ---------------------------------------------------------------------------

def load_keywords_from_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line and not line.startswith("#")]


def print_trends_report(results: list[TrendResult]) -> None:
    name_w = max(len(r.keyword) for r in results + [TrendResult(keyword="IDEA", ok=True)])
    header = f"{'IDEA':<{name_w}}  {'INTEREST':>8}  {'12M CHANGE':>10}  {'VERDICT':<8}  RISING RELATED"
    print(header)
    print("-" * len(header))

    ranked = sorted(
        results,
        key=lambda r: (r.verdict != "RISING", r.verdict == "DECLINING", -r.change_pct),
    )

    for r in ranked:
        if not r.ok:
            print(f"{r.keyword:<{name_w}}  {'--':>8}  {'--':>10}  {'ERROR':<8}  {r.error}")
            continue
        mark = VERDICT_MARK[r.verdict]
        related = ", ".join(r.rising_related) if r.rising_related else "-"
        print(
            f"{r.keyword:<{name_w}}  {r.current_interest:>8.1f}  {r.change_pct:>+9.1f}%  "
            f"{mark:<8}  {related}"
        )

    rising = [r for r in results if r.ok and r.verdict == "RISING"]
    if rising:
        print()
        print(f"-> {len(rising)} idea(s) cleared the trend gate. Next: run the landing-page test.")


def write_trends_csv(results: list[TrendResult], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["idea", "current_interest", "change_pct", "verdict", "rising_related", "error"])
        for r in results:
            writer.writerow(
                [
                    r.keyword,
                    r.current_interest if r.ok else "",
                    r.change_pct if r.ok else "",
                    r.verdict if r.ok else "ERROR",
                    "; ".join(r.rising_related),
                    r.error or "",
                ]
            )


def trends_ledger_entries(results: list[TrendResult]) -> list[LedgerEntry]:
    entries = []
    for r in results:
        entries.append(
            LedgerEntry(
                station="trends",
                subject=r.keyword,
                verdict=r.verdict if r.ok else None,
                data={
                    "current_interest": r.current_interest if r.ok else None,
                    "change_pct": r.change_pct if r.ok else None,
                    "rising_related": r.rising_related,
                    "error": r.error,
                },
            )
        )
    return entries


def cmd_trends(args: argparse.Namespace) -> int:
    keywords = list(args.keywords)
    if args.file:
        keywords += load_keywords_from_file(args.file)

    if not keywords:
        print("error: provide keywords as arguments or with --file", file=sys.stderr)
        return 2

    seen = set()
    deduped = []
    for k in keywords:
        if k.lower() not in seen:
            seen.add(k.lower())
            deduped.append(k)

    print(f"Checking {len(deduped)} idea(s) against Google Trends ({args.timeframe}, geo={args.geo or 'worldwide'})...")
    print()

    results = check_ideas(deduped, timeframe=args.timeframe, geo=args.geo, pause_seconds=args.pause)
    print_trends_report(results)
    append_to_ledger(trends_ledger_entries(results))

    if args.csv:
        write_trends_csv(results, args.csv)
        print(f"\nFull report written to {args.csv}")

    return 0


# ---------------------------------------------------------------------------
# mine
# ---------------------------------------------------------------------------

def rank_pain_points(pain_points: list[PainPoint]) -> list[PainPoint]:
    """Highest opportunity first; buildability breaks ties. Deliberately no
    combined formula -- opportunity (is this real) and buildability (is
    this easy) answer different questions and are shown separately."""
    return sorted(pain_points, key=lambda p: (-p.opportunity_score, -p.buildability_score))


def print_pain_report(
    pain_points: list[PainPoint],
    trend_by_term: dict[str, TrendResult] | None = None,
) -> None:
    if not pain_points:
        print("No pain points extracted.")
        return

    ranked = rank_pain_points(pain_points)

    for i, p in enumerate(ranked, start=1):
        print(f"#{i}  [{p.category}]  Opportunity {p.opportunity_score}/10 * Buildability {p.buildability_score}/10")
        print(f"    App idea: {p.simplest_fix}")
        print(f"    Pain: {p.description}")
        for q in p.quotes[:3]:
            snippet = q if len(q) <= 140 else q[:137] + "..."
            print(f'      "{snippet}"')
        if len(p.quotes) > 3:
            print(f"      ...and {len(p.quotes) - 3} more quote(s)")
        if trend_by_term is not None:
            t = trend_by_term.get(p.search_term)
            if t is None or not t.ok:
                print(f'    Trend for "{p.search_term}": N/A ({t.error if t else "not checked"})')
            else:
                mark = VERDICT_MARK[t.verdict]
                print(f'    Trend for "{p.search_term}": {mark} ({t.change_pct:+.1f}%)')
        print()

    if trend_by_term is not None:
        rising = [
            p for p in ranked
            if (t := trend_by_term.get(p.search_term)) and t.ok and t.verdict == "RISING"
        ]
        if rising:
            print(f"-> {len(rising)} suggestion(s) also cleared the trend gate. Those are the strongest bets.")
    print(
        "Reminder: opportunity/buildability are the model's read of the evidence, not proof of "
        "demand. Only a RISING trends verdict (or real landing-page signups) counts as validated."
    )


def write_pain_csv(
    pain_points: list[PainPoint],
    path: str,
    trend_by_term: dict[str, TrendResult] | None = None,
) -> None:
    ranked = rank_pain_points(pain_points)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = [
            "rank", "category", "app_idea", "pain_point", "quotes",
            "opportunity_score", "buildability_score", "search_term",
        ]
        if trend_by_term is not None:
            header += ["trend_verdict", "trend_change_pct"]
        writer.writerow(header)
        for i, p in enumerate(ranked, start=1):
            row = [
                i, p.category, p.simplest_fix, p.description, " | ".join(p.quotes),
                p.opportunity_score, p.buildability_score, p.search_term,
            ]
            if trend_by_term is not None:
                t = trend_by_term.get(p.search_term)
                row += [t.verdict if t and t.ok else "N/A", t.change_pct if t and t.ok else ""]
            writer.writerow(row)


def pain_point_ledger_entries(
    pain_points: list[PainPoint],
    market: str,
    trend_by_term: dict[str, TrendResult] | None = None,
) -> list[LedgerEntry]:
    entries = []
    for p in pain_points:
        t = trend_by_term.get(p.search_term) if trend_by_term else None
        entries.append(
            LedgerEntry(
                station="mine",
                subject=p.category,
                verdict=None,  # mine never claims validated demand on its own
                data={
                    "market": market,
                    "pain_point": p.description,
                    "quotes": p.quotes,
                    "simplest_fix": p.simplest_fix,
                    "opportunity_score": p.opportunity_score,
                    "buildability_score": p.buildability_score,
                    "search_term": p.search_term,
                    "trend_check": (
                        {"verdict": t.verdict if t.ok else "N/A", "change_pct": t.change_pct if t.ok else None}
                        if t is not None else None
                    ),
                },
            )
        )
    return entries


def run_mine(
    market: str,
    subreddits: list[str] | None = None,
    pain_phrases: list[str] | None = None,
    max_searches: int = 5,
    model: str = "claude-opus-4-8",
    check_trends: bool = False,
    trends_timeframe: str = "today 12-m",
    trends_geo: str = "",
    trends_pause: float = 1.5,
    csv_path: str | None = None,
) -> int:
    """The actual `mine` pipeline, factored out of cmd_mine so `explore
    --auto-mine` can chain straight into it without going through argparse."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "error: ANTHROPIC_API_KEY required.\n"
            "  Get one at https://console.anthropic.com/settings/keys and set it in\n"
            "  your .env (ANTHROPIC_API_KEY=...). It's the only key `mine` needs.",
            file=sys.stderr,
        )
        return 2

    pain_phrases = pain_phrases if pain_phrases else DEFAULT_PAIN_PHRASES

    print(f"Searching the web for real complaints about '{market}' (up to {max_searches} searches)...")
    try:
        research = research_market(
            market,
            subreddits=subreddits,
            pain_phrases=pain_phrases,
            model=model,
            max_searches=max_searches,
        )
    except anthropic.APIError as exc:
        print(f"error: web-search research failed: {exc}", file=sys.stderr)
        return 1

    if research.is_empty():
        print("The web search turned up no usable complaints. Try a broader market or different pain phrases.")
        return 0

    if research.sources:
        print(f"Ran {research.search_count} search(es) across {len(research.sources)} source(s).")

    print(f"Extracting scored app suggestions with {model}...")
    pain_points = extract_pain_points(research.text, model=model)

    trend_by_term = None
    if check_trends and pain_points:
        # Trend-check the model's real-world search terms (e.g. "co parenting
        # app"), not the category labels (e.g. "unreliable notifications")
        # which nobody Googles. Dedupe so shared terms cost one request.
        terms = list(dict.fromkeys(p.search_term for p in pain_points if p.search_term))
        print(f"Checking {len(terms)} search term(s) against Google Trends...")
        trend_results = check_ideas(
            terms,
            timeframe=trends_timeframe,
            geo=trends_geo,
            pause_seconds=trends_pause,
            fetch_related=False,  # mine's report never shows rising_related; skip the extra request
        )
        trend_by_term = {r.keyword: r for r in trend_results}

    print()
    print_pain_report(pain_points, trend_by_term=trend_by_term)
    append_to_ledger(pain_point_ledger_entries(pain_points, market, trend_by_term))

    if csv_path:
        write_pain_csv(pain_points, csv_path, trend_by_term=trend_by_term)
        print(f"Full report written to {csv_path}")

    return 0


def cmd_mine(args: argparse.Namespace) -> int:
    return run_mine(
        args.market,
        subreddits=args.subreddit or None,
        pain_phrases=args.pain_phrase,
        max_searches=args.max_searches,
        model=args.model,
        check_trends=args.check_trends,
        trends_timeframe=args.trends_timeframe,
        trends_geo=args.trends_geo,
        trends_pause=args.trends_pause,
        csv_path=args.csv,
    )


# ---------------------------------------------------------------------------
# explore
# ---------------------------------------------------------------------------

def rank_niches(candidates: list[NicheCandidate], trend_by_name: dict[str, TrendResult]) -> list[NicheCandidate]:
    """RISING first (highest change first), then FLAT/DECLINING, then
    anything Trends couldn't score at all -- same ordering as `trends`."""
    def sort_key(c: NicheCandidate):
        t = trend_by_name.get(c.name)
        if t is None or not t.ok:
            return (2, 0, 0.0)
        return (0 if t.verdict == "RISING" else 1, 1 if t.verdict == "DECLINING" else 0, -t.change_pct)

    return sorted(candidates, key=sort_key)


def print_niche_report(candidates: list[NicheCandidate], trend_by_name: dict[str, TrendResult]) -> None:
    if not candidates:
        print("No candidate niches generated.")
        return

    ranked = rank_niches(candidates, trend_by_name)

    for i, c in enumerate(ranked, start=1):
        t = trend_by_name.get(c.name)
        if t is None or not t.ok:
            trend_str = f"N/A ({t.error if t else 'not checked'})"
        else:
            # show absolute interest alongside the % change -- a big swing
            # off a tiny base (e.g. interest 2 -> 30) is easy to mistake for
            # a real breakout otherwise.
            trend_str = f"{VERDICT_MARK[t.verdict]} ({t.change_pct:+.1f}%, interest {t.current_interest:.1f}/100)"
        print(f'#{i}  {c.name}  [{c.parent_category}]  {trend_str}')
        print(f"    {c.rationale}")
        print()

    rising = [c for c in ranked if (t := trend_by_name.get(c.name)) and t.ok and t.verdict == "RISING"]
    if rising:
        print(
            f'-> {len(rising)} niche(s) cleared the trend gate. Best bet: '
            f'app-guru mine "{rising[0].name}" --check-trends'
        )


def write_niche_csv(
    candidates: list[NicheCandidate],
    path: str,
    trend_by_name: dict[str, TrendResult],
) -> None:
    ranked = rank_niches(candidates, trend_by_name)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "niche", "parent_category", "rationale", "trend_verdict", "trend_change_pct"])
        for i, c in enumerate(ranked, start=1):
            t = trend_by_name.get(c.name)
            writer.writerow(
                [
                    i, c.name, c.parent_category, c.rationale,
                    t.verdict if t and t.ok else "N/A",
                    t.change_pct if t and t.ok else "",
                ]
            )


def niche_ledger_entries(
    candidates: list[NicheCandidate],
    trend_by_name: dict[str, TrendResult],
) -> list[LedgerEntry]:
    entries = []
    for c in candidates:
        t = trend_by_name.get(c.name)
        entries.append(
            LedgerEntry(
                station="explore",
                subject=c.name,
                verdict=t.verdict if t and t.ok else None,  # real Trends data, same as `trends`
                data={
                    "parent_category": c.parent_category,
                    "rationale": c.rationale,
                    "current_interest": t.current_interest if t and t.ok else None,
                    "change_pct": t.change_pct if t and t.ok else None,
                    "error": t.error if t and not t.ok else None,
                },
            )
        )
    return entries


def cmd_explore(args: argparse.Namespace) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "error: ANTHROPIC_API_KEY required.\n"
            "  Get one at https://console.anthropic.com/settings/keys and set it in\n"
            "  your .env (ANTHROPIC_API_KEY=...).",
            file=sys.stderr,
        )
        return 2

    categories = [args.category] if args.category else CORE_MARKETS
    print(f"Expanding {', '.join(categories)} into candidate niches with {args.model}...")
    try:
        candidates = expand_market(categories, model=args.model, count_per_category=args.count)
    except anthropic.APIError as exc:
        print(f"error: market expansion failed: {exc}", file=sys.stderr)
        return 1

    if not candidates:
        print("No candidate niches generated.")
        return 0

    # categories can overlap (e.g. two broad areas both propose the same
    # niche) -- dedupe by name, keeping the first rationale seen.
    deduped: dict[str, NicheCandidate] = {}
    for c in candidates:
        deduped.setdefault(c.name, c)
    candidates = list(deduped.values())

    names = [c.name for c in candidates]
    print(f"Checking {len(names)} candidate niche(s) against Google Trends...")
    trend_results = check_ideas(
        names, timeframe=args.timeframe, geo=args.geo, pause_seconds=args.pause, fetch_related=False
    )
    trend_by_name = {r.keyword: r for r in trend_results}

    print()
    print_niche_report(candidates, trend_by_name)
    append_to_ledger(niche_ledger_entries(candidates, trend_by_name))

    if args.csv:
        write_niche_csv(candidates, args.csv, trend_by_name)
        print(f"Full report written to {args.csv}")

    if args.auto_mine:
        ranked = rank_niches(candidates, trend_by_name)
        rising = [c for c in ranked if (t := trend_by_name.get(c.name)) and t.ok and t.verdict == "RISING"]
        if not rising:
            print("\nNo niche cleared the trend gate -- skipping --auto-mine. Try a different category.")
            return 0
        top = rising[0]
        print(f'\n--auto-mine: mining the top candidate, "{top.name}"...\n')
        return run_mine(top.name, model=args.model, check_trends=True, csv_path=args.mine_csv)

    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="app-guru", description="Automated idea-search assistant.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    trends = subparsers.add_parser("trends", help="check candidate ideas against Google Trends")
    trends.add_argument("keywords", nargs="*", help="idea/problem keywords to check")
    trends.add_argument("--file", "-f", help="path to a text file of keywords, one per line")
    trends.add_argument("--geo", default="", help="two-letter country code, e.g. US (default: worldwide)")
    trends.add_argument("--timeframe", default="today 12-m", help="pytrends timeframe string")
    trends.add_argument("--csv", help="write the full report to this CSV path")
    trends.add_argument("--pause", type=float, default=1.5, help="seconds between requests")
    trends.set_defaults(func=cmd_trends)

    mine = subparsers.add_parser("mine", help="search the web for scored app-idea suggestions")
    mine.add_argument("market", help="the market/problem to search for, e.g. 'co-parenting'")
    mine.add_argument(
        "--subreddit",
        action="append",
        help="nudge the search toward this subreddit (repeatable); omit to search the open web",
    )
    mine.add_argument(
        "--pain-phrase",
        action="append",
        help="override the default frustration phrases used in the search (repeatable)",
    )
    mine.add_argument("--max-searches", type=int, default=5, help="max web searches Claude may run (default: 5)")
    mine.add_argument("--model", default="claude-opus-4-8", help="Claude model for research + extraction")
    mine.add_argument("--csv", help="write the full report to this CSV path")
    mine.add_argument(
        "--check-trends",
        action="store_true",
        help="after extraction, check each pain-point category against Google Trends",
    )
    mine.add_argument("--trends-geo", default="", help="geo filter for --check-trends (default: worldwide)")
    mine.add_argument("--trends-timeframe", default="today 12-m", help="timeframe for --check-trends")
    mine.add_argument("--trends-pause", type=float, default=1.5, help="seconds between Trends requests")
    mine.set_defaults(func=cmd_mine)

    explore = subparsers.add_parser(
        "explore", help="expand a broad category into candidate niches, ranked by real trend data"
    )
    explore.add_argument(
        "category",
        nargs="?",
        help="broad area to expand, e.g. 'health', 'wealth', 'relationships' (default: expand all three)",
    )
    explore.add_argument("--count", type=int, default=8, help="candidate niches to propose per category (default: 8)")
    explore.add_argument("--model", default="claude-opus-4-8", help="Claude model for expansion (and --auto-mine)")
    explore.add_argument("--csv", help="write the full niche report to this CSV path")
    explore.add_argument("--geo", default="", help="two-letter country code, e.g. US (default: worldwide)")
    explore.add_argument("--timeframe", default="today 12-m", help="pytrends timeframe string")
    explore.add_argument("--pause", type=float, default=1.5, help="seconds between Trends requests")
    explore.add_argument(
        "--auto-mine",
        action="store_true",
        help="automatically run `mine --check-trends` on the top RISING niche",
    )
    explore.add_argument("--mine-csv", help="if --auto-mine, write mine's report to this CSV path")
    explore.set_defaults(func=cmd_explore)

    return parser


def load_env() -> None:
    """Load a .env file (ANTHROPIC_API_KEY) if one is present, so the key
    doesn't have to be exported by hand every session. Real environment
    variables always win over the .env file. No-op if python-dotenv isn't
    installed."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    # usecwd=True so we find a .env in the directory the user runs from
    # (and its parents), not next to this package file.
    load_dotenv(find_dotenv(usecwd=True), override=False)


def main(argv: list[str] | None = None) -> int:
    load_env()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
