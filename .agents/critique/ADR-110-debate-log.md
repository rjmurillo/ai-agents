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

## Revision 3

Two corrections found while planning milestone 3, both raised against the
record's own text rather than by a seat.

| ID | Finding | Fix |
|---|---|---|
| R3-1 | The Context called the 13 untrusted-content files "an independently written version of the same policy", which rests on a grep. A diff shows two variants: a generic one in eleven files and a review-specific one in two | Restated the claim as what the diff shows, and said why it matters: a fix to one variant leaves the other stale |
| R3-2 | Milestone 3 planned to replace prompt text with a pointer to `templates/rules/security.md`. An agent running under Copilot CLI never loads that tree, so the pointer would thin a prompt-injection defense | Milestone 3 now composes through the mustache partial mechanism the repository already uses, which renders the canonical text into every consumer. The after count is two files, one per partial tree, pinned byte-identical by a test |

R3-2 is the same objection the critic raised as C6, reaching further than the
first fix did. C6 saved the consumer-specific procedure; R3-1 and R3-2 save the
shared core as text rather than as a citation.

## Revision 4, review round 1 on PR #5879

An automated reviewer on the pull request found three defects in the validator
and raised two design questions. All five were accepted.

| ID | Finding | Fix |
|---|---|---|
| D1 | `_shared_run` collapsed the owner's lines into a set, so a consumer whose lines each appeared somewhere in the owner failed even when the owner held no such block | Compares contiguous windows on both sides. Regression test: `test_scattered_owner_lines_do_not_count_as_a_copied_block` |
| D2 | `--report` rendered from its own shorter path, so a broken graph printed a report and exited zero | One `survey` reads the trees for both modes. The report still renders, and the exit code reports the findings |
| D3 | `_names` normalized a mapping or a non-string entry to empty, so a malformed declaration was indistinguishable from an absent one | `_field_defect` reports the shape, and `_names` accepts only the two shapes the schema allows |
| D4 | The agent declaration site was ambiguous between `*.shared.md` and the per-harness templates | One site per class, stated in the record and enforced: a block in a per-harness template is a defect naming the shared file |
| D5 | An empty capability block counted as a node | An empty block is a defect |

## Revision 5, review round 2 on PR #5881

| ID | Finding | Fix |
|---|---|---|
| R5-1 | The gate stopped refusing a projection's `owns` declaration, but ADR-110, REQ-031, and TASK-040 still required that refusal. Code and contract disagreed | Amended Decision 3 and invariant 5 in this record, and invariant 5 plus criterion 5 in REQ-031, with the reason the first wording was unenforceable against this repository's own binplace step |
| R5-2 | The security rule told prompt surfaces not to restate the policy while four agent shared bodies restate it, with no waiver in the rule itself | The rule now names the four files, the generator reason, the byte-identity requirement, and the ADR-109 B1 retirement condition, and states that a fifth copy is a violation rather than residue |

## Security seat, run on PR #5881

The seat-count deviation above named security as the uncovered seat whose
subject was the untrusted-content conversion. That seat has now run, against
the conversion diff plus the ten rendered consumers before and after.

**Verdict: PASS.** No HIGH or CRITICAL finding, no secret, no CWE-22, CWE-77 or
CWE-78, no unmitigated agent-boundary issue. Three Low findings, all judged not
material by the seat:

| Finding | Disposition |
|---|---|
| The heading lost its `Critical:` prefix in all ten consumers; content unchanged | Accepted as is. The seat recorded no fix required, and restoring the prefix would change every rendered file for salience alone |
| "memory files retrieved from Serena" became "memory files" | Accepted. The replacement is a superset, so coverage did not narrow |
| pipeline-validator lost one skill-specific sentence about build logs and PR descriptions | Accepted. The retained general sentence names build and CI logs, and the skill's own anti-pattern row still guards the injection path |

The seat's answers to the four questions it was given: no rendered prompt lost a
normative sentence or a role-specific instruction; every consumer carries the
guard inline with no runtime dependency on a rule file; the canonical text is at
least as strong as every variant it replaced, and three consumers gained
sentences they previously lacked; the partial include adds no injection surface,
because it resolves at build time and no rendered file carries a mustache tag.

## Verification after revision

- `uv run python scripts/validation/check_capability_graph.py .` exits 0 against
  the real trees.
- `uv run pytest tests/validation/test_check_capability_graph.py -q` reports 29
  passed after revision 4.
- Counts in the record were recomputed from the tree, not carried forward.
