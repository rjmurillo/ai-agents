# ADR Debate Log: ADR-101 review-honesty amendment

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: none for this amendment (the closed ADR-101 logs are cited as precedent only)
- **Outcome**: Consensus (architect Accept, critic Accept after one revision)
- **Final Status**: accepted (ADR-101 stays `accepted`; this is an amendment in its Status section)
- **Panel**: reduced panel of architect and critic, the size `adr-review` SKILL.md assigns to a prose-only or metadata-only edit
- **Records**: `.project-toolkit/architecture/ADR-101-enforcement-planes.md`, `.github/PULL_REQUEST_TEMPLATE.md`

## How this panel was run, stated plainly

The Claude CLI is not logged in on the box that prepared this change, so the `adr-review` skill could not launch its agents as separate sessions. The architect pass and the critic pass were instead performed by one agent in one session, in two separate passes, each strictly following its own definition file (`src/claude/agents/architect.md`, `src/claude/agents/critic.md`) and the Phase 1 and Phase 4 formats in `src/claude/skills/adr-review/references/`. The two passes share one model and one context, so the critic did not have the fresh-context asymmetry its definition relies on. That is the exact limitation the amendment records: this panel counts as one vote. The owner ordered it on 2026-11-01 ("Run the architect and critic panel on #7027 first"), after a bot reviewer pointed out that the first version of this log held no debate. The nine required deterministic contexts remain the assurance, which is what the amendment says.

Phase 0 related-work research was a read of the tree and of PR #7027's review threads, not a separate analyst run.

## Change under review

1. `.github/PULL_REQUEST_TEMPLATE.md`: the two "Security agent reviewed" boxes carry an `Artifact:` slot for a run URL or file path.
2. ADR-101 Status section: one dated amendment paragraph. It says the review panel counts as one vote, and that review assurance is the nine required deterministic contexts plus post-merge detection. It adds no AI reviewer and no AI check.
3. ADR-101: one doubled blank line removed so the record stays at the 500-line size cap.

## Round 1: Phase 1 independent review

### Architect review

Architecture Reasoning Protocol, answered in order:

1. Governing ADRs, found with `git grep -F -i -- "required contexts" .project-toolkit/architecture/`: ADR-101 (planes, the control plane that pins the contexts) and ADR-114 (status proposed, which treats every agent verdict as advisory and defers to ADR-101 for required-context precedence). Neither conflicts. The amendment restates a property ADR-101 already relied on (line 65 says eleven rounds of six-role panel review still shipped defects).
2. Quality attributes: the amendment buys honesty about assurance and gives up the comfort of a "6/6 consensus" number. The trade is named in the text.
3. Top failure mode in two years: a reader treats "counts as one vote" as permission to skip the panel, or treats an `Artifact:` link as a gate when no script reads it.

#### Strengths

- Sits in the Status section like the 2026-10-01 amendment, so no Decision clause moves.
- Reversible by deleting one paragraph and two template suffixes. No data, vendor or legacy impact.
- File stays at exactly 500 lines.

#### Weaknesses/Gaps

- The paragraph says nothing about whether the panel still runs, so the failure mode above is open.
- The 2026-10-01 amendment states that the invariant and Decision clauses are unchanged and names its debate log. This one did neither.
- The text relies on the nine-context script but does not say why those contexts are deterministic.

#### Scope Concerns

- None. One concern (honest statement of review assurance), two files.

#### Questions

- Where does the amendment's debate log live? It must be findable from the record.

#### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| A1: amendment does not say the panel still runs | P1 | Without it the paragraph can be read as retiring `adr-review`. |
| A2: no "Decision clauses unchanged" statement and no debate-log pointer | P1 | Breaks the pattern of the prior amendment and the traceability the ADR-073 gate expects. |
| A3: "deterministic" asserted without evidence | P2 | Cite the test that holds it. |

#### Claims Checked

| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| The script pins nine required contexts | count-or-path | `scripts/ci/ruleset_required_contexts.py`, `REQUIRED_CONTEXTS` has 9 entries; `tests/ci/test_pr_workflow_classification.py` docstring says nine | VERIFIED |
| ADR-101 cites eight in Context, the impact table and Phase 1 | count-or-path | `grep -n -w eight` on ADR-101: lines 94, 102, 118 (Context, lines 45-119), 160, 176, 193 (Decision, line 120 onward), 424 (impact table), 442 (Implementation Notes, Phase 1) | VERIFIED for the count, REFUTED for the section list: the figure also appears in Decision |
| Two Security agent boxes exist in the template | count-or-path | `.github/PULL_REQUEST_TEMPLATE.md` lines 131 and 132 | VERIFIED |
| ADR-101 is `accepted` and 500 lines | status | frontmatter line 3; `wc -l` prints 500 | VERIFIED |
| The 2026-10-01 amendment names its debate log | contract | ADR-101 Status section, last sentence of that paragraph | VERIFIED |

### Critic review

Reasoning Protocol:

1. What breaks if this is wrong: a reader believes six independent reviewers vouched for a change, or believes a checked box was verified. Both mislead the owner about assurance.
2. Constraint conflict: `adr-review` SKILL.md line 61 says consensus is "6/6 Accept or D&C". The amendment does not contradict that procedure but redefines what the tally means. The text must not read as a change to the procedure.
3. Strongest counterargument: do not amend a binding ADR for a statement of fact, put it in a README or the skill. Rejected: ADR-101's whole subject is what counts as enforcement, and a claim of assurance belongs there. The amendment must stay narrow.

Persona pass (prose artifact): Naive Reader, Hostile Expert, Cynic.

#### Strengths

- Adds no mechanism, so it has little to break.
- The count was checked against the source, not copied from the owner's direction.

#### Weaknesses/Gaps

- Hostile Expert: "all run on one model family" is asserted. `src/claude/agents/*.md` for the six roles carry no `model:` field, so the repository cannot show which model runs them. The claim is unverifiable from the tree as written.
- Naive Reader: "post-merge detection" is used with no example. A reader cannot tell what it is.
- Cynic: "now needs a link" reads as a gate. `git grep` of `scripts`, `.github/workflows`, `.github/scripts` and `tests` finds no reader of those boxes, so nothing enforces it.
- The first debate log was a statement that no debate was held. That is the process gap the bot reviewer found.

#### Scope Concerns

- None.

#### Questions

- Does any workflow parse the Security Review section of the PR body? (Answered by search: no.)

#### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| C1: the "one model family" claim is unverifiable from the repository | P1 | A REFUTED-or-UNVERIFIED factual claim is blocking under the Factual Claim Verification rules. Restate it as what the tree shows. |
| C2: "post-merge detection" undefined | P1 | Name a concrete detector and what it cannot see. |
| C3: the link requirement reads as enforced | P1 | State that no script reads the box. |
| C4: no real debate log | P1 | Replace the owner-direction log. |
| C5: section list for the eight-context citations is incomplete | P2 | The figure also appears in Decision. See the refuted row above. |

#### Claims Checked

| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| The six roles run on one model family | contract | `grep -n -E "^model" src/claude/agents/{architect,critic,independent-thinker,security,analyst,high-level-advisor}.md` prints nothing; the `adr-review` SKILL.md names no model | UNVERIFIED |
| The roles are invoked from one session | contract | `src/claude/skills/adr-review/references/debate-protocol.md` launches each role with `Task(subagent_type=...)` from the orchestrating session | VERIFIED |
| A daily post-merge detector exists | contract | `.github/workflows/check-ruleset-drift.yml` lines 3-6, cron `0 6 * * *`; comment says `GITHUB_TOKEN` cannot read `bypass_actors` and the script logs NOT OBSERVABLE | VERIFIED |
| Required workflows read no model credential | contract | `tests/ci/test_pr_workflow_classification.py::test_required_workflows_read_no_model_credential`, parametrized over `REQUIRED_WORKFLOWS` | VERIFIED |
| A script enforces the PR template review boxes | contract | `git grep -n -E "Security agent reviewed\|No security-critical changes\|Security patterns applied" -- scripts .github/workflows .github/scripts tests` finds no reader | REFUTED |
| The nine contexts are pinned at origin/main | count-or-path | `git show origin/main:scripts/ci/ruleset_required_contexts.py` (commit 23ce9bda1) | VERIFIED |

## Round 1: Phase 2 consolidation

Consensus: no mechanism is added, scope is right, the nine count is correct, and the work is reversible.

Conflicts: none between the two seats. The critic's C3 and the architect's A3 overlap on evidence for what the text claims. No high-level-advisor routing was needed.

Anti-pattern check (Zimmermann): neither pass is Pass Through (each has P1 findings), Copy Edit (findings are about claims and structure), or Groundhog Day (round 1). Self Promotion and Power Game do not apply. The critic's fresh-context limitation is recorded above rather than hidden.

## Round 1: Phase 3 resolution

| Finding | Priority | Resolution |
|---------|----------|------------|
| A1 | P1 | Added: "The panel still runs as `adr-review` requires. This amendment changes how its result is counted, not whether it runs." |
| A2 | P1 | Added: "The invariant, requirement 1 and every Decision clause are unchanged." and the debate log path. |
| A3 | P2 | Added the test `tests/ci/test_pr_workflow_classification.py` as the evidence that required contexts are deterministic. |
| C1 | P1 | Replaced "all run on one model family" with "invoked from one session, and the agent definitions under `src/claude/agents/` pin no model, so nothing in the repository makes their judgments independent." The owner's point survives (correlated, one vote) on a claim the tree supports. |
| C2 | P1 | Named `.github/workflows/check-ruleset-drift.yml` (daily) and what it cannot read (`bypass_actors`). |
| C3 | P1 | Added: "No script reads that box, so the link is a check a reader makes, not a gate." |
| C4 | P1 | This log replaces the owner-direction log. |
| C5 | P2 | The amendment listed the sections as "Context, the impact table and Phase 1". Corrected to "Context, Decision, impact table and Implementation Notes sections". |

Dissent recorded: none. Alternative rejected: a script that parses the PR body and fails on a checked Security box with no link. The owner ruled out new AI checks, and this would be a new deterministic check with its own false-block risk. It is a reasonable follow-up and is not part of this amendment.

## Round 2: Phase 4 convergence check

Changes checked: the revised ADR-101 paragraph (still one line, file still 500 lines, no em or en dashes) and the unchanged template change.

### Claims Checked (round 2, text added this round)

| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| Agent definitions pin no model | contract | the `grep` in round 1 over the six role files, and `src/claude/agents/security.md` lines 1-8 | VERIFIED |
| `check-ruleset-drift.yml` cannot read `bypass_actors` with its token | contract | workflow comment above the Run drift check step | VERIFIED |
| `tests/ci/test_pr_workflow_classification.py` fails on a required workflow that reads a model credential | contract | `test_required_workflows_read_no_model_credential` | VERIFIED |
| The debate log path in the paragraph exists | count-or-path | `ls .project-toolkit/critique/ADR-101-review-honesty-amendment-debate-log.md` | VERIFIED |
| ADR-101 is 500 lines after the edit | count-or-path | `wc -l` prints 500 | VERIFIED |

### Agent Positions

| Agent | Position | Notes |
|-------|----------|-------|
| architect | Accept | A1, A2, A3 resolved. No new claim is wrong. Reversible, within the size cap. |
| critic | Accept | C1 to C4 resolved. The model claim is now what the tree shows, the detector is named, and the text says the link is not a gate. Confidence MEDIUM, because this pass shares the author session and cannot claim fresh-context independence. |

Critic verdict in definition terms: APPROVED_WITH_CONCERNS, with the single concern that the link requirement stays unenforced. That concern is documented in the ADR text itself, so it travels with the record.

## Outcome

Consensus after 2 rounds. Final status: accepted. Unresolved P0 and P1 issues: none. Open P2: a script that enforces the link requirement is not built, by design (see Dissent recorded).
