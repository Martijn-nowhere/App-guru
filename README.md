# app-guru

Automated idea-search assistant. Two stations so far, both mirroring gates
from the idea-sourcing frameworks this repo is built around:

## `app-guru trends` — is anyone searching for this?

> "Type it into Google search. Is it going up and to the right? If it is,
> that's a great sign."

> "Google Trends, plug in your core keyword ... if it's flat or declining,
> skip it. If it's trending up, then it's worth exploring."

Scores a list of candidate problem/idea keywords against Google Trends and
tells you which ones are RISING, FLAT, or DECLINING, plus any related
queries that are themselves trending up (adjacent niches you didn't think
to check).

## `app-guru mine` — what are people actually complaining about?

From the "Gold Mining Framework": instead of the Reddit API, use a
Google-search query scoped to `reddit.com` (optionally to specific
subreddits) plus a disjunction of frustration phrases ("I wish it did",
"why can't it just", "so frustrating") to surface threads where people are
venting about a problem. Fetch each thread's post + top comments via
Reddit's public `.json` endpoint (no API credentials needed), then run the
combined text through Claude to extract categorized, quote-backed pain
points — the same "extract pain points and refine them, with categories
and quotes attached" step described in that framework.

Neither station replaces the rest of the sourcing framework — Product
Hunt, MicroAcquire/Flippa comps, App Store complaints, support-ticket
mining — they automate the cheapest, fastest filters so you stop spending
time on ideas nobody is searching for or complaining about.

## Install

```bash
pip install -r requirements.txt
```

or, for the `app-guru` command:

```bash
pip install -e .
```

## `trends` usage

```bash
# check a few ideas directly
app-guru trends "quit vaping" "ai sales rep" "prd maker"

# check a whole list (see ideas.example.txt for the format)
app-guru trends --file ideas.example.txt

# write the full report out for your monthly log
app-guru trends --file ideas.example.txt --csv report.csv

# restrict to one country, use a longer/shorter trend window
app-guru trends --file ideas.example.txt --geo US --timeframe "today 3-m"
```

Example output:

```
Checking 6 idea(s) against Google Trends (today 12-m, geo=worldwide)...

IDEA                          INTEREST  12M CHANGE  VERDICT   RISING RELATED
------------------------------------------------------------------------------
cancel subscription reminder      12.0      +42.0%  UP        subscription tracker app, ...
quit vaping                       31.0       +9.0%  UP        -
track macros                      54.0       +2.0%  FLAT      -
ai sales rep                      18.0       -3.0%  FLAT      -
prd maker                          2.0      -18.0%  DOWN      -
coding agent                      67.0     -11.0%  DOWN      -

-> 2 idea(s) cleared the trend gate. Next: run the landing-page test.
```

### Notes on the trends signal

- `INTEREST` is Google's 0-100 relative interest index, averaged over the
  most recent 4 weeks in the window — not absolute search volume.
- `12M CHANGE` compares the mean of the second half of the window to the
  first half. It's deliberately coarser than a raw regression slope so a
  single viral spike week doesn't flip the verdict.
- Thresholds: >= +8% is `RISING`, <= -8% is `DECLINING`, otherwise `FLAT`.
  Tune `RISING_THRESHOLD` / `DECLINING_THRESHOLD` in `app_guru/trends.py`
  if that's too strict or too loose for your niche.
- Google Trends' public endpoint is unofficial and rate-limits
  aggressively. `app-guru` pauses between requests and retries a couple of
  times; if you're still getting errors, raise `--pause` or run a smaller
  batch.
- A `RISING` verdict here is a green light to move to the next gate (the
  landing-page/waitlist test), not a green light to build. It only tells
  you the problem is a live, growing search behavior.

## `mine` usage

Requires two sets of credentials:

1. **Google Programmable Search** (free tier: 100 queries/day) — create a
   search engine at https://programmablesearchengine.google.com/ configured
   to search the entire web, plus a Google Cloud API key with the Custom
   Search API enabled. Set `GOOGLE_SEARCH_API_KEY` and `GOOGLE_SEARCH_CX`,
   or pass `--google-api-key` / `--google-cx`.
2. **`ANTHROPIC_API_KEY`** for the pain-point extraction step (standard
   Anthropic API key; the SDK reads it from the environment automatically).

```bash
export GOOGLE_SEARCH_API_KEY=...
export GOOGLE_SEARCH_CX=...
export ANTHROPIC_API_KEY=...

# search all of reddit.com for a market
app-guru mine "co-parenting"

# scope to specific subreddits, pull more threads
app-guru mine "co-parenting" \
  --subreddit coparenting --subreddit blendedfamilies \
  --max-threads 20

# write the full quote-backed report to CSV
app-guru mine "co-parenting" --csv pain_points.csv

# also check each pain-point category against Google Trends
app-guru mine "co-parenting" --check-trends
```

Example output:

```
Query: (site:reddit.com/r/coparenting) co-parenting ("I wish it did" OR "why can't it just" OR ...)
Searching for up to 10 Reddit thread(s)...
Found 8 thread(s). Fetching content...
Fetched 8 thread(s). Extracting pain points with claude-opus-4-8...

1. [hostile co-parent communication] Parents feel pressure to maintain a
   friendly relationship with an ex for the kids' sake, even when the ex
   is abusive or unreasonable.
     "it's hard to co-parent with your abuser"
     "why does everyone act like we HAVE to be friends now"

2. [scheduling conflicts] ...
```

With `--check-trends`, each pain-point category is also run through the
same Google Trends check as `app-guru trends`, so you get a combined
signal -- a real complaint *and* a rising search behavior -- without
retyping anything:

```
1. [hostile co-parent communication] Parents feel pressure to...
     "it's hard to co-parent with your abuser"
   Trend: UP (+14.0%)

2. [scheduling conflicts] ...
   Trend: FLAT (+2.0%)

-> 1 pain point(s) also cleared the trend gate. Those are the strongest bets.
```

### Notes on the mining pipeline

- The default frustration phrases are tuned for venting/complaint threads;
  override with `--pain-phrase` (repeatable) if your market talks about
  problems differently.
- `--max-threads` pages through Google's 10-results-per-request cap
  automatically.
- Read each thread before trusting the extraction — the LLM step merges
  duplicate complaints and only reports pain points with a supporting
  quote, but it can't tell you whether a thread is representative or a
  one-off rant.
- `--model` defaults to `claude-opus-4-8`; override for a cheaper/faster
  model if you're running this often.

## Roadmap

Planned next automated stations, matching the other hunting grounds from
the sourcing frameworks:

- [x] Google Trends validation
- [x] Reddit pain-point mining (via Google search + LLM extraction)
- [ ] Product Hunt top launches (official GraphQL API)
- [ ] App Store / Play Store critical-review scraping
- [ ] MicroAcquire / Flippa listing pull (comps under a revenue ceiling)

## License

MIT
