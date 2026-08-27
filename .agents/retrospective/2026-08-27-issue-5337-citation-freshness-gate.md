# Retrospective: Issue #5337 (citation freshness gate)

## Session Info

- **Date**: 2026-08-26 to 2026-08-27
- **Agent**: Claude Code (remote session)
- **Task Type**: Feature (deterministic validation gate), from a cost analysis
- **Outcome**: Shipped on PR #5338; two Copilot review rounds fully addressed

## What shipped

The user's framing: mechanically checkable claims were reaching paid AI
review rounds instead of a free local check, one full push cycle each (PR
#5335 spent its third cycle on a claim a grep verifies; PR #5336 exists
solely to repair four stale `file:line` citations; PR #5322 measured
sixteen stale descriptions caught by review rather than any gate, while
its one machine-replayed claim class never recurred). The solve had to be
model-independent: a harness-enforced gate, not prompting, because it must
bind Sonnet, Opus, and Fable class authors identically.

PR #5338 adds the `Citation Freshness (added lines)` gate to the `pre_pr`
sequence: every `path:line` citation on a line added since the base ref is
verified against HEAD (tracked, in range, and at least one anchor the
citing sentence names present in the cited range, with the relocated line
reported when content moved). Three modules: gate policy, anchor
semantics, git reads. Historical trees are exempt; the escape hatch is a
line-scoped reasoned marker. Issue #5337 tracks the incident record;
issue #5339 spun out of the session (the merge-state check's UNKNOWN
transient, hit twice in one evening).

## What worked

- **Calibration on real history before shipping.** Replaying the gate over
  PR #5327's merged diff re-found every stale citation open PR #5336
  fixes, plus two more no review round caught, and exposed five false
  positives across the session (substring-of-path exclusion, docstring
  triple-quote pairing, wrapped-contract matching, bare-filename stems,
  token-bisecting segmentation). Each was verified against file content,
  fixed, and pinned as a regression test before the finding set was
  believed. The replay re-ran after every heuristic change; the three true
  positives survived every time.
- **Mutation-proofing the parser tests.** Restoring the splitlines and
  header-misread defects failed exactly the two tests written for them,
  with a byte-identical restore confirmed afterward.
- **The gate ate its own dogfood.** It blocked its own PR three times,
  each on a literal expected-finding string in a test that was itself a
  citation to an untracked path. Each block was a true positive.

## What failed, and the correction

- **Working-tree gate runs are not push evidence.** The gate reads
  committed state; an own-diff check run before committing the new tests
  passed while the push then failed on those very tests. Correction: the
  own-diff check counts only after the commit exists.
- **The 500-line taste ceiling was hit three times.** Prose-trimming
  converged only after structural extraction (git reads, then anchor
  semantics) split the module along its real seams. The lesson matches
  the sibling `checks_changed_paths.py` precedent: extract at the seam,
  do not shave sentences.
- **Copilot's two rounds were converging, not thrashing.** Round one found
  eight defects, round two found five different ones; thirteen of
  thirteen verifiable findings were real after independent verification.
  One proposed remedy (suppressing neighbor anchors for anchorless
  citation lines) was declined with a measured reason: it un-catches the
  PR #5336 flagship case.

## Learnings

- A gate that polices a claim class must expect its own tests to carry
  that class as fixtures; compose expected-finding strings dynamically.
- GitHub computes mergeability lazily, so any check that queries it
  seconds after a push sees UNKNOWN; remediation is a bounded retry in the
  check, not repeated manual re-runs (issue #5339).
- The pre-push suite is the calibration instrument: every one of its
  blocks this session (entry-point imports, mypy Namespace typing, taste
  ceiling, the gate itself, this retrospective policy) was a real defect
  or a real obligation, none a flake.
