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
| 4 | CI required checks | Push and PR events | `pytest.yml`; `pr-validation.yml` (commit count is advisory only, no block); `ai-spec-validation.yml`; CodeQL, drift, and plugin-bump workflows. Nine deterministic contexts are pinned in `scripts/ci/ruleset_required_contexts.py:REQUIRED_CONTEXTS`. Neither AI specialist verdicts nor committed session logs block merge; their workflows were deleted |

Local Git hooks only run after Lefthook is installed. Run
`uv run --frozen lefthook install --reset-hooks-path`, then verify with
`uv run --frozen lefthook check-install`. `pre_pr.py` also validates the binary,
configuration, and installed shims (`scripts/validation/checks_plugin.py`).

## Respect commit discipline

| Rule | Limit | Enforcement |
|------|-------|-------------|
| Files per commit | 5 or fewer | `.claude/rules/universal.md` MUST 4; AGENTS.md Boundaries |
| Commits per PR | Advisory only: notice at 10, alert at 15, no block | `scripts/validation/pr_commit_count.py` (`WARNING_THRESHOLD = 10`, `ALERT_THRESHOLD = 15`), wired at `pr-validation.yml`. The former 20/40-commit block and its `commit-limit-bypass` human-only label were removed (issue #5230): the block required local, pre-push verification of a GitHub label that a sandboxed harness cannot always perform, and the only way through an unverifiable-but-satisfied gate was an expensive stacked-branch workaround |
| Mid-session check | Notice at 10, alert at 15, no block | `git rev-list --count HEAD ^origin/main` (thresholds from `scripts/validation/pr_commit_count.py`) |
| Lint scope | Changed files only | PR #908 fix: scope `markdownlint --fix` to `git diff --name-only` output, never `**/*.md` |

The story behind the original caps. PR #908 (January 2026) grew to 228+ comments, 59 commits, 95 files, and 5,060 additions (`.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md:6`). More than half the diff was collateral: the session protocol at the time mandated an unscoped `markdownlint --fix **/*.md`, which reformatted memory files across the repo (53 memory-file changes, 56% of the diff; five-whys at retro lines 285-298). Review became impossible and feedback arrived late on everything. `pre_pr.py` itself and the scoped-lint rule date from that retrospective and remain in force. The 20-commit block that also came out of it was removed in issue #5230, once the human-only bypass label it relied on turned out to force the exact kind of PR sprawl (a whole new stacked branch and PR to route around an unverifiable local check) that the original cap existed to prevent. Splitting a large PR is still good practice; it is no longer mandatory.
