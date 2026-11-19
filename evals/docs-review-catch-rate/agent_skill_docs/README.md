# Agent and skill docs replay

Caught 2 of 2 in-scope positives, 0 FP on 12 negatives, 1 manual with reasons.
Both pages missing from PR #7416 count within one positive case.
All three expected missing-page findings matched.

## Run

```sh
uv run python scripts/eval/docs_review_agent_skill_docs_replay.py
```

The runner fetches each PR head and reads its recorded case SHA.
It queries `baseRefOid`, then computes the merge base with that SHA.
It creates disposable worktrees under `~/worktrees/ai-agents/`.
It runs both current pre-PR adapters against each historical checkout.
It removes its worktrees and temporary refs after each case.
Historical code never executes.

## Score

Matches require the same file and defect class, within three lines.
Missing files use line one because no source line exists.
Every expected finding must match before a positive case counts as caught.
All findings on negatives count, including freshness advisories.

Structural findings count only for sources added, renamed, or removed.
The receipt preserves excluded findings and raw pre-PR outcomes.
Nine negative checkouts predate the required docs README files.
Their pre-existing configuration gaps remain visible in the receipt.
The runner rejects removed READMEs or changed sources it cannot evaluate.
Freshness warnings are never filtered by structural attribution.

## Limits

C2-03 remains manual because agent-template semantics exceed the SKILL.md heuristic.
The corpus records that reason beside the case.
The replay measures three missing pages, not every possible page defect.
Fixture tests cover orphan pages, README rows, section order, and freshness.
The gate cannot prove prose accuracy or detect every changed fact.

The dated result records case SHAs, base SHAs, outputs, and source hashes.
The twelve negatives and three positives came from Richard's review findings.
