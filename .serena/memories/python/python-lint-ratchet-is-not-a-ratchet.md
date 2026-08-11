# Skill: `python-lint-ratchet` is not a ratchet (94%)

## Statement

Two pre-push gates carry "ratchet" in the name and have opposite semantics.
`python-lint-ratchet` runs ruff over the files you changed and fails on any
violation, including one that predates your branch. It reads no baseline.
Touching a file makes that file's entire lint state yours.

`python-lint-count-ratchet` is the real ratchet: repo wide count against a
frozen baseline, passes while the count does not rise.

Both run in the same pre-push. Seeing one pass tells you nothing about the
other.

## The trap

"Ratchet" conventionally means do not make it worse. That reading is correct
for the count gate and wrong for the changed-files gate. So the sequence that
looks like sound reasoning ends in a blocked push:

1. Gate fails on `E402` in a file you edited.
2. You stash your change, re-run ruff, and confirm the violation is
   pre-existing.
3. You conclude the finding is not yours, because a ratchet only blocks
   regressions.
4. Push fails anyway. Nothing about the violation being old exempts it.

Step 2 measures the right thing and answers the wrong question. Age is not
the gate's criterion. Membership in the changed set is.

## Evidence in the source

| Gate | lefthook.yml | Script | Baseline refs | Fails on |
| --- | --- | --- | --- | --- |
| `python-lint-ratchet` | line 421 | `scripts/ci/ruff_ratchet.py` | 0 | any violation in a changed file |
| `python-lint-count-ratchet` | line 428 | `scripts/ci/ruff_count_ratchet.py` | via `count_ratchet.py` | count above baseline |

`scripts/ci/ruff_ratchet.py:2` states it outright: "Fail on ruff violations in
changed Python files only." `run_ruff` shells `ruff check` over the changed
file list and returns `EXIT_VIOLATIONS` on returncode 1. Grep the file for
`baseline` and you get zero hits.

`scripts/ci/count_ratchet.py:3-8` describes the other contract: "freezes a
repository wide violation ceiling in a baseline file. The measured count must
not exceed the baseline."

## Application

When `python-lint-ratchet` fails, fix the violation. Do not spend a cycle
proving it is old, and do not expect a bypass on those grounds.

```bash
uv run --frozen --extra dev ruff check <the changed files>
```

Prefer the idiomatic fix over a suppression, per `.claude/rules/code-quality.md`
section "Suppressions Are a Last Resort" (line 206).
A stray module level import 200 lines down moves to the top import block once
you confirm the module it pulls has no import cycle back. Check that first:

```bash
grep -n "^import\|^from" <the module being imported>
```

Stdlib only imports mean the move is safe.

Fixing it costs minutes. Discovering the rule costs a failed push plus the
full pre-push suite, which runs the Python tests at roughly 15 minutes.

## Evidence

2026-08-05, branch `fix/memory-search-blind-to-nested`. A one line
`glob` to `rglob` fix in `memory_router.py` pulled in an `E402` added by
`c00a32e5f`, an unrelated feature commit that had appended
`from .url_validation import validate_http_url` next to its use site at line
219 instead of the top of the file.

The push output showed `python-lint-count-ratchet` green and
`python-lint-ratchet` red in the same run, which is the clearest possible
statement of the two contracts and is easy to read past.

`git push` exited 0 because the command was piped into `tail`, so the failure
surfaced only on reading the log. Pipelines report the last command's status;
capture the push to a file and echo `$?` instead.

## Related

- [ci-count-ratchet-never-names-the-offending-file](../ci/ci-count-ratchet-never-names-the-offending-file.md), locating the offender once a true count ratchet fires
- [python-lint-prepush-fix](python-lint-prepush-fix.md), the auto-fix first
  reflex for your own new lint
