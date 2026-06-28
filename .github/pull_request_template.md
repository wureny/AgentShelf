## Summary

- 

## Type of change

- [ ] Scoring, extraction, or benchmark behavior
- [ ] GEO audit, task contract, or coding-agent workflow
- [ ] GitHub Action, CI, or release workflow
- [ ] Documentation, examples, or templates

## Verification

Paste the commands you ran:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
agentshelf public-audit .
agentshelf release-check --expected-version <version>
```

## AgentShelf boundaries

- [ ] I did not add secrets, customer personal data, or raw third-party HTML that cannot be shared.
- [ ] I did not fabricate reviews, ratings, stock, shipping promises, return promises, press, certifications, or external authority.
- [ ] I did not add claims of ChatGPT, Google, Perplexity, Claude, Gemini, Bing, ranking, conversion, or revenue lift without separate evidence.
- [ ] If this changes release-facing docs, I updated `CHANGELOG.md` and the current `docs/releases/` draft.
