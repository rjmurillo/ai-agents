---
paths:
  - "scripts/validation/**"
  - "scripts/**"
  - ".github/workflows/**"
  - ".github/actions/**"
  - "build/**"
priority: high
---

# CI and Validation Script Rules

Scripts under `scripts/validation/`, `build/`, and `.github/workflows/` gate every PR. A broken change here blocks the entire repository (see Issue #1711).

## MUST

1. **Local run before commit**. CI-critical scripts MUST be exercised locally before commit. Use `gh act` for workflows, direct `python3` invocation for validation scripts, and the actual test suite for helpers.
2. **Shift-left validation**. Before pushing, MUST run `python3 scripts/validation/pre_pr.py` and resolve any failures.
3. **Python for new scripts**. New scripts MUST be Python per ADR-042. MUST NOT create new `*.sh` bash scripts.
4. **Exit codes**. Scripts MUST follow the exit code contract: `0`=ok, `1`=logic, `2`=config, `3`=external, `4`=auth (`AGENTS.md`).
5. **Tests required**. New validation scripts MUST ship with pytest or Pester coverage in `tests/` or `.claude/skills/<name>/tests/`.
6. **Pin Actions to SHA**. Workflow changes MUST pin every Action reference to a commit SHA.
7. **Verify worktree identity before writing**. A script that resolves the repository root and then writes to it MUST confirm the current directory is inside the resolved root before the first write (`Path.cwd().is_relative_to(top_level)`). `git rev-parse --show-toplevel` reports a claim, not a fact about where you are: a local `core.worktree` value or a `GIT_WORK_TREE` environment variable redirects it to a directory you are not standing in, and `git status` then reports every tracked file as deleted because it is looking somewhere else. Measured: an ordinary `git worktree add` sets neither, a moved worktree still resolves correctly, and a worktree whose main checkout moved away fails closed with a non-zero exit. So the redirection is always something a person or a tool set on purpose, which is exactly why a script that inherits it has no way to notice.
8. **Anchor helper resolution on the absolute top level**. A resolver that walks candidate roots to find a repository helper MUST anchor its in-repo rung on `git rev-parse --show-toplevel`, and MUST order that rung ahead of any out-of-repo root. A bare relative `.claude` rung only resolves when cwd happens to be the repository root; invoked from a subdirectory it falls through to a copy under `~/.copilot/installed-plugins` or `~/.claude/plugins/cache`, which can be arbitrarily old. `check_skill_resolver_anchoring.py` enforces this for `SKILL.md` resolvers; the same requirement binds resolvers written anywhere else, where nothing enforces it for you.

## SHOULD

1. **Thin workflows**. Workflow YAML SHOULD delegate to a testable module (ADR-006). No inline multi-step logic.
2. **Logging structure**. Scripts SHOULD emit structured output (JSON or key=value) to allow automated parsing.
3. **Use skills when available**. SHOULD prefer `.claude/skills/<name>` over inline `gh`, `git`, or shell commands.

## MUST NOT

1. MUST NOT put branching logic inside YAML workflow steps (ADR-006).
2. MUST NOT commit changes that silently change validator behavior without an ADR; validators are authoritative.
3. MUST NOT skip pre-push validation when touching CI paths.

## References

- `.agents/architecture/ADR-006-thin-workflows-testable-modules.md`. Workflow pattern
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
- `scripts/validation/pre_pr.py`. Canonical pre-PR runner
- `scripts/validation/check_skill_resolver_anchoring.py`. Enforces the anchoring requirement for `SKILL.md` resolvers
- `.claude/skills/validation-authority/`. Validator-authority skill
- Issue #1711. validator change that blocked all PRs
- Issue #3402. worktree identity and stale helper resolution
- Issue #3408. a linked worktree's imported session log wedging `check_branch_context`
