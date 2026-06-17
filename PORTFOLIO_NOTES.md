# Portfolio Notes

## Thesis
This project shows practical AI-commerce product thinking by turning vague "agentic commerce readiness" into a concrete, deterministic audit workflow.

## What Makes It Portfolio-Worthy
- It targets a current AI-commerce problem with a concrete business user.
- It is small enough to demo locally but credible enough to expand into a real audit product.
- It demonstrates product scoring, prioritization, and actionable reporting rather than generic chat UX.

## Resume Bullets
- Built `AgentShelf`, an open-source CLI and GitHub Action that audits product pages for AI shopping-agent readiness across price, stock, shipping, returns, specs, reviews, FAQ, and structured data.
- Designed a multi-dimensional scoring engine that turns storefront HTML into evidence-backed, prioritized machine-readability fixes without relying on external APIs.
- Added an agent-native JSON contract that converts audit failures into coding-agent tasks with reasons, page areas, acceptance checks, and priority.
- Added optional Playwright-backed rendered snapshots so JS-heavy Shopify/DTC pages can be audited without making the default CLI heavy.
- Added production-oriented CI and agent surfaces: SARIF output, repeatable JSON config, batch URL snapshots with manifests, and JSONL remediation tasks.
- Added raw-vs-rendered snapshot comparison so operators can justify when browser-based capture is necessary.
- Added sitemap-based product URL discovery so real merchants can audit page sets without hand-maintained URL lists or arbitrary crawling.
- Added audit-run diff reports so scheduled jobs can highlight product-page regressions, resolved blockers, and next agent tasks across merchant catalogs.
- Added a scheduled audit-run workflow that manages previous/current artifacts and timestamped archives locally, making the CLI useful in cron and GitHub Actions without external services.
- Added Shopify/theme-style commerce extraction for embedded variants, selling plans, metafield-like keys, and policy snippets, making the engine more credible on real DTC storefront snapshots.
- Added storefront adapter profiles for Shopify, WooCommerce, headless, and generic pages so production CI and coding agents can pin deterministic extraction behavior.
- Added profile-specific benchmark contracts for Shopify, WooCommerce, and headless storefront exports to keep production extraction behavior stable.
- Added applicable merchant rule packs for subscriptions, bundles, regional shipping, and return policy schema so AgentShelf now catches higher-value agent-readiness gaps beyond basic SEO/schema checks.
- Added a real-page calibration workflow that groups likely false-positive categories and exports anonymized merchant fixtures for repeatable benchmark improvement.
- Added labeled calibration evaluation so AgentShelf can guard rule changes against confirmed true-positive and false-positive merchant fixtures in CI.
- Added draft label generation so merchant calibration findings can become reviewable label contracts without hand-writing JSON from scratch.
- Added standalone calibration dashboards so non-technical operators and consultants can review page priorities, blockers, and agent tasks without reading raw JSON.
- Added a GitHub Actions artifact workflow that uploads SARIF, dashboards, draft labels, evaluation notes, scan JSONL, and coding-agent task queues before enforcing score gates.
- Added product-export-to-fixture generation for Shopify, WooCommerce, and headless HTML snapshots, giving real storefront teams a low-ops pre-merge audit path without live crawling.
- Packaged a professional open-source release with installable Python metadata, CI, contribution docs, benchmark fixtures, tests, and GitHub Action integration.

## Positioning Angle
Useful as evidence of AI product strategy, commerce-domain judgment, and the ability to ship agent-adjacent developer tools quickly.
