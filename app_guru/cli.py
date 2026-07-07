"""
app-guru: a monthly idea-search assistant.

Two stations so far:

  trends  Google Trends validation -- is anyone actually searching for this
          problem? ("If it's flat or declining, skip it. If it's trending
          up, then it's worth exploring.")

  mine    Reddit pain-point mining -- find real complaint threads about a
          market via Google search, then have Claude extract categorized,
          quote-backed, SCORED app suggestions from them (opportunity +
          buildability), favoring boring single-feature ideas over
          ambitious ones. Mirrors the "Gold Mining Framework".

Every run of either station appends to a shared, append-only history file
(app_guru/ledger.py) so results compound across months instead of living
only in a one-off CSV. `mine` entries never claim validated demand on
their own -- only `trends` writes a real verdict; `mine` always logs
verdict=None, because a pain point is a lead to investigate, not proof.

Usage:
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

from app_guru.extract import PainPoint, extract_pain_points, join_threads
from app_guru.ledger import LedgerEntry, append_to_ledger
from app_guru.reddit_fetch import fetch_threads
from app_guru.search import DEFAULT_PAIN_PHRASES, build_reddit_query, search_reddit_threads_paged
from app_guru.trends import TrendResult, check_ideas

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
    trend_by_category: dict[str, TrendResult] | None = None,
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
        if trend_by_category is not None:
            t = trend_by_category.get(p.category)
            if t is None or not t.ok:
                print(f"    Trend: N/A ({t.error if t else 'not checked'})")
            else:
                mark = VERDICT_MARK[t.verdict]
                print(f"    Trend: {mark} ({t.change_pct:+.1f}%)")
        print()

    if trend_by_category is not None:
        rising = [
            p for p in ranked
            if (t := trend_by_category.get(p.category)) and t.ok and t.verdict == "RISING"
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
    trend_by_category: dict[str, TrendResult] | None = None,
) -> None:
    ranked = rank_pain_points(pain_points)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = [
            "rank", "category", "app_idea", "pain_point", "quotes",
            "opportunity_score", "buildability_score",
        ]
        if trend_by_category is not None:
            header += ["trend_verdict", "trend_change_pct"]
        writer.writerow(header)
        for i, p in enumerate(ranked, start=1):
            row = [
                i, p.category, p.simplest_fix, p.description, " | ".join(p.quotes),
                p.opportunity_score, p.buildability_score,
            ]
            if trend_by_category is not None:
                t = trend_by_category.get(p.category)
                row += [t.verdict if t and t.ok else "ERROR", t.change_pct if t and t.ok else ""]
            writer.writerow(row)


def pain_point_ledger_entries(
    pain_points: list[PainPoint],
    market: str,
    trend_by_category: dict[str, TrendResult] | None = None,
) -> list[LedgerEntry]:
    entries = []
    for p in pain_points:
        t = trend_by_category.get(p.category) if trend_by_category else None
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
                    "trend_check": (
                        {"verdict": t.verdict if t.ok else "ERROR", "change_pct": t.change_pct if t.ok else None}
                        if t is not None else None
                    ),
                },
            )
        )
    return entries


def cmd_mine(args: argparse.Namespace) -> int:
    google_api_key = args.google_api_key or os.environ.get("GOOGLE_SEARCH_API_KEY")
    google_cx = args.google_cx or os.environ.get("GOOGLE_SEARCH_CX")

    if not google_api_key or not google_cx:
        print(
            "error: Google Programmable Search credentials required.\n"
            "  Pass --google-api-key/--google-cx, or set GOOGLE_SEARCH_API_KEY / GOOGLE_SEARCH_CX.\n"
            "  Create an engine at https://programmablesearchengine.google.com/ with reddit.com\n"
            "  as the site to search (mine only searches Reddit), then add a Google Cloud API key\n"
            "  with the Custom Search API enabled.",
            file=sys.stderr,
        )
        return 2

    pain_phrases = args.pain_phrase if args.pain_phrase else DEFAULT_PAIN_PHRASES
    query = build_reddit_query(args.market, subreddits=args.subreddit or None, pain_phrases=pain_phrases)
    print(f"Query: {query}")

    print(f"Searching for up to {args.max_threads} Reddit thread(s)...")
    search_results = search_reddit_threads_paged(query, google_api_key, google_cx, total=args.max_threads)
    if not search_results:
        print("No Reddit threads found for this query. Try different subreddits or pain phrases.")
        return 0

    print(f"Found {len(search_results)} thread(s). Fetching content...")
    threads, fetch_errors = fetch_threads(
        [r.url for r in search_results], max_comments=args.max_comments
    )
    for url, error in fetch_errors:
        print(f"  warning: could not fetch {url}: {error}", file=sys.stderr)

    if not threads:
        print("Could not fetch any thread content.", file=sys.stderr)
        return 1

    print(f"Fetched {len(threads)} thread(s). Extracting scored app suggestions with {args.model}...")
    joined = join_threads([t.as_text_block() for t in threads])
    pain_points = extract_pain_points(joined, model=args.model)

    trend_by_category = None
    if args.check_trends and pain_points:
        categories = [p.category for p in pain_points]
        print(f"Checking {len(categories)} pain-point categor{'y' if len(categories) == 1 else 'ies'} against Google Trends...")
        trend_results = check_ideas(
            categories, timeframe=args.trends_timeframe, geo=args.trends_geo, pause_seconds=args.trends_pause
        )
        trend_by_category = {r.keyword: r for r in trend_results}

    print()
    print_pain_report(pain_points, trend_by_category=trend_by_category)
    append_to_ledger(pain_point_ledger_entries(pain_points, args.market, trend_by_category))

    if args.csv:
        write_pain_csv(pain_points, args.csv, trend_by_category=trend_by_category)
        print(f"Full report written to {args.csv}")

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

    mine = subparsers.add_parser("mine", help="mine Reddit for scored app-idea suggestions")
    mine.add_argument("market", help="the market/problem to search for, e.g. 'co-parenting'")
    mine.add_argument(
        "--subreddit",
        action="append",
        help="restrict search to this subreddit (repeatable); omit to search all of reddit.com",
    )
    mine.add_argument(
        "--pain-phrase",
        action="append",
        help="override the default frustration phrases used in the query (repeatable)",
    )
    mine.add_argument("--max-threads", type=int, default=10, help="max Reddit threads to fetch (default: 10)")
    mine.add_argument("--max-comments", type=int, default=15, help="max comments to pull per thread (default: 15)")
    mine.add_argument("--google-api-key", help="Google Cloud API key (or set GOOGLE_SEARCH_API_KEY)")
    mine.add_argument("--google-cx", help="Programmable Search Engine ID (or set GOOGLE_SEARCH_CX)")
    mine.add_argument("--model", default="claude-opus-4-8", help="Claude model for pain-point extraction")
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

    return parser


def load_env() -> None:
    """Load a .env file (ANTHROPIC_API_KEY, GOOGLE_SEARCH_API_KEY,
    GOOGLE_SEARCH_CX) if one is present, so keys don't have to be exported
    by hand every session. Real environment variables always win over the
    .env file. No-op if python-dotenv isn't installed."""
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
