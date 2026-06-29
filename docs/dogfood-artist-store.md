# Artist Store Dogfood Fixture

The `artist_store` vertical matters because creator-commerce and artist shops often sell products where narrative, provenance, customization, lead time, and trust matter as much as price. These pages are also easy to make beautiful for humans while leaving important facts hard for coding agents and shopping agents to extract.

AgentShelf includes a fully fictional fixture set:

- `examples/fixtures/artist-store-before`
- `examples/fixtures/artist-store-after`
- `examples/profiles/artist-store.example.json`

No real artist, real store, real private information, fake reviews, fake ratings, fake press, or fake AI visibility data is included.

## Before Fixture

`artist-store-before` intentionally includes common gaps:

- Poetic homepage copy without a clear opening answer block.
- Product pages with weak price, availability, lead time, care, return, and customization details.
- Missing Product schema and FAQPage schema.
- Short about page with weak artist/studio entity facts.
- Commission process page without concrete steps or policy boundaries.
- Vague shipping and returns pages.
- Collection page that does not link clearly to product pages.
- Missing image alt text and weak internal linking.

## After Fixture

`artist-store-after` shows a conservative remediation target:

- Clear opening answer blocks.
- Product attributes in visible HTML.
- Product JSON-LD skeletons using only fixture-confirmed facts.
- FAQPage schema from visible answers.
- Artist/studio factsheet copy.
- Commission process details.
- Shipping and return boundaries.
- Gift and custom-calligraphy collection pages.
- More complete internal links and descriptive image alt text.

## Run The Dogfood Comparison

```bash
agentshelf geo-run \
  --store-snapshot examples/fixtures/artist-store-before \
  --store-profile examples/profiles/artist-store.example.json \
  --vertical artist_store \
  --output-dir reports/artist-store-before \
  --format json

agentshelf geo-run \
  --store-snapshot examples/fixtures/artist-store-after \
  --store-profile examples/profiles/artist-store.example.json \
  --vertical artist_store \
  --output-dir reports/artist-store-after \
  --format json
```

The expected result is that the after fixture has a higher deterministic store score and fewer issues than the before fixture.

## Interpretation

This before/after fixture only proves local deterministic readiness improvement. It does not prove AI provider visibility lift, ranking lift, citation lift, impression lift, referral lift, traffic lift, or revenue lift. It does not call ChatGPT, Google AI, Perplexity, Claude, Gemini, Bing, GSC, or Bing Webmaster.

Use the fixture to test whether AgentShelf finds actionable gaps and produces coding-agent-ready tasks that improve local AI-readability without fabricating merchant facts.
