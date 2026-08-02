# Skill: Invoking the count ratchet scripts from other code (95%)

## Statement

Two of the four count ratchets shell out to a **bare `ruff` executable**, not to
a Python module. Run them with `sys.executable` from a venv without the `dev`
extra and they report `command not found`. That reads as a ratchet failure but
is really a missing dependency, so a gate built on top of them fails a clean
tree.

Invoke them the way `lefthook.yml` does, through `uv`, and carry the `--extra
dev` flag for the two that need it.

## The four commands

```bash
uv run --frozen --extra dev python scripts/ci/ruff_ratchet.py
uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py --base-ref origin/main
uv run --frozen python scripts/ci/taste_count_ratchet.py --base-ref origin/main
uv run --frozen python scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main
```

Only the first two take `--extra dev`. `taste_count_ratchet.py` runs
`sys.executable` against a linter script, and `type_ignore_count_ratchet.py` is
pure stdlib, so neither reaches for a console entry point.

Note the flag name: these scripts take `--base-ref`. The `build/scripts` gates
in `checks_common.py` take `--base`. Copying the wrong one produces an argparse
error that looks like a ratchet failure.

## Re-derive

```bash
git grep -n '"ruff"' -- scripts/ci/
```

Any ratchet that appears in that output needs the dev extra. (`verify_code_env.py`
also matches; it probes with `shutil.which` and is not a ratchet.) Confirm the
live command shape against the pre-push stage rather than trusting this note:

```bash
git grep -n -A2 "name: .*-ratchet" -- lefthook.yml
```

That returns exactly four jobs, which makes the `-ratchet` suffix a safe
selector for code that has to enumerate them.

Note the pattern shape. Lefthook jobs are YAML **list entries** (`- name: x`),
not mapping keys, so a grep for `ratchet:` matches nothing and reads as "the
ratchets are gone." Match on `name: .*-ratchet` instead. Code that walks the
config should parse the YAML and iterate the job list rather than grepping at
all; see `tests/ci/test_lefthook_ratchet_wiring.py` for that traversal.

## Anti-Pattern

Reconstructing the invocation from first principles because
`python scripts/ci/ruff_ratchet.py` looks like it should work. It does work in a
dev venv, which is exactly what makes the failure late and confusing: it passes
locally for whoever wrote it and fails for the next person.

Also an anti-pattern: parsing the `run:` strings out of `lefthook.yml` at
runtime to build the argv. That needs `shlex.split` on YAML text and adds a
string-to-argv execution path this repo's CWE-78 rules disfavor. Hardcode the
table and assert parity against `lefthook.yml` in a test instead.

## Evidence

2026-08-02, issue #4251. The pre-PR gate ran zero ratchets, so a count breach
surfaced only after a 674 second push. The fix added
`scripts/validation/checks_ratchet.py`, which catches the same breach in 2.9
seconds. The first draft used `sys.executable` and failed on a clean tree with
`ruff: command not found`.

## Related

- `scripts/validation/checks_ratchet.py` (the `RATCHETS` table and `build_command`)
- `tests/ci/test_pre_pr_runs_lefthook_ratchets.py` (the parity assertion)
- `.serena/memories/ci/ci-count-ratchet-never-names-the-offending-file.md`
