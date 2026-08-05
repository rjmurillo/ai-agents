# Verifying a Fact in the Shared Checkout Answers About the Wrong Commit

## The trap

`~/src/GitHub/rjmurillo/ai-agents` is the shared clone every session starts in. It is
usually on a **detached HEAD well behind `origin/main`**, because worktree-based work
leaves it parked wherever the last operation put it.

Reading a workflow, a script, or a validator there and treating the answer as current
is wrong. The file may be several days stale.

## How it burned a session

2026-08-03. A memory documented the step list of `.github/workflows/pr-validation.yml`.
The list was built by grep, so it was replaced with a `yaml.safe_load` parse, which is
the right instinct. The parse ran in the shared checkout and returned **22 steps**.
Current `origin/main` had **23**, including a `Check bare-python3 documentation
entrypoints` step that the stale tree lacked.

Result: a correct table was "corrected" into a wrong one, and the commit message
claimed the original had invented a step name that in fact existed. The parse was
methodologically better and factually worse, because the input was wrong.

An adversarial reviewer running the same command in a fresh worktree got 23 and
flagged the contradiction. That is the only reason it was caught.

## The check

```bash
cd ~/src/GitHub/rjmurillo/ai-agents
git rev-parse --abbrev-ref HEAD    # "HEAD" means detached
git rev-parse HEAD
git rev-parse origin/main          # compare
```

If they differ and you are about to assert a fact about repository content, verify in a
tree that is actually at the commit you mean:

```bash
git -C ~/src/GitHub/rjmurillo/ai-agents fetch origin main
git -C ~/src/GitHub/rjmurillo/ai-agents worktree add --detach ~/src/scratch/wt-check origin/main
```

Or read the blob directly, which needs no worktree:

```bash
git -C ~/src/GitHub/rjmurillo/ai-agents show origin/main:.github/workflows/pr-validation.yml
```

`git show <ref>:<path>` is the cheapest correct form and is immune to whatever the
working tree happens to be sitting on.

## Generalization

A better tool on a stale input is worse than a worse tool on a fresh one. When you
upgrade a verification method, re-verify the **input** at the same time. "I parsed it
properly" is not evidence if you parsed the wrong commit.

Pin the commit in the artifact. A memory that says "23 steps as of `03dc6a9ca`" stays
auditable when the workflow changes. One that says "23 steps" silently rots.

## Related

- [ci-validate-pr-is-many-gates-only-some-read-the-body](../ci/ci-validate-pr-is-many-gates-only-some-read-the-body.md).
  The memory this quirk corrupted, now pinned to a commit.
