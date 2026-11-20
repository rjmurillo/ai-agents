# ADR Debate Log: re-anchor stale path:line citations in 12 ADRs

## Summary

- **Rounds**: 5 of 10
- **Outcome**: Consensus
- **Final Status**: unchanged (the edit changes no ADR status or decision)
- **Scope**: line-number citations in ADR-036, ADR-052, ADR-080, ADR-083, ADR-096, ADR-101,
  ADR-102, ADR-106, ADR-107, ADR-108, ADR-109, and ADR-116.
- **Panel**: reduced panel, architect and critic. The edit changes citations only. No gate,
  test, or validator reads the changed lines.

A whole-tree run of the shipped `check_citation_freshness.py` scan found stale citations in
these ADRs. Base: `origin/main` at `15c13340a`, read 2026-11-20.

## Method

Each candidate was traced with `git blame` to the commit that wrote the citing line. The cited
lines were read at that commit. A new number was proposed only when that text sits at one place
at HEAD. The shipped checker then had to pass the new citation. Tiers: exact block, one unique
line of 20 or more characters, or the citation's own anchor found once in the file.

## Round 1 Summary

### Key Issues Addressed

- Both seats confirmed that only digits inside citations changed. No prose changed.
- Seven rows describe code as it stood when the ADR was written. Moving them to HEAD would
  point at text that now says the opposite: ADR-080 lines 117, 296, and 322, ADR-101 lines 96
  and 425, and ADR-102 line 316.
- ADR-096 line 99 is a "structure being changed" note. Its sibling numbers on the same line
  stay old, so a partial update would mix two versions.
- ADR-083 line 180 quotes the `_DEFAULT_EXCLUDES` definition. That moved to
  `build/scripts/skill_support_mirror.py:45`. It needs a path change, not a number change.
- Sibling numbers on edited lines were still stale: ADR-107 line 65 `:2319`, ADR-108 line 34
  `:2226`, and ADR-107 line 100 `:120-122`.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block. 23 of 31 rows hold. Reject the historical rows and ADR-083 line 180 as proposed. Fix the stale sibling numbers. |
| critic | Block. Same historical rows. ADR-102 line 325 left half-updated. The gate reads HEAD only, so the staged tree was checked by hand. |

## Round 2 Summary

### Major Changes Made

- Reverted eight rows to their original numbers: ADR-080 lines 117, 296, and 322, ADR-096
  line 99, ADR-101 lines 96 and 425, and ADR-102 lines 316 and 325.
- ADR-083 line 180 now cites `build/scripts/skill_support_mirror.py:45`.
- ADR-107 line 65 and ADR-108 line 34 now cite `:2454`, the `assert_no_claude_writes(` call.
- ADR-107 line 100 now cites `:125-127`, the same two paragraphs moved down five lines.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. 23 changes, all correct. No decision text changed. |
| critic | Accept. Rerun the gate after commit and confirm a nonzero examined count. |

## Round 3 Summary

### Key Issues Addressed

- ADR-101 line 272 cites `claude.yml` with a bare `:101`. That line at blame commit
  `5b88ed23f` passes `secrets.CLAUDE_CODE_OAUTH_TOKEN`, and it now sits at line 114. The
  sentence is still true at HEAD.
- ADR-102 line 315 cites `validate_session_json.py:960-986`. The block now sits at 982 to 1008.
  The row is in the Change Impact table, which cites the code before the change.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Apply ADR-101 line 272. Keep ADR-102 line 315: rows 313, 314, 316, and 325 cite the old code, so one updated row would mix two versions in one table. |
| critic | Apply both. The ADR-102 line 315 row is true at HEAD. |

ADR-101 line 272 now cites `:114`. ADR-102 line 315 has no consensus, so it stays unchanged
and is listed as indeterminate in the pull request.

## Round 4 Summary

The added-lines gate also checks citations within three lines of an edit. Eight such
citations in these ADRs failed it after round 3.

### Key Issues Addressed

- ADR-101 line 274 cites `:153` for the token line. That text now sits at line 155. The
  sentence also names `:2-4` on purpose, as the earlier wrong revision, so the line carries a
  reasoned ignore marker.
- ADR-109 line 303 cites a file under `.claude/skills/`, a symlink the gate does not track. The
  same file is tracked at `src/claude/skills/agent-harness-reference/references/`. Line 48
  there now sits at line 51, and lines 291 to 299 now sit at 316 to 324, an exact match.
- ADR-107 line 65 and ADR-108 line 34 cite `build_all.py:2454`, which is correct. Their anchors
  describe the whole guard, so no single line matches. Both carry a reasoned marker.
- ADR-108 lines 163 and 164 are Change Impact rows that quote sentences as they were. One
  quoted sentence is gone. The other was reworded, and its successor is at
  `generated-artifacts.md` line 198. Both keep their numbers with a reasoned marker.
- ADR-080 line 58 cites `build_child_argv`. That block moved down two lines, so lines 158 to
  184 are now 160 to 186, an exact match.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block on one item: the ADR-108 line 164 marker wrongly said no successor exists. Fixed to name line 198. All other items verified. |
| critic | Block on one item: ADR-080 line 58 was correct at its citing commit and only moved two lines. Fixed to `:160-186`. All other items accepted. |

Both required changes were applied as given.

## Round 5 Summary

The gate then flagged three more citations beside the round 4 edits. Each keeps its number
with a reasoned same-line marker.

### Key Issues Addressed

- ADR-080 line 58: lines 160 to 186 hold `build_child_argv`, an exact match. The gate pairs
  the next citation's anchor with this range, a false anchor.
- ADR-108 line 166: at blame commit `5159f30da` the cited test line asserted that
  `@CLAUDE.md` is present. HEAD lines 168 and 172 assert it is absent. The row records the
  state before the pilot.
- ADR-109 line 301 quotes the section "Generator order: sync before build". That section is now
  "Generator order: one command, not a sequence" at line 171, and the quoted text is gone.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. All three reasons verified against the blame commits and HEAD. |
| critic | Accept. All three reasons hold. The diff matches the reviewed artifact byte for byte. |

## Decision

Accepted by both seats. ADR-101 line 96 and ADR-102 line 316 make claims about current
behavior that are false at HEAD. That is flagged in the pull request body for the owner.
This edit does not change them.
