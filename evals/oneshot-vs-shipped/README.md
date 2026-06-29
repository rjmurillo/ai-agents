# One-shot-vs-shipped benchmark (#2788)

Grades whether the harness produces a same-or-better fix than what humans merged
and shipped, on real closed bugs. The closed loop on a self-graded harness is
broken because the ground truth here is a human-merged, released fix.

## How it runs

```bash
# Validate fixtures and print the call plan with ZERO API spend:
uv run python scripts/eval/eval-oneshot-vs-shipped.py --dry-run

# Live run (needs ANTHROPIC_API_KEY; two model calls per fixture):
uv run python scripts/eval/eval-oneshot-vs-shipped.py --hardest-n 5 --report evals/oneshot-vs-shipped/reports/run.json
```

For each fixture the harness:

1. Shows the agent the issue and its discourse, withholding the merged fix, and
   asks for a root cause, a fix, and self-set acceptance criteria.
2. Shows an LLM judge the discourse, the shipped fix, the agent's proposal, and
   the discourse-named edges, and asks for a `FULL` / `PARTIAL` / `NONE` grade
   plus which edges the agent fix caught or missed.
3. Aggregates the grade distribution, the same-or-better rate, and the
   edge-catch rate. `PARTIAL` / `NONE` rows feed prompt tuning.

## Fixture schema

One JSON object per file under `fixtures/`:

| Field | Required | Meaning |
|-------|----------|---------|
| `id` | yes | Stable fixture id. |
| `source_repo` | yes | `owner/repo` the bug came from. |
| `issue_number` | yes | Issue number in `source_repo`. |
| `title` | yes | Issue title. |
| `discourse` | yes | Issue + discussion text the agent sees. The merged fix is NOT in here. |
| `shipped_fix` | yes | The merged fix, withheld from the agent, shown to the judge. |
| `edges_named_in_discourse` | no | Edge cases the discussion called out; the judge checks each. |
| `difficulty` | no | 1..5; `--hardest-n` selects by this. Default 3. |

## Corpus status

The seed fixture (`moq1208-1091.json`) is a curated summary of the Sample 1
example named in #2788 (Moq1208 #1091: PARTIAL, matched root cause, missed a
valid-suppression edge). The remaining issue->fix pairs from
`rjmurillo/moq.analyzers` are authored incrementally; the full corpus and the
calibrated live run require API spend and are owner-gated follow-up work.
