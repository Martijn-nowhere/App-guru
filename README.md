# app-guru

Automated first-pass validation for app ideas — the "is anyone actually
searching for this?" gate you're supposed to run before writing a single
line of code:

> "Type it into Google search. Is it going up and to the right? If it is,
> that's a great sign."

> "Google Trends, plug in your core keyword ... if it's flat or declining,
> skip it. If it's trending up, then it's worth exploring."

`app-guru` scores a list of candidate problem/idea keywords against Google
Trends and tells you which ones are RISING, FLAT, or DECLINING, plus any
related queries that are themselves trending up (adjacent niches you
didn't think to check).

This is stage one of a bigger pipeline. It doesn't replace the rest of the
sourcing framework — Product Hunt, MicroAcquire/Flippa comps, Reddit and
App Store complaints, support-ticket mining — it just automates the
cheapest, fastest filter so you stop spending time on ideas nobody is
searching for.

## Install

```bash
pip install -r requirements.txt
```

or, for the `app-guru` command:

```bash
pip install -e .
```

## Use

```bash
# check a few ideas directly
app-guru "quit vaping" "ai sales rep" "prd maker"

# check a whole list (see ideas.example.txt for the format)
app-guru --file ideas.example.txt

# write the full report out for your monthly log
app-guru --file ideas.example.txt --csv report.csv

# restrict to one country, use a longer/shorter trend window
app-guru --file ideas.example.txt --geo US --timeframe "today 3-m"
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

## Notes on the signal

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

## Roadmap

Planned next automated stations, matching the other hunting grounds from
the sourcing framework:

- [ ] Reddit search (official API — recurring complaint threads by keyword)
- [ ] Product Hunt top launches (official GraphQL API)
- [ ] App Store / Play Store critical-review scraping
- [ ] MicroAcquire / Flippa listing pull (comps under a revenue ceiling)

## License

MIT
