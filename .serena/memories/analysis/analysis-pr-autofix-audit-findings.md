# pr-autofix Audit Findings (2026-07-26)

Audited `src/copilot-cli/skills/pr-autofix/SKILL.md` (282 lines) at `origin/main` @ `17b89457`. Every claim below is execution-verified, not read-verified.

## What is correct (do not re-file these)

Verified by running the scripts, not by reading them:

| Documented contract | Test | Result |
|---|---|---|
| live-state gate: exit 0 + `action=ACT` | open PR #3382 | exit 0, `ACT` |
| live-state gate: exit 1 + `action=SKIP` | merged PR #3390 | exit 1, `SKIP`, "PR is already merged" |
| `test_pr_merged.py` exits 0 always (#2308) | merged PR #3390 | exit 0 |
| `--exit-100-on-merged` legacy sentinel | same | exit 100 |
| `--exit-zero-on-merged` parsed no-op | same | exit 0 |
| all 10 referenced pr scripts exist | both trees | 10/10 |
| tier tables match `docs/autonomous-pr-monitor.md` | T1..T5 | identical |

## Two false alarms that cost time

1. **`--output-format` appeared absent.** `grep -c -- "--output-format"` returned 0 in `check_pr_live_state.py`. The flag is registered indirectly via an imported `add_output_format_arg(parser)` helper. Executing the script proved it fully supported. **Never conclude a flag is unsupported from a literal grep; invoke it or read `--help`.** Negative control: `--bogus-flag` yields exit 2 with a usage line, so argparse is genuinely strict.

2. **`src/` vs `.claude/` duplication looked like drift.** `pr-autofix` lives in `src/copilot-cli/skills/` and as `.claude/commands/pr-autofix.md`. Bodies are byte-identical apart from one blank line, because `.claude/commands/` is **generated** by `build/scripts/generate_commands.py`. Not a finding. 14 skills follow this pattern (build, ship, spec, plan, test, pr-review, push-pr, ...).

## Finding 1: resolver picks a stale copy from any subdirectory

`resolve_pr_scripts_dir()` appears **5 times verbatim** in the file. Its ladder probes the bare relative string `".claude"` (lines 44, 135 at `17b89457`), which only resolves when cwd is the repo root.

Executed from three directories:

| cwd | resolves to |
|---|---|
| repo root | `.claude/skills/github/scripts/pr` (correct) |
| `repo/src/` | `~/.copilot/installed-plugins/_direct/project-toolkit/...` (wrong) |
| outside repo | same installed-plugin path |

Consequence measured: that installed copy was dated 2026-06-26, one month stale. Its `check_pr_live_state.py` was **495 lines vs the repo's 560, 215 lines different**. That script is the blocking per-PR live-state gate (#2455) run before every tier action. From a subdirectory the skill enforces its primary safety gate using a month-old implementation, silently.

Fix: anchor the repo-relative rung on `git rev-parse --show-toplevel`, order in-repo copies ahead of installed-plugin copies, and announce on stderr when a non-repo rung matches.

Corroboration already in the file: line 93 (#2443) documents the same stale-helper hazard for `test_pr_merge_ready.py` and adds a `ScriptCommit` field to detect it. The resolver has no equivalent guard.

## Finding 2: no test binds SKILL.md contracts to script behavior

`grep -rln "pr-autofix/SKILL.md" tests/` returns nothing. `tests/test_pr_autofix_worktree_identity.py` and `tests/test_pr_autofix_lease.py` exercise scripts, never the documented contracts.

Positive control proving this is a solved pattern in-repo: `tests/validation/test_check_skill_md_exec_portability.py` parses `SKILL.md` files as test input. Content-testing a SKILL.md is established here, not a new capability.

The #2308 exit-code semantics already drifted once and were re-documented in prose. Prose does not go red on the next drift.

## Rules written from this audit

`.claude/rules/harness-path-resolution.md`, `.claude/rules/skill-contract-tests.md`, `.claude/rules/worktree-identity.md`. See memory `worktree-identity-before-writes`.
