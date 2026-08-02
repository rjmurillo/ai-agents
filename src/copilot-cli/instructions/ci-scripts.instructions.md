---
applyTo: scripts/validation/**,scripts/**,.github/workflows/**,.github/actions/**,build/**,src/copilot-cli/skills/**/scripts/**,src/copilot-cli/skills/**/tests/**
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
7. **Verify worktree identity before writing**. A script that resolves the repository root and then writes to it MUST confirm the current directory is inside the resolved root before the first write (`Path.cwd().resolve().is_relative_to(top_level)`). `git rev-parse --show-toplevel` reports a claim, not a fact about where you are: a local `core.worktree` value or a `GIT_WORK_TREE` environment variable redirects it to a directory you are not standing in, and `git status` then reports every tracked file as deleted because it is looking somewhere else. Measured: an ordinary `git worktree add` sets neither, a moved worktree still resolves correctly, and a worktree whose main checkout moved away fails closed with a non-zero exit. So the redirection is always something a person or a tool set on purpose, which is exactly why a script that inherits it has no way to notice.
8. **Anchor helper resolution on the absolute top level**. A resolver that walks candidate roots to find a repository helper MUST anchor its in-repo rung on `git rev-parse --show-toplevel`, and MUST order that rung ahead of any out-of-repo root. A bare relative `.claude` rung only resolves when cwd happens to be the repository root; invoked from a subdirectory it falls through to a copy under `~/.copilot/installed-plugins` or `~/.claude/plugins/cache`, which can be arbitrarily old. `check_skill_resolver_anchoring.py` enforces this for `SKILL.md` resolvers; the same requirement binds resolvers written anywhere else, where nothing enforces it for you.
9. **Read the state you are asserting about, and name the ref**. A claim about what the repository *contains* MUST be computed from a named ref: `git ls-tree -r -z --name-only HEAD` for a path inventory, the full `git ls-tree -r -z HEAD` wherever entry mode matters, and `git log HEAD` for history. Use `-z`; paths are not newline-safe, and `--name-only` hides modes, so the tracked `memory_enhancement` symlink is indistinguishable from a regular file. Such a claim MUST NOT come from `git log --all` or from a directory walk. `--all` reads every ref the clone holds rather than the branch: at diagnosis this clone held 2054 `refs/remotes/pr/*` refs while `remote.origin.fetch` covered only branch heads, and deleting one of them flipped a shipped test from failing to passing without changing a byte of the repository (Issue #3753). Prefer `HEAD` to `origin/main`, since a guard scoped to the base branch cannot see what the current change does. Reads of the working tree, the index, and untracked files remain correct and required wherever that state is itself the subject, as in regeneration drift and pre-commit checks. Their findings describe local state and MUST NOT be restated as claims about a ref: a directory walk reported three skills as unusable when what remained on disk was untracked residue from a deletion in PR #2359, and the resulting Issue #3420 was closed NOT_PLANNED.

## SHOULD

1. **Thin workflows**. Workflow YAML SHOULD delegate to a testable module (ADR-006). No inline multi-step logic.
2. **Logging structure**. Scripts SHOULD emit structured output (JSON or key=value) to allow automated parsing.
3. **Use skills when available**. SHOULD prefer `.claude/skills/<name>` over inline `gh`, `git`, or shell commands.

## MUST NOT

1. MUST NOT put branching logic inside YAML workflow steps (ADR-006).
2. MUST NOT commit changes that silently change validator behavior without an ADR; validators are authoritative.
3. MUST NOT skip pre-push validation when touching CI paths.
4. MUST NOT raise a count baseline (`scripts/ci/*_count_baseline.txt`) to clear a blocked push. Those ratchets exist to refuse a new error-severity violation; raising the number defeats the gate rather than satisfying it. Fix the violation, split the file, or use the rule's documented escape (`# taste-lint: ignore <rule>` with a reason, issue #3779).

## Count ratchets

A count ratchet may only fall. Two consequences follow, and both bite in practice.

**A real improvement MUST be recorded.** An unrecorded improvement leaves slack, so the next regression up to the stale number passes silently. Lower it with the per-ratchet updater, not the shared module:

```bash
uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py --update
```

`scripts/ci/count_ratchet.py --update <name>` reports success and changes nothing. Verify the file afterwards rather than trusting the message.

**The failure never names the offending file.** It reports a delta, and the remediation command it suggests prints the same aggregate. Locate the offender by diffing per-file counts against `origin/main`; the linter needs `--format json -- <files>` because with no file arguments it scans nothing and reports zero, which reads as a clean tree. Prove attribution instead of inferring it: `git rm --cached <suspect>` and re-run; if the ratchet returns OK, that file was the whole delta.

## References

- `.agents/architecture/ADR-006-thin-workflows-testable-modules.md`. Workflow pattern
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
- `scripts/validation/pre_pr.py`. Canonical pre-PR runner
- `scripts/validation/check_skill_resolver_anchoring.py`. Enforces the anchoring requirement for `SKILL.md` resolvers
- `.claude/skills/validation-authority/`. Validator-authority skill
- Issue #1711. validator change that blocked all PRs
- Issue #3402. worktree identity and stale helper resolution
- Issue #3408. a linked worktree's imported session log wedging `check_branch_context`
