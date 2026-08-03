# A Self-Blaming Conclusion Still Needs Evidence

Conventional retrospective practice says to be hard on yourself and to err
toward owning the failure. That advice is about tone, and it quietly protects a
class of claim from scrutiny. Self-criticism is not self-verification.

## What happened

PR #4290 suppressed a file size taste violation with a written rationale
arguing the idiomatic fix, extraction, would only reset the counter. Later I saw
PR #4302 remove that suppression and split the file from 520 lines to 455. I
read its diff, confirmed it did what it claimed, and concluded my rationale had
been falsified. On that basis I wrote a retrospective classifying my own
decision as FM-9 confident incorrectness, amended an always-on rule, and
regenerated both instruction mirrors.

PR #4302 is closed. Its author closed it himself, called it the wrong fix, and
wrote that "the suppression's rationale is correct on the merits, not just
expedient." The suppression is still on `main`. Issue #4285 already held the
same position in its title.

The check that would have caught this is one command:

```bash
gh pr view <N> --json state,closedAt
```

I ran it after committing the analysis, not before.

## Why the error survived

Every other conclusion I reach gets challenged, because a conclusion that
favors me invites the question "how do you know." A conclusion that indicts me
does not invite that question, from me or from a reviewer. It reads as rigor
already applied. So it skips the step it most needs.

There is a second tell in the same episode. The retrospective quoted a memory
that prescribes "a split along a seam that already exists rather than a
suppression." That memory scopes the guidance to "an existing 470 line test
file." I dropped the scope when I quoted it, because the quote supported the
self-blaming conclusion I had already reached.

## The rule

Before an artifact is allowed to overturn a prior decision, check its
disposition, not just its content. A diff shows what a change does. It does not
show whether anyone accepted it. An open pull request is a proposal; a closed
one may be a rejected proposal, and its diff is not evidence its approach was
right.

State it generally: apply the same evidence bar to a conclusion that assigns
fault to you as to one that defends you. If anything, a self-indictment deserves
more scrutiny, because nothing else in the review process will supply it.

## Related

- The always-on rule change this produced was reverted. `instruction_budget.py`
  independently rejected it at 83100 of 83000 bytes, so two separate checks
  said no.
- `.serena/memories/validation/validation-ratchet-command-paths.md` now carries
  the test-file scope tag that this episode showed was missing.
