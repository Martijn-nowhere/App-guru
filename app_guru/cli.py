"""
app-guru: a monthly idea-search assistant.

First automated station: Google Trends validation. Point it at a list of
candidate "problem" keywords (the kind of phrase someone would actually type
into Google when they're stuck: "quit vaping", "track macros", "cancel
subscription reminder") and it tells you which ones are trending up, flat,
or declining -- the same gate described in the sourcing framework this repo
is built around:

    "If it's flat or declining, skip it. If it's trending up, then it's
     worth exploring."

Usage:
    app-guru "quit vaping" "ai sales rep"
    app-guru --file ideas.txt
    app-guru --file ideas.txt --csv report.csv
"""

from __future__ import annotations

import argparse
import csv
import sys

from app_guru.trends import TrendResult, check_ideas

VERDICT_MARK = {
    "RISING": "UP",
    "FLAT": "FLAT",
    "DECLINING": "DOWN",
    "UNKNOWN": "N/A",
}


def load_keywords_from_file(path: str) -> list[str]:
    with open(path, encoding="utf-8") as f:
        lines = [line.strip() for line in f]
    return [line for line in lines if line and not line.startswith("#")]


def print_report(results: list[TrendResult]) -> None:
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


def write_csv(results: list[TrendResult], path: str) -> None:
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app-guru",
        description="Check whether candidate app ideas are trending on Google Trends.",
    )
    parser.add_argument("keywords", nargs="*", help="idea/problem keywords to check")
    parser.add_argument("--file", "-f", help="path to a text file of keywords, one per line")
    parser.add_argument("--geo", default="", help="two-letter country code, e.g. US (default: worldwide)")
    parser.add_argument(
        "--timeframe",
        default="today 12-m",
        help="pytrends timeframe string (default: 'today 12-m')",
    )
    parser.add_argument("--csv", help="write the full report to this CSV path")
    parser.add_argument(
        "--pause",
        type=float,
        default=1.5,
        help="seconds to wait between requests, raise this if you hit rate limits (default: 1.5)",
    )
    args = parser.parse_args(argv)

    keywords = list(args.keywords)
    if args.file:
        keywords += load_keywords_from_file(args.file)

    if not keywords:
        parser.error("provide keywords as arguments or with --file")

    seen = set()
    deduped = []
    for k in keywords:
        if k.lower() not in seen:
            seen.add(k.lower())
            deduped.append(k)

    print(f"Checking {len(deduped)} idea(s) against Google Trends ({args.timeframe}, geo={args.geo or 'worldwide'})...")
    print()

    results = check_ideas(deduped, timeframe=args.timeframe, geo=args.geo, pause_seconds=args.pause)
    print_report(results)

    if args.csv:
        write_csv(results, args.csv)
        print(f"\nFull report written to {args.csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
