# ADR Debate Log: Citation Renumbers After the One Frontmatter Parser Refactor

## Summary

- **Rounds**: 4 of 10
- **Prior debate log**: none
- **Outcome**: Consensus
- **Final Status**: accepted

Reduced panel: architect and critic. The change touches no executable enforcement
and no rule another gate reads. It only renumbers `path:line` citations, so
AGENTS.md calls for the reduced panel.

Scope: ADR-052, ADR-059, ADR-080, ADR-102 and ADR-108. The branch
`refactor/frontmatter-one-parser` moved every frontmatter parser onto
`scripts/hook_utilities/frontmatter_block.py`. That moved lines in the cited code
files, and `scripts/validation/citation_reverse_pass.py` flagged the ADR
citations below as newly stale. No decision, status or prose meaning changes.

## Round 1 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block |
| critic | Block |

### Key Issues Addressed

- Both seats confirmed the first five renumbers point at the same code.
- Both found citations into moved files that the first diff missed, including
  ADR-108:27 and :59.
- ADR-108 cited one transform two ways, `:137` and `:140`.

### Major Changes Made

- Every ADR citation into a changed file was scanned and shifted where its
  block had moved unchanged.

## Round 2 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block |
| critic | Block, then Accept after ADR-087:66 was fixed |

### Key Issues Addressed

- Architect: ADR-100's `git_hook_policy.py` citations are pinned to old commits
  by `citation-freshness: ignore` comments, because they describe a deleted gate.
  The block-match scan had moved them onto unrelated lines. The architect also
  found the patch built on a stale base: origin/main had merged #7504, which
  re-anchored citations in several of these ADRs.
- Critic: ADR-087:66 cited `eval-agent-vs-baseline.py` "lines 1046-1062" in prose
  form, which the scan missed.

### Major Changes Made

- Every round-2 ADR edit was discarded and origin/main was merged.
- The method changed. A citation is renumbered only when the reverse-pass gate
  flags it as newly stale, meaning it was valid at the merge base and this branch
  moved its code.

## Round 3 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept |
| critic | Block |

### Key Issues Addressed

- Architect: all 9 renumbers follow their original code. The gate's flagged set
  equals the diff. No commit-pinned citation changed.
- Critic: ADR-108:27 and :201 followed `copilot_body_translation.py:140` to
  `:137`. But `:140` had drifted onto `body: str,` in
  `_translate_outside_fenced_code`. At ADR-108's authoring commit efd148e89, it
  was the `return (` inside `_translate_includes`, which builds the HTML comment
  the prose describes.

### Major Changes Made

- ADR-108:27 and :201 now cite `:151`, the `return (` in `_translate_includes`.

## Round 4 Summary

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Accept (round 3; ADR-108 was the only later change) |
| critic | Accept |

### Key Issues Addressed

- Critic verified that both ADR-108 lines name the HTML-comment `return (` and
  that the other 7 renumbers are unchanged from round 3.

### Final Diff

| Citing line | Old | New |
|-------------|-----|-----|
| ADR-052:146 | `generate_agent_catalog.py:159-172` | `158-171` |
| ADR-059:464 | `copilot_body_translation.py:395` | `392` |
| ADR-080:60 | `eval-agent-vs-baseline.py:118,394-406` | `122,397-409` |
| ADR-102:221 | `git_hook_policy.py:2774` | `2763` |
| ADR-102:355 | `git_hook_policy.py:2774` | `2763` |
| ADR-108:27 | `copilot_body_translation.py` `:140` | `:151` |
| ADR-108:201 | `copilot_body_translation.py` `:140` | `:151` |

The same commit fixes two non-ADR citations the gate flagged:
`.agents/governance/FAIL-OPEN-INVENTORY.md:155` and `scripts/eval/eval-suite.py:810`.

### Next Steps

Pre-existing faults the panel noticed. They were already wrong on the merge base
and are out of scope for this change:

- ADR-073:34 and :148 cite `detect_adr_changes.py` lines 40 to 48 for
  `_get_adr_status`.
- ADR-087:60 cites lines 1095-1115 of `eval-agent-vs-baseline.py` for
  `_load_fixture_paths`.
- ADR-099:31 cites `git_hook_policy.py` lines 6062-6073 for a comment that is
  not in that file.
- ADR-102:227 and :242 cite `validate_session_json.py:1647` and `qa_report.py:182`.
