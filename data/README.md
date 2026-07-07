# Ledger

`ledger.jsonl` is app-guru's shared, append-only history of everything
`explore`, `trends`, and `mine` have ever found. It's created automatically
the first time you run any of them, and is committed to the repo — it's
not secret (public web quotes, Trends numbers, category labels; no API
keys or PII), and the whole point of a monthly-cadence tool is that
results should accumulate across runs instead of disappearing.

One JSON object per line:

```json
{"id": "...", "ts": "2026-07-06T12:00:00Z", "station": "explore", "subject": "co-parenting", "verdict": "RISING", "data": {"parent_category": "relationships", "rationale": "...", "current_interest": 30.0, "change_pct": 13.0, "error": null}}
{"id": "...", "ts": "2026-07-06T12:00:00Z", "station": "trends", "subject": "quit vaping", "verdict": "RISING", "data": {"current_interest": 31.0, "change_pct": 9.0, "rising_related": []}}
{"id": "...", "ts": "2026-07-06T12:05:00Z", "station": "mine", "subject": "hostile co-parent communication", "verdict": null, "data": {"market": "co-parenting", "pain_point": "...", "quotes": [...], "simplest_fix": "...", "opportunity_score": 8, "buildability_score": 9, "search_term": "co parenting app", "trend_check": null}}
```

Rules (see `app_guru/ledger.py` for the implementation):

- **Append-only.** A new check always writes a new entry; nothing is ever
  edited or overwritten. "Current status" of an idea is computed from the
  full history, not a mutable field.
- **`verdict` is only ever a real, objective result.** `trends` and
  `explore` both write `RISING` / `FLAT` / `DECLINING`, because both are
  testing something measurable (real search demand) — `explore`'s niche
  proposals are an LLM guess, but the verdict attached to them is real
  Trends data, not the model's opinion. `mine` always writes
  `verdict: null` — a pain point mined from web complaints is a research
  lead, never a claim of validated demand on its own. The only things that
  can ever say an idea is validated are a `RISING` trends/explore entry,
  or (once that station exists) real landing-page signups.
