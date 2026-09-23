# Retrospective: issue-5404

## Session Info
- **Date**: 2026-09-03
- **Agents**: Claude (Claude Code, autoplan -> orchestrated single-session implementation)
- **Task Type**: Feature (cross-cutting policy: task-completion contract + completion-tail audit)
- **Outcome**: Success

## Phase 0: Data Gathering

### Work Items
- Read issue #5404 in full plus its dependency issues (#5391, #5392) to confirm neither blocks this work and that the design (rules, not Serena) does not compete with #5392's placement contract.
- Added a Task Completion Contract section (terminal predicate, precedence, finding disposition, reactivation) to `.claude/rules/builder-ethos.md`, and a Completion-Tail Audit section to `.claude/rules/voice.md`.
- Replaced the "find at least three issues" manufactured-finding quota in `templates/agents/critic.shared.md` and `templates/agents/qa.shared.md` (plus all hand-maintained and generated copies) with a requirement to inspect exhaustively and allow a zero-finding APPROVED/PASS verdict.
- Cross-referenced the terminal predicate from `templates/agents/orchestrator.shared.md`'s Completion Gate and Orchestration Budget sections so remaining delegation budget reads as a backstop, not proof of completion.
- Added FAILURE-MODES.md pattern 12 (Post-Completion Continuation).
- Added verdict/classification eval scenarios (critic TC-1, new `qa-scenarios.json`, orchestrator S8) plus a registration test pinning them to the shipped prompt text.
- Added `tests/evals/completion-terminal-runtime-fixtures.json`, a regex-based regression backstop for the completion-tail phrases, using the existing `eval_runtime_parity.py` fixture schema; explicitly scoped out the semantic (model-graded) response-reopening assertion kind the issue also asks for, since implementing it is a separate capability lift, not part of this PR.
- Regenerated all mirrors (`build/scripts/build_all.py`) after every canonical edit and reconciled `docs/agent-catalog.md`.

### Commits
- 4974684 fix(rules): add task-completion contract and completion-tail audit
- 2798f79 fix(critic): replace manufactured-finding quota with exhaustive inspection
- 94ec3e3 fix(qa): replace manufactured-finding quota with exhaustive inspection
- 7891525 fix(orchestrator): note terminal predicate as completion gate, budget as backstop
- 470ade5 docs(governance): add failure-mode pattern for post-completion continuation
- 34aa67e test(eval): add terminal-predicate scenarios for critic, qa, orchestrator
- 50d9fef test(eval): add completion-tail regression fixtures for runtime parity
- af52558 Merge remote-tracking branch 'origin/main' into claude/autoplan-4mqusg
- 3ff4f3b fix(rules): tighten task-completion contract prose to clear instruction budget
- 8bfdfaf fix(tests): resolve ruff findings in completion-terminal test files
- f97798c fix(docs): update always-on corpus byte figures for builder-ethos/voice
- 004795f chore(build): regenerate mirrors for updated always-on corpus figures

## Phase 1: Insights Generated

### Five Whys (the instruction-budget overflow)
1. `uv run python scripts/validation/pre_pr.py` was not run until after the first four content commits were already staged conceptually, so the overflow surfaced late in the session rather than immediately after the first edit.
2. `builder-ethos.md`/`voice.md` are `applyTo: "**"`, so any byte added to them is charged against every language's always-on ceiling (`.py`, `.ps1`, `.cs`, `.md`), not just markdown.
3. The initial draft of the Task Completion Contract and Completion-Tail Audit sections used full prose (tables, ASCII precedence diagrams, worked anti-pattern examples) sized for readability, not for a shared byte budget with zero slack.
4. Nothing in the editing workflow checked `instruction_budget.py` incrementally after each addition to a universally-scoped rule; it was only checked once, near the end.
5. Root cause: no per-edit checkpoint against a shared, finite resource (the always-on corpus ceiling) when editing a file that everyone else's PRs also compete for.

### Patterns and Shifts
- Adding substantive policy to an `applyTo: "**"` rule is not free; it recurs across `.py`, `.ps1`, `.cs`, and `.md` simultaneously, so a rule addition that looks small in isolation can tip a shared ceiling that has no per-file signal.
- Byte-figure claims that are quoted verbatim as prose (not computed at read time) create a cluster of documents that must all move together. Three separate files (`canonical-source-mirror.md`, `model-context-doctrine.md`, a Serena memory) all quoted the same numbers and all needed the same fix.

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Ran the full `pre_pr.py` gate before pushing rather than assuming green | Caught the instruction-budget overflow, 3 ruff findings, and 10 stale doctrine-figure assertions before they reached CI | 9 | 90% |
| Measured before guessing when trimming prose | Used `instruction_budget.py` after every trim round instead of estimating byte counts by eye; converged in 4 rounds instead of overshooting or undershooting | 8 | 85% |
| Declined to "fix" unrelated CRLF churn on two other issues' handoff files | Normalizing surfaced a pre-existing em-dash violation in unrelated content; reverted immediately rather than expanding scope to fix it | 8 | 80% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Wrote the full-prose version of the two new rule sections before checking the instruction budget | Late-detected regression | No incremental budget check while editing an `applyTo: "**"` file | Run `instruction_budget.py` after the first substantive edit to any universally-scoped rule, not only before push | 75% |
| Did not anticipate that trimming `builder-ethos.md`/`voice.md` would require also updating byte figures quoted in three other documents | Missed cross-file consequence | The self-referential doctrine documents are not colocated with the rules they describe | Grep for the rule's own byte figures (`grep -rn "<old byte count>"`) immediately after any edit that changes a universally-scoped rule's size | 70% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Push failed with a shallow-clone error from `push-ref-policy` | The hook's own error message named the fix (`git fetch --unshallow origin`); ran it and re-pushed | A shallow clone is a session/container property, not a branch property; check for it early in a fresh session rather than discovering it at push time |
| `run_retrospective.py`'s auto-generated Phase 0 "Work Items" described an unrelated prior session (`pragmatic-programmer.md`/`ci-scripts.md`) | Noticed the mismatch against this session's actual commits, discarded the generated skeleton, and hand-wrote the Phase 0-3 content | An auto-generated retrospective skeleton's narrative fields are not self-verifying; check them against the actual commit list before trusting them |

## Phase 3: Decisions

### Action Classification
| Class | Action | Owner | Reference |
|-------|--------|-------|-----------|
| Keep | Task Completion Contract (builder-ethos.md) + Completion-Tail Audit (voice.md), critic/qa quota removal, orchestrator cross-reference, FAILURE-MODES.md pattern 12 | Issue #5404 implementation | commits 4974684, 2798f79, 94ec3e3, 7891525, 470ade5 |
| Keep | Verdict/classification eval scenarios and regex-based completion-tail runtime fixtures | Issue #5404 implementation | commits 34aa67e, 50d9fef |
| Defer | Semantic (model-graded) response-reopening assertion kind for `eval_runtime_parity.py` | Follow-up issue, not filed yet: flagged explicitly in the fixture's `_scope_note` and in `scripts/eval/README.md` | tests/evals/completion-terminal-runtime-fixtures.json |
| Drop | CRLF/LF normalization of two unrelated handoff files (issues #4789, #5361) | Out of scope; would have required also fixing a pre-existing em-dash violation in unrelated content | reverted, not committed |

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Universally-scoped rule edits (`applyTo: "**"`) must be sized against the always-on instruction budget before committing; adding a task-completion contract to `builder-ethos.md` and a completion-tail audit to `voice.md` pushed `.py` and `.ps1` past `scripts/validation/instruction_budget.py`'s ceiling and required several rounds of prose tightening to clear it with the 600-byte merge-safety reserve.
- **Atomicity Score**: 85%
- **Evidence**: `uv run python scripts/validation/instruction_budget.py` reported `.py` at 102.0% (FAIL, -1984 bytes headroom) after the first draft; four tightening rounds converged to 99.4% (631 bytes headroom, above the 600-byte reserve). Commit 3ff4f3b.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a (new)

### Learning 2
- **Statement**: Byte-figure claims quoted verbatim across `canonical-source-mirror.md`, `model-context-doctrine.md`, and a Serena memory must all be re-measured and updated together whenever the rule files they describe change size; `tests/validation/test_always_on_corpus_claims.py` catches drift in any one of them.
- **Atomicity Score**: 85%
- **Evidence**: 10 test failures in `test_always_on_corpus_claims.py` after the rule edits, spanning mirror bytes, source bytes, the largest-rule figure, and the 8KB-threshold multipliers; fixed in commit f97798c plus the companion regen in 004795f.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a (new)

### Learning 3
- **Statement**: A shallow git clone blocks the `push-ref-policy` pre-push gate with a plain push failure; `git fetch --unshallow origin` is the documented fix in the hook's own error message, not a workaround to avoid.
- **Atomicity Score**: 75%
- **Evidence**: `git push` failed with `ERROR: push validation requires complete Git history` naming the exact remedy; `git fetch --unshallow origin` resolved it and the push succeeded on retry.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a (new)

### Learning 4
- **Statement**: Pre-existing CRLF/LF churn on files unrelated to the current task is not a free fix: normalizing it surfaced a pre-existing em-dash policy violation in unrelated content, which would have expanded scope into files outside the issue. Leaving it alone was correct.
- **Atomicity Score**: 70%
- **Evidence**: Staging the normalized files tripped `staged-dash-policy` on a prohibited dash already present in each handoff's title line (issues #4789, #5361 handoffs), neither of which this session touched otherwise; reverted with `git reset` + `git checkout --`.
- **Skill Operation**: ADD
- **Target Skill ID**: n/a (new)

## Phase 5: Persist and Close

### +/Delta

#### + Keep
- Running `pre_pr.py` in full before push, in the background, rather than trusting individual gate scripts in isolation.
- Measuring exact figures with the repo's own helper functions (`always_on_corpus_helpers.py`, `instruction_budget.py`) instead of estimating byte deltas by eye.

#### Delta Change
- Check `instruction_budget.py` immediately after the first substantive edit to any `applyTo: "**"` rule, not only once near the end of the session.
- When editing a rule with known self-referential doctrine documents (per `canonical-source-mirror.md`'s own "Read frontmatter with a YAML parser" and "always-on membership" sections), grep for its current byte figures before editing so the update list is known upfront instead of discovered via test failure.

### ROTI Assessment
**Score**: 3

**Benefits Received**:
- Shipped the full scope of issue #5404's core deliverable (task-completion contract, completion-tail audit, consumer reconciliation, failure-mode catalog entry, eval coverage) in one session, fully green against the repo's own gates.
- Concretely learned the always-on-budget interaction for universally-scoped rules, useful for any future edit to `builder-ethos.md`, `voice.md`, `universal.md`, `claude-model-patches.md`, `code-quality.md`, or `search-before-building.md`.

**Time Invested**: ~1 session (multi-hour, spanning a worker restart).

**Verdict**: Continue

### Helped, Hindered, Hypothesis

#### Helped
- The repo's own measurement tools (`instruction_budget.py`, `always_on_corpus_helpers.py`) gave exact, reproducible numbers to trim against instead of guessing.
- `_runtime_parity.py`'s existing fixture schema (positive/negative controls validated offline via `load_fixtures`) made the completion-tail regression fixtures tractable without needing a live CLI in this sandbox.

#### Hindered
- The `copilot` CLI binary is not installed in this sandbox, so the runtime-parity fixtures could be validated structurally (schema, control discrimination) but not run live against both harnesses; this is reported honestly rather than claimed as a pass.
- `run_retrospective.py`'s auto-generated Phase 0 content described a different, unrelated session and had to be discarded and hand-written.

#### Hypothesis
- Wiring a lightweight instruction-budget check into the editing loop itself (not just pre-push) for any file matching `applyTo: "**"` would catch this class of overflow at the point of the edit instead of at the pre-PR gate.
