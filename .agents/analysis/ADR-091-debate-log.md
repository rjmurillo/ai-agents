# ADR-091 Debate Log

## What ran, and what did not

The `adr-review` skill's six-agent debate did not run against `ADR-091: Judge Verdict Recovery Bounds`. The sessions that authored and reviewed it ran as isolated worktree subagents with no Task tool, so no subagent could be spawned. This file records the review that did happen and names the gap, rather than reporting a consensus nobody reached.

Read every verdict below as coming from a reviewer that examined the branch, not from the six-role panel the skill would have convened. Nothing here should be read as a 6/6 accept.

## Reviewers

| Reviewer | Basis | Verdict on the decision | Verdict on the artifact |
|----------|-------|-------------------------|--------------------------|
| Reviewer 1 (independent, branch diff) | Read the whole diff plus `git status`, `git ls-files`, `git diff main HEAD --stat` | Not contested | BLOCKING: four committed references to a file that does not exist in the repo |
| Reviewer 3 (independent, branch diff) | Same diff, plus the orphan-ref-validator and `evals/architect-spike/fixtures/A001.json` | Not contested | MAJOR: three #3988 sub-claims stay open without this file; the repo's own eval plants `ADR-091` as the canonical fabricated citation |
| Reviewer 5 (independent, branch diff) | Same diff, plus `pre_pr.py` run to confirm no gate catches it | Not contested | MAJOR: the 0.15 default's rationale is unrecoverable while the ADR is untracked |
| Round 16 measurement (`.claude/skills/context-optimizer/references/rule-audit-parser-forensics.md`) | 288 archived judge payloads replayed | Supports keeping the recovery path | Retracts the zero-marker inference issue #3988 rested on |

All three independent reviewers reached the same conclusion from the same evidence and none disputed the decision the ADR records. That is agreement about a missing file, not a debate about the architecture.

## Findings and resolution

| Finding | Resolution |
|---------|------------|
| ADR-091 cited four times, tracked nowhere | Committed alongside the four citing files. |
| Decision item 6 claimed every salvaged record keeps `judge_raw`, and the prefix recovery in `score_response` kept none | Fixed in `scripts/eval/eval-rule-activation.py`; item 6 now names all three salvage paths. |
| The `--max-salvaged-fraction` bound moved the exit code and the rendered report disclosed nothing | Salvage rate added to `_render_caveats`; decision item 5 records it. |

## What the decision rests on, and what would overturn it

The ADR keeps the recovery path because deleting it drops 24 of 288 archived samples, 8.3%, measured after issue #3988 was filed and against a retracted zero. Two facts would overturn it:

- A provider-enforced structured-output schema (`response_format` or a tool-call schema) lands anywhere in `scripts/eval/`. Recovery becomes dead code and deletion is free. Named as the exit path in the ADR and out of scope there.
- A re-measurement showing the 8.3% figure is itself an artifact of the replay rather than of the run. The 288 payloads are archived at `.agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/recovered-judge-payloads.json`, so this is checkable.

## Accepted risks

- Two residuals ship live. An exemplar object at offset 0 followed by a prose refusal still grades 5/5/5, and adjacent string literals are undetected. Both are recorded in the ADR and pinned by tests. Both now retain the payload under `judge_raw`, so a reader can find them in the artifact.
- The six-agent debate is unrun. An agent that can spawn subagents should run `adr-review` against this ADR and replace this file with its output. Until then the ADR's status stays `proposed`.
