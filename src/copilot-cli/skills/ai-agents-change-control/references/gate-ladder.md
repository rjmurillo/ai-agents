# Gate Ladder and Commit Discipline

Consult this before your first push in a session. SKILL.md Phase 3 names the ladder and the commit caps; the full rung table, the install commands, and the incident that set the caps live here.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

## Run the gate ladder, local to CI

The ladder is ordered by feedback cost. Catching a violation at rung 1 costs seconds; at rung 4 it costs an hour of CI round-trip plus reviewer attention. The enforcement-timing hierarchy is deliberate: pre-commit beats CI beats code review beats documentation.

| Rung | Gate | Command or trigger | What runs |
|------|------|--------------------|-----------|
| 1 | Shift-left runner | `uv run python scripts/validation/pre_pr.py` (`--quick` skips slow checks) | Roughly 30 validations: session end, tests, scoped markdownlint, workflow YAML, dash prohibition, plugin version field, install parity, hook anchoring. Exit codes per ADR-035: 0 pass, 1 logic failure, 2 config error (`scripts/validation/pre_pr.py` docstring) |
| 2 | Pre-commit hook | Automatic on `git commit` through Lefthook | Lefthook filters staged files and runs the named validators in `lefthook.yml` |
| 3 | Pre-push hook | Automatic on `git push` through Lefthook | Lefthook filters files in the push range and runs the named validators in `lefthook.yml` |
| 4 | CI required checks | Push and PR events | `pytest.yml`; `pr-validation.yml` (20-commit cap); `ai-pr-quality-gate.yml` (10 parallel LLM reviewers; the authoritative blocker is `scripts/quality_gate/check_critical_failures.py`, wired at `ai-pr-quality-gate.yml:735`); drift and plugin-bump workflows |

Local Git hooks only run after Lefthook is installed. Run
`uv run --frozen lefthook install --reset-hooks-path`, then verify with
`uv run --frozen lefthook check-install`. `pre_pr.py` also validates the binary,
configuration, and installed shims (`scripts/validation/checks_plugin.py`).

## Respect commit discipline

| Rule | Limit | Enforcement |
|------|-------|-------------|
| Files per commit | 5 or fewer | `.claude/rules/universal.md` MUST 4; AGENTS.md Boundaries |
| Commits per PR | Block at 20, or 40 when the branch carries a merge from main | `scripts/validation/pr_commit_count.py:58` (`BLOCK_THRESHOLD = 20`) and `:64` (`MAIN_MERGE_BLOCK_THRESHOLD = 40`, ADR-008 relief, issue #3596), wired at `pr-validation.yml:145-155`; human override only via the `commit-limit-bypass` label (`scripts/ci/enforce_pr_validation.py:11,54`) |
| Mid-session check | Notice at 10, warning at 15 | `git rev-list --count HEAD ^origin/main` (AGENTS.md Mid gate; thresholds from `scripts/validation/pr_commit_count.py`) |
| Lint scope | Changed files only | PR #908 fix: scope `markdownlint --fix` to `git diff --name-only` output, never `**/*.md` |

The story behind the caps. PR #908 (January 2026) grew to 228+ comments, 59 commits, 95 files, and 5,060 additions (`.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md:6`). More than half the diff was collateral: the session protocol at the time mandated an unscoped `markdownlint --fix **/*.md`, which reformatted memory files across the repo (53 memory-file changes, 56% of the diff; five-whys at retro lines 285-298). Review became impossible and feedback arrived late on everything. The 20-commit cap, `pre_pr.py` itself, and the scoped-lint rule all date from that retrospective. When your PR approaches the caps, split it; do not reach for the bypass label.
