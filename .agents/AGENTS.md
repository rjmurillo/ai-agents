# .agents/

Governance, planning, history; no plugin ships it.

## Matters

- Rules auto-load: `session-logs`,`token-economy`->`.agents/**`; `adr-records`,`tool-use-hook-bar`->`architecture/**`; `governance`,`push-lock`->`governance/**`; `canonical-source-mirror`->`governance/**`,`retrospective/**`; `retros`->`retrospective/**`; `secret-redaction`->`sessions/**`,`retrospective/**`; `security`->`security/**`; `testing`->`security/benchmarks/**`.
- Markdownlint ignores `.agents/**`; dash ban binds (`staged-dash-policy`). `governance/DOCUMENTATION-LINK-REQUIREMENTS.md`: relative links, unenforced. Gemini skips it (`.gemini/config.yaml`).

## Entry points

- `sessions/handoffs/<date>-<issue>-handoff.md`: read latest, update at end. Sibling `handoffs/`: separate per-branch tier (ADR-014 Tier 2).
- `AGENT-INSTRUCTIONS.md`: BLOCKING scaffold; `implementer.md`/`orchestrator.md` gate on it.
- `architecture/ADR-NNN-*.md`: YAML `status` is truth; `README.md` generated (`generate_adr_index.py`), drift-gated (`OWNED_PREFIXES`), hand-edits lost. Frontmatter ratcheted pre-PR vs committed baseline (`check_adr_lifecycle.py`, ADR-073).
- `memory/episodes/*.json`: never hand-edit; auto-staged by `extract-session-episodes` pre-commit, exempt from the 5-file atomic limit. `recovery-hints.yaml`: hand-edited `error_classification.py` data.

## Where to look

| Path | Why |
|---|---|
| `governance/` | Constraints, testing, naming; `GENERATOR-FILES.md` registers generated trees |
| `specs/` | EARS `REQ`/`TASK`/`DESIGN-NNN`; ID+traceability gated |
| `steering/` | `claude-skills.md` cited by `.claude/skills/CLAUDE.md` |

## Skip

- `sessions/*.json`, `archive/`, `retrospective/` (same-day file gates non-docs pushes); `critique/`, `metrics/`: read only when named; not all gate-exempt.
- Stray: `prototypes/`, `pr-batch-review-session-2025-12-20.md`, `workflow-context.json`. `README.md`: stale project-phase doc.

## Constraints

- `validate-planning-artifacts.yml` fires on `planning/**`: estimate divergence (20%) and orphan conditions, not task coverage.

## Dangerous assumptions

- `hooks/hooks.yaml` retired, read by nothing; `hooks/README.md` misnames the live sources. ADR-109 B4: `templates/hooks/` is the source, `.claude/hooks/` and `.claude/settings.json` generated. Copilot map: `templates/platforms/copilot-cli.yaml`.
- Gate exemptions differ: `check_doc_interpreter_portability.py` `HISTORICAL_ROOTS` and `stale_script_refs.py` omit `metrics/`, `roadmap/`, `plans/`, `handoffs/`; a bare-interpreter call of a tracked script with a non-stdlib import, or a ref to a deleted `.ps1`, fails there.
- `AGENT-SYSTEM.md` stale: `**File**:` lines cite `src/claude/<stem>.md`; live is `src/claude/agents/<stem>.md` (generated, ADR-109 B1).

## Dependencies

- `schemas/*.json` gate `skillbook/` JSON (`skillbook-validation.yml`); `tests/skillbook/conftest.py` imports `hooks/post-eval.py`.

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
