# Gotchas

Non-obvious repository behavior that cost real time to learn and cannot be
inferred from reading the code. Each entry states the trap, the symptom you
will actually see, and the fix.

`AGENTS.md` is budget-capped because it is injected into every session. Two
byte gates disagree: `tests/test_workspace_limits.py` allows 3072 per file,
`scripts/validate_workspace_budget.py` allows 3000. **Write to 3000.** The
stricter gate binds, and a file between the two passes one and fails the other
(Refs #3951). These entries live here instead so detail is not paid for on
every turn. `AGENTS.md` points at this file from its Retrieval section.

## Session log ordering

Create the session log **untracked in the worktree before the first commit**,
and stage it only at session end.

`branch-context-policy` reads the worktree and wants the log present.
`session-policy` rejects a *staged* log whose `sessionEnd` is incomplete. A
session log cannot be both staged early and complete early, so following the
protocol literally (create and stage at start) cannot pass both gates.

Symptom: a commit is rejected by one of the two policies no matter which order
you try. Refs #3904.

## Run validation with `uv run python`, never bare `python3`

`scripts/validation/checks_spec.py` shells out to child validators with
`sys.executable`. A system interpreter at the entry point therefore propagates
to every child check, and two of them fail with `ModuleNotFoundError:
markdown_it` because the dependency lives in the project venv.

Symptom: `python3 scripts/validation/pre_pr.py` reports failures that have
nothing to do with your change. Refs #3938.

## Instruction-budget ceilings ratchet to measured size

`scripts/validation/instruction_budget.py` enforces a ceiling that was set from
the corpus as it stood, and it has been raised as the corpus grew. A passing
gate therefore says the corpus did not grow since the last ratchet. It does not
say the corpus is small.

Compare against the goal, not the ceiling. The always-on corpus is roughly 95KB
on a `.py` edit.

## Suppression comments block the push, including inert ones

`git_hook_policy.py security-suppressions-push` rejects any commit that **adds**
a line matching a `noqa`, `nosec`, `nosemgrep`, `lgtm[`, or `type: ignore`
comment. It matches the comment shape, not the rule name, so a `noqa` naming a
rule the project does not even select is still a block.

Ruff selects `E`, `F`, `W`, `I`, `N`, `UP`, `B`, `ANN`. Anything else in a
`noqa` is inert and should be deleted rather than carried.

The check diffs the whole push range, so a suppression added in one commit and
removed in a later one nets out and passes. Existing lines on `main` are
grandfathered because only added lines are scanned, which is why inert
suppressions can sit in the tree looking like sanctioned precedent. Refs #3940.

## The mypy and ruff gates are ratchets, not clean-tree checks

`git_hook_policy.py mypy` tolerates the pre-existing error count in a file and
fails only when your change adds to it. Touching a file with pre-existing
errors does not oblige you to fix them, but adding one error to a file that had
eight will fail the push with all nine printed.

Symptom: a wall of errors on lines you did not touch. Count them against the
merge base before assuming the change is yours.

## Eval harness

These matter only when running `scripts/eval/`. Full detail lives in
`.claude/skills/context-optimizer/references/rule-audit-procedure.md`.

- Run without an API key using `EVAL_PROVIDER=copilot-cli`. The provider must
  run in an empty working directory, because the Copilot CLI loads `AGENTS.md`,
  `CLAUDE.md`, and `.github/instructions/**` from its cwd and would otherwise
  put the treatment into the control cell.
- Copilot CLI reported token counts are non-monotonic (109k from `/tmp` against
  96k in-repo for the same trivial prompt). They are not a measurement of
  anything. Use `instruction_budget.py`. Refs #3906.
- A single eval run cannot resolve a delta under about 1.0 on a 0-5 scale.
  Measured run-to-run spread on identical inputs was 0.94 on Opus 5 and 1.11 on
  Sol 5.6. Run four times per model and count sign consistency, not means.
