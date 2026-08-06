# Skill: A ratchet is declared twice, so drop it twice and nothing fails (93%)

## Statement

Every pre-push ratchet is declared in two files: a job in `lefthook.yml` and a
`Ratchet(...)` entry in `scripts/validation/checks_ratchet.py`. The second list
is what `pre_pr.py` runs, so a ratchet in only one file is enforced on push and
skipped in pre-PR, or the reverse.

`tests/ci/test_pre_pr_runs_lefthook_ratchets.py` compares the two as strings,
and it is not advisory. Deleting one `Ratchet(...)` entry produces exactly two
failures, `TestParityWithLefthook::test_job_names_match` and
`::test_commands_match`.

**Deleting both sides produces zero failures.** Measured 2026-08-05: removing
the job from `lefthook.yml` and its `Ratchet(...)` entry together leaves the
suite at 16 passed. The two files stay consistent with each other and
inconsistent with intent, so the gate goes quiet instead of going red.

## The merge trap

This pair attracts add/add conflicts, because a new ratchet appends at the same
position on both sides. Merging `main` into any branch that added a ratchet
conflicts in both files at once, and the merge base at the hunk is empty:

```text
marker: <<<<<<< HEAD
        "cli-exit-contract-ratchet",
marker: ||||||| 5ec85be51
marker: =======
        "memory-index-token-ratchet",
```

The `|||||||` line followed immediately by `=======` means the base contributed
nothing, so neither side edited the other's work. Keep both entries. Picking a
side drops a ratchet in the one way the parity test cannot see.

## Recipe

Verify a resolution by counting, not by trusting the green suite. The two
counts must be equal:

```bash
grep -c 'Ratchet(' scripts/validation/checks_ratchet.py
grep -c '^          - name: .*-ratchet$' lefthook.yml
```

Both returned 7 on 2026-08-05. The count works only because the dataclass is
declared `class Ratchet:` with no parenthesis; if someone rewrites it as
`class Ratchet(NamedTuple):` the left side silently gains one.

Do not use a bare `- name:` count. `grep -c '^          - name:' lefthook.yml`
returns 64, every job in the file, and pairs with nothing.

## Field shape

`Ratchet(job_name, script, extra_dev, uses_base_ref)`. The last two are
booleans that must match the lefthook job exactly: `extra_dev` is true only
when the job passes `--extra dev`, `uses_base_ref` only when it passes
`--base-ref`. Getting either wrong passes a syntax check and fails the parity
test on the command string.

## Generalization

When one fact is declared in two files and a test compares them to each other,
a symmetric deletion is the failure that test cannot catch. The test measures
agreement, not existence. Verify against the count you expected, not against
the test result.
