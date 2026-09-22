# ADR Debate Log: Capability Ownership and the Artifact Dependency DAG

Record under review: `.agents/architecture/ADR-110-capability-ownership-dag.md`
Tracker: issue #5396. Branch: `feat/5396-capability-dag`.

## Summary

- Rounds: 1
- Seats: 2 (architect, critic)
- Round 1 outcome: **1 Block, 1 Revise.** No seat approved revision 1.
- Disposition: revision 2 written against every P0 and every P1. Two findings
  were rejected with reasons recorded below.
- Final status: proposed, `implemented: false`, `review-by: 2027-03-22`.

Each seat received the artifacts and nothing else. Neither saw the reasoning
that produced them, and neither saw the other seat's findings.

## Seat count deviation

The `adr-review` skill runs six seats. This debate ran two. The operator's
standing fan-out cap for this session is three subagents total and two
concurrent, and one had already been spent on the prior-art inventory. The
architect seat covered the record's internal consistency and its citations; the
critic seat covered acceptance-criteria coverage against issue #5396 and the
epic. The uncovered seats are security, independent-thinker, analyst, and
high-level-advisor. The security seat's subject, the untrusted-content
conversion, is deferred to TASK-040 Milestone 3, which runs the security review
axis over that diff. Record this as a known gap rather than a completed
six-seat review.

## Agent positions

| Agent | Round 1 vote | Load-bearing objection |
|-------|--------------|------------------------|
| architect | Block | Two counts were wrong and one was untagged: "233 files" (actual 170) and "143 scripts" (actual 130 `.py` tracked at HEAD). The record also stated #5384's metadata format as settled when #5384 calls it an implementation choice |
| critic | Revise | Epic #5456 allows a new validator only when it removes or consolidates an existing mechanism, and the plan removed nothing. The "13 identical copies" claim rested on a grep, not a diff, so the conversion would have dropped consumer-specific procedure |

## Findings accepted

| ID | Seat | Finding | Fix |
|---|---|---|---|
| A1 | architect | "233 authored artifacts" was wrong; `ls templates/agents \| wc -l` counted the `partials/` directory and the per-harness `.tmpl` files | Recomputed to 170 (111 skills, 31 `*.shared.md` agents, 28 rules) and cited the glob |
| A2 | architect | #5384's routing key was stated as a settled sibling under `metadata` | Retagged `hypothesis`, dropped the reservation claim, recorded that #5384 commits to nothing |
| A3 | architect | `validate_copilot_agent_frontmatter.py` citation named lines 38-41; the closed role set is line 43 | Corrected to lines 38 and 43 |
| A4 | architect | "143 scripts" in `scripts/validation/` | Corrected to 130 tracked `.py` files, with the command |
| A5 | architect | "A node under `.claude/` is a projection" is false for skill support files, which `build/scripts/generate_skills.py:129` syncs outward from `.claude/skills/<name>/` | Scoped the rule to the three frontmatter classes and named the support-file exception |
| C1 | critic | Issue #5396 requires one deterministic copied-policy class to be prevented; the plan deferred all of it | The validator now blocks a consumer that repeats three or more consecutive lines of its declared dependency's text. New criterion 11 |
| C2 | critic | The lifecycle checklist wants a replaceable capability to name the target platform and upstream owner; no field existed | Added `replacement-platform` and `replacement-owner`, required with `sunset` and `deprecated` when `replaced-by` is absent. New criterion 12 |
| C3 | critic | The stable output was to expose ownership, validation commands, and replacement status; it exposed counts and edges only | Added a `validation` field and put owner, status, replacement, and validation on each owner line. Criterion 7 rewritten |
| C4 | critic | Nothing updated a surface an agent reads while authoring | TASK-040 Milestone 5 adds the instruction to the knowledge placement rule. New criterion 13 |
| C5 | critic | Epic #5456 forbids a new validator that consolidates nothing | TASK-040 Milestone 4 retires `metadata.type` into `capability.kind`, which is the consolidation the gate pays for |
| C6 | critic | The 13 untrusted-content copies are not interchangeable; `code-reviewer.shared.md` and `research.SKILL.md.tmpl` carry role-specific procedure | Milestone 3 now requires diffing all 13 first and keeping the role-specific half in place |
| C7 | critic | Milestone 1's exit had no command | Added the ADR link check and the debate-log path to the exit |
| C8 | critic | The before and after count in criterion 10 was a hand-written assertion | Criterion 10 now requires the command that computes it, and the command is in the verification table |

## Findings rejected

| ID | Seat | Finding | Why rejected |
|---|---|---|---|
| A6 | architect | The four-kind vocabulary works only because the walker ignores support files, and the prose does not say so | Accepted in substance and folded into A5's rewrite rather than tracked separately. The revised Decision 3 states the walker's scope in its first sentence |
| C9 | critic | Semantic duplicate detection should also ship | Out of scope by the issue's own text, which permits warning-only heuristics and does not require the paraphrase class. Recorded under Deferred with issue #5397 named as owner |

## Verification after revision

- `uv run python scripts/validation/check_capability_graph.py .` exits 0 against
  the real trees.
- `uv run pytest tests/validation/test_check_capability_graph.py -q` reports 23
  passed.
- Counts in the record were recomputed from the tree, not carried forward.
