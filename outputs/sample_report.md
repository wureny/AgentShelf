# AgentShelf Report: TrailBottle Pro 24oz

## Summary
- Source: /Users/wurenyu/Documents/Codex/2026-06-06/intent-to-prompt-users-wurenyu-codex/projects/agentic-commerce-readiness-scanner/examples/sample_product_page.html
- Score: 89/100
- Readiness band: strong
- Passed checks: 13/15
- Not applicable checks: 2
- Dimension scores: discoverability=100, offer_clarity=100, policy_clarity=79, agent_actionability=75
- Confidence: high (Most passing checks include direct visible or structured evidence.)
- Adapter profile: generic (requested=auto, detected=generic)

## Commerce Signals
- Variants: 0 (0 with price, 0 with availability)
- Options: None detected
- Selling plan groups: 0
- Metafield-like keys: None detected
- Return policy schema: missing
- Subscription intent: no
- Bundle intent: no
- Regional shipping intent: yes

## Checks
- [PASS] Clear product title (10 pts): A shopping agent can identify the item name from page chrome or main heading. Evidence: title: TrailBottle Pro 24oz. Impact: Agents need a stable product name to identify, compare, and cite the item.
- [PASS] Explicit price (15 pts): Price appears directly in page text or Product offer metadata. Evidence: Offer price: USD 39.00. Impact: Agents cannot make purchase recommendations when price is hidden or ambiguous.
- [PASS] Availability or inventory state (12 pts): Inventory state is stated in visible text or Product offer metadata. Evidence: Offer availability: https://schema.org/InStock. Impact: Agents need stock state to avoid recommending unavailable products.
- [PASS] Shipping details (10 pts): The page gives shipping timing or cost clues. Evidence: ships in 2 business days. Impact: Delivery timing and cost affect whether an agent can recommend the item for a user's need date.
- [PASS] Return policy (10 pts): Returns or refunds are discoverable on the page. Evidence: 30-day returns and exchanges. Impact: Return terms affect buyer risk and agent confidence.
- [PASS] Structured product specs (12 pts): Agents can extract concrete item attributes. Evidence: specifications. Impact: Agents need concrete attributes to match products to user constraints.
- [PASS] Social proof or reviews (8 pts): Review or rating signals are present. Evidence: review. Impact: Ratings and review volume help agents rank comparable products.
- [PASS] Product structured data (15 pts): Structured Product metadata is present. Evidence: 1 Product JSON-LD object(s). Impact: Structured data gives agents a reliable extraction path when visible content is noisy.
- [PASS] FAQ or policy answers (8 pts): Common purchase objections are pre-answered. Evidence: faq. Impact: FAQ answers reduce uncertainty for agent-generated buying guidance.
- [FAIL] Variant readiness (10 pts): Expose variant options with readable price and availability context. Impact: Agents need option, price, and stock signals to recommend the right variant.
- [PASS] Complete offer metadata (12 pts): Offer metadata includes core purchase-decision fields. Evidence: Offer has price, currency, availability, and seller or policy metadata. Impact: Agents need price, currency, availability, and seller or policy metadata as one coherent offer.
- [PASS] Agent answerability (10 pts): The page can answer common agent-mediated purchase questions. Evidence: shipping and return policy snippets are present. Impact: Agents need enough page context to answer fit, delivery, returns, and limitations questions.
- [PASS] Merchant feed hints (10 pts): The page includes schema hints useful for merchant feeds and agent ingestion. Evidence: product. Impact: Merchant-feed-like metadata helps agents ingest offers beyond generic SEO snippets.
- [FAIL] Return policy structured data (8 pts): Add hasMerchantReturnPolicy metadata with return window, method, and refund terms. Evidence: Visible return policy exists without hasMerchantReturnPolicy metadata.. Impact: Agents can compare buyer risk more reliably when return terms are available as structured policy metadata.
- [N/A] Subscription purchase terms (10 pts): Not applicable to this snapshot. Evidence: No subscription or selling-plan intent detected.. Impact: Agents need cadence, price, and cancellation terms before recommending a subscription offer.
- [N/A] Bundle component clarity (10 pts): Not applicable to this snapshot. Evidence: No bundle or kit intent detected.. Impact: Agents need bundle contents and bundle-level offer data to compare kits against single items.
- [PASS] Regional shipping promises (10 pts): Shipping promises include region plus timing or cost. Evidence: US, ships in 2 business days, free shipping on us orders over $25. Impact: Agents need destination-specific delivery promises to avoid recommending products that miss a buyer's region or deadline.

## Top Fixes
- Expose variant options with readable price and availability context.
- Add hasMerchantReturnPolicy metadata with return window, method, and refund terms.

## Warnings
- None

## Contradictions
- None

## Agent Risks
- Agents may skip the item if price or inventory state is ambiguous.
- Missing structured data increases extraction errors and ranking instability.
- Thin policy details reduce confidence for autonomous checkout recommendations.
