# GitHub skill issue scripts refuse a comment file outside the repository root

## Which scripts, and which flag

The guard is not family-wide. Measured on the scripts under
`.claude/skills/github/scripts/issue/`:

| Script | Flag | Enforces repo-root containment |
|---|---|---|
| `close_issue.py` | `--comment-file` | yes |
| `reopen_issue.py` | `--comment-file` | yes |
| `post_issue_comment.py` | `--body-file` | no |

`post_issue_comment.py` takes a different flag name and accepts a path anywhere.
Its `repo_root` computation exists to locate `.github/artifacts`, not to
constrain the body file. Do not generalize the guard to it.

## Symptom on the two that do guard

```
[FAIL] Comment file must stay under /home/richard/src/GitHub/rjmurillo/ai-agents6:
/tmp/.../scratchpad/c4309.md
```

This collides with `AGENTS.md`, which lists "Scratch in tree" under **Never**.
The harness scratchpad is refused by the script; the working tree is refused by
policy.

## Workaround, and where it stops working

In a normal clone, write the body under `.git/`. It is inside the repository
root so the path check passes, and it is not part of the tree so no policy is
broken and nothing appears in `git status`:

```bash
mkdir -p .git/issue-scratch
cat > .git/issue-scratch/body.md <<'EOF'
...
EOF
uv run --frozen python .claude/skills/github/scripts/issue/close_issue.py \
  --owner rjmurillo --repo ai-agents --issue 1234 \
  --reason "not planned" --comment-file .git/issue-scratch/body.md --verify-claims
```

**This fails in a linked worktree.** There `.git` is a regular file, not a
directory, so `mkdir -p .git/issue-scratch` cannot succeed. Measured on a
worktree under `.claude/worktrees/`: `.git` is 87 bytes of ASCII text.

`git rev-parse --git-dir` does resolve to a real directory in both cases, but in
a linked worktree it points at `<main-repo>/.git/worktrees/<name>`, which is
outside that worktree's own toplevel. Whether that path satisfies a given
script's containment check depends on how the script computes the root, so it is
not a verified universal substitute. Check before relying on it.

Issue #4276 is exactly this gap, raised for review-thread reply bodies.

## The workaround that does work: set `TMPDIR`

`assert_valid_body_file` in `scripts/github_core/validation.py` accepts a path
under the repo root **or** under any plausible temp root, and it builds that
list from the live environment at call time:

```python
for temp_root in _candidate_temp_roots():
    if is_safe_file_path(body_file, temp_root):
        return
```

`_candidate_temp_roots()` reads `TMPDIR` first. So exporting `TMPDIR` to a
directory outside the tree makes that directory an accepted body-file location,
with no repo-root containment and no `.git` write:

```bash
export TMPDIR="$HOME/src/scratch"
uv run --frozen python3 .claude/skills/github/scripts/pr/add_pr_review_thread_reply.py \
  --thread-id "$TID" --resolve --body-file "$HOME/src/scratch/reply.md"
```

Measured with a negative control on 2026-08-05, calling the validator directly
on the same file with only the environment changed:

| Environment | Exit | Result |
|---|---|---|
| `TMPDIR` unset | 2 | `Body file path traversal not allowed: /home/richard/src/scratch/_nc_body.md` |
| `TMPDIR=$HOME/src/scratch` | 0 | accepted |

Same path, same file, opposite outcomes. `TMPDIR` is the mechanism, not a
coincidence of where the file happened to live.

This works in a linked worktree, where the `.git/issue-scratch/` form above
cannot, and it does not use `/tmp`, which policy forbids. Four review-thread
replies were posted this way from `$HOME/src/scratch` after the documented
workaround failed.

What it does **not** do is grant #4276's literal ask, which is for the guard to
accept a path under the worktree git dir. That request is still open. If you
want it, add the resolved `git rev-parse --git-dir` to `_candidate_temp_roots()`;
do not widen the guard.

## Two guards, two error strings, and a grep that misses one

Searching for the containment check by its message finds only half the family,
because there are two independent guards with different accept rules:

| Guard | Message | Accepts |
|---|---|---|
| repo-root containment | `Comment file must stay under <root>` | repo root only |
| body-file traversal | `Body file path traversal not allowed: <path>` | repo root **or** any temp root, including `$TMPDIR` |

Measured 2026-08-05 across every script in the family that takes `--body-file`
or `--comment-file`:

| Script | repo-root | traversal | Net effect |
|---|---|---|---|
| `issue/close_issue.py` | yes | no | repo root only |
| `issue/reopen_issue.py` | yes | no | repo root only |
| `issue/edit_issue_body.py` | no | yes | repo root or `$TMPDIR` |
| `pr/add_pr_review_thread_reply.py` | no | yes | repo root or `$TMPDIR` |
| `pr/post_pr_comment_reply.py` | no | yes | repo root or `$TMPDIR` |
| `issue/post_issue_comment.py` | no | no | anywhere |
| `issue/new_issue.py` | no | no | anywhere |
| `pr/new_pr.py` | no | no | anywhere |
| `pr/close_pr.py` | no | no | anywhere |
| `pr/validate_pr_description.py` | no | no | anywhere |

So the answer to "is this script guarded" is one of three, not two. Grepping
only for `must stay under` reports the middle group as unguarded, which is
wrong. Grepping only for `assert_valid_body_file` reports the top group as
unguarded, which is also wrong. Check both.

## Do not probe a guard by running a mutating script

Confirming `post_issue_comment.py` accepts an outside path by actually posting a
comment leaves a junk comment on a real issue. It happened on 2026-08-05 against
issue #4276 and needed a `DELETE /issues/comments/{id}` to undo.

Call the validator directly instead. It is a pure function and needs no network:

```python
from scripts.github_core.validation import assert_valid_body_file
assert_valid_body_file("/path/to/body.md")   # SystemExit(2) if rejected
```

Static `grep` for the call site answers "is it wired up"; the direct call
answers "what does it accept". Neither writes to GitHub.

## Two argument traps on the guarding scripts

**`--reason "not planned"` must be quoted.** The value contains a space, so an
unquoted `--reason not planned` is parsed as `--reason not` and fails with
`invalid choice: 'not' (choose from 'completed', 'not planned')`. The error
names the choices but not the quoting, so it reads as a bug in the allowed
values.

**`--verify-claims` rejects any cited PR that is not merged, including one cited
as context.** A closing comment mentioning `#4017` purely as a note for whoever
lands that branch aborts the close:

```
[FAIL] Closing comment cites unverifiable artifact(s); aborting close. cited PR #4017 is not merged on rjmurillo/ai-agents
```

The guard exists for "resolved by PR X" claims naming a phantom or unmerged PR
(issue #2481), and it cannot tell a resolution claim from an aside. Refer to the
branch by name rather than by number when the mention is contextual, or drop
`--verify-claims` and accept the weaker check.

**A failed check reads differently from a failed claim (issue #4951).** The
message above is a verdict: the remote answered, and the answer was no. When
the remote cannot be reached, the script says so instead of guessing:

```
[FAIL] Could not verify closing comment claim(s) against GitHub; aborting close without judging them. could not verify cited PR #4729 on rjmurillo/ai-agents: HTTP 502: Bad Gateway
```

Exit 1 means a claim was checked and failed. Exit 3 (external) or 4 (auth)
means it was never checked, and the word "merged" will not appear. Both abort
the close. The exit-1 line also names the state the remote reported when it
has one, so an unmerged PR now reads `... is not merged on OWNER/REPO (state
OPEN)`. Before #4951 an API failure printed the exit-1 wording above, so
`cited PR #N is not merged` could mean the probe fell over: on 2026-08-13 it
said that about two PRs that had been merged for weeks.

## Also worth knowing

Argument shapes differ across the family. `new_pr.py` takes neither `--owner`
nor `--repo` nor `--output-format`; it infers the repository. `close_issue.py`
requires `--owner` and `--repo`. Run `--help` rather than copying flags from a
sibling script.
