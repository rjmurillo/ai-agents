# ADR Debate Log 3: ADR-057 Criterion 2, Gated Skill Change Exception

## Summary

- **Rounds**: 6 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-057-debate-log-2.md`
- **Outcome**: Consensus (2 Accept)
- **Final Status**: accepted. The record's status is unchanged. This debate covers three sentences, and round 5 revisits one of them.
- **Panel**: reduced, architect and critic. The edit removes a contradiction in prose. It changes no executable enforcement.
- **Trigger**: a review bot on PR #7629 noted that criterion 2 says a behavior change updates scenario expectations alongside the prompt. That contradicts the gated-change freeze.
- **Date**: 2026-11-25

## Exit gates before review

| Gate | Result |
|---|---|
| Claims ledger | NOT RUN. The sentence makes no count, path, or quote claim. Each behavior it names maps to a check function the seats read. |
| Self-consistency | VERIFIED by the architect. Lines 135, 137, 218, and 257 already name the ADR-127 exception. Only line 92 carried the conflict. |

## Round 1 Summary

### Key Issues Addressed

- Criterion 2 told every author to update expectations alongside the prompt. ADR-127 decision 7 items 8 and 10 forbid that for a gated skill change.
- The first draft said only that a kept label may not change. The critic showed that understates the freeze. Adds, drops, and text edits also fail after the first template edit.
- The first draft said "gated change". Without "skill", a reader could apply it to non-gated prompts.

### Major Changes Made

- Line 92 now reads: "An ADR-127 gated skill change is the exception: scenarios, including any dropped through `retired.json`, land before the first template edit and then stay frozen, and a kept scenario's `expected_verdict` may not change (Amendment 2026-11-25)."

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept, with a P2 wording note on `expected_verdict` and `retired.json` |
| critic | Disagree-and-Commit until the full freeze is stated |

## Round 2 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Line 92 matches ADR-127 and the shipped check. |
| critic | Accept. "Gated skill change" scopes it away from non-gated prompts. |

## Round 3 Summary

### Key Issues Addressed

- A second review bot found lines 89 and 112 still say no CI check blocks a merge on a FAIL.
- The critic found the first line 89 text too narrow. The check also fails closed on missing or invalid evidence.

### Major Changes Made

- Line 89 now ends: "The one exception is an ADR-127 gated skill change, where the deterministic evidence check blocks a recomputed FAIL and any missing or invalid evidence (Amendment 2026-11-25)."
- Line 112 now ends: "An ADR-127 gated skill change is the exception (Amendment 2026-11-25)."

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. No other line still claims nothing blocks; the `/spec` lines stay accurate. |
| critic | Disagree-and-Commit until line 89 names missing or invalid evidence |

## Round 4 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. The wording matches Amendment 2026-11-25 items 1 and 3. |
| critic | Accept. Its replacement text is applied verbatim. |

## Round 5 Summary

### Key Issues Addressed

- A second CodeRabbit pass found line 92 said scenarios land "before the first template edit". The gate starts the freeze at the first commit that touches any file of the skill, `references/` included. An author who edits a reference first would follow the text and fail.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. Flagged that ADR-127 decision 7 item 8 still says "before any template edit", outside this diff. |
| critic | Disagree-and-Commit. "Prompt surface" undersells the rule: `_freeze_findings` counts `scripts/` too, and the template path needs its `templates/skills/` prefix. |

## Round 6 Summary

### Major Changes Made

- Line 92 now says scenarios "land in a commit before the first commit that touches the skill (its `templates/skills/<name>.SKILL.md.tmpl` or any file under `src/claude/skills/<name>/` or `.claude/skills/<name>/`, `scripts/` included) and then stay frozen". This is the critic's text, verbatim.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept. The text matches `_freeze_findings` lines 21 to 30. |
| critic | Accept. No P0 or P1 remains. |

### Next Steps

- ADR-127 decision 7 item 8 keeps its narrower "before any template edit" wording. It is recorded in the PR body for Richard.
- Richard ratifies the ADR-057 and ADR-127 amendments at merge of PR #7629.
