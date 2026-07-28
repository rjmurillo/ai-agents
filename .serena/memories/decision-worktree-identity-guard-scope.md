# Decision: how far to guard against a redirected `--show-toplevel`

## Question

Issue #3402 AC 1 asked for a rule that verifies worktree identity before
writes, on the premise that `git rev-parse --show-toplevel` can point somewhere
the process is not standing. Should the repository also add a runtime
containment check to `scripts/github_core/repo.py::get_repo_root`, which every
caller uses to anchor writes?

## Conventional answer

Guard the shared helper. It is one place, every caller inherits the fix, and a
silent write into the wrong tree is undetectable downstream. `.claude/rules/`
and `AGENTS.md` both push enforcement over prose.

## What I measured

The premise is true but narrower than it reads.

```text
$ git config core.worktree /tmp/p3402/elsewhere
$ git rev-parse --show-toplevel
/tmp/p3402/elsewhere
$ git status --porcelain
 D f
```

`status` reports the tracked file as deleted, because it is looking at the
other directory. From a subdirectory the redirection persists.

The three cases that would make this a latent hazard all came back negative:

| Case | Result |
| --- | --- |
| `git worktree add` | sets neither `core.worktree` nor `GIT_WORK_TREE` |
| worktree moved on disk | `--show-toplevel` still resolves correctly |
| main checkout moved away | `fatal: not a git repository`, non-zero exit |

A dangling gitdir link makes `get_repo_root` return `None` on the existing
non-zero-exit path, so it already fails closed. `GIT_WORK_TREE` also redirects,
but that is a declaration by the caller: with cwd outside the tree and
`GIT_DIR` plus `GIT_WORK_TREE` set, `--show-toplevel` correctly reported the
tree, which a containment check would have rejected.

`grep -rn "core.worktree"` across `scripts/`, `build/`, `.claude/`, and
`.github/` returns nothing that sets it, and the live checkout has it unset.

## Position

Ship the rule, not the runtime guard.

The redirection is always something a person or a tool set on purpose, so the
exposure is a configuration this repository does not create. Against that, the
containment check would have broken five tests in `tests/test_repo_root.py`
that mock `subprocess.run` to return `/home/user/repo` while cwd is the real
checkout, and it would have rejected the legitimate `GIT_WORK_TREE` invocation
above. Trading a working, tested contract for a guard against a configuration
nobody creates is a bad exchange.

The hazard is real enough to write down, so `.claude/rules/ci-scripts.md` MUST
7 states the requirement and carries the measurements above, so the next reader
does not re-run the experiments to decide the same thing.

## Also settled here

AC 2 and AC 3 were already built. `check_skill_resolver_anchoring.py` enforces
absolute-top-level anchoring for `SKILL.md` resolvers, naming the same
`~/.copilot/installed-plugins` stale-copy failure the issue describes.
`check_skill_contract_tests.py` enforces the test requirement for skill prose
that defines an executable contract. Neither had a rule stating the
requirement, so the rules now point at the validators rather than restating
them.

## Negative finding worth keeping

`tests/build_scripts/test_generate_rules.py` passes with a corrupted
instruction mirror: 43 passed after rewriting a heading in
`.github/instructions/ci-scripts.instructions.md`. Mirror drift is caught by
`build/scripts/build_all.py --check` (exit 2, "STALENESS DETECTED"), which is
wired into `lefthook.yml` and two workflows. The generator's own test file is
not the gate; do not read a green run there as proof the mirrors are current.

## Where it landed

- `.claude/rules/ci-scripts.md` MUST 7 and MUST 8
- `.claude/rules/claude-agents.md` MUST 7
- Both instruction mirrors, regenerated with `build/scripts/generate_rules.py`
- Issue #3402, PR on `fix/3402-worktree-identity-rules`
