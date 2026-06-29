# Real-Page Dogfooding

Use this workflow when testing AgentShelf against public merchant pages that you do not own.

## Goal

Real-page dogfooding should improve rules, task wording, and calibration coverage without copying third-party storefront source into this repository.

## Safe Default

```bash
agentshelf dogfood https://example.com/products/custom-teacup \
  --brand "Example Studio" \
  --category "custom handmade teacups" \
  --vertical artist_store \
  --output-dir reports/example-studio-dogfood
```

`agentshelf dogfood` fetches the page in memory and writes derived artifacts:

- `geo-report.json`
- `geo-report.md`
- `geo-tasks.jsonl`
- `geo-report-validation.json`
- `geo-tasks-validation.json`
- `scan-report.md`
- `scan-report.json`
- `dogfood-notes.md`
- `summary.json`

It does not write the fetched raw HTML. The summary includes `raw_html_persisted: false`.

## Deterministic Fixture Dogfood

Use this workflow when you want a repeatable Codex-style agent loop without fetching any third-party page:

```bash
agentshelf dogfood \
  --fixture artist-store-comparison \
  --vertical artist_store \
  --output-dir reports/artist-store-fixture
```

This writes a synthetic before/after comparison plus `report.json`, `report.md`, `report.html`, and `geo-tasks.jsonl` for both fixture states. Use it to verify that AgentShelf can produce actionable coding-agent tasks and that the after fixture improves deterministic local readiness. It is not evidence of live AI provider visibility or ranking lift.

## What Can Be Committed

Safe to commit:

- bug reports that describe rule failures in your own words
- aggregate counts and score deltas
- anonymized task IDs and issue categories
- synthetic fixtures that recreate the pattern without copying the page
- calibration labels for synthetic or owned fixtures

Do not commit by default:

- raw third-party HTML snapshots
- copied product descriptions, reviews, policies, or page copy
- screenshots from a third-party storefront unless you have permission
- merchant data exports that are not yours

## Turning Findings Into Fixtures

1. Run `agentshelf dogfood <url>` and inspect `dogfood-notes.md`.
2. Decide whether the finding is a true positive, false positive, or missing rule.
3. Recreate the pattern as a small synthetic fixture under `benchmarks/fixtures/`.
4. Add or update the matching expectation under `benchmarks/expected/`.
5. Add a test or calibration label only after the synthetic fixture captures the pattern.
6. Re-run:

```bash
agentshelf scan benchmarks/fixtures --batch --format jsonl --output /tmp/agentshelf-benchmarks.jsonl
python3 -m unittest discover -s tests
```

## When Raw HTML Is Acceptable

Only store raw HTML when one of these is true:

- the page belongs to you or your client and you have permission
- the HTML is generated from your own catalog export or fixture renderer
- the HTML is already an intentionally public test fixture

When in doubt, keep raw capture in `/tmp` or another ignored local directory and commit only derived notes or synthetic fixtures.
