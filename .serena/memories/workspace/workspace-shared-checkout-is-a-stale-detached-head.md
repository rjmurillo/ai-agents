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

## The second form: stale *tooling*, not stale *facts*

The section above is about reading the wrong content. There is a nastier variant:
**running** a repository script from the shared checkout executes a version of that
script that may be hundreds of commits old. The failure does not look like a stale
read. It looks like a live bug in the tool.

2026-08-05. `new_pr.py` was invoked from the shared checkout and died in its first
gate:

```
Session End validation failed
```

That was the whole message. The diff it was validating had **926** files. The branch
contained **2**.

```bash
git diff --name-only main...docs/subagent-worktree-hazard | wc -l   # 926
git rev-list --count main..origin/main                              # 101
```

Local `main` was 101 commits behind, so the three-dot merge-base was ancient and every
file merged upstream since looked like part of the branch. That pulled `.agents/`
session logs belonging to other people into the changed set, and Session End validated
the newest one it found.

`git fetch origin main:main` dropped 926 to 2 and the gate passed. That looked like a
complete diagnosis. It was not.

### Why the obvious diagnosis was wrong

Two explanations fit every observation:

1. The local `main` ref was stale, and refreshing it fixed the bug.
2. The **script** was stale, and current `new_pr.py` never had this bug.

The fast-forward is consistent with both, so it confirms neither. Checking the tool
version separates them:

```bash
grep -c resolve_comparison_base .claude/skills/github/scripts/pr/new_pr.py
# current origin/main: 2  (defined, and called)
# shared checkout:     0  (absent entirely)
```

Explanation 2. `resolve_comparison_base` diffs against `refs/remotes/<remote>/<base>`
instead of the local branch, and its docstring names this exact failure, Session End
included. The bug had been fixed upstream 101 commits earlier. The shared checkout was
the only place left that could still reproduce it.

The stale tree also suppressed the evidence. Current `new_pr.py` does not print a bare
`Session End validation failed`. It names the offending log, explains the cause, and
prints the validator's own output:

```
Session End validation failed for <path>
  (selected as the newest log in 'git diff main...<head>'. If that log is not
  yours, the base is behind: run 'git fetch origin' and retry.)
```

That message would have ended the investigation in one read. The shared checkout was
old enough to reproduce the bug *and* old enough to lack the diagnostic added to
explain it, which is the compounding hazard: stale tooling hides the fix and the
explanation together.

Had the investigation stopped at the fast-forward, the conclusion would have been a
memory documenting an already-fixed bug and prescribing "keep local `main` fresh" as
the remedy, when the real remedy is "do not run repository tooling from the shared
checkout."

### The check

Before diagnosing any repository script that misbehaves, establish which version ran:

```bash
git rev-list --count HEAD..origin/main    # how stale is this tree?
```

Non-zero means the script you just ran is not the script on `origin/main`. Reproduce in
a current worktree before believing the failure is real. Run repository tooling from a
worktree cut from `origin/main`, not from the shared checkout.

### Generalization

A tool failure is evidence about a *version* of the tool, not about the tool. When a
fix makes the symptom disappear, check that the fix explains the symptom **better than
the alternatives**, not merely that the symptom stopped. A remedy that is consistent
with two root causes has confirmed neither, and shipping it as knowledge propagates the
wrong one.

## Related

- [ci-validate-pr-is-many-gates-only-some-read-the-body](../ci/ci-validate-pr-is-many-gates-only-some-read-the-body.md).
  The memory this quirk corrupted, now pinned to a commit.
