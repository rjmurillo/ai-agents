---
paths: ".claude/skills/**,src/copilot-cli/skills/**,.claude/commands/**"
priority: high
---

# Skill Contract Test Rule

When a `SKILL.md` documents a script's exit codes, output fields, or flag semantics, that documentation is executable behavior written in prose. Nothing recompiles it when the script changes. The script's own unit tests assert the script against itself; they never open the `SKILL.md` and never notice when the two disagree.

This rule exists because `pr-autofix` documents several load-bearing contracts that no test binds:

- `check_pr_live_state.py` exits `0` with `action=ACT` for an actionable PR and exits `1` with `action=SKIP` for one already merged. The skill branches on both.
- `test_pr_merged.py` exits `0` unconditionally (issue #2308), with `--exit-100-on-merged` restoring the legacy `100` sentinel and `--exit-zero-on-merged` retained as a parsed no-op.

All of these were verified correct on `9768d541` by execution. None of them are covered by a test that reads the `SKILL.md`. `tests/test_pr_autofix_worktree_identity.py` and `tests/test_pr_autofix_lease.py` exercise scripts, not documented contracts. The exit-code semantics in #2308 already drifted once and were re-documented in prose; prose does not go red the next time.

## What a skill that documents a contract MUST have

A test that reads the `SKILL.md`, extracts the documented contract, and asserts the script actually honors it. The established in-repo pattern is `tests/validation/test_check_skill_md_exec_portability.py`, which parses `SKILL.md` files as test input — content-testing a `SKILL.md` is a solved problem here, not a new capability.

The test asserts the pairing, not either side alone:

- Exit codes: invoke the script against a fixture in each documented state and assert the exit code the `SKILL.md` names.
- Output fields: assert the documented key exists in the emitted envelope with the documented value.
- Flags: assert the flag parses. A flag registered indirectly through a shared helper such as `add_output_format_arg(parser)` will not appear in a literal grep of the script; verify with `--help` or an actual invocation, never with a string search.

## Why grep is insufficient for these checks

Auditing `pr-autofix` produced a false alarm: `grep -c -- "--output-format"` returned `0` in the script, suggesting the `SKILL.md` invoked an unsupported flag. Executing the script disproved it — the flag is registered by an imported helper and is fully supported. A contract test must invoke, not scan.

The negative control matters equally: confirm `argparse` rejects a bogus flag (`--bogus-flag` → exit `2`, usage line) before concluding that a real flag was accepted. An acceptance that cannot fail proves nothing.

## What the reviewer MUST verify

- If a diff changes a script's exit codes, output schema, or flag surface, confirm a test binds the new behavior to the `SKILL.md` text — or that the `SKILL.md` stops making the claim.
- If a diff adds a contract statement to a `SKILL.md` (an exit-code table, a documented field, a tier table mirrored from a protocol doc), confirm a test asserts it. An unbound contract is a comment.
