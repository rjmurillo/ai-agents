# .agents/

Agent governance, planning, and history for the `rjmurillo/ai-agents` repository. Consumed by contributors, CI validators, and skills (`retrospective`, `memory`); never shipped to a plugin consumer.

## Matters

- Not a plugin root. Nothing under here reaches an installed `.claude/`, `src/claude/`, or `src/copilot-cli/` consumer.
- Most subtrees are history or write-only; read one only when the task names it (see Skip).
- `governance/PROJECT-CONSTRAINTS.md` is the index of record; read it before acting on anything governance-shaped.
- ADR `status` in YAML frontmatter is truth; `architecture/README.md` is generated from it, never hand-edited.
- Session log creation is discontinued; do not create a new `.agents/sessions/*.json` file.
- Markdownlint ignores `.agents/**` (`.markdownlint-cli2.yaml`), but the dash ban and `governance/DOCUMENTATION-LINK-REQUIREMENTS.md` (relative links, not bare paths) still bind.
- Rules that fire here by `paths:` scope: `session-logs.md`, `token-economy.md` (`.agents/**`), `governance.md` (`governance/**`), `retros.md` (`retrospective/**`), `secret-redaction.md` (`sessions/**`, `retrospective/**`), `tool-use-hook-bar.md` (`architecture/**`), `security.md`/`testing.md` (`security/**`, `security/benchmarks/**`).

## Entry points

- `governance/PROJECT-CONSTRAINTS.md`: read at session start (root `AGENTS.md` Gates).
- `sessions/handoffs/<date>-<issue>-handoff.md`: read the latest at start, update at end.
- `architecture/ADR-NNN-*.md` (108 tracked): check `status` before citing a decision as active.
- `memory/episodes/*.json` (750 tracked): auto-extracted; read through the `memory` skill, never hand-edit.

## Where to look

| Path | Why |
|---|---|
| `governance/*.md` | Constraints, testing rigor, generator files, CI feedback subloop, naming; every normative line needs an evidence anchor |
| `architecture/ADR-NNN-*.md` (108) | Decision records; YAML `status` is truth, `README.md` is generated |
| `sessions/handoffs/` | Per-issue continuity: read latest at start, update at end |
| `specs/` | EARS requirements: `REQ-NNN`, `TASK-NNN`, `DESIGN-NNN`; `check_spec_id_uniqueness.py` and `traceability.py` gate it |
| `steering/claude-skills.md` | Skill schema authority |
| `memory/episodes/` (750) | Auto-extracted by pre-commit `extract-episodes`; never hand-edit |
| `security/` | Threat models (`TM-NNN`), reviews; `benchmarks/` is a test location, not docs |
| `schemas/` | JSON schemas: session-log, skill-output, pr-quality-gate-output, workflow, policy, evidence-entry |
| `hooks/` | Retired Phase 1 hook inventory; see Dangerous assumptions before trusting it |

## Skip

- `sessions/*.json`: session log creation discontinued; validate-if-present only.
- `archive/`: closed history; `retrospective/` writes go through the `retro`/`retrospective` skill only.
- `critique/`, `analysis/`, `qa/`, `planning/`, `plans/`, `projects/`, `audits/`, `audit/`, `checkpoints/`, `eval-results/`, `metrics/`, `pr-checks/`, `pr-consolidation/`, `incidents/`, `devops/`, `debt/`, `decisions/`, `benchmarks/`, `roadmap/`, `handoffs/`: write-only or historical; stale-script-ref and doc-interpreter gates exclude these roots, so treat contents as evidence, not instructions.
- `prototypes/`: A/B compression candidates (issue #1738), not the active agents in `.claude/agents/`.
- `.hook-state/`: gitignored runtime log directory, not tracked.
- `pr-batch-review-session-2025-12-20.md`: stray root file, historical.

## Constraints

- Any `ADR-*.md` edit fires the `adr-review` skill (root `AGENTS.md`).
- `governance/**` changes need human approval, an ADR for a new rule or policy reversal, and consensus for cross-role rules (`governance.md`); no single agent may alter rules governing another unilaterally.
- Never amend a commit that already carries a recorded `endingCommit`; commit the SHA in a follow-up commit instead (`session-logs.md` MUST-2), and re-point it after any rebase (MUST-3).
- `validate-planning-artifacts.yml` fires on `planning/**`: estimate divergence, orphan conditions, task coverage.
- `sessions/**` and `retrospective/**` content must be secret-redacted before it is written (`secret-redaction.md`).
- Worktree Serena writes: behavior and the binding rule live in `.claude/rules/universal.md` MUST NOT 10; not restated here.

## Dangerous assumptions

- `hooks/hooks.yaml` looks like the live hook manifest. Its own `hooks/README.md` says otherwise: "a retired inventory. No generator or runtime reads it." The real sources of truth are `.claude/settings.json`, `.claude/hooks/`, and `templates/platforms/copilot-cli.yaml`.
- `governance/naming-conventions.md` documents a lowercase `prd-name.md` PRD pattern under `.agents/planning/`. Tracked PRDs mostly use `PRD-Name.md` (uppercase) under `specs/`, `plans/`, or `archive/planning/`; go by the tracked files, not the doc alone.
- `naming-conventions.md` defines no `TASK-EPIC-NNN-MM` pattern; the only other tracked occurrence is `.agents/archive/phase3-complete-handoff.md`, a retired PowerShell validator's pattern list. Live tasks are `TASK-NNN-<kebab-name>.md` under `specs/tasks/`.

## Dependencies

- Feeds the `retrospective` skill, memory extraction, and the PreCompact hook, which all read existing session logs under `sessions/`.
- `architecture/README.md` is generated by `build/scripts/generate_adr_index.py` (via `build/scripts/build_all.py`); a hand-edit is overwritten on next regen.
- `governance/*.md` changes should cross-link from root `AGENTS.md`/`CLAUDE.md` when they change agent defaults (`governance.md` SHOULD-2).

## Architecture

- Two "hooks" trees exist and are unrelated: `.agents/hooks/` is a retired Phase 1 inventory; `.claude/hooks/` holds the canonical scripts Claude Code actually runs. Do not edit registrations in the former.
- `.agents/skills/` (steering learnings), `.agents/skillbook/` (policies/tensions/workflows JSON), and `.claude/skills/` (the actual skill catalog) are three distinct trees; don't conflate them.

## Commands

```bash
uv run python scripts/validation/pre_pr.py
uv run python scripts/validation/check_adr_links.py
uv run python scripts/validation/check_spec_id_uniqueness.py
uv run python scripts/validate_session_json.py <path-to-log>
```
