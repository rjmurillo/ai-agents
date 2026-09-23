---
type: task
id: TASK-041
title: Move code-reviewer doctrine into the review skill and thin the agent
status: draft
priority: P2
related:
  - REQ-032
  - ADR-110
created: 2026-09-22
updated: 2026-09-22
author: plan
tags:
  - review
  - capability-graph
  - agents
---

# TASK-041: Move code-reviewer doctrine into the review skill and thin the agent

## Objective

Give review doctrine one owner, the `review` skill, run it inside `/review`,
and reduce `code-reviewer` to an execution boundary. Closes #5395.

## Design

- The contract is a hand-maintained support file,
  `.claude/skills/review/resources/technical-review.md`. It is not under
  `references/`, because every file there is auto-discovered as a CI axis.
- `/review` gains step 4c, an always-on correctness pass. It dispatches
  `Task(subagent_type="code-reviewer")` with the contract as the response
  contract, and falls back to `general-purpose` when the harness registers no
  such agent. The pass emits a `VERDICT:` line that `extract_verdict` parses,
  and its verdict joins the step 7 merge. The output table appends one
  `correctness` row, the same way it appends `unresolved_axes` rows, so the
  16-row axis count stays pinned.
- The agent loads the contract by path, first match wins:
  `${CLAUDE_PLUGIN_ROOT}/skills/review/resources/technical-review.md`,
  `.claude/skills/review/resources/technical-review.md`,
  `skills/review/resources/technical-review.md`. When none resolves, it applies
  its one-line invariants and says the contract was unavailable.
- The agent keeps its canonical untrusted-content block byte-identical
  (`templates/rules/security.md`, "Approved residue").
- `chestertons-fence` keeps its workflow and gains the post-2023 evidence rules.
  It owns `code-archaeology` and depends on nothing new, so no cycle forms.

## Milestone 1: the contract (M)

1. Write `technical-review.md` covering REQ-032 AC 2 to 14.
2. Take convention discovery, caller tracing, duplicate verification,
   observable impact, and confidence from `code-reviewer.shared.md`, verbatim
   where the text still holds.
3. Done when every AC 2 to 14 maps to a named section.

## Milestone 2: the owners (M)

1. Add the `metadata.capability` block to `review.SKILL.md.tmpl` and
   `chestertons-fence.SKILL.md.tmpl`.
2. Add step 4c and the `correctness` output row to the review template.
3. Add the post-2023 evidence section to the chestertons-fence template.
4. Done when `check_capability_graph.py` passes and lists both owners.

## Milestone 3: the agent (S)

1. Rewrite `code-reviewer.shared.md` and its three partials as a thin boundary.
2. Declare `kind: specialized-implementation` with the two `depends-on` edges
   in the shared body only.
3. Record the retention evidence table from REQ-032 in the agent body.
4. Done when the agent restates no contract paragraph and the gate passes.

## Milestone 4: proof (S)

1. Extend `tests/evals/code-reviewer-scenarios.json` with the REQ-032 AC 19
   cases.
2. Add `tests/skills/review/test_technical_review_contract.py`: the contract's
   sections exist, the review template runs step 4c, the agent names the
   contract, and the agent carries no contract paragraph.
3. Run `build_all.py`, commit the regenerated trees, run `pre_pr.py`.

## Dependency graph

Milestone 1 blocks 2 and 3. Milestones 2 and 3 can run in parallel. Milestone 4
runs last.

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A test pins old agent prose (`test_code_reviewer_prompt_injection.py`, build fixtures) | High | Low | Run the suite; keep the untrusted block; update only tests whose subject moved |
| Axis-count contract test reds | Medium | Low | Append the correctness row outside the 16-row count |
| Plugin portability ratchets flag new paths | Medium | Low | Use the plugin-root env var form; run the ratchets |
| Consumer copy of 3+ owner lines trips the graph gate | Low | Low | Agent keeps one-line invariants only |
| VS Code agent loses doctrine | Medium | Medium | Inline invariants plus an explicit "contract unavailable" note |

## Deferred items

- New CI axis: operator cost decision.
- Claude `tools:` allowlist on `code-reviewer`.
- #5403 conversation protocol.
