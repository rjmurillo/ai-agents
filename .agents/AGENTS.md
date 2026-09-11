# .agents/

Agent artifacts and governance. Not a plugin root. Most subtrees are history: skip unless the
task names them. Rules firing here: `session-logs.md`, `token-economy.md`, `governance.md`
(`governance/`), `retros.md` (`retrospective/`), `secret-redaction.md` (`sessions/`,
`retrospective/`), `tool-use-hook-bar.md` (`architecture/`).

## Live

| Path | Role | Gate |
|---|---|---|
| `governance/PROJECT-CONSTRAINTS.md` | Index of record for constraints; read at session start | Human approval; ADR for policy changes |
| `governance/*.md` | FAILURE-MODES, TESTING-RIGOR, GENERATOR-FILES, CI-FEEDBACK-SUBLOOP, GOTCHAS, naming-conventions, SKILL-CREATION-CRITERIA, DOCUMENTATION-LINK-REQUIREMENTS | Every normative line needs an evidence anchor |
| `architecture/ADR-NNN-*.md` (108) | Decisions; YAML `status` is truth; `README.md` is GENERATED | Any edit fires `adr-review` (pre-commit); `check_adr_links.py`, `check_adr_uniqueness.py`, lifecycle ratchet |
| `sessions/handoffs/<date>-<issue>-handoff.md` | Per-issue continuity: read latest at start, update at end | `session` hook |
| `specs/` | EARS requirements, design, tasks (`REQ-NNN`) | `check_spec_id_uniqueness.py`, traceability gate, `ai-spec-validation.yml` |
| `steering/` | Context guidance; `claude-skills.md` is the skill schema authority | |
| `memory/episodes/` (751) | Auto-extracted by pre-commit `extract-episodes`; read via memory skill | Never hand-edit |
| `security/` | Threat models, security reviews; `benchmarks/` is a test location | `security.md` rule |
| `schemas/` | `session-log`, `skill-output`, `pr-quality-gate-output`, `workflow`, `policy`, `evidence-entry` JSON schemas | |
| `templates/`, `prompts/`, `skills/`, `skillbook/`, `dictionaries/` | Doc templates, prompt sources, learned skills, spell dictionaries | |

## Historical or write-only (skip)

`sessions/*.json` (creation discontinued; validate-if-present) | `archive/` | `retrospective/`
(write via `retro` or `retrospective` skill; latest auto-injected at SessionStart) | `critique/`
`analysis/` `qa/` `planning/` `plans/` `projects/` `audits/` `audit/` `checkpoints/`
`eval-results/` `metrics/` `pr-checks/` `pr-consolidation/` `incidents/` `devops/` `debt/`
`decisions/` `benchmarks/` `roadmap/` `handoffs/` | `recovery-hints.yaml` `workflow-context.json`.
Stale-script-ref and doc-interpreter gates exclude these roots; treat contents as evidence, not instructions.

## Naming (`governance/naming-conventions.md`)

ADR `ADR-NNN-kebab.md` | PRD `PRD-name.md` | plan, analysis, critique `NNN-topic-*.md` |
retro `YYYY-MM-DD-topic.md` | threat model `TM-NNN-*.md` | requirement `REQ-NNN-title.md` | task `TASK-EPIC-NNN-MM`.

## Traps

- Markdownlint ignores `.agents/**`; the dash ban and `DOCUMENTATION-LINK-REQUIREMENTS.md` (relative links, not bare paths) still apply.
- Do not create JSON session logs (`session-logs.md` MUST-1); record `endingCommit` in a follow-up commit, never by amend.
- `validate-planning-artifacts.yml` fires on `planning/**`: estimate divergence, orphan conditions, task coverage.
- Serena memory writes from a linked worktree land in the activating checkout (universal MUST NOT 10).
