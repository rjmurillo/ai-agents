# Decision: premise verification (issue #5069) reused reviewer-findings, not a new script

## Question

Issue #5069 asked for a "premise-verification step" in `pr-comment-responder`'s
triage phase, and the auto-generated PRD attached to the issue proposed a new
Python helper script (`verify_finding_premise.py`), a new triage taxonomy
(`PREMISE_TRUE`/`PREMISE_FALSE`/`PREMISE_UNVERIFIABLE`), and flagged a
"CRITICAL blocking question" about whether an unverifiable premise should keep
a thread open or resolve it.

## Conventional answer (the auto-generated PRD)

Build a new scripted verification helper with a JSON contract, wire it into a
new triage branch, and escalate the open/resolve policy question to a human
before implementing.

## First-principles position

`reviewer-findings` already implements almost the whole ask: the three-claims
split (verdict/diagnosis/prescription), MUST 3 (re-verify the prescribed fix
against the current tree), and MUST 4 ("report evidence you cannot get, leave
the thread open"). `pr-comment-responder` Phase 2 step 4 already routes every
actionable finding through `Skill(skill="reviewer-findings")` before
implementing. So the PRD's proposed new script and taxonomy would have
duplicated an existing mechanism (a DRY violation), and its "blocking
question" was already answered by MUST 4: an unverifiable premise stays open,
it does not auto-resolve.

## Evidence

- `.claude/skills/reviewer-findings/SKILL.md` (before this change): "Confirmed
  / Declined / Unreproduced" reply dispositions already map onto
  premise-true/false/unverifiable; MUST 4 already says "leave the thread
  open."
- `.claude/skills/pr-comment-responder/SKILL.md` Phase 2 step 4 (before this
  change): already invokes `reviewer-findings` per finding.
- `.serena/memories/pr-review/dispatched-model-reviewer-reliability.md`: the
  concrete failure shape (six findings on PR #4485, all refuted by
  `git log -S`) already names the exact commands (`git grep -F`,
  `git log -S`) that were missing from `reviewer-findings`' prose.

## Decision

Scoped the change down to what was actually missing: explicit `git grep -F`
(current state) / `git log -S` (provenance) instructions in
`reviewer-findings`, a premise-true/false/unverifiable disposition table
naming the existing Confirmed/Declined/Unreproduced replies, a gate in
`pr-comment-responder` Phase 3 that routes a refuted premise to
`Action: Reply Only` before `Action: Implement` can be chosen, and a new
"Premise Refuted" reply template. No new script, no new taxonomy, no
escalation needed: `reviewer-findings` MUST 4 already answered the PRD's
blocking question. Landed in PR for issue #5069 (commits `743a05a`,
`bad269d`).
