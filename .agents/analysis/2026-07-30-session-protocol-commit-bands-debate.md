# Debate: correcting the commit-count bands in SESSION-PROTOCOL

Date: 2026-07-30
Trigger: `.agents/SESSION-PROTOCOL.md` edit, which fires adr-review per AGENTS.md.
Issue: #3944. Branch: `fix/commit-threshold-drift`.

## Question under debate

Live guidance taught a commit-count warning threshold of 15 and attributed the
rule to ADR-008. The enforcing module warns at 10 and ADR-008 contains no such
rule. Should the correction touch `.agents/SESSION-PROTOCOL.md`, which is live
protocol and therefore gated, or stop at `AGENTS.md` and the skill documents?

## Ground truth

Established by executing the classifier, not by reading constants:

```text
limit=20: OK 0-9, WARNING 10-14, ALERT 15-20, BLOCKED 21+
limit=40: OK 0-9, WARNING 10-14, ALERT 15-40, BLOCKED 41+
```

Constants in `scripts/validation/pr_commit_count.py`: 10, 15, 20, 40.
`scripts/validation/git_hook_policy.py` imports them rather than restating them,
so hook and CI cannot drift from each other.

## Round 1: grok-4.5, verdict REQUEST CHANGES

Position: stopping short of SESSION-PROTOCOL leaves the protocol split-brain on
the one gate the change exists to fix. `AGENTS.md` names SESSION-PROTOCOL as the
protocol of record, and it is the section agents expand into for the Mid gate.
It still said "warn when commit count reaches 15" and carried a table reading
"< 15 continue / 15-19 WARNING / >= 20 BLOCKED". All three bands were wrong, and
20 is allowed rather than blocked.

Second finding: every corrected document now cites
`scripts/validation/pr_commit_count.py` as the authority, and that module's own
header comment still said "ADR-008 relieves the ceiling to 40". A citation that
leads the reader back to the phantom claim defeats the correction.

Counter-position considered and rejected: that the ADR-review gate makes the
SESSION-PROTOCOL edit too expensive to be worth it. Rejected because the cost of
the gate is not evidence that the guidance should stay wrong.

Resolution: accepted both findings. SESSION-PROTOCOL bands corrected to match
the classifier; the ADR-008 attribution removed from the cited module.

## Round 1 correction to the author's own evidence

grok-4.5 also showed that the claim in issue #3944, that no ADR defines a commit
ceiling, was wrong. `.agents/architecture/ADR-049-pre-pr-validation-gates.md:35`
contains `| Commit count vs. base branch | <=20 |`. Removing ADR-008 remains
correct, because ADR-049 defines neither the warn threshold, the alert
threshold, nor the 40 relief. The claim was not repeated in the PR body.

## Constraint discovered during implementation

`scripts/validate_workspace_budget.py` caps `AGENTS.md` at 3000 bytes with a
strict greater-than comparison. The file sat at 2991 bytes, so the first attempt
at a more explicit Mid line pushed it to 3056 and failed the gate. The line was
rewritten to shrink rather than grow: it now carries the corrected warn
threshold and drops the phantom citation, ending at 2982 bytes. The alert band
and the 40 relief remain documented in
`.claude/skills/ai-agents-change-control/references/gate-ladder.md` and
`.claude/skills/ai-agents-diagnostics-toolkit/references/instrument-guides.md`,
which have room for them.

## Rounds 2 and 3: in flight at time of writing

Two independent reviews on different model families were dispatched against the
corrected tree: one arithmetic and gate review, one governance review covering
proportionality of the ADR-review gate, choice of citation authority, and
whether shrinking `AGENTS.md` loses more than it gains. Their findings are
recorded in the session log for this session and, where they require code
changes, in follow-up commits on this branch.

## Scope line applied

Live guidance is corrected. Historical artifacts are not. Retrospectives,
session logs, and incident narratives such as
`.claude/skills/ai-agents-failure-archaeology/references/incidents.md` keep the
ADR-008 wording, because rewriting them would falsify the record of what the
project believed at the time. The Serena memory
`.serena/memories/session/session-protocol-observations.md` is treated as live,
not historical: it is a retrieval surface future sessions load as current
guidance, and its actionable line told agents to display "Commit X/20
(ADR-008)". The attribution was corrected there while the historical evidence
line recording 59 commits on PR #908 was left intact.
