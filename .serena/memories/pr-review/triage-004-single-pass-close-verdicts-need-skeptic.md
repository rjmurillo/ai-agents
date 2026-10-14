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

[2026-10-14] A single-pass post-merge security audit of 104 merged PRs flagged 7 as FAIL. An independent skeptic pass checked 6 of them and refuted 5:

- Refuted: PR #6421, #6348, #6297, #6287, #6273.
- Confirmed: PR #6308. Issue #6493 tracked the fail-open, and PR #6498 fixed it.

The rule holds beyond triage. Never act on a single-pass FAIL or close verdict. Run an independent pass that tries to refute it first. Act only on what survives.

## Source

- Triage run of 2026-10-11, 187 open issues, 38 proposed closes, 22 refuted.
- Security audit of 2026-10-14, 104 merged PRs, 7 FAIL, 5 of 6 checked refuted.

## Related

- [triage-001-verify-before-stale-closure](triage-001-verify-before-stale-closure.md)
- [triage-002-bot-closure-verification](triage-002-bot-closure-verification.md)
