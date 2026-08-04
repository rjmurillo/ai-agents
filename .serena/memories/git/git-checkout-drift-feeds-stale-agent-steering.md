# Always on steering renders from the live checkout

## Question

The always on rules in an agent's system prompt look authoritative. Are they the
rules CI enforces?

No. They are a snapshot of whatever sat on disk in the working checkout when the
session started. If that checkout is behind, detached, or dirty, every turn runs
on superseded steering and nothing reports it.

## The evidence

Observed, not inferred. The imported instruction block names its own source path:

```text
<imported_custom_instruction source="/home/richard/src/GitHub/rjmurillo/ai-agents/AGENTS.md">
```

Measured in that checkout:

| Source | `AGENTS.md` Boundaries line ends with |
|---|---|
| live checkout at `48c520ee9` | `Bump plugin manifest` |
| `origin/main` at `4459b886a` | `No manifest version (ADR-092)` |

The loaded text matched the checkout, not `main`. That checkout was detached, 320
commits behind `origin/main`, and carried 551 modified files.

## Why it bites

The two strings are not merely different vintages. They are opposites, and the
superseded one points at the destructive action:

- `build/scripts/validate_plugin_version_bump.py` exits 1 when any of the three
  packaged manifests carries a `version` key. Following the loaded instruction
  adds the key and fails that gate.
- Absence is load bearing. With no `version` in `plugin.json` and none in either
  marketplace entry, Claude Code resolves plugin freshness from the git commit
  SHA of the source, which changes on every merge. Adding the field switches
  resolution to the explicit version, where pushing new commits has no effect
  until a human bumps it.
- It re-creates the conflict that motivated the inversion. Issue #4080 measured
  14 of 22 conflicting PRs conflicting on nothing but that single line.

ADR-092 supersedes ADR-079. The repo rule `.claude/rules/plugin-version-bump.md`
is current and correct. Only the loaded snapshot was stale.

## Why no gate catches it

Every gate runs in CI against the PR branch, which is built from `main` plus the
change. No gate reads the context the agent was steered by. So the failure does
not surface as a rule violation. It surfaces as a confidently wrong action with a
clean local rationale, caught only when CI rejects the result or a reviewer
happens to know the newer rule.

This is the same shape as the inherited context problem: an assertion handed to
you by a snapshot is one closed loop, not two. The instruction corpus is inherited
state, so it earns the same distrust as a compaction note.

## What to do

Before acting on an always on rule that would change a gated artifact, check the
loaded text against `origin/main` instead of trusting it:

```bash
git fetch origin
git diff origin/main -- AGENTS.md .claude/rules/
```

Compare against the working tree, not `HEAD`. `git diff HEAD origin/main` is
tree to tree and would skip uncommitted edits, which is exactly the state the
agent loaded from. Fetch the remote without naming a branch so the
`refs/remotes/origin/*` tracking refs update regardless of refspec
configuration; `git fetch origin main` can leave `origin/main` stale and make
the diff compare against an old reference.

Measured on the drifted checkout that prompted this memory, where `AGENTS.md`
was itself locally modified: the `HEAD` form reported 41 diff lines and the
working tree form reported 50. The tree to tree comparison hid nine lines of
real drift.

A non empty diff there means the steering in context is not the steering CI
enforces. Prefer the `origin/main` version.

Work from a worktree cut fresh off `origin/main` rather than the shared checkout.
The shared checkout drifts, and its dirty state is not yours to reset.

## Related

- `.claude/rules/plugin-version-bump.md`, the current and correct rule.
- `.agents/architecture/ADR-092-omit-plugin-manifest-version.md`, which supersedes
  `.agents/architecture/ADR-079-merge-time-plugin-version-bump.md`.
- `git/git-stash-is-shared-across-every-worktree.md`, the sibling case where
  shared checkout state silently crosses between agents.
