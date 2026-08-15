# Retrospective: the ADR that skipped its gate, then collided with its own number

Date: 2026-08-15
Branch: `adr/094-scoped-review-axes`
PR: #5062
Outcome: proposal rejected, recorded as ADR-095

## What happened

A draft ADR proposing `/review --axes=<list>` was authored, committed, and
pushed as ADR-094. `AGENTS.md:44` fires the `adr-review` skill on any
`ADR-*.md` edit. It did not fire, because `core.hooksPath` pointed at a
nonexistent `.githooks` directory (issue #5090). Every local gate was inert for
the life of that work.

When the hooks were repaired, `adr-review-policy` immediately blocked the next
commit with `ERROR: no debate log references the staged ADR IDs: ADR-094`. The
debate then ran, six roles, one round. It reached no consensus: two Block, three
Accept-with-changes, one Disagree-and-Commit. The deciding finding was that the
proposal's three motivating cost incidents merged 25 to 30 days before the
mechanism they were cited as evidence about existed. The maintainer rejected the
proposal.

Merging `origin/main` then surfaced a second failure: `ADR-094` was already
taken. `.agents/architecture/ADR-094-govern-copilot-cli-compatibility.md` was
accepted in PR #5024 and owns `.agents/critique/ADR-094-debate-log.md`. The
collision showed up as an add/add merge conflict on the debate-log path, not as
anything that named the real problem. The branch renumbered to ADR-095.

## Five whys: why did a draft reach review with anachronistic evidence

1. Why did the ADR cite incidents that predate its mechanism? The brief that
   fed it asserted the marker was the cost amplifier without checking when the
   marker started existing.
2. Why was that not caught in drafting? The incidents are real and the numbers
   in them are accurate. Only the causal attribution is wrong, and nothing about
   a correct number signals a wrong cause.
3. Why did the first QA pass not catch it? That QA checked text-rule
   conformance and that citations resolve. A citation to a real retrospective
   resolves whether or not the retrospective is about the right thing.
4. Why did ten review threads not catch it? All ten were real defects, and all
   ten were local: arithmetic, citation precision, an axis-validation gap. None
   asked whether the evidence base was about the right system.
5. Why did the debate catch it? Because three independent roles were asked to
   verify the ADR's citations rather than to review its reasoning, and one of
   them ran `git log --diff-filter=A` on the mechanism.

The root cause is not carelessness. It is that "does this citation resolve" and
"is this citation about the thing I am claiming" are different checks, and only
the first one is cheap and habitual.

## What worked

**Reading the checker instead of guessing the artifact.** The debate log's path
and format came from `scripts/validation/git_hook_policy.py
check_adr_review_policy`, not from recall. It passed the gate on the first
commit.

**Re-measuring the debate's own numbers before committing them.** One role's
headline finding was "32 merged PRs carry a review marker on `origin/main`,
mean 2.22, median 1". `origin/main` carries zero, because the repository
squash-merges and the empty marker commit is discarded. The finding survived in
a stronger form (14 marker commits exist, none merged) only because it was
checked. A second role's census was off by one in two counts. Neither error
would have been visible to a later reader.

This is `.claude/rules/canonical-source-mirror.md` working as intended, applied
to a subagent's output rather than to a docstring. A reviewing role is a source
like any other.

**The full fan-out earning its cost.** The counter-evidence handed to the debate
was that on PR #5059 four independent axes converged on a silent no-op that 26
passing unit tests missed. That evidence did not just weaken the proposal; it
became the concrete instance of the debate's fifth finding, because the defect
had been introduced by the fix for a previous defect and so was invisible to any
scoping keyed on previously-flagged axes.

## What did not work

**Inert hooks are silent.** Nothing reported that `core.hooksPath` pointed
nowhere. The failure mode is a green local run that checked nothing, which is
indistinguishable from a green local run that checked everything. The gates
worked the moment they were restored, so the gate design was never the problem.

**ADR numbers are allocated by looking, not by a gate.** Two branches took 094
concurrently and neither knew. The collision surfaced only because both wrote a
debate log to `.agents/critique/ADR-NNN-debate-log.md`, which forced an add/add
conflict. Had one of them used a different critique filename, both ADR-094 files
would have merged cleanly and the repository would hold two different ADR-094
records. No validator checks for a duplicate ADR id.

**One QA report cannot serve two session logs.** `validate_qa_report` binds a
report to exactly one session log and one commit, and CI validates every session
log on the branch against the same PR head. Two logs naming the same report made
one of them permanently red. The `SKIPPED: docs-only` sentinel is not an escape:
`validate_qa_skip_scope` rejects it unconditionally. So every session log on a
branch needs its own QA report bound to the last content commit. That is not
written down anywhere; it was derived by probing the validator.

**A concurrent writer touched this worktree.** Two unattributed working-tree
changes appeared mid-session: a QA-binding rewrite, and a 187-line revision of
the ADR. Both were plausible and one was good work. Both were reverted, because
committing content of unverified provenance under this session's name is not
acceptable regardless of quality. Diffs were preserved.

## Actions

| Action | Rationale | Status |
|---|---|---|
| Record the proposal as a rejection at ADR-095 rather than closing PR #5062 silently | A rejected ADR that says why stops the same proposal returning | Done |
| Keep the subset-marker finding alive as its own issue | 11 of 14 markers name a subset and 4 name a nonexistent `code-review` axis; `validate_review_marker.py` never checks membership. Independent of the rejected proposal | Open, named in ADR-095 and the debate log |
| Consider a duplicate-ADR-id validator | Nothing catches two branches taking one number; the collision here was luck | Proposed, not filed |
| Consider writing down the one-QA-report-per-session-log rule | Derived by probing; the next session will re-derive it | Proposed, not filed |

## Evidence

- `c3ddc571a` 2026-05-24, `/review` becomes a skill.
- `16c960418` 2026-06-04, the SHA-bound marker lands.
- PR #1887 merged 2026-05-05; PRs #1965 and #1979 merged 2026-05-10.
- `458028d2b`, PR #5010, risk-based axis selection, the approach that shipped.
- `.agents/critique/ADR-095-debate-log.md`, the debate and its verification section.
- Issue #5090, the inert-hooks incident.
