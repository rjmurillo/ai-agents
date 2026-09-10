# Retrospective: two ADR rounds where the panel converged and execution disagreed

**Date**: 2026-09-09
**Scope**: ADR-072 round 1, ADR-101 round 12, issue #5669, branch `claude/adr-101-072-settle`
**Failure mode classification**: #6, multi-agent rubber-stamping
(`.agents/governance/FAILURE-MODES.md`), inverted. The panel did not rubber-stamp
a bad record; it converged, unanimously and independently, on a wrong factual
premise. Secondary touch on #4, false completion markers: a session's worth of
work was built against a record that had already been settled on `main`.

## What happened

Three ADRs were to be settled in one session. Two produced a result worth
recording, and the third produced a lesson about checking `main` first.

### ADR-064: a session of work against a record already settled

An earlier session had amended ADR-064, built a `.claude/commands/` prohibition
guard with 49 tests, hardened it through two review rounds, and committed it. On
merging `origin/main` the checkout turned out to be 33 commits behind, and ADR-064
was already `accepted` with `implemented: true`, settled on 2026-09-08 by issue
#5632. `.claude/commands/` held zero tracked files. `build/scripts/generate_commands.py`
was deleted. And `scripts/validation/check_commands_retired.py` had shipped a
guard strictly better than the one built here: it covers all three plugin roots
rather than one, reads HEAD **plus the index** so a staged violation fails before
the commit lands, and needs no baseline at all because the tree is empty, which
removes the grandfathering, the ratchet, and the stale-entry class outright.

Every hour of that work was wasted, and the session-start hook had said so:
"Checkout is 3 commit(s) behind `origin/main`. Investigation or triage against
this tree may be reasoning about dead code."

### ADR-072: five seats converged on a false premise

Six seats reviewed ADR-072. Five returned Block recommending `rejected`, all
resting on one claim: that a plugin-manifest `dependencies` field and explicit
content keys are capabilities the platform does not offer. The sixth seat ran
`claude plugin validate` and refuted it. Reproduced independently on 2.1.266
before anything was written into the record:

| Probe | Result |
|---|---|
| `dependencies` plus explicit `skills`/`commands` keys | passes |
| an unrecognized key | warns "Claude Code ignores it at load time", passes |
| `dependencies: "nope"` | `Invalid input`, fails |

The second and third are the controls. A field the host merely tolerated could
not be type-checked, so the hard type failure is what establishes the field as
first-class.

All five had read the same comment in `build/scripts/validate_plugin_manifests.py`,
which pins its rationale to Claude Code 2.1.122 measured on 2026-05-01, and read
a dated measurement as a standing platform law. None read the function beneath
it, `_is_repo_marketplace_manifest`, which gates the check on three hardcoded
paths, so the constraint they blocked on does not even reach a new plugin root.

### ADR-101: the round the cap ruling saved

ADR-101 had reached 6/6 Accept-or-Disagree-and-Commit at round 11, which meets
the documented consensus condition. The same line of `.claude/skills/adr-review/SKILL.md`
also says `Max 10 rounds`, and the log deferred that ruling to the owner three
times without resolution. The owner ruled the cap binding, so round 12 ran.

It returned two Blocks. Commit `a1278384f` had edited the record after round 11
with no panel pass, by its own PR body's admission, narrowing requirement 2's
guarantee to "the run terminated with an exit status the candidate cannot forge".
The candidate authors exactly that value:

```
two failing tests under pytest                                  exit 1
+ conftest.py whose pytest_sessionstart calls os._exit(0)       exit 0
```

Had the cap not been ruled binding, round 11's tally would have settled the
record and shipped that sentence.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Wasted session | High | A guard, 49 tests, and two review rounds against a settled ADR |
| ADR-072 near-miss | High | A `rejected` stamp on a record whose blocking premise was false |
| ADR-101 near-miss | High | A requirement whose operative sentence had no satisfiable reading |
| Citation rot | Medium | 11 stale citations, one wrong from the day it merged |

## Root cause, five whys

**Why did five independent seats reach the same wrong answer?**

1. Why did they block? Because the manifest schema appeared to lack `dependencies`.
2. Why did it appear to? Because a code comment said Claude Code rejects such keys.
3. Why was that believed? Because it is in-repo, specific, and cites a version.
4. Why did nobody check the version? Because the comment reads as a statement of
   platform behavior, not as a dated observation. It says "Claude Code 2.1.122
   rejects", present tense.
5. Why did five seats independently fail the same way? Because they were not five
   observations. They were one observation read five times.

Root cause: **agreement among reviewers who share a source is not corroboration.**
The panel's independence is in its reasoning, not in its inputs, and a stale
in-repo comment is a single point of failure that unanimity actively disguises.

## What went well

- **Asking the sixth seat to attack the consensus rather than join it.** The
  critic seat was briefed to break the emerging agreement. It did, by running
  something. A sixth confirming opinion would have been worthless.
- **Reproducing every subagent claim before acting on it.** Both refutations were
  re-run in the parent session before a word reached a decision record. The
  ADR-101 one took three lines and thirty seconds.
- **A seat reporting an absence as unverified.** Round 12's analyst had no
  issue-search tool and wrote `NOT RUN` rather than "no tracker exists". A search
  then found three open trackers, #5244, #5245, #5241. Had it asserted the
  absence, this session would have filed duplicates.
- **The citation-freshness gate.** Eleven citations were repaired by hand and the
  gate still rejected four, because it checks that the quoted content sits at the
  cited lines rather than that the numbers resolve.

## What to improve

- **Merge `origin/main` before the first edit, not before the first push.** The
  freshness hook fires at session start and is easy to read past. The cost here
  was an entire session's work.
- **Date every platform observation at the point of writing.** A comment saying
  "Claude Code 2.1.122 rejects X" should read "measured against 2.1.122 on
  <date>". The fix landed in this change; the class is wider, and
  `VALID_HOOK_EVENTS` in the same file still carries a ten-event list against
  thirty documented, which a memory already flags as a historical snapshot.
- **Treat unanimity as a prompt to find the shared input.** When N seats agree,
  ask what single artifact they all read. If one exists, execute against it.
- **A panel cannot verify a claim about code behavior.** ADR-101 says this about
  itself, and this session produced two more instances in one day. The
  falsification harness its Follow-up section proposes is unowned and gates two
  of its own phases; that is the single highest-value fix available.

## Artifacts

- `.agents/critique/ADR-072-jtbd-plugin-architecture-debate-log.md`, round 1
- `.agents/critique/ADR-100-101-enforcement-planes-debate-log.md`, round 12
- Issue #5669, the ADR-072 successor
- The obsolete ADR-064 branch, preserved locally as `claude/adr-064-amend-obsolete`
