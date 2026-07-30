# Gotchas

Non-obvious repository behavior that cost real time to learn and cannot be
inferred from reading the code. Each entry states the trap, the symptom you
will actually see, and the fix.

`AGENTS.md` is budget-capped because it is injected into every session. Two
byte gates disagree: `tests/test_workspace_limits.py` allows 3072 per file,
`scripts/validate_workspace_budget.py` allows 3000. **Write to 3000.** The
stricter gate binds, and a file between the two passes one and fails the other
(Refs #3951). These entries live here instead so detail is not paid for on
every turn. `AGENTS.md` points at this file from its Retrieval section, and
`.github/copilot-instructions.md` points at it from its Gotchas section.

`.github/copilot-instructions.md` is injected into every Copilot session too,
at roughly twice that per-file budget, and **no gate measures it**: the
workspace budget covers only `CLAUDE.md`, `AGENTS.md`, and `.claude/CLAUDE.md`,
and `instruction_budget.py` covers only `.github/instructions/*.instructions.md`.
New always-on guidance therefore belongs here, not there (Refs #3991).

## Three portability checkers exist and their names do not tell you the scope

Running two of them is not running the third, and only the third reads
Markdown.

| Script | Scans | Catches |
|---|---|---|
| `build/scripts/check_vendor_portability.py` | skill scripts | code that reads an upstream-only path |
| `build/scripts/check_skill_portability.py` | skill scripts | drift against the script baseline |
| `scripts/validation/check_skill_md_portability.py` | skill `.md` | an upstream path cited in **prose** |

Symptom: the first two pass, you commit, and the push is rejected by
`pre_pr.py` with `[FAIL] Skill Markdown Portability` naming a reference file
you just added. A new `.md` under `.claude/skills/` that cites a repo path such
as `.agents/analysis/...` starts at baseline 0 and any reference is drift.

Fix: resolve the path through the plugin or skill root, or declare it with an
HTML comment marker on its own line at the end of the file:

```text
<!-- vendor-portability: declared. <what the path is, why the file cites it,
and what a vendored install loses without it>. Issue #2050. -->
```

Both the canonical file and its `src/copilot-cli/` mirror carry the marker,
because the checker scans both trees.

## Pass explicit file paths to taste-lints, never a directory

`taste_lints.py --rules file-size <dir>` scans **zero** files and reports "no
violations". That is a false pass, not a clean result. It only reads paths you
name.

```
uv run --frozen python .claude/skills/taste-lints/scripts/taste_lints.py \
  --rules file-size path/to/one.md path/to/two.md
```

Authored file size is a **hard error at 501 lines** and a warning from 301 to
500, so a file that silently skipped the check can block a later commit.

## A commit touching `.agents/` must carry the session log

`session-policy` rejects any commit that stages a file under `.agents/` unless
the JSON session log is staged in that **same** commit. Splitting the work into
"content commit, then log commit" fails on the first one.

Symptom: a commit touching `.agents/analysis/` or `.agents/architecture/` is
rejected while the identical change under any other path commits fine. See also
"Session log ordering" below, which governs when the log may first be staged.

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

## The PR description gate blocks on paths and on dashes

`scripts/validation/pr_description.py --ci` runs as `PR Validation / Validate
PR` in branch protection and blocks merge on two things.

**A file path mentioned but not in the diff.** The validator extracts paths
only from inline code, bold, list items, and Markdown links, so a path in plain
prose is fine but an inline-backtick mention is not. Silence a genuine
reference the way the validator recognizes: a citation cue (`see` before the
path), a fenced code block, a GitHub admonition (`> [!NOTE]`), or a contextual
H2 such as `## References`, `## Related Files`, `## See Also`, `## Notes`,
`## Background`, `## Evidence`, `## Out of Scope`, or `## Prior Art`. The full
set is `_CONTEXTUAL_SECTION_NAMES` and `_REFERENCE_SECTION_PREFIXES` in the
validator.

**Any em-dash (U+2014) or en-dash (U+2013).** Byte-verify rather than trusting
a visual scan:

```
python3 -c "import sys;d=open(sys.argv[1],'rb').read();print(sum(d.count(c.encode()) for c in ('\u2014','\u2013')))" body.md
```

Editing the body re-triggers the gate on `pull_request: edited`, so no new
commit is needed. Bot reviewers produce false positives on both checks; verify
at byte level before editing.

The validator takes `--pr-number` and fetches the **live** body, so push and
update the PR before running it locally.

## Never put a literal pipe inside a Markdown table cell

Escape it as `\|` or reword. A bare `|` breaks rendering and trips bot
table-format flags.

## Reference skill scripts by plugin root, not a bare `.claude/` path

Use `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/..."`. A
bare `.claude/skills/...` path fails under Copilot CLI and trips
`check_skill_md_exec_portability.py`.

## `gh pr view --json reviewThreads` is not a valid field

The field does not exist on that command and the error does not suggest the
alternative. Use `gh api graphql` with a `reviewThreads` query on the pull
request instead.
