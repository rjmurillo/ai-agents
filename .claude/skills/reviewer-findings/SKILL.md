---
name: reviewer-findings
version: 1.0.0
description: Verify a review finding before acting on it. Splits a finding into verdict, diagnosis, and prescribed fix, each needing its own evidence, so you verify before you fix and check the supporting claims rather than only the conclusion. Use when you say "address this review comment", "the bot flagged this", "handle this finding", "a sub-agent reported this", or when you inherit findings from a prior session. Do NOT use to produce a review (use review) or to run the PR thread workflow end to end (use pr-comment-responder, which applies this per finding).
license: MIT
---

# Reviewer Findings

A review finding is evidence that someone looked, not proof that they were
right. Verify it before you act on it. This skill is the discipline for
consuming a finding; it does not produce one.

## Triggers

- `address this review comment`
- `the bot flagged this`
- `handle this finding`
- `a sub-agent reported this`

Also fires without any of those phrases when a bot or human leaves a review
comment, when an adversarial sub-agent or a model on another family returns a
report, or when you inherit findings from a compaction note, a handoff, or a
prior session.

## The three claims

A finding is up to three separate claims stacked together. Each carries its own
evidence, and each can fail while the others hold.

| Claim | Example | What it is worth on arrival |
|---|---|---|
| Verdict | "this fails on Windows" | A hypothesis until you reproduce it |
| Diagnosis | "because that call is POSIX-only" | An account of the repro, not proof of it |
| Prescription | "guard the call or skip on Windows" | A claim with its own decay |

A correct verdict can carry a wrong diagnosis. A correct diagnosis can carry an
incomplete fix. Accepting the bundle because the top line is right is how a
wrong fix lands with a green review.

## Process

1. **Establish the verdict.** For a behavioral claim, write the fixture, run
   it, read the output. For a structural claim, read the cited code. Do this
   before you write the fix, not after.
2. **Test the diagnosis separately.** A repro proves the behavior. It does not
   prove the stated cause. Change the one thing the diagnosis blames and see if
   the repro flips.
3. **Re-verify the prescription at apply time.** The fix was written against
   the tree as the reviewer saw it. Confirm it still applies, still compiles,
   and still covers the failure you reproduced.
4. **Check the supporting claims.** "The repo already does this" and "this is
   the standard pattern" are load-bearing and cheap to check. Count the call
   sites before you trust the count.
5. **Prefer the codebase's own idiom.** If the repo already carries a complete
   pattern for this failure, use it instead of the reviewer's invention.

## MUST

1. **Verify before you fix, with the strongest evidence the claim admits.** A
   behavioral claim ("it fails on Windows") needs an executed reproduction. A
   structural claim ("this guard is missing") is settled by reading the cited
   code. Applying a fix on the reviewer's say-so alone leaves you unable to
   tell a fix from a no-op.
2. **Say what you measured when you decline.** "I do not think this is a
   problem" is not a reason. "I ran the fixture on both paths and neither
   raised" is.
3. **Re-verify the prescribed fix at apply time**, against the tree in front of
   you, not the tree the reviewer read.
4. **Report evidence you cannot get.** Leave the thread open and say what you
   tried. Do not close it as unfounded because one attempt to settle it failed.

## SHOULD

1. **Scale effort to the claim.** A `Nit:` needs no evidence beyond reading it.
   A correctness or security claim needs the strongest evidence available, and
   an executed reproduction whenever the claim is about behavior.
2. **Check the supporting claims, not only the conclusion.** A finding whose
   conclusion is right and whose supporting count is wrong usually has a fix
   that is scoped wrong too.
3. **Prefer this codebase's existing idiom** over an invented one when both
   close the same hole.

## MUST NOT

1. **MUST NOT resolve a thread by rote compliance.** Applying an unverified fix
   to close an unexamined thread converts a review into paperwork.
2. **MUST NOT treat agreement between reviewers as proof.** Two models sharing
   a training distribution share blind spots. Agreement raises the prior; it
   does not replace verification.
3. **MUST NOT use this skill to dismiss findings.** The default posture is that
   the reviewer saw something real. Verification decides what it was, not
   whether to engage.

## Replying

State the measurement, then the disposition.

- Confirmed: name the evidence, the fixture and its output or the file and line
  you read. Then the fix.
- Declined: name what you ran or read and what it showed. Not what you believe.
- Unreproduced: name what you tried, leave it open, say what would settle it.

## Verification

Before you resolve the thread:

- [ ] The verdict is settled by evidence you produced, not by the finding asserting it.
- [ ] The diagnosis was tested separately from the verdict.
- [ ] The prescribed fix was re-checked against the tree in front of you.
- [ ] Every supporting count, and every "the repo already does this", was checked.
- [ ] Your reply names the evidence rather than your confidence.

## Why this exists

Each pattern below was observed on this repository's own review threads, and
each is readable in the review history of the PRs referenced at the end.

- A reviewer certified a code path as sound while it still held two live
  fail-opens. The verdict was wrong in the direction nobody double-checks.
- A model attached a fixture that reproduced the failure correctly while its
  diagnosis of the cause was wrong. Its proposed fix, applied as written, would
  have rejected every one-character name.
- A bot filed a real cross-platform defect. Its supporting claim, that the
  repository already followed the pattern it prescribed, did not hold across the
  call sites it implied. Its prescribed fix covered part of the failure, and the
  codebase already carried a more complete idiom.

Each is a finding worth engaging and a fix not worth applying as written. That
combination is the whole reason this skill exists: the reviewer earns your
attention, not your compliance.

## Anti-Patterns

- **Applying the prescribed fix because the verdict was right.** The three
  claims are independent. A finding can name a real defect and still prescribe
  a fix that is wrong, partial, or already superseded by a better idiom in the
  tree.
- **Rejecting the whole finding because one claim failed.** A wrong diagnosis
  does not clear the defect. Re-derive the cause and fix the thing that is
  actually broken.
- **Verifying against the diff instead of the tree.** A finding written against
  an earlier push may describe code that no longer exists, or miss code that
  now does. Check the current tree.
- **Treating agreement between reviewers as verification.** Two reviewers
  reading the same wrong assumption produce two findings, not two proofs.
- **Resolving a thread with prose.** A verdict without a command, a file and
  line, or a measurement is an opinion. Close the thread with the evidence.
