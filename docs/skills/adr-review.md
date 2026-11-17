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

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:adr-review`. The agent loads it when your request matches, and when an ADR file changes. To ask for it by name, say:

```text
Use the adr-review skill to review .project-toolkit/architecture/ADR-005-api-versioning.md.
```

The agents review the ADR in rounds. At the end you get a debate log and an updated ADR status. A session-start hook and the pre-commit hook also remind you when ADR files change.

## What you get

- A debate log at `.project-toolkit/critique/ADR-NNN-debate-log.md`.
- After a closed debate, a revised ADR gets a new log (`ADR-NNN-debate-log-2.md`, then `-3`). The new log restarts at round 1 and names the closed log. The skill never overwrites a closed log.
- An ADR `status` set to one of `proposed`, `accepted`, `rejected`, `deprecated`, or `superseded`. A missing or out-of-enum value is a P1 blocker.
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

The panel size follows the repository rule in `AGENTS.md`. The full six-agent panel runs when the ADR change touches executable enforcement or a rule other gates read. A prose-only or metadata-only edit takes a reduced panel of `architect` and `critic`. Any edit that is not frontmatter-only still needs the staged debate log.

| Agent | Focus |
| --- | --- |
| [`architect`](../agents/architect.md) | Structure, governance, coherence, ADR compliance |
| [`critic`](../agents/critic.md) | Gaps, risks, alignment, completeness |
| [`independent-thinker`](../agents/independent-thinker.md) | Challenges assumptions, surfaces contrarian views |
| [`security`](../agents/security.md) | Threat models and security trade-offs |
| [`analyst`](../agents/analyst.md) | Root cause, evidence, feasibility |
| [`high-level-advisor`](../agents/high-level-advisor.md) | Priority, conflict resolution, tie-breaks |

The debate runs in five phases: Phase 0 searches related issues and pull requests, Phase 1 is independent review with the Zimmermann seven-question checklist, Phase 2 consolidates and flags review anti-patterns, Phase 3 proposes updates for P0 and P1 issues, and Phase 4 is the convergence vote (Accept, Disagree-and-Commit, or Block). A strategic review then checks four lenses, each scored PASS, FAIL, or N/A: Chesterton's Fence, Path Dependence, Core vs Context, and Second-System Effect. The strategic verdict is `APPROVED`, `CONCERNS`, or `REJECTED`.

Deleting an ADR follows four steps: detect the deletion, assess impact on dependent records, archive an accepted ADR, and clean up references.

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
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
