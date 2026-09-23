# Retrospective: A wrong grep pattern manufactured a phantom failure mode

## Session Info

- **Date**: 2026-08-07
- **Agents**: Copilot CLI (Claude Opus 5) orchestrator, Gemini 3.1 Pro adversarial reviewer
- **Task Type**: Bug
- **Outcome**: Partial
- **Failure Mode**: Confident-incorrectness from an unvalidated measurement instrument

### Provenance of figures

Every number below is reproducible from the repository or from
`~/src/scratch/push*.log` on the authoring machine. The push-log counts come
from a single `grep -lE` over 779 files and are stated with the exact pattern
used, so a reader can rerun them. Nothing here is self-reported from memory.

## Phase 0: Data Gathering

### 4-Step Debrief

**Observe.** A five-PR stack needed its bottom branch pushed. Over the session I
concluded three separate times that a branch had failed to push silently. That
conclusion drove real work: re-pushes costing roughly twelve minutes each, a
memory written about unexplained push rejection, and a standing warning added to
my own operating notes.

**Respond.** I checked ground truth at the end by comparing `git rev-parse` to
`git ls-remote` for all five branches in the stack.

**Analyze.** Of the five, three were in sync, one was diverged for a documented
and expected reason (`gh pr update-branch` moved the remote ahead), and exactly
one was genuinely unpushed. The genuinely unpushed one was not silent at all: a
pre-push hook printed `ERROR: git push requires retrospective evidence for this
session` and exited 1.

**Adjust.** The phantom failure mode traces to one pattern.

## Phase 1: Root Cause

I detected "was this branch pushed" by grepping my captured push logs for the
receipt line `To github.com`.

Git does not write that line. When the remote is an HTTPS URL, git writes the
URL it actually pushed to:

```
To https://github.com/rjmurillo/ai-agents.git
 * [new branch]          docs/memory-push-gate-lessons -> docs/memory-push-gate-lessons
```

Measured over every push log on the machine:

| Pattern | Log files matched |
|---|---|
| `^To github\.com` (what I used) | 0 |
| `^To (https://)?github\.com` (correct) | 313 |
| total push logs | 779 |

The pattern I used has a 100 percent false-negative rate against this remote. It
cannot ever report a successful push. Every push looked like a failure, so the
first branch that genuinely was unpushed did not stand out as different, and
three normal successes were misread as a pattern of silent failure.

The specific misread: `push13.log` ends with a `[new branch]` receipt for
`docs/memory-push-gate-lessons`. I recorded in my notes that the log contained
"no `To github.com` line anywhere in it" and concluded the branch was never
pushed. Ground truth at the end of the session: that branch is IN SYNC, local
and remote both at `0cd0bf34c`. It had been pushed the whole time.

### Why this survived so long

Three properties made it self-reinforcing.

The instrument failed in the direction that generates work. A false "not pushed"
produces a re-push, which appears to fix it, which confirms the theory. A false
"pushed" would have been caught immediately by the next operation.

The instrument was never given a negative control. I never once ran the pattern
against a push I knew had succeeded. One such check would have returned zero
matches and ended this in seconds.

The remedy I reached for was documentation, not verification. When the
explanation would not close, I wrote it down as an open uncertainty ("the
mechanism is unpinned, do not fabricate a cause") rather than questioning
whether the observation was real. Refusing to fabricate a cause is correct.
Refusing to re-examine the evidence that produced the question is not.

## Phase 2: What Went Well

The habit of checking ground truth before claiming completion is what caught
this. `git rev-parse <branch>` compared against `git ls-remote origin
refs/heads/<branch>` is authoritative and cheap; parsing a log is neither.

The retrospective gate did its job. It blocked a push, printed the reason, and
exited nonzero. The one genuine problem in the set was loudly reported. The
noise came entirely from my own tooling.

Refusing to invent a mechanism for the unexplained rejection was right, and it
preserved the evidence trail that made this diagnosis possible.

## Phase 3: Corrective Actions

**Never parse a log to answer a question the tool answers directly.** Push
status has an authoritative query. Use it:

```bash
set -euo pipefail
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git ls-remote origin "refs/heads/$BRANCH" | cut -f1)"
if [ "$LOCAL" = "$REMOTE" ]; then
  echo "in sync at $LOCAL"
else
  echo "DIVERGED local=$LOCAL remote=${REMOTE:-none}"
fi
```

This is correct regardless of remote URL scheme, exit code, hook output, or
whether a log was captured at all.

**Give every new detection pattern a negative control before trusting it.** A
pattern meant to detect success must be shown to fire on a known success. A
pattern that has never matched anything is indistinguishable from a broken one,
and this session shows the broken case is not rare.

**Treat a zero-match grep as a claim about the pattern first.** When a search
for an expected string returns nothing, the two candidate explanations are that
the thing is absent and that the pattern is wrong. Rank them by cost: checking
the pattern is one command, acting on absence cost roughly thirty-six minutes of
re-pushes here.

**Anchor receipt patterns on the stable part of the line.** `^To ` plus the
repository name is stable. The scheme and host prefix are not, since a remote
can be SSH (`git@github.com:owner/repo.git`), HTTPS, or a mirror.

## Phase 4: Lessons

An instrument that only ever reports one answer is reporting its own defect, not
a measurement. The tell is uniformity: three branches in a row failing the same
novel way should have prompted suspicion of the detector before suspicion of
git.

Documenting an unexplained observation is not the same as validating it. Writing
"the mechanism is unpinned" recorded honest uncertainty about the cause while
silently promoting the observation itself to fact. The observation deserved the
same scrutiny as the explanation.

The cheapest check is usually against the tool's own authoritative interface,
not against its human-readable output. Human-readable output is not a contract
and changes with configuration.

## Related

- `.serena/memories/git/git-a-script-run-by-absolute-path-validates-its-own-worktree.md`, the same session's other instance of an instrument silently measuring the wrong thing.
