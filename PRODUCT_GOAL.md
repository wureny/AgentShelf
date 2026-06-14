# AgentShelf

## Product Name
AgentShelf

## Target User
- Shopify and DTC operators preparing catalog pages for AI shopping agents
- growth-minded indie founders testing whether product pages are machine-legible
- AI consultants auditing storefront readiness before automation work

## Problem
Most product pages are written for humans only. They often hide price, stock, shipping, returns, or schema signals in ways that make AI shopping agents unreliable at discovery, ranking, and checkout recommendation time.

## Product Thesis
A deterministic scanner that scores product-page readiness for AI shopping agents is small enough to ship quickly, useful as an audit workflow, and differentiated from generic SEO tooling.

## MVP Promise
Given a product page HTML or text file, generate a readiness score, pass/fail checklist, agent-risk summary, and prioritized fixes in markdown or JSON without external APIs.

## Non-Goals
- Live storefront crawling in the first milestone
- CMS plugins or browser extensions
- Real checkout automation

## Required Local Run Command
`cd /Users/wurenyu/Documents/Codex/2026-06-06/intent-to-prompt-users-wurenyu-codex/projects/agentic-commerce-readiness-scanner && python3 -m pip install -e . && agentshelf scan examples/sample_product_page.html --format markdown`

## Required Demo Mode
Deterministic local mode only. `MOCK_MODE=true` by default and no external services are required.

## Required Env Vars
- Optional: `MOCK_MODE`
- Required for demo: none

## Definition Of Done
- Runs locally against a bundled sample product page
- Includes README, `.env.example`, example input, example output, tests, smoke verification, deployment path, architecture note, portfolio notes, and resume bullets
- Supports markdown and JSON output
- Documents next improvements and mock-first usage

## First Milestone
Ship a runnable deterministic CLI with a bundled sample product page, generated report, and unit tests.

## Resume Bullets This Project Should Support
- Built a deterministic commerce-audit CLI that scores how well product pages expose the signals AI shopping agents need.
- Designed a heuristic scoring engine for price, inventory, shipping, returns, specs, reviews, FAQ, and Product schema readiness.
- Packaged a demo-first open-source workflow with sample HTML, tests, and portfolio-ready reporting output.

## Decision Record
- 2026-06-14: Selected this project after the user explicitly asked for a new side project before the prior one was finished.
- 2026-06-14: Used repo-local fallback path because `/Users/wurenyu/workspace` is not writable in this environment.
- 2026-06-14: Rebranded the public open-source project to `AgentShelf` with package and CLI name `agentshelf`.
