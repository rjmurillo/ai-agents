# Frozen finding contract (rounds after the first)

Round caps bound cost. They do not bound what a later round may count, so an open-ended re-scan raises new scope each round and the loop ends at the cap, not at clean (issue #6745). Round 1 scans the whole diff. The caller supplies `ROUND: N` context. In round 2 and 3 only two things count:

1. A defect the diff introduced. That covers lines the PR added or changed, the caller's own fix commits since round 1, and a regression the diff causes in code it did not touch.
2. An acceptance criterion the PR claims (PR body or linked issue) that is still unmet.

Everything else is a **flagged note**: a pre-existing defect the diff neither changed nor broke, a nice-to-have, or new scope no acceptance criterion asks for. A flagged note is listed, never counted. It does not block, does not enter `merge_verdicts`, and does not trigger another round. Only a counted finding can. The loop ends when a round counts nothing (`PASS`), or at the cap.

## Running a later round

- Put `ROUND: N` on the line after `CONTEXT_MODE:` in every axis input, followed by the two counting rules above. Each axis returns counted findings under its verdict and flagged notes under a `Flagged notes` heading.
- Append `--frozen` to the Process step 4a arguments, keeping the rest. A verdict whose every cited location is outside the PR diff becomes `PASS`, and its findings become flagged notes. When the locations are mixed, the script keeps the verdict. Re-derive that axis verdict from the counted findings only: drop every finding whose location is marked `[pre-existing - not in this PR diff]`, and keep the rest, tagged findings included.
- A finding can count although its file is outside the diff. Tag the location line `[diff-caused]` for a regression the diff causes in a file it did not touch, and `[unmet-criterion]` for an unmet acceptance criterion that points at such a file. The script keeps the verdict of any output that carries a tag and never marks a tagged line pre-existing. Because the script judges by file, re-derive the verdict from the counted findings, as above. Axis inputs in a later round say so.
- A finding inside a changed file still needs rule 1. A defect on a line the PR did not touch, and did not break, is a flagged note.
- Stage 1 already counts only unmet acceptance criteria, so it runs unchanged.
- Report flagged notes in the Output section. The operator or owner decides what to do with them. The loop neither files issues nor fixes them.

## Caps

The caps stay as the backstop: 3 rounds for this skill, and the default 5 for `check_pr_round_cap.py`. Round 3 still escalates with every open counted finding, and the flagged notes ride along as their own list. A new invocation or human checkpoint resets the round count, as it resets the cap.

PR-comment loops (`pr-review`, `pr-comment-responder`) apply the same contract through the review-conversation protocol's "Bounded loops and handoff" section.
