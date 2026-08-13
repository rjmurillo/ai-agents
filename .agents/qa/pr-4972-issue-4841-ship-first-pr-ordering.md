---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14705.json
qaCommit: 3bd39453140a49b4104c505c46460f2f6b777f8d
---

# PR 4972 Ship First-PR Ordering QA

## Scope

Validate the `/ship` pre-flight reordering in `a2fbf2fb6bc915f16f7e343121ae227e402d3d05`:
`.claude/commands/ship.md`, its generated Copilot mirror
`src/copilot-cli/skills/ship/SKILL.md`, and the new contract test
`tests/commands/test_ship_first_pr_ordering.py`.

## Acceptance Criteria

Quoted from issue 4841, "Expected": "For GitHub owner mode with no PR, run local
readiness checks, create the PR, then validate its CI checks. Existing GitHub PRs can
keep preflight pipeline validation."

- [x] GitHub owner mode with no open PR records `Pipeline: DEFERRED` at pre-flight
  check 1 and never invokes `pipeline-validator` there.
- [x] The same run still executes pre-flight checks 2 to 4 (security, review marker,
  tests) as the local readiness checks, then reaches `/push-pr`.
- [x] Process step 4 invokes `pipeline-validator` against the PR `/push-pr` created and
  fails the ship on a red result.
- [x] A GitHub run with an open PR keeps `pipeline-validator` in pre-flight, unchanged.
- [x] Contributor mode and the ADO branch are unchanged.
- [x] The Copilot mirror carries the same ordering.

## Evidence

| Check | Result |
|-------|--------|
| Targeted contract tests | 24 passed (`tests/commands/test_ship_first_pr_ordering.py`) |
| Pre-fix control (same tests, `origin/main` ship documents at `ab9c636de5`) | 16 of 24 failed; the 8 that passed are the ADO sibling, contributor-mode, and inline pre-fix control checks |
| Command, eval, and command-size suites | 475 passed (`tests/commands/`, `tests/eval/test_eval_prompt_change.py`, `tests/test_validation_command_size.py`) |
| Generator and portability suites | 309 passed (`tests/build_scripts/test_generate_commands*.py`, `tests/test_plugin_tree_no_unicode_dashes.py`, `tests/validation/test_check_skill_md_portability.py`) |
| Generated-tree drift | `build_all.py --check` exit 0 after commit |
| Command size | 1 file, 0 failures, 1 warning: `ship.md` 156 lines against a 200-line ceiling and a 150-line warning |
| Ruff check and format | pass on the new test file |
| Mypy changed files | 1 file type-checked, no issues |
| Markdown lint | `NOT LINTED`: selected 0 of 2 targets because the five lifecycle commands and their Copilot mirrors are in the `.markdownlint-cli2.yaml` ignore list |
| Pre-PR validation | 51 passed, 1 failed before this report existed; the single failure was Session End Validation reporting the incomplete `sessionEnd` block this report completes |

## Canonical Source Check

`.claude/skills/pipeline-validator/SKILL.md` line 118, read this session:

```text
- **No PR found:** Report to user. A PR must exist before pipeline validation. The calling skill should have created one.
```

`ship.md` quotes that sentence verbatim, and
`test_no_pr_bullet_quotes_the_canonical_validator_contract` re-reads the skill at test
time, so a reworded validator contract fails the suite instead of leaving a stale quote.

## Testing Quality Checklist

- [x] Security-critical paths: none touched. The change reorders workflow prose; it adds
  no secret handling, input parsing, command execution, or path construction.
- [x] Tests verify behavior, not execution: each assertion targets one branch of the
  ordering, and the pre-fix control demonstrates that 16 of them fail on the old text.
- [x] Coverage gaps only in low-risk code: the ADO and contributor branches are asserted
  as unchanged rather than left unread.
- [x] No coverage theater: the two inverse failures (deferring when a PR exists, and
  deferring without discharging) each have a dedicated test.

## Verdict

PASS. The first-PR deadlock is removed for GitHub owner mode without weakening pipeline
validation for any other path.
