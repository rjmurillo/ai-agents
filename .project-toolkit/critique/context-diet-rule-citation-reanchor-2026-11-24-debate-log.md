# ADR Debate Log: re-anchor ADR citations of rules removed by the context diet

## Summary

- **Rounds**: 2 of 10
- **Outcome**: Consensus
- **Final Status**: unchanged (the edit changes no ADR status or decision)
- **Scope**: citations of deleted `.claude/rules/*.md` files in ADR-062, ADR-071, ADR-083,
  ADR-084, ADR-092, ADR-093, ADR-096, ADR-097, ADR-100, ADR-101, ADR-102, ADR-103, ADR-107,
  ADR-108, and ADR-109, plus the ADR-093 row in the architecture README.
- **Panel**: reduced panel, architect and critic. The edit changes citations only. No
  enforcement logic changes.
- **Gate scope**: only lines the two gates read were changed. `check_adr_lifecycle.py`
  cited-paths-exist reads Decision and Implementation Notes. `citation_reverse_pass.py`
  reads path:line citations to moved files. Older paths in Context, Impact, References, and
  in the `proposed` ADR-107 were left on purpose.

The context diet branch deletes 26 rule templates and their outputs. Twenty-one moved into
skill references. Five were dropped: universal, agent-skill-docs, plugin-version-bump,
session-logs, and token-economy. Base: `d6082a4406`, read 2026-11-23.

The moves are not all verbatim. Each reference drops frontmatter and gains a header comment
and portability markers. `rule-generated-artifacts.md` MUST 2 is now a pointer to the
repo-local `ai-agents-validation-and-qa` skill, which owns the full text. Two checklist lines
in `rule-code-quality.md` were merged. A few cross-skill paths became prose.

## Method

- A moved rule's citation now reads "the former `X` rule (now at `<successor path>`)". The
  sentence stays historical and the path resolves.
- A dropped rule's citation now reads "the former `X` rule". It names no path.
- New line numbers were mapped by exact text match against the base blob.
- A citation whose text left the file before the diet keeps its old path. It gets a
  reasoned `citation-freshness: ignore` marker.

## Round 1 Summary

### Key Issues Addressed

- ADR-109 lines 29, 40, and 300 had been moved to `rule-claude-agents.md:22`. That line is
  MUST 1. The "54 of 173 commits (31%)" measurement left the file in `f50f685512` (#5758),
  so the old `:24` was already stale. The new anchor looked current but cited the wrong
  text.
- ADR-109 line 300 was not edited, so the reverse pass would stay red.
- ADR-062 line 295 now said the successor file is mirrored to `.github/instructions/`. A
  skill reference has no mirror, so the claim was false.
- ADR-093 line 51 called the deleted rule "always-on" in the present tense.
- ADR-092 lines 85 and 209 started sentences with a lowercase "the former".
- ADR-101 line 305 tells readers to document a bypass in a deleted rule.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block. ADR-109 `:22` anchors cite the wrong text, and `:300` was missed. Make ADR-062:295 historical. |
| critic | Block. Same ADR-109 findings. Use one historical pattern. Fix tense at ADR-093:51 and ADR-100:260. Flag ADR-101:305 to the owner. |

## Round 2 Summary

### Major Changes Made

- All moved-rule citations use "the former `X` rule (now at ...)".
- ADR-109 lines 29, 40, and 300 keep `.claude/rules/claude-agents.md:24`, each with a
  reasoned ignore marker naming `f50f685512`. No `:22` remains.
- ADR-093 line 51 now says "which was always-on" and names the `AGENTS.md` red remote check
  line as the MUST's current home. The README row was regenerated.
- ADR-100 lines 260 and 430 moved to the past tense.
- Sentence-start capitals fixed in ADR-092, ADR-097, and ADR-102. Nested parentheses in
  ADR-102 now use commas. The ADR-109 markers sit on the citing list line.
- ADR-101 line 305 is unchanged. Choosing a new home for that bypass note is an Ask First
  decision. The PR body names it for the ADR owner.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Every changed line changes only a citation. Successor paths hold the cited items. |
| critic | Accept. Round-1 blockers fixed. Correct the verbatim claim in this log, done above. |

## Final Verdicts

| Agent | Verdict |
|-------|---------|
| architect | ACCEPT |
| critic | ACCEPT |

## Gate Evidence

- `check_adr_lifecycle.py`: cited-paths-exist at 57/57, at baseline.
- `citation_reverse_pass.py`: reads HEAD, so it is checked again after this commit.
