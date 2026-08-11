# A conflict resolved for convenience records a falsehood

**Statement**: When a merge conflict has two valid sides, "take the side that
matches the base so the file stops conflicting" is not a resolution rule. It
optimizes for the next merge instead of for the truth, and it ships a wrong
value that every downstream gate accepts.

**Context**: Resolving conflicts by hand, especially on a stack where several
branches carry the same file. Applies to any field whose value is a fact about
the world rather than a preference: a commit SHA, a count, a timestamp, a
version.

## What happened

A squash merge severed a five-branch stack. Three branches each had to merge
their base again, and the same session log conflicted every time on one field:

```json
"endingCommit": "..."
```

Every side passed containment. `git merge-base --is-ancestor` said yes for all
of them, so the usual validity test could not discriminate. The resolution taken
was "match the base branch, then the file stops conflicting downstream."

That was wrong, and it was wrong twice.

| Branch | Recorded | Commit time | Rank |
| --- | --- | --- | --- |
| `fix/worktree-walk-timeouts` | `0d386e7a5` | 2026-08-06 17:15 | middle |
| `fix/gc-worktrees-stale-entries` | `cbed7c48f` | 2026-08-06 18:06 | **latest, correct** |
| `fix/gc-worktrees-admin-anchors` | `7e3590b9e` | 2026-08-06 12:46 | earliest, 5h off |

The session's own work log names the right answer in plain text:

> Repair merge cbed7c48f in a dedicated worktree

## Why the gates did not catch it

They were never asked the right question. `validate_session_json.py` checks that
the SHA resolves and is reachable:

```text
git cat-file -e <sha>^{commit}
git merge-base --is-ancestor <sha> HEAD
```

A negative control confirms it is not shape-only. Substituting a non-existent
SHA fails with "names no commit in this repository". So the PASS is real
evidence of **existence**, and no evidence of **correctness**. Three different
values all passed.

The cost is downstream. `endingCommit` bounds the range the episode extractor
reads. Moving it backward shrank the session's recorded range from 39 changed
paths to 27, understating the episode without failing anything.

## The rule

Ask which side is true, not which side is quiet. When both sides are valid, the
tie is broken by evidence outside the conflict, usually in the same file:

```bash
set -euo pipefail
FILE=".agents/sessions/2026-08-05-session-10005.json"
# Every SHA the log itself mentions, newest last.
git show "HEAD:$FILE" | grep -oE '\b[0-9a-f]{9}\b' | sort -u | while read -r sha; do
  git cat-file -e "${sha}^{commit}" 2>/dev/null || continue
  git merge-base --is-ancestor "$sha" HEAD || continue
  git show -s --format="%ci %h %s" "$sha"
done | sort
```

The last line that both resolves and is contained is the candidate. Read the
prose around it before accepting it.

## On a stack, check every branch, not just the one that conflicted

The conflict surfaced on one branch. The worst value sat on a different branch
that had not conflicted at all, because it merged later and its copy was simply
older.

Merge order decides the winner. The branch that merges **last** writes the value
that survives on the default branch, so fixing only the branch in front of you
leaves the bad value queued behind it.

```bash
set -euo pipefail
FILE=".agents/sessions/2026-08-05-session-10005.json"
for BRANCH in branch-a branch-b branch-c; do
  printf '%-40s ' "$BRANCH"
  git show "$BRANCH:$FILE" 2>/dev/null | grep -o '"endingCommit": "[a-f0-9]*"' || echo "(absent)"
done
```

Run that before you resolve, not after. It is three seconds and it is the only
way to see the value that will actually land.

## What this does and does not prove

Proven: three branches carried three different values for one field, all three
passed the validator, the chosen one was 5 hours and 12 changed paths away from
the truth, and the work log contained the answer the whole time.

Not proven: that a merge driver could have picked correctly. It could not.
Both sides were syntactically valid JSON with a valid SHA. No automated
resolution has the context to know which commit a session actually ended at.
This one needs a person or a model reading the prose.

## Related

- [git-conflict-resolution-workflow](git-conflict-resolution-workflow.md).
  The mechanical checkout, merge, commit loop. This memory is the judgement
  step that loop does not cover.
- [git-a-script-run-by-absolute-path-validates-its-own-worktree](git-a-script-run-by-absolute-path-validates-its-own-worktree.md).
  Same failure shape: a green result for a question nobody asked.
