---
applyTo: "scripts/validation/**,scripts/**,.github/workflows/**,.github/actions/**,build/**"
priority: high
---

# CI and Validation Script Rules

Scripts under `scripts/validation/`, `build/`, and `.github/workflows/` gate every PR. A broken change here blocks the entire repository (see Issue #1711).

## MUST

1. **Local run before commit** — CI-critical scripts MUST be exercised locally before commit. Use `gh act` for workflows, direct `python3` invocation for validation scripts, and the actual test suite for helpers.
2. **Shift-left validation** — Before pushing, MUST run `python3 scripts/validation/pre_pr.py` and resolve any failures.
3. **Python for new scripts** — New scripts MUST be Python per ADR-042. MUST NOT create new `*.sh` bash scripts.
4. **Exit codes** — Scripts MUST follow the exit code contract: `0`=ok, `1`=logic, `2`=config, `3`=external, `4`=auth (`AGENTS.md`).
5. **Tests required** — New validation scripts MUST ship with pytest or Pester coverage in `tests/` or `.claude/skills/<name>/tests/`.
6. **Pin Actions to SHA** — Workflow changes MUST pin every Action reference to a commit SHA.

## SHOULD

1. **Thin workflows** — Workflow YAML SHOULD delegate to a testable module (ADR-006). No inline multi-step logic.
2. **Logging structure** — Scripts SHOULD emit structured output (JSON or key=value) to allow automated parsing.
3. **Use skills when available** — SHOULD prefer `.claude/skills/<name>` over inline `gh`, `git`, or shell commands.

## MUST NOT

1. MUST NOT put branching logic inside YAML workflow steps (ADR-006).
2. MUST NOT commit changes that silently change validator behavior without an ADR; validators are authoritative.
3. MUST NOT skip pre-push validation when touching CI paths.

## References

- `.agents/architecture/ADR-006-thin-workflows-testable-modules.md` — workflow pattern
- `.agents/architecture/ADR-042-python-migration-strategy.md` — Python-first
- `scripts/validation/pre_pr.py` — canonical pre-PR runner
- `.claude/skills/validation-authority/` — validator-authority skill
- Issue #1711 — validator change that blocked all PRs
