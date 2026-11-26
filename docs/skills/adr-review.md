# adr-review

Runs a structured debate among up to six agents on an Architecture Decision Record (ADR). It ends in a consensus verdict, a debate log, and an updated ADR.

## When to use it

- You created, edited, or deleted an ADR.
- You want to review, accept, or update a decision file under `.project-toolkit/architecture/`, `docs/architecture/`, `docs/decisions/`, `docs/adr/`, or `architecture/decisions/`.
- You say `review this ADR`, `validate ADR-005`, `review this decision record`, or `check this rationale for future maintainers`.
- You are deleting an ADR and need the impact and archive checks.

## When not to use it

- You want to write a new ADR: use [`adr-generator`](adr-generator.md) instead.
- You want to challenge one decision's reasoning, outside the ADR process: use [`decision-critic`](decision-critic.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:adr-review`. The agent loads it when your request matches, and when an ADR file changes. To ask for it by name, say:

```text
Use the adr-review skill to review .project-toolkit/architecture/ADR-005-api-versioning.md.
```

The agents review the ADR in rounds. At the end you get a debate log and an updated ADR status. A session-start hook and the pre-commit hook also remind you when ADR files change.

## What you get

- A debate log at `.project-toolkit/critique/ADR-NNN-debate-log.md`.
- After a closed debate, a revised ADR gets a new log (`ADR-NNN-debate-log-2.md`, then `-3`). The new log restarts at round 1 and names the closed log. The skill never overwrites a closed log.
- An ADR `status` set to one of `proposed`, `accepted`, `rejected`, `deprecated`, or `superseded`. A missing or out-of-enum value is a P1 blocker.
- A reset `review-by` when the review accepts a `proposed` record: `null`, or a revisit date the prose also states. A kept decision date fails the lifecycle gate once it passes.
- Recommendations for the orchestrator, and recorded dissent for any Disagree-and-Commit vote.

Consensus means all six agents vote Accept or Disagree-and-Commit. A debate has at most 10 rounds. Revising the ADR text does not reset the cap.

Issues are ranked by priority:

| Priority | Requirement | Gate |
| --- | --- | --- |
| P0 | Must resolve | Blocking |
| P1 | Resolve, or defer with a reason in the debate log | Blocking |
| P2 | Document | Non-blocking |

A change to `accepted` must carry debate-log evidence in the same change. A hand edit to `accepted` with no log is a forgeable approval and gets rejected.

## Advanced use

### Panel

The panel size follows the repository rule in [`AGENTS.md`](../../AGENTS.md). The full six-agent panel runs when the ADR change touches executable enforcement or a rule other gates read. A prose-only or metadata-only edit takes a reduced panel of `architect` and `critic`. Any edit that is not frontmatter-only still needs the staged debate log.

| Agent | Focus |
| --- | --- |
| [`architect`](../agents/architect.md) | Structure, governance, coherence, ADR compliance |
| [`critic`](../agents/critic.md) | Gaps, risks, alignment, completeness |
| [`independent-thinker`](../agents/independent-thinker.md) | Challenges assumptions, surfaces contrarian views |
| [`security`](../agents/security.md) | Threat models and security trade-offs |
| [`analyst`](../agents/analyst.md) | Root cause, evidence, feasibility |
| [`high-level-advisor`](../agents/high-level-advisor.md) | Priority, conflict resolution, tie-breaks |

The debate runs in five phases: Phase 0 searches related issues and pull requests, Phase 1 is independent review with the Zimmermann seven-question checklist, Phase 2 consolidates and flags review anti-patterns, Phase 3 proposes updates for P0 and P1 issues, and Phase 4 is the convergence vote (Accept, Disagree-and-Commit, or Block). A strategic review then checks four lenses, each scored PASS, FAIL, or N/A: Chesterton's Fence, Path Dependence, Core vs Context, and Second-System Effect. The strategic verdict is `APPROVED`, `CONCERNS`, or `REJECTED`.

### Review guidance from Zimmermann

Phases 1 and 2 use Olaf Zimmermann's article ["How to review Architectural Decision Records (ADRs)"](https://www.ozimmer.ch/practices/2023/04/05/ADRReview.html), subtitled "and how not to" (2023, updated 2026). The same guidance helps when you review an ADR yourself or read a debate log. The skill's [reference file](../../src/claude/skills/adr-review/references/zimmermann-review-guidance.md) holds the full adaptation.

**Pick the review perspective first.** The article names at least three reviewer roles. Rigor rises with each one, and a mismatch between the review you asked for and the one you got can cause surprises and tension.

| Perspective | Ask for it when |
| --- | --- |
| Friendly peer or coach | You want early feedback while you still write the ADR. |
| Official stakeholder | You want to confirm the decision will work and has a chance to win agreement. |
| Formal design authority | You can defend an agreed decision and need formal approval. |

The reference file maps this skill's debate to the stakeholder perspective by default, with `high-level-advisor` as the design authority when needed. In Phase 2, conflicts between agents go to `high-level-advisor` for a ruling.

**Phase 1: the seven questions.** Every agent must answer each one:

1. Is the problem relevant enough to solve and record in an ADR?
2. Do the options have a chance to solve the problem? Are valid options missing?
3. Are the decision drivers (criteria) mutually exclusive and collectively exhaustive?
4. If the criteria conflict, are they prioritized?
5. Does the chosen option solve the problem? Is the rationale sound and convincing?
6. Are the good and bad consequences reported as objectively as possible?
7. Is the decision actionable and traceable to requirements? Does it set a validity period or review date?

The article adds two checks. Look for subjective words, ambiguity, and loopholes in the ADR's wording. Ask whether the decision is really done. If the ADR template has no field a question needs, that gap is a finding too.

**Phase 2: the seven anti-patterns.** Consolidation checks each agent's review for these. A flagged agent must review again and answer the seven questions.

| Anti-pattern | Sign in a review |
| --- | --- |
| Pass Through | Few or no real findings. Variant: Over-Friendliness, all comments positive and some shallow. |
| Copy Edit | Only wording and grammar, no content. |
| Siding or Dead End | Drifts off the decision, then stops with no advice. |
| Self Promotion | Pushes the reviewer's own work or favored option without objective reasons. |
| Power Game | Rank or past experience in place of technical argument. |
| Offended Reaction | Subjectively defends a position the ADR's rationale criticizes. Variant: "Hate To Say I Told You So." |
| Groundhog Day | Repeats the same point across rounds. |

**How to write findings.** The article gives 14 practices in four themes. The reference file lists them as guidance; no debate phase checks them.

- Scope: review only what is ready and asked for. Rank findings by importance. The article suggests H/M/L or 1/2/3; this skill uses P0, P1, and P2. Record what you reviewed and its version.
- Content: tie each finding to a quality such as consistency or completeness. Judge the decision by the context it was made in. Be concrete: "evaluate the performance of O1 in more depth" beats "O1 needs work."
- Style: ask questions and suggest options, not commands. Report what you saw, not guesses about root causes. Be at least as factual and thorough as the ADR itself. Say what works as well as what does not. Stay polite.
- Actionability: pair each finding with a recommendation. Mark comments FYI or action required. Offer an example for missing content. Reread your comments: could you fix the ADR from them alone?

A footnote passes on a student's observation that longer review subjects draw fewer comments. Choose how much of the ADR log to share, and split a large log. The article also proposes a reviewer pledge, whose last line is "Review like you want to be reviewed." Its 2026 update offers a reusable ADR review prompt template that addresses [Ten Common Mistakes in Architectural Decision Records (ADRs)](https://www.ozimmer.ch/practices/2026/09/12/ADRMistakes.html).

### Deleting an ADR

Deleting an ADR follows four steps: detect the deletion, assess impact on dependent records, archive an accepted ADR, and clean up references.

### Detecting ADR changes

To list pending ADR changes yourself, run the detector from the root of a checkout of this repository:

```bash
uv run python .claude/skills/adr-review/scripts/detect_adr_changes.py --include-untracked
```

| Flag | Meaning |
| --- | --- |
| `--base-path BASE_PATH` | Repository root path. Defaults to the current directory. |
| `--since-commit SINCE_COMMIT` | Commit to compare against. Defaults to `HEAD~1`. |
| `--include-untracked` | Include untracked new ADR files. |

| Exit code | Meaning |
| --- | --- |
| 0 | Success, whether or not changes were found |
| 1 | Not a git repository, or an unexpected error |
| 2 | A file or directory is missing |
| 3 | `git diff` failed (including an unknown `--since-commit`) or another I/O failure |

When the skill was auto-triggered by a file change, `HasChanges` is `true`. On a manual review of a committed ADR, `HasChanges: false` is expected.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`adr-generator`](adr-generator.md): writes the ADR this skill reviews.
- [`decision-critic`](decision-critic.md): challenges a single decision outside the ADR flow.
- [`buy-vs-build-framework`](buy-vs-build-framework.md): sends its final decision here for multi-agent consensus.
- Source: [`SKILL.md`](../../src/claude/skills/adr-review/SKILL.md)
- References: [`debate-protocol.md`](../../src/claude/skills/adr-review/references/debate-protocol.md), [`zimmermann-review-guidance.md`](../../src/claude/skills/adr-review/references/zimmermann-review-guidance.md)
- Source article: Olaf Zimmermann, ["How to review Architectural Decision Records (ADRs)"](https://www.ozimmer.ch/practices/2023/04/05/ADRReview.html), subtitled "and how not to", and its companion on [creating ADRs](https://www.ozimmer.ch/practices/2023/04/03/ADRCreation.html)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
