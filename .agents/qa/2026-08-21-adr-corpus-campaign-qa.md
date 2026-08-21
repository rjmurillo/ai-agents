---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-5189-54e494d-adr-corpus-evaluation-and-tooling.json
qaCommit: 46ba463681b370dad222097d906f0d7038e0bd0a
---

# QA: ADR Corpus Evaluation and Repair Campaign (issues #5189 to #5201, #5205)

**Branch**: `claude/adr-evaluation-tooling-6od8rd`
**Validated at commit**: `46ba463681b370dad222097d906f0d7038e0bd0a`
**Session log**: `.agents/sessions/2026-08-21-session-5189-54e494d-adr-corpus-evaluation-and-tooling.json`

## Verdict

PASS. 388 tests green, every gate at or below its baseline, `pre_pr.py` clean
apart from the session-end check this report exists to satisfy.

## Test evidence

```
uv run pytest tests/validation/test_check_adr_lifecycle.py \
              tests/validation/test_check_adr_links.py \
              tests/build_scripts/test_generate_adr_index.py \
              tests/skills/adr-review/ \
              tests/skills/test_misc_skill_scripts.py \
              tests/validation/test_pre_pr_sequence_registry.py \
              .claude/skills/adr-review/tests/ -q

============================= 388 passed in 6.98s ==============================
```

Breakdown of new coverage:

| Suite | Tests | Subject |
|---|---|---|
| `test_check_adr_lifecycle.py` | 85 | The nine lifecycle checks, containment, cycle termination, never-mutates |
| `test_check_adr_links.py` | 63 | Four link violation classes, historical-root exemption, fenced-block edges |
| `test_generate_adr_index.py` | 57 | Section routing, failure policy, determinism, no-banner, chain walk, review-by rendering |
| `test_detect_adr_changes.py` (x3 trees) | 93 | Frontmatter-only parsing, `unknown` sentinel, fenced-yaml regression guard |

Coverage measured on the new gates: `check_adr_links.py` 99% (single miss is the
`__main__` guard), `check_adr_lifecycle.py` 96% (misses are the `__main__` guard,
a `sys.path` insert, and two defensive I/O legs).

## Gate evidence

```
check_adr_lifecycle.py   [PASS] 78 violation(s), no check above its baseline.
check_adr_links.py       check_adr_links: 0 violation(s)
check_adr_uniqueness.py  [PASS] All ADR numbers unique (next free: 099)
taste count ratchet      OK. 573 violations <= baseline 576 (-3 slack).
ruff count ratchet       OK (count == baseline 27).
pre_pr.py                all gates PASS except Session End Validation
```

`pre_pr.py`'s single failure was `Session End Validation`, whose QA-evidence
check requires a path to a report under `.agents/qa/`. This file is that report.

## Corpus movement, measured

Run against a `git archive HEAD` extraction of the pre-campaign corpus versus the
working tree:

| Check | Before | After |
|---|---|---|
| `frontmatter-parses` (records with no parseable frontmatter) | 59 | 54 |
| `supersession-reciprocal` | 1 | 0 |
| ADR link violations | 26 | 0 against baseline, 21 pre-existing elsewhere |

`_get_adr_status` before and after, on real corpus files:

```
BEFORE  ADR-042 -> proposed    ADR-005 -> proposed
AFTER   ADR-042 -> accepted    ADR-005 -> superseded
```

ADR-073 regression guard held at `accepted` on both sides: its real frontmatter
says `accepted` and its Decision section contains a fenced YAML block whose
`status:` line the old whole-file regex could have read instead.

## Governance evidence

Ten ADR records were modified. Every substantive edit routed through the
mandatory six-role `adr-review` debate, which the pre-commit gate
`check_adr_review_policy` enforces. No hook was bypassed; `--no-verify`,
`LEFTHOOK=0`, and `LEFTHOOK_EXCLUDE` were not used at any point.

Consensus: 2 Accept (architect, high-level-advisor), 3 Disagree-and-Commit
(independent-thinker, security, analyst), 1 Block (critic) whose blocking
findings were all resolved before merge.

Debate logs, one per change-set rather than one for the batch:

- `.agents/critique/ADR-corpus-repair-5189-5201-debate-log.md`
- `.agents/critique/ADR-079-091-092-chain-debate-log.md`
- `.agents/critique/ADR-005-042-scripting-language-debate-log.md`
- `.agents/critique/ADR-023-032-033-link-repair-debate-log.md`

The per-change-set split was deliberate. The security reviewer proved that the
gate accepts one log as authorization for every ADR staged in the same commit
(issue #5205), so a single batch log would have exploited a defect the same
review had just found.

## Reviewer P0s found and fixed

| Finding | Resolution |
|---|---|
| ADR-055 claimed live accepted ADR-014 was retired. ADR-014 is Distributed Handoff Architecture, bound by `universal.md` MUST-3. | Rewritten to say where the marker actually points. |
| ADR-055 cited two ADR-007 survivals while the same diff removed one. | Claim deleted; it was also unverifiable. |
| `implemented: true` on ADR-055 while 21 of 132 `runs-on` declarations are non-ARM and none carries an exception marker. | Set to `false`; the residual gap is stated in the Metrics table with the 2026-08-21 measurement. |
| ADR-055's provenance prose was fabricated (claimed PR #476, 2025-12-29). | Refuted against `mcp__github__list_commits`: single commit `3e24d2c0`, PR #1604, 2026-04-10. This record **was ADR-032**. Corrected. |
| ADR-042 carried the corpus's most load-bearing enum without citing its evidence. | `## Status` now names `.agents/critique/ADR-042-debate-log.md` and four supporting artifacts. |
| ADR-025 quoted "111 of 127" with no matcher; measured total is 132. | Corrected with the command and the matrix-expression caveat. |

## Author errors found by reviewers and corrected on the issues

Two findings in the originally-filed issues were the author's and were wrong.
Both are corrected on the issues so an implementer does not chase them.

1. **#5197**: the reported malformed nested-bracket ADR-080 links do not exist.
   All eleven are well-formed. The audit regex began matching at the opening
   paren of a surrounding prose parenthetical and ran through the `](`.
2. **#5200**: five of the six `proposed` plus `implemented` records are
   deliberate, documented refusals to self-ratify, not drift. Zero flips made,
   which is the correct outcome.

## Known gaps carried forward

- 54 records still have no frontmatter (issue #5190). The ratchet holds the line;
  the index's "Needs backfill" section is the live meter.
- 21 pre-existing ADR link violations in files outside this change, each
  baselined with a written diagnosis.
- 21 non-ARM `runs-on` declarations carry no exception marker (issue #5199).
- The debate-log gate is forgeable (issue #5205), filed with a proven exploit.
- Six governance forks deferred to the owner, four of which the tie-breaker
  judged decidable by evidence rather than taste.


## Addendum: review-by renderer (commit 46ba46368)

CI's spec-validation completeness reviewer returned PARTIAL naming a real gap:
this campaign added `review-by` to `ADR-TEMPLATE.md` and shipped an index that
never read it, while issue #5198 specifies the Proposed table carries "the
condition or review date blocking acceptance".

Fixed. The index now reads `review-by` from frontmatter and renders it in the
Proposed blocking column, alone or alongside the prose blocker.

Re-verified at this commit:

```
388 passed in 6.98s
check_adr_lifecycle    [PASS] 78 violation(s), no check above its baseline.
check_adr_links        0 violation(s)
generate_adr_index     --check OK (README byte-identical)
```

Four added tests: the date renders; date and prose render together; absence
leaves prior output unchanged (negative control); and a determinism guard that
renders a long-past and a far-future date and asserts the output differs only in
the date itself. That last one pins a deliberate limitation: the renderer does
not compare against today, because it must be byte-identical for identical input.
Past-due detection belongs in the lifecycle gate, where a test can freeze the
clock. Tracked on #5193.

The generated README is byte-identical because no record sets `review-by` yet,
so this adds the reader ahead of the first writer rather than leaving the field
inert.
