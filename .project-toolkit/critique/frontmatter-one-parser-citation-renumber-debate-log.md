# ADR Debate Log: Citation Renumbers After the One Frontmatter Parser Refactor

## Summary

- **Rounds**: 5 of 10
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

## Round 5 Summary

The pre-PR "Citation Freshness (added lines)" gate also checks citations on and
near changed lines. It flagged two more ADR-108 citations on lines this change
touched.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block, then Accept after rechecking a line it had misread |
| critic | Block, then the remedy it named was applied |

### Key Issues Addressed

- ADR-108:201 cited `build_all.py` at `:793` and `:2226`. Both were stale before
  this branch. At authoring commit 5159f30da they were `def assert_no_claude_writes(`
  and its call site, and both now sit at lines 1036 and 2454.
- The checker reads prose between code spans as anchors. On ADR-108:27 it
  rejected a correct citation. On line 201 it rejected the word "and" between two
  citations.
- The architect first claimed `copilot_body_translation.py:14` had moved to 13.
  On recheck it confirmed line 14 is still the `@CLAUDE.md` probe and withdrew
  the claim.

### Major Changes Made

- ADR-108:201 cites both `build_all.py` lines as full paths, with no prose between them.
- ADR-108:27 carries an inline `citation-freshness: ignore` marker with a reason.
  The reason holds no citation-shaped token, because a token in the reason would
  itself be read as a citation.

### Final Diff

| Citing line | Old | New |
|-------------|-----|-----|
| ADR-052:146 | `generate_agent_catalog.py:159-172` | `158-171` |
| ADR-059:464 | `copilot_body_translation.py:395` | `392` |
| ADR-080:60 | `eval-agent-vs-baseline.py:118,394-406` | `124,399-411` (round 6) |
| ADR-102:221 | `git_hook_policy.py:2774` | `2785` (round 6) |
| ADR-102:355 | `git_hook_policy.py:2774` | `2785` (round 6) |
| ADR-108:27 | `copilot_body_translation.py` `:140` | `:151` |
| ADR-108:201 | `copilot_body_translation.py` `:140` | `:151` |
| ADR-108:201 | `build_all.py:793` and `:2226` | `:1036` and `:2454` |

The same change fixes three non-ADR citations the gates flagged:
`.agents/governance/FAIL-OPEN-INVENTORY.md:148` and `:155`, and
`scripts/eval/eval-suite.py:810`.

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

## Round 6 Summary

Commits after round 5 moved two cited files again. `git_hook_policy.py` grew,
so its lines sit 11 below base. The eval runner gained a two-line comment, so
its lines sit 6 below base. The decision-rigor review axis found the round 5
values stale at the new head.

### Method

Each new number maps the base line through the hunks of
`git diff -U0 <base> HEAD` for the target file. The cited line then holds the
same text it held at base. A citation that was already wrong at base keeps its
base text, so this branch does not own it.

### Agent Positions

| Agent | Position |
|-------|----------|
| architect | Block on ADR-102:112, then the remedy it named was applied; Accept on the other three ADR lines |
| critic | Block on five lines already wrong at base and one missed citation, then both remedies were applied |

### Key Issues Addressed

- ADR-102:112 cited a docstring at base, not the mode flag line. It keeps its
  base text.
- FAIL-OPEN-INVENTORY:121 and REQ-023:275 were wrong at base. They keep their
  base text.
- FAIL-OPEN-INVENTORY:151, REQ-023:48 and TASK-026:51 were also wrong at base.
  The reverse-pass gate refuses their base numbers because the base text moved.
  They map through the diff, so each still points at the same text as at base.
  The mapping neither fixes nor worsens them.
- The critic found one missed citation: the probe toolkit's `provenance.md:16`
  cites `eval-agent-vs-baseline.py:447-475`, now 5 lines low. It stays as it is.
  Its row mixes shell commands with paths, so the added-lines gate misreads the
  row, and its neighbor rows were already stale at base.
- The critic confirmed the other round 5 rows still hold at head.

### Final Diff (round 6)

| Citing line | Round 5 | Round 6 |
|-------------|---------|---------|
| ADR-080:60 | `122,397-409` | `124,399-411` |
| ADR-102:221 | `2763` | `2785` |
| ADR-102:355 | `2763` | `2785` |

The same commit re-anchors these non-ADR citations: FAIL-OPEN-INVENTORY:103 and
:116 to :120, `check_push_lock_before_commit.py:49`, and
`citation_head_state.py:91`.

### Next Steps

These lines were wrong at base and stay out of scope: ADR-102:112,
FAIL-OPEN-INVENTORY:93, :121 and :151, REQ-023:48 and :275, TASK-026:51, and
ADR-100:31, :37 and :250.

