# ADR Debate Log: ADR-084 Amendment Record relocation

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-084-debate-log-3.md` (closed, rule 2b)
- **Outcome**: Consensus (rounds 1 and 2: architect Accept, critic Disagree-and-Commit). Under ADR-101 the panel counts as one vote.
- **Final Status**: no status change. ADR-084 frontmatter stays `status: accepted`. Rule 2b stays proposed and not yet binding.
- **Subject**: two older Amendment Record entries moved out of ADR-084 on 2026-11-25. They now sit in `.project-toolkit/critique/ADR-084-amendment-record-archive.md`.
- **Trigger**: the `size-cap` check in `scripts/validation/check_adr_lifecycle.py`. Rule 2b grew ADR-084 from 498 lines on `origin/main` (`9df30da9d0`, 2026-11-25) to 609 lines, past the 500-line cap.
- **Panel**: reduced (architect, critic), per AGENTS.md. The change moves amendment history only. It edits no rule text and no executable enforcement. One test does scan the moved text; round 2 covers it and both seats kept the reduced panel.
- **Decided without the owner**: the author chose the relocation during an unattended run. The owner did not pick it. The alternatives are listed below.

## What changed

- The 2026-08-18 entry (rule 3, tool-use events) left ADR-084.
- The 2026-10-31 entry (rule 2a and the rule 5 correction) left ADR-084.
- Both entries sit unchanged in the archive file, under a short header.
- A four-line stub under `## Amendment Record` names both entries and links the archive.
- The 2026-11-25 rule 2b entry stays in ADR-084, beside the rule it explains.
- ADR-084 is 482 lines after the move (staged tree, 2026-11-25).

Two citation repairs ride along, because rule 2b shifted line numbers:

- `REQ-048-friction-triggered-retrospective-nudge.md` lines 70 and 473 now cite ADR-084 line 263. The second citation sits in its own paragraph, so the reverse pass reads only its own anchors.
- A docstring in `tests/build_scripts/test_hook_contract_knowledge.py` now names the section "What this ADR does NOT do".

## Alternatives considered

| Option | Why not |
|--------|---------|
| Shrink rule 2b to a pointer at ADR-128 | It changes owner decision D10, which put rule 2b in ADR-084. |
| Raise the baseline or add a `taste-lint: ignore` comment | The gate text forbids it. It excuses the growth and fixes nothing. |
| Move the rule 2b entry and keep the older ones | It removes only 50 lines. The file would still be 559 lines. |
| Move all three entries | The proposed entry is still under owner review. It reads best beside rule 2b. |

## Round 1 Summary

### Agent Positions

| Agent | Position | Head finding |
|-------|----------|--------------|
| architect | Accept | The archive header cited this log before it existed. |
| critic | Disagree-and-Commit | Same finding, plus a move date one day ahead of the local date. |

### Verified by both seats

- The move is verbatim. `diff` of the 131 old lines against the archive body printed nothing.
- The staged ADR-084 diff has one hunk, inside `## Amendment Record`.
- Status, Decision, and Consequences are untouched.
- ADR-084 line 263 holds the rule 5 text that REQ-048 cites.
- No file cites ADR-084 by line number at or past line 400.

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| R-1 | P1 | architect, critic | The archive header cited a debate log that did not exist. This log now exists. |
| R-2 | P1 | critic | The stub and the archive header said 2026-11-26. Both now say 2026-11-25, the local date of the move. |
| R-3 | P2 | critic | A second REQ-048 citation still pointed at ADR-084 line 203. It now cites line 263, from REQ-048 line 473. |
| R-4 | P2 | architect, critic | ADR-084 lines 170 and 289 say "the Amendment Record" and need one extra hop. Documented. The stub names both moved entries. |
| R-5 | P2 | architect | A critique file is a weak home for accepted history. Documented. The gate message names critique and analysis files as the place for moved detail. |

### Strategic checklist

| Lens | Assessment |
|------|------------|
| Chesterton's Fence | PASS. The entries keep their text and stay linked from the record. |
| Path Dependence | PASS. Rollback is one revert. The text returns unchanged. |
| Core vs Context | N/A. No capability changes. |
| Second-System Effect | N/A. No scope is added. |

## Round 2 Summary

Round 2 corrected a false claim in the round 1 record. Round 1 said the move touched no text a gate reads.

`tests/hooks/test_adr_hook_claims.py` scans every `ADR-*.md` under `.project-toolkit/architecture/` for hook file names. The moved text names one hook, `invoke_auto_retrospective.py`, and calls it since-deleted. The test accepted that mention as retired. The archive sits under `.project-toolkit/critique/`, which the test does not scan.

### Agent Positions

| Agent | Position | Head finding |
|-------|----------|--------------|
| architect | Accept | No check changes today. The panel rationale in this log was wrong. |
| critic | Disagree-and-Commit | Same finding. Nothing now checks that the archived mention stays marked retired. |

### Key Issues Addressed

| ID | Priority | Source | Resolution |
|----|----------|--------|------------|
| R-6 | P1 | architect, critic | The Panel line claimed no gate reads the moved text. Corrected above. |
| R-7 | P2 | architect, critic | Row R-3 named REQ-048 line 471. The citation sits at line 473. Corrected. |
| R-8 | P2 | critic | The hook-claims test no longer scans the one archived hook mention. Documented. The archive is a frozen record and names no live hook. |
| R-9 | P2 | architect | ADR-084 line 289 says the Amendment Record names two restored tests. Lines 273 to 275 name them. This predates the move. Documented, not changed. |
| R-10 | P2 | architect | The commit message of `c4cdd484b5` (2026-11-25) says REQ-048 line 471. A later commit moved the citation to line 473. The message stays as written. |

### Panel size

Both seats judged the reduced panel adequate. AGENTS.md asks for the full panel when a change touches executable enforcement or a rule other gates read. The test reads amendment history here, not rule text, and it passes either way.

## Dissent

- critic: do not commit until R-1 and R-2 are fixed. Both are fixed in this change.
- architect: none.

## Not verified by the panel

- Neither seat ran `pre_pr.py` or `pytest`. The author ran both on the committed tree.
- The round 2 seats read the hook-claims test. They did not run it.
- The architect did not resolve each relative path inside the moved text. The text is unchanged from `origin/main`.

## Next Steps

- The owner may move the history elsewhere or split ADR-084 another way.
- Any later amendment to ADR-084 must fit under the cap or move its own detail out.
