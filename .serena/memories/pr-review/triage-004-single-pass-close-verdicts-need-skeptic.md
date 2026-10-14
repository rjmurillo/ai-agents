# Skill: Never Close an Issue on a Single-Pass Triage Verdict

## Problem

[2026-10-11] [user]: A single-pass Sonnet triage of 187 open issues proposed 38 closes. An independent skeptic pass refuted 22 of 38 (58%). The skeptic prompt told it to refute and to default to refuted when any acceptance criterion was unmet.

## Root Causes

1. PRs that used "Refs #N" instead of closing keywords were read as fixes.
2. The triage checked the issue headline, not every acceptance criterion.
3. Owner comments that kept an issue open as a tracker were missed.
4. Triage confused sibling files with the file the issue named.

## Rule

Never close an issue on a single-pass triage verdict. Closing is the irreversible step. Require a second, adversarial pass that:

- Defaults to refuted when any acceptance criterion is unmet.
- Checks every acceptance criterion, not the headline.
- Checks whether each cited PR used a closing keyword or only a reference.
- Reads owner comments for tracker intent.
- Confirms the cited file is the file the issue names, not a sibling.

## Why

Conventional wisdom says triage is cheap and safe to automate on a small model. First principles say the cost sits in the close, not the read. A wrong close hides open work. A wrong keep costs one extra look. The checks must be asymmetric.

## Second data point: post-merge security audit verdicts

[2026-10-13] A single-pass post-merge security audit of 104 merged PRs flagged 7 as FAIL. A later independent skeptic pass checked 6 of them and refuted 5:

- Refuted as FAIL: PR #6421, #6348, #6297, #6287, #6273. Some still carry low-severity residuals, tracked in #6506. Refuted does not mean clean.
- Confirmed: PR #6308. Issue #6493 tracked its two fail-open paths, and PR #6498 fixed both.
- Unchecked: the seventh FAIL. The report this memory came from does not name it. Treat it as open until someone checks it.

The two-pass pattern holds beyond triage, but the default flips. For a close verdict, the skeptic defaults to refuted, because a wrong close hides work. For a security FAIL, a wrong refute ships the vulnerability. So the second pass must show evidence to refute a FAIL, with no default. Refuted FAILs stay on record, as #6506 does for residuals.

## Source

- Triage run of 2026-10-11, 187 open issues, 38 proposed closes, 22 refuted.
- Security audit of 2026-10-13, 104 merged PRs, 7 FAIL. A later skeptic pass refuted 5 of 6 checked. Confirmed: #6493. Low-severity residuals: #6506.

## Related

- [triage-001-verify-before-stale-closure](triage-001-verify-before-stale-closure.md)
- [triage-002-bot-closure-verification](triage-002-bot-closure-verification.md)
