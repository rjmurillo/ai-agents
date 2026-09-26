## Matters

- Root `conftest.py` autouse `_guard_real_repo_head`, every test: fails (#2316) when a test-launched git command moves real HEAD, fails (#5123) when the call phase also failed, else warns (#3109).
- `tests/conftest.py` autouse: git-config isolation (`GIT_CONFIG_COUNT=1`, gpgsign off, no leaked `core.hooksPath`), clears `CI` (`.claude/rules/testing.md` SHOULD-13), defaults `AI_AGENTS_PROJECT_REPO=1`, sanitizes `GIT_*`, caps git discovery at `tmp_path.parent` via `GIT_CEILING_DIRECTORIES`.
- 111 `tests/skills/<name>/test_skill_md_contract.py` via `tests/skills/_template_contract.py`: template render == `src/claude/skills/<name>/SKILL.md` == `.claude/skills/<name>/SKILL.md`, no `@CLAUDE.md` line, no literal `{{`. Hand-editing a shipped SKILL.md reds one.
