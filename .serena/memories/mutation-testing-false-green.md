# A mutation whose edit never applied reports a passing suite as proof

## Symptom

You mutate a guard to prove a test is load-bearing, run the suite, and see
`9 passed`. That reads as "the mutation changed nothing, so the test is
vacuous." The opposite conclusion is equally consistent with the output: the
edit never landed, so the suite ran against unmodified code and passing is
exactly what it should do.

A green mutation run has two causes and the output cannot tell them apart.

## Cause

Observed 2026-08-02 while verifying the `worktree-gc-report` push guard.

```bash
sed -i 's| || echo "..."||' lefthook.yml
```

`sed` takes the character after `s` as the delimiter. The pattern being removed
contained `||`, which closed the expression early. `sed` exited with
`unknown option to 's'` and wrote nothing. The pytest run that followed printed
`9 passed`, which looked like a vacuous-test finding and was not.

The general shape is any mutation applied by a tool that can fail silently or
whose failure scrolls past: a `sed` delimiter collision, a pattern that no
longer matches after a refactor, an edit written to the wrong worktree, or a
here-doc mangled by quoting.

## The practice

Assert the edit landed before trusting the result. In Python:

```python
assert old in text, "PATTERN NOT FOUND - mutation would be a no-op"
path.write_text(text.replace(old, new, 1))
print("applied")
```

Print `applied` and read it. A mutation harness that cannot say whether it
mutated anything is measuring nothing, the same way a scanner that scores every
non-zero exit as success is measuring nothing.

Prefer Python over `sed` when the pattern contains shell or regex
metacharacters. `sed` has no delimiter that is safe against arbitrary content,
and choosing one per pattern is how the collision happens.

## Pin only the bytes the mutation is about

Observed 2026-08-03. `tests/ci/test_mutation_harness_ciperms.py::test_target_literal_is_present_exactly_once[M7]`
failed on `origin/main` with `literal appears 0 times`. M7 exists to prove a
test notices an `if:` guard re-added to the ADR-006 ratchet step, and its
`old_bytes` pinned two lines:

```text
      - name: Run ADR-006 run-block ratchet
        run: python3 scripts/ci/adr006_run_block_scanner.py --max 58
```

PR #4406 ratcheted `--max 58` to `--max 0`. The literal stopped matching and
the mutation went un-runnable. Nothing about the guard changed.

The obvious fix is to update the literal to `--max 0`. That fix is wrong: the
whole point of a ratchet is that its value moves, so the mutation would break
again on the next burn-down, and each break costs a red main plus a triage
cycle. The `--max` value is not what M7 mutates.

Anchor on the smallest span that is both unique and invariant. Here that is the
step-name line alone, which the harness's own uniqueness test already enforces:

```python
old_bytes=b"      - name: Run ADR-006 run-block ratchet\n",
new_bytes=(
    b"      - name: Run ADR-006 run-block ratchet\n"
    b"        if: steps.should-run.outputs.skip != 'true'\n"
),
```

Before adding or repairing a mutation, read its literal and ask which bytes the
mutation is actually about. Any threshold, budget, count, version, or SHA in
the span is a scheduled failure. Step names, job names, and function names are
stable and usually unique, which makes them the right anchors.



Deleting a guard proves a test notices its absence. It does not prove the test
notices a guard that is present but wrong. Run both mutations. On issue 4257
the deletion and the subtle corruption (a `#` inserted into the guard's
message) each failed three tests, which is what made the pair meaningful.
