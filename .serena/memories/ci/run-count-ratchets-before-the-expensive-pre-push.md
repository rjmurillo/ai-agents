# Run the count ratchets before you push, because pre-push finds them last

## Update 2026-08-15: the ordering is fixed in tooling (issue #5066)

`lefthook.yml` pre-push is now staged: the count ratchets and the other
seconds-scale blocking gates run in a fast stage ahead of `python-tests`,
semgrep, mypy, `build_all --check`, and the e2e smokes, and the hook is
piped, so a ratchet failure aborts before the expensive jobs start. The
trap below describes the pre-#5066 shape. Running the ratchets by hand
before pushing is still the cheapest loop (no hook startup, no stdin
group), but a forgotten ratchet no longer costs a 12 minute pytest run;
it costs the fast stage, seconds.

## The trap

A pre-push in this repository runs the full pytest suite. Measured 2026-08-06:

```
✔️ pre-pr-validation (75.86 seconds)
✔️ python-tests (741.85 seconds)
```

Twelve minutes for the suite alone, and pushes also serialize on
`$HOME/src/scratch/locks/push-lock-<branch>.lock`, so a fleet of agents queues
behind each other and wall-clock is longer than that.

The count ratchets are cheap by comparison and they fail on conditions that have
nothing to do with your tests passing. A single new error-severity taste
violation is enough:

```
taste count ratchet: REGRESSION. 584 violations > baseline 583 (+1).
```

Adding one 531-line test file did that. The suite was green. Every test passed.
The push would still have been refused, after the twelve minutes.

## What it looks like when it bites

The ratchets are count-based, so the violation you are blocked on is often not
in the file you were thinking about, and the report lists the whole current set,
hundreds of lines, with your new entry in it somewhere. Reading the first line
is what tells you the delta:

```
584 violations > baseline 583 (+1)
```

Then the first entry under `Current violations:` is normally the file you just
touched, because the report leads with the changed paths.

## Do this instead

Run the ratchets against the base before you push. Each takes seconds:

```bash
git fetch origin main
uv run --frozen --extra dev python scripts/ci/taste_count_ratchet.py --base-ref origin/main
uv run --frozen --extra dev python scripts/ci/type_ignore_count_ratchet.py --base-ref origin/main
uv run --frozen --extra dev python scripts/ci/memory_index_count_ratchet.py --base-ref origin/main
uv run --frozen --extra dev python scripts/ci/merge_tree_ratchet_check.py --base-ref origin/main
```

Do **not** copy the CI form of these commands, which historically fetched with
`git fetch --depth=1`. That writes a repository-global graft and blocks every
push from every worktree until you run `git fetch --unshallow origin`. See
`.serena/memories/git/git-shallow-is-shared-across-every-worktree.md`.

## Fix idiomatically before reaching for the escape hatch

The ratchet names a suppression comment as an option:

```
add a reasoned `# taste-lint: ignore <rule>` comment in the first 10 lines
```

That is the last resort, not the first. For a file-size breach the idiomatic fix
is usually available and better: a 531-line test module split along a real seam
became a 357-line module that reads workflow YAML and a 194-line module that
drives real clones, and the ratchet returned to `OK (count == baseline 583)`.
Splitting on a seam that already exists costs one commit. A suppression is
permanent and teaches the next reader that the rule does not matter here.

## Related

`.serena/memories/root-cause-late-feedback.md` is the general form: move the
cheap check earlier than the expensive one.
