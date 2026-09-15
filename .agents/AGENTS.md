# .agents/

Governance, planning, history; no plugin ships it.

## Matters

- Rules auto-load: `session-logs.md`,`token-economy.md`->`.agents/**`; `governance.md`->`governance/**`; `retros.md`->`retrospective/**`; `secret-redaction.md`->`sessions/**`,`retrospective/**`; `tool-use-hook-bar.md`->`architecture/**`; `security.md`->`security/**`; `testing.md`->`security/benchmarks/**`.
- Markdownlint ignores `.agents/**`; dash ban binds (`staged-dash-policy`). `governance/DOCUMENTATION-LINK-REQUIREMENTS.md` demands relative links, unenforced. Gemini skips the tree (`.gemini/config.yaml`).

## Entry points

- `sessions/handoffs/<date>-<issue>-handoff.md`: read latest, update at end. Sibling `handoffs/`: separate per-branch tier (ADR-014 Tier 2).
- `AGENT-INSTRUCTIONS.md`: BLOCKING scaffold; `implementer.md`/`orchestrator.md` gate on it.
- `architecture/ADR-NNN-*.md`: YAML `status` is truth; `README.md` generated (`generate_adr_index.py`), hand-edits lost. New: number from `check_adr_uniqueness.py --print-next`; frontmatter ratcheted pre-PR vs committed baseline (`check_adr_lifecycle.py`, ADR-073).
- `memory/episodes/*.json` (regenerated, auto-staged by `extract-session-episodes` pre-commit; exempt from the 5-file atomic limit), `recovery-hints.yaml` (`error_classification.py` data): never hand-edit, not docs.

## Where to look

| Path | Why |
|---|---|
| `governance/*.md` | Constraints, testing, generators, naming |
| `specs/` | EARS `REQ`/`TASK`/`DESIGN-NNN`; ID+traceability gated |
| `steering/` | `claude-skills.md` cited by `.claude/skills/CLAUDE.md` |

## Skip

- `sessions/*.json`, `archive/`, `retrospective/` (write via `retrospective` skill), other history dirs (`critique/`, `metrics/`): read only when named; not all CI-gate-exempt.
- Stray: `prototypes/`, `.hook-state/` (gitignored), `pr-batch-review-session-2025-12-20.md`, `workflow-context.json`. `README.md`: stale project-phase doc.

## Constraints

- `validate-planning-artifacts.yml` fires on `planning/**`: estimate divergence (20%) and orphan conditions, not task coverage.

## Dangerous assumptions

- `hooks/hooks.yaml` is a retired inventory nothing reads (`hooks/README.md`). Live: `.claude/settings.json`, `.claude/hooks/`, `templates/platforms/copilot-cli.yaml`.
- Historical dirs not uniformly gate-exempt: `check_doc_interpreter_portability.py` `HISTORICAL_ROOTS` and `stale_script_refs.py` omit `metrics/`, `roadmap/`, `plans/`, so a documented `python3 <tracked>.py` importing a non-stdlib module is ratcheted there.
- `AGENT-SYSTEM.md` stale: `**File**:` lines cite `src/claude/<stem>.md`; live is `src/claude/agents/<stem>.md` (generated, ADR-109 B1).

## Dependencies

- Rule owners: `session-logs.md`, `governance.md` (Matters).

## Architecture

- Distinct trees: `skills/` (steering learnings), `skillbook/` (policy/tension/workflow JSON), `.claude/skills/` (catalog).

## Commands

```bash
uv run python scripts/validation/pre_pr.py
uv run python scripts/validation/check_adr_links.py
uv run python scripts/validation/check_adr_uniqueness.py --print-next
uv run python scripts/validation/check_spec_id_uniqueness.py
uv run python scripts/validate_session_json.py <path-to-log>
```
