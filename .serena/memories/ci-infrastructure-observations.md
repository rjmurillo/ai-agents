# Skill Sidecar Learnings: CI Infrastructure

**Last Updated**: 2026-05-30
**Sessions Analyzed**: 2

## Constraints (HIGH confidence)

- When a CI job fails on a PR, check if the failure exists on main before debugging PR code. Run the same workflow on main or check recent main runs. Pre-existing bugs waste time if misattributed to the PR. (PR #1361, 2026-03-04)

## Preferences (MED confidence)

- After major cleanup operations (file deletions, merges from main), update the PR description before pushing. The `pr_description.py` CI validator checks that files mentioned in the description match the actual diff. Stale descriptions cause `DESCRIPTION_RESULT: FAIL`. (PR #1361, 2026-03-04)
- Virtual environment tools (`uv run python`) should be first priority in Python detection functions like `set_python_cmd()`, before system `python3`/`python`/`py` fallbacks. System Python often lacks project dependencies (pytest, etc.) that live in the virtual environment. See `.githooks/pre-push:110`. (PR #1361, 2026-03-04)

## Edge Cases (MED confidence)

- Agent multi-platform sibling model (ADR-036): a SHARED_AGENT's hand-maintained siblings are `templates/agents/<n>.shared.md` + `src/claude/<n>.md` + `.claude/agents/<n>.md` + `.github/agents/<n>.agent.md`; `build/scripts/validate_install_parity.py` requires they move together. `.github/agents/*.agent.md` is hand-curated (different body+frontmatter from the copilot mirror), NOT generated. If you edit any sibling of an agent that LACKS its `.github` copy, parity fails ("missing required sibling"). Either create the `.github` variant or revert that agent. Hit on `issue-feature-review` (no `.github` copy at main). (wiki-rubric audit #2126/#2136, 2026-05-30)
- Agent/skill generators: use `python3 build/generate_agents.py` (writes only `src/copilot-cli/agents` + `src/vs-code-agents`) and `python3 build/scripts/build_all.py` (regenerates all mirrors incl. `src/copilot-cli/skills`). Docs' `pwsh build/Generate-Agents.ps1` is STALE/absent. Drift detector is `build/scripts/detect_agent_drift.py` (src/claude vs src/vs-code, 80% threshold; weekly cron, opens an issue, NOT a blocking PR gate). `build_all.py --check` reporting "STALENESS DETECTED" just means your regen output is uncommitted; it is idempotent and clears once committed. `.claude/agents` and `.github/agents` are hand-synced (no install script). (wiki-rubric audit, 2026-05-30)
- `validate-skill.py` (SkillForge) has a CWE-22 cwd path guard: it rejects target paths outside the current working dir. To validate an `origin/main` worktree copy, `cd` INTO the worktree first. It is local-pre-commit-hook only (not wired into any CI workflow), and `core.hooksPath` may point at `.git/hooks` so it may not even run on commit. ~16 skills fail its structural checks (missing Process/Verification sections) on origin/main; ALWAYS diff validator output against an origin/main worktree before "fixing" pre-existing failures as if they were your regression. (wiki-rubric audit, 2026-05-30)

## Notes for Review (LOW confidence)

- `$GITHUB_OUTPUT` requires heredoc delimiter syntax for multiline values. Writing `key=value` where value contains newlines causes each line after the first to be parsed as a separate output entry. Lines not matching `key=value` format trigger `##[error]Invalid format`. The `write_output()` helper in `scripts/ai_review_common.py` does not handle this. Filed as issue #1386. (PR #1361, 2026-03-04)
