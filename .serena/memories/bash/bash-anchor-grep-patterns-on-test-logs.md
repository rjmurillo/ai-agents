# Skill: Grepping a push or CI log without flooding the context (90%)

## Statement

An alternation containing a common English word matches far more than the log
line you wanted. `grep -E "REAL_EXIT|new branch|error:|rejected"` over two push
logs returned **90 KB**, because pytest test ids contain the word:
`test_absolute_source_dir_rejected`, `test_relative_path_rejected`, and dozens
more. The signal was four lines.

Anchor every pattern to the position the real line occupies.

## Recipe

```bash
grep -E "^REAL_EXIT|^error:|^ ! \[remote rejected\]|^[[:space:]]*\* \[new branch\]|^ [0-9a-f]{7,}\.\.[0-9a-f]{7,}" "$LOG"
```

Each alternative is pinned: `REAL_EXIT` and `error:` at column zero, git's
transport lines to their exact rendered prefix. A push log carries thousands of
pytest lines and roughly five git lines, so an unanchored word is the wrong
instrument by three orders of magnitude.

Bound the output regardless: `| head -20`. A guard costs nothing when the
pattern is right and saves the window when it is not.

## Generalization

The same failure mode has two siblings already recorded in this repo:

- `grep -v "^./.git"` silently drops every `.github/` path, because `.git` is a
  prefix of `.github`. Use `git grep`.
- An unbounded `ls` on `/tmp` floods for the same reason: the filter was never
  the constraint, the population was.

The common shape: **a filter chosen for what it keeps, never checked against
what the corpus actually contains.**

## The mirror image: an empty result is not evidence of absence

The same unvalidated-instrument error runs the other way. `git grep 'ratchet:'
-- lefthook.yml` returns nothing, which reads as "the ratchet jobs are gone."
They are not. Lefthook jobs are YAML **list entries** (`- name: python-lint-ratchet`),
not mapping keys, so nothing in the file ever ends in `ratchet:`. Plain
`grep -c ratchet lefthook.yml` returns 8 on the same file.

Before reporting that a grep found nothing, prove the pattern can match by
loosening it one step:

```bash
grep -c "<the bare word>" "$FILE"   # does the corpus contain the term at all?
git grep -c "<your pattern>" -- "$FILE"
```

If the bare word appears and the pattern does not, the pattern is wrong, not the
corpus. That is the same lesson as the `.git` / `.github` prefix trap, arriving
as a false negative instead of a flood.

## Verify the instrument first

```bash
grep -Ec "<pattern>" "$LOG"
```

A count is one line of output and tells you whether the full grep is safe to
run. Do this whenever the log is a test run, since test ids are prose.

## Anti-Pattern

Adding a word to an alternation because it appears in the failure you are
hunting, without asking whether it also appears in the 21000 test names the same
log contains.

Equally: reading a push log to decide whether a push succeeded. The log's own
`RESULT: All validations passed` and `Ready to create pull request!` lines come
from `pre_pr.py` describing itself, not from git. Confirm against the asset:

```bash
git ls-remote origin <branch>
```

## A backgrounded push outlives the shell that started it

Related trap, same discipline. A push launched with `&` keeps running after its
shell is killed or the session moves on. Relaunching it "because the first one
died" puts two pushes on the same branch, and the loser reports:

```
 ! [remote rejected] <branch> -> <branch> (cannot lock ref 'refs/heads/<branch>': reference already exists)
error: failed to push some refs
REAL_EXIT=1
```

That exit 1 is a race, not a rejection of the work. The first push created the
ref; the second still believed it was creating one, because the local
remote-tracking ref had not been updated. The message says `already exists`
precisely because the create raced a create.

Before relaunching, check the asset and the process:

```bash
git ls-remote origin <branch>          # did the first one already land?
pgrep -af "git push"                   # is it still running?
```

Then reconcile before believing either answer, since `ls-remote` reflects the
remote at the instant it ran and an in-flight push can land a second later:

```bash
git fetch origin <branch>
git merge-base --is-ancestor origin/<branch> HEAD && echo "local is ahead or equal"
git rev-parse HEAD origin/<branch>     # equal means the work is on the remote
```

Do not read the pre-push hook's success banner as push completion. This repo's
hook prints

```
RESULT: All validations passed

Ready to create pull request!
```

and that text appears in the push log roughly two minutes in, while the ref
transfer has not started. Misread once on 2026-08-02: `ls-remote` came back
empty right after that banner, which looked like a failed push and was actually
a push still running. The only completion signals are a non empty
`git ls-remote origin <branch>` matching local `HEAD`, or the `REAL_EXIT=` line
the wrapper appends after `git push` returns.

Better than detecting the race is preventing it. Serialize pushes through a
lockfile, keyed on the branch:

```bash
BR=$(git rev-parse --abbrev-ref HEAD)
SLUG=$(printf '%s' "$BR" | tr '/' '-')
mkdir -p "$HOME/src/scratch/locks"
flock "$HOME/src/scratch/locks/push-lock-$SLUG.lock" git push -u origin "$BR"
```

`flock` waits for the lock rather than failing, so a queued push runs when the
one ahead of it finishes instead of racing it.

Key the lock on the branch, not on the repo. The collision that actually
happens is two agents pushing the SAME ref; two pushes to different refs never
contended. A single global lock (`/tmp/aiagents-push.lock`) serializes every
push behind an 11 minute pre-push hook it did not need to wait for. See
`.serena/memories/git/git-lock-pushes-per-branch-not-globally.md` for the measurement.

Every agent must name the lock identically or it excludes nothing. Measured
2026-08-02: three schemes were live at once (`/tmp/aiagents-push.lock`,
`/tmp/aiagents-push-$SLOT.lock` hashed into four slots, and the per branch
path above), and one branch had two concurrent pushes running under two
different lock names. `flock` only excludes processes that agree on the path,
so the extra schemes bought nothing and hid the race. The path above is now the
only sanctioned one: `.claude/rules/push-lock.md` states it and
`scripts/validation/check_push_lock_paths.py` fails a tracked prescription that
names anything else (issue #4366).
<!-- push-lock-historical: the two dead scheme names above are the 2026-08-02
census, evidence of what was live, not a recipe to copy. -->


The lock file currently lives under `/tmp`. The requirement is that every agent
names it identically, since `flock` excludes only processes that agree on the
path; `/tmp` is just the one absolute path every agent here can already name.
The push *log* must not go there: use `~/src/scratch`. See
`.serena/memories/git/git-lock-pushes-per-branch-not-globally.md` for the `/tmp`-wipe hazard this
carries and how to detect it.

## Evidence

2026-08-02: the 90 KB flood, recovered by re-running with anchored patterns
against the same two files. The corrected grep returned 4 lines and answered the
question, which was whether two backgrounded pushes had landed.

Later the same day, the corrected pattern paid for itself. Run against a push
log it returned three lines, the `remote rejected` line, the `error:` line, and
`REAL_EXIT=1`, which turned out to be the concurrent-push race above. A
`git rev-parse HEAD origin/<branch>` then showed the two SHAs equal: the work
had landed and only the duplicate push had failed.

## The SHA in a push log is not necessarily the SHA that landed

`git push origin <branch>` resolves the ref at transfer time, not at invocation
time. The pre-push hook runs first and is slow here: a full run is roughly 11
minutes, and one measured `python-tests` step alone took 1030 seconds. Any
commit made to that branch while the hook is running is included in the transfer
that follows.

So a background push whose log reads `de60979fb..4ef4bfb80` can leave the remote
at a third SHA entirely, with no error and no second push. That was observed on
2026-08-02 and recorded as unexplained at the time. It is not a race and not a
bug; it is the ordering of hook execution against ref resolution.

Two consequences:

- Do not verify a push by reading the SHA range in its log. Verify with
  `git ls-remote origin <branch>` and compare against `git rev-parse HEAD`.
- A push launched during active work on the same branch is not a snapshot of
  what you had when you launched it. If you need a specific commit pushed and
  nothing after it, stop committing until the transfer completes.
