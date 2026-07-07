# app-guru

Automated idea-search assistant. Two stations so far, both mirroring gates
from the idea-sourcing frameworks this repo is built around, plus a shared
history file so results compound across months instead of disappearing
into one-off reports.

## `app-guru trends` — is anyone searching for this?

> "Type it into Google search. Is it going up and to the right? If it is,
> that's a great sign."

> "Google Trends, plug in your core keyword ... if it's flat or declining,
> skip it. If it's trending up, then it's worth exploring."

Scores a list of candidate problem/idea keywords against Google Trends and
tells you which ones are RISING, FLAT, or DECLINING, plus any related
queries that are themselves trending up (adjacent niches you didn't think
to check).

## `app-guru mine` — scored app-idea suggestions from real complaints

From the "Gold Mining Framework": search Reddit for threads where people
are venting about a problem, then have Claude turn those complaints into
scored app ideas. It uses **Reddit's own free search** (`reddit.com/
search.json`, optionally per-subreddit) with a disjunction of frustration
phrases ("I wish it did", "why can't it just", "so frustrating") to bias
toward complaint threads — no Google, no API key, no billing, nothing to
set up. It fetches each thread's post + top comments via Reddit's public
`.json` endpoint, then runs the combined text through Claude to extract
**scored app-idea suggestions**: a category, the pain point, supporting
quotes, the simplest possible single-feature fix, an **opportunity score**
(how painful/common the complaint looks), and a **buildability score**
(how simple that fix would be to actually build). It deliberately favors
boring, narrow, single-feature ideas over ambitious ones — per the
sourcing videos, the apps that print money are usually the simplest ones
solving one real problem well (a puff counter, a QR reader), not the most
impressive.

The only thing `mine` needs is your `ANTHROPIC_API_KEY` (for the Claude
extraction step). `trends` needs nothing at all.

### On the other "proven tools" from the sourcing videos

Reddit and Google Trends are the two sources here because they're the two
that are genuinely, reliably automatable for free. The others mentioned in
the source material aren't (yet), and it's worth being honest about why
rather than faking coverage:

- **Product Hunt** has an official free GraphQL API — this is the next
  realistic station to add (see Roadmap).
- **MicroAcquire, Flippa, TrustMRR, Sensor Tower** have no free public
  API. They're either paywalled enterprise tools or marketplaces you'd
  have to scrape — fragile, and often against their terms of service.
  These stay manual steps for now.

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

The only credential `mine` needs is your **`ANTHROPIC_API_KEY`** (for the
Claude extraction step). No Google, no search-engine setup, no billing —
the search runs against Reddit's own free endpoint.

Easiest way to set the key: copy `.env.example` to `.env`, paste your
Anthropic key in, and `app-guru` loads it automatically every run.
`.env` is gitignored, so your key is never committed.

```bash
cp .env.example .env
# then edit .env and paste your ANTHROPIC_API_KEY in
```

Or set it as an environment variable:

```bash
export ANTHROPIC_API_KEY=...
```

Then run:

```bash
# search all of reddit.com for a market
app-guru mine "co-parenting"

# scope to specific subreddits, pull more threads
app-guru mine "co-parenting" \
  --subreddit coparenting --subreddit blendedfamilies \
  --max-threads 20

# write the full quote-backed report to CSV
app-guru mine "co-parenting" --csv pain_points.csv

# also check each suggestion's category against Google Trends
app-guru mine "co-parenting" --check-trends
```

Example output — ranked by opportunity score, each entry a scored app idea:

```
Searching Reddit for up to 10 thread(s)...
Searching for up to 10 Reddit thread(s)...
Found 8 thread(s). Fetching content...
Fetched 8 thread(s). Extracting scored app suggestions with claude-opus-4-8...

#1  [hostile co-parent communication]  Opportunity 8/10 * Buildability 9/10
    App idea: A one-tap button that turns a rant into a neutral, drama-free message.
    Pain: Parents feel pressure to maintain a friendly relationship with an
    ex for the kids' sake, even when the ex is abusive or unreasonable.
      "it's hard to co-parent with your abuser"
      "why does everyone act like we HAVE to be friends now"
    Trend: UP (+14.0%)

#2  [scheduling conflicts]  Opportunity 6/10 * Buildability 7/10
    App idea: A shared calendar with one-tap swap requests and a confirmation log.
    Pain: Parents argue over swap requests via text, nothing tracked.
      "we always fight about who has them on holidays"
    Trend: FLAT (+1.0%)

-> 1 suggestion(s) also cleared the trend gate. Those are the strongest bets.
Reminder: opportunity/buildability are the model's read of the evidence, not
proof of demand. Only a RISING trends verdict (or real landing-page signups)
counts as validated.
```

### Notes on the mining pipeline

- The default frustration phrases are tuned for venting/complaint threads;
  override with `--pain-phrase` (repeatable) if your market talks about
  problems differently.
- Search runs against Reddit's own public `search.json` endpoint — no API
  key. Reddit rate-limits anonymous requests, so if you get a rate-limit
  error, just wait a moment and re-run.
- **Opportunity score** (1-10) reflects how painful/common the complaint
  looks from the evidence alone (quote count, intensity) — it is *not* a
  claim of validated demand.
- **Buildability score** (1-10) reflects how simple the suggested fix is:
  10 = a trivial single-feature app, buildable with no-code AI tools in
  hours; 1 = needs a complex multi-part product or regulatory hurdles.
- Read each thread before trusting the extraction — the LLM step merges
  duplicate complaints and only reports pain points with a supporting
  quote, but it can't tell you whether a thread is representative or a
  one-off rant. A high opportunity score is a lead worth investigating,
  not proof.
- `--model` defaults to `claude-opus-4-8`; override for a cheaper/faster
  model if you're running this often.

## The ledger — a shared history across every run

Every run of `trends` or `mine` appends to `data/ledger.jsonl` — an
append-only, git-committed history of every idea you've ever checked. See
`data/README.md` for the exact schema and the reasoning behind it. The
short version:

- Nothing is ever overwritten — every check adds a new entry, so the
  history is a real audit trail, not a mutable snapshot.
- `mine` entries always log `verdict: null`. A pain point is a research
  lead, never a claim of validated demand — only `trends` (real search
  data) or, eventually, real landing-page signups can say something is
  actually validated. This is deliberate: it stops an unverified Reddit
  hunch from quietly being trusted as if it were confirmed demand.

## Roadmap

Planned next automated stations, matching the other hunting grounds from
the sourcing frameworks — added the same simple way `trends` and `mine`
were built, no framework/plugin system:

- [x] Google Trends validation (no key)
- [x] Reddit pain-point mining, scored (opportunity + buildability) — via
      Reddit's own free search, no key
- [x] Shared, append-only ledger across runs
- [ ] Product Hunt top launches (official GraphQL API)
- [ ] App Store / Play Store critical-review scraping
- [ ] MicroAcquire / Flippa / TrustMRR / Sensor Tower — no free API;
      stays a manual step unless that changes

## License

MIT
