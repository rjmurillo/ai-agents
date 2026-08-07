# `--repo-root` defaults to the script's own repository, so a scratch-clone test can pass vacuously

## The trap

`scripts/validation/git_hook_policy.py` registers `--repo-root` on the top-level
parser with a default of the module's own `REPO_ROOT`:

```python
parser.add_argument("--repo-root", default=str(REPO_ROOT))
```

`REPO_ROOT` is derived from the file's location, not from the current working
directory. In CI that is correct and invisible, because the script ships inside
the checkout it is meant to inspect, so the two are the same directory.

In a test they are not. A test that builds a scratch clone under `tmp_path`,
puts the repository into the state under test, and then runs the script with
`cwd=<clone>` will still measure **ai-agents**. `cd` does not move the default.

## What it looks like when it bites

Observed 2026-08-06 while adding a guard that had to return exit 2 on a grafted
clone. The test built a real clone, grafted it with `git fetch --depth=1`,
asserted the graft with `rev-parse --is-shallow-repository`, and then ran:

```python
subprocess.run([sys.executable, POLICY, "security-suppressions-diff",
                "--base-ref", "origin/main"], cwd=clone)
```

It returned 0, and the failure read exactly like a missing guard:

```
AssertionError: expected exit 2 on a grafted clone, got 0
```

The guard was present and correct. The scratch clone was grafted. The script
was simply looking at a different repository, one that was not grafted, so it
answered honestly about the wrong tree. Roughly twenty minutes went into
re-reading the guard before the default was the suspect.

The dangerous direction is the inverse, and it is silent. Had the assertion been
`== 0` on a healthy clone, the test would have passed while measuring
ai-agents, and kept passing after the guard was deleted.

## Do this instead

Pass `--repo-root` explicitly whenever the target is not the script's own
checkout, and put it before the subcommand because it is a top-level argument:

```python
[sys.executable, str(POLICY), "--repo-root", str(repo), *argv]
```

Then prove the test can fail. Restore the defect, clear `__pycache__`, rerun,
and confirm the named test fails and no other test moves. A test against a
scratch repository that has never been shown to fail is not evidence about the
guard; it is evidence about whichever repository it actually read.

## Generalizes past this one script

The shape is "a path default computed from `__file__` rather than from the
caller". Grep before writing a scratch-repository test:

```bash
grep -n 'default=str(REPO_ROOT)\|Path(__file__).resolve().parents' <script>
```

If the entrypoint has one, the test must override it, and the override belongs
in the shared helper that spawns the process rather than in each case, so a
later case cannot be added without it.

## Related

`.serena/memories/mutation-testing-false-green.md` is the same family: a check
that reports success without having examined the thing it names.
