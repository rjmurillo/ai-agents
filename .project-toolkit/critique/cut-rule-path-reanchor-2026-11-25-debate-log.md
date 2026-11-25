# ADR Debate Log: re-anchor ADR citations of rules cut by PR #7541 and PR #7563

## Summary

- **Rounds**: 2 of 10
- **Outcome**: Consensus after round 2 fixes
- **Final Status**: unchanged for every ADR. No status or decision changes.
- **Scope**: 47 changed lines in 20 ADRs: 41 citation lines, 4 marker lines, and 2 tense fixes. The ADRs:
  - ADR-062
  - ADR-066
  - ADR-068
  - ADR-071
  - ADR-074
  - ADR-076
  - ADR-093
  - ADR-096
  - ADR-097
  - ADR-100
  - ADR-101
  - ADR-102
  - ADR-104
  - ADR-107
  - ADR-108
  - ADR-109
  - ADR-112
  - ADR-116
  - ADR-117
  - ADR-118
- **Cut rules cited**: lsp-first, generated-artifacts, and ci-scripts from #7541. security, testing, retros, and tool-use-hook-bar from #7563.
- **Panel**: reduced panel, architect and critic.
- **Why reduced**: the edit changes citations only. No gate logic or rule text changes.
- **Base**: `d8d140bb2e`, the head of `feat/widen-rule-skill-triggers`.

Both precedent logs left these citations as history.
They sit in Context, Prior Art, Impact, or References sections.
`check_adr_lifecycle.py` does not read those sections.
Richard asked on 2026-11-25 for them to be re-anchored too.

## Prior debate logs

This is a new cross-ADR debate. It closes no earlier log and reopens none.
The latest closed log for each ADR:

- ADR-062: `ADR-062-debate-log.md`
- ADR-066: none found under `.project-toolkit/critique/`
- ADR-068: `ADR-068-071-084-085-109-req048-task006-debate-log.md`
- ADR-071: `ADR-071-debate-log-2.md`
- ADR-074: `ADR-074-debate-log.md`
- ADR-076: `ADR-076-ADR-090-lease-retirement-debate-log.md`
- ADR-093: `ADR-093-debate-log.md`
- ADR-096: `ADR-096-debate-log.md`
- ADR-097: `ADR-097-debate-log-2.md`
- ADR-100: `ADR-100-amendment-2026-09-22-debate-log.md`
- ADR-101: `ADR-101-dispatch-closure-exempt-links-debate-log.md`
- ADR-102: `ADR-102-ruff-format-fmt-markers-debate-log.md`
- ADR-104: `ADR-104-6200-pytest-step-bound-debate-log.md`
- ADR-107: `ADR-107-debate-log-3.md`
- ADR-108: `ADR-108-debate-log.md`
- ADR-109: `ADR-109-debate-log-12.md`
- ADR-112: `ADR-112-debate-log.md`
- ADR-116: `ADR-116-debate-log.md`
- ADR-117: `ADR-117-debate-log.md`
- ADR-118: `ADR-118-debate-log.md`

The cross-ADR re-anchor logs are `context-diet-rule-citation-reanchor-2026-11-24-debate-log.md` and `trigger-widening-rule-citation-reanchor-2026-11-24-debate-log.md`.
Carried forward: the trigger-widening log noted these citations as left unchanged. This debate takes up that item.

## Method

- Same method as `context-diet-rule-citation-reanchor-2026-11-24-debate-log.md`.
- A cut rule's citation reads "the former `X` rule (now at `<successor path>`)".
- An item number reads "MUST 2 of the former `X` rule (now at ...)".
- Nested parentheses become commas.
- Text that describes the old file keeps that meaning.
- Every successor path uses the `.claude/skills/...` form.
- No line count changes. ADR-097 and ADR-101 sit at the 500-line cap.

## Deliberately unchanged

- ADR-088:229 and ADR-062:468 are dated amendments that record the deletion itself.
- Bare names such as `retros.md` MUST NOT 1 refer back to a full citation earlier in the ADR.

## Round 1

Critic verdict: REVISE. Architect verdict: ACCEPT-WITH-CHANGES.

Both seats confirmed all seven successor paths exist.
Both confirmed each cited item number matches its successor file.
The critic found no missed citation across the 15 deleted rule names.

### Accepted

- ADR-062:65 read "ships as context every session" next to the successor. A skill reference does not load every session. It now reads "shipped".
- ADR-062:85 said "that file currently documents". It now reads "that file then documented".
- ADR-108:164 said "its line 196", which bound to the successor. It now reads "line 196 of the former file".
- The ADR-108:164 marker named a deleted file. It now names `rule-generated-artifacts.md` line 180.
- ADR-109:41, :192, and :350 now say the section was "reworded since". The successor heading is "Generator order: one command, not a sequence".
- The ADR-109:350 marker named a deleted file. It now names `rule-generated-artifacts.md` line 153.
- ADR-097:388 had two parentheticals in a row. They now share one, split by a semicolon.
- `check_citation_freshness.py` flagged four unedited lines beside edits.
- ADR-096:185, ADR-097:397, ADR-109:44, and ADR-109:195 now carry reasoned ignore markers.
- Each marker sits on the same line, so line counts do not change.

### Noted, not changed

- ADR-102:70 quotes "MUST come from a named ref". The source says "MUST be computed from a named ref". The drift predates this diff.

## Round 2

Both seats reviewed the round 1 fixes.

| Agent | Position |
|-------|----------|
| architect | ACCEPT-WITH-CHANGES. ADR-062:86 kept "documents" after "then". |
| critic | ACCEPT. Nit: ADR-062:65 joined past and present tense with a comma. |

### Accepted

- ADR-062:86 now reads "documented".
- ADR-062:65 now uses a semicolon before "Serena Init is".
- The four marker lines change no visible text. They carry no path change.

Both fixes are one word or one mark on an existing line.
No seat raised an open finding after round 2.

### After round 2

- `check_measurement_anchoring.py` flagged four historical counts on ADR-109:33.
- The line changed only a citation, so the counts now count as added.
- The line gains a reasoned `measurement-anchor: ignore` HTML comment.
- No visible text changes, so the panel was not reconvened.

## Round 3: PR review findings

Devin Review left three nits on PR #7569.

### Accepted

- ADR-076:318 said to run `sync_plugin_lib.py` first, next to the successor path.
- The successor runs `build_all.py` alone. The row now says the rule was reworded since.
- This log lacked prior debate references. It now has a Prior debate logs section.

### Not changed, left to Richard

- Devin asked for relative links in place of code-span paths.
- `DOCUMENTATION-LINK-REQUIREMENTS.md:15` covers ADRs, and code-span paths break it.
- ADRs already diverge: 19 of 126 use relative links (2026-11-25).
- No checker enforces the policy. Converting the ADRs is left to Richard.

| Agent | Position |
|-------|----------|
| architect | ACCEPT-WITH-CHANGES. Four prior-log rows named older logs. Fixed. |
| critic | REVISE. The link decline cited house practice, not policy. Reworded. |

Both seats confirmed the ADR-076:318 claim against the successor.

## Final Verdicts

| Agent | Verdict |
|-------|---------|
| architect | ACCEPT-WITH-CHANGES in round 3. Its four row fixes are applied. |
| critic | REVISE in round 3. Its proposed wording is applied as given. |

Neither seat raised a finding against the ADR text after round 2.
Round 3 findings touched this log only, apart from ADR-076:318.

## Eval fixture outside the ADR scope

- `tests/evals/rule-scenarios/canonical-source-mirror.json` S3 named `.claude/rules/testing.md`.
- It now names `.claude/skills/test/references/rule-testing.md`.
- The `canonical-source-mirror` rule scopes `.claude/skills/**`, so S3 stays in scope.
- `evals/ponytail-incumbent/cases/a01-consolidate-policy/prompt.md` keeps its path.
- That prompt describes an imagined two-harness repo, so the path is a label.
- The recorded runs under `runs/2026-09-23/` quote the prompt verbatim.

## Gates

All runs are at `438fb87d49` on 2026-11-25.

- `check_citation_freshness.py --base d8d140bb2e`: exit 0, 15 citations examined, none stale.
- `check_adr_lifecycle.py`: PASS, 153 violations, none outside the baseline.
- `check_measurement_anchoring.py`: exit 0.
- `pre_pr.py`: exit 0. 122 PASS, 4 ADVISORY, 2 SKIP, 0 blocking.
- Doc Date Drift is advisory. It asks to bump ADR dates. A citation edit changes no decision, so dates stay.
