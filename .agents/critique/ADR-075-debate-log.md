# ADR-075 Review Debate Log

## Subject

ADR-075: Form-Factor Evaluation Methodology (Agent vs Skill).

Recovered from never-merged orphan commit `109b15ae3b` (branch
`chore/issue-triage-sweep-2026-06-19`). Closes issue #1875, the form-factor
follow-on that ADR-058 deferred.

## Date

2026-06-27

## Participants

architect, critic, independent-thinker, security, analyst, high-level-advisor.

## Round 1: Independent Review

### Verdict tally

| Agent | Verdict |
|-------|---------|
| architect | ACCEPT with 4 P1 conditions |
| security | ACCEPT (2 P2, both already mitigated) |
| analyst | ACCEPT with P1/P2 corrections |
| high-level-advisor | ACCEPT (ship at Proposed) |
| critic | DISAGREE-AND-COMMIT |
| independent-thinker | DISAGREE-AND-COMMIT |

Consensus: ACCEPT or DISAGREE-AND-COMMIT across all six. No BLOCK. The gate
clears.

## Consolidated Findings

### P0 (factual, fixed in this pass)

- **Fixture count error.** ADR Confirmation said "(F001 to F010)" but the run
  used 16 fixtures (F001 to F016). Confirmed by four agents against
  `report.json` `per_fixture_pass_rates` (16 keys) and the call math
  (16 fixtures x 3 variants x 3 runs = 144 calls). Fixed: text now reads
  "(F001 to F016)".

### P1 (addressed in this pass)

- **Verdict overclaim vs CI width (critic, independent-thinker, architect,
  high-level-advisor).** The 95% CI on agent-minus-skill recall is
  [-26.67pp, +26.67pp], a 53pp span centered near zero. "Includes zero" means
  the experiment cannot distinguish equivalence from a 27pp loss. The recall
  comparison did not decide the verdict; cost did. Fixed: the verdict now states
  the CI is too wide to prove recall equivalence and names the 3x token
  advantage as the deciding factor. The decision criteria now note the
  non-significance-vs-equivalence distinction.
- **Content confound (independent-thinker, P0 in its frame).** The skill artifact
  (`security-review/SKILL.md`, ~215 lines) is a smaller projection of the agent
  (`security.shared.md`, ~704 lines) with a different verdict taxonomy. The
  comparison varies content as well as form. Recorded as an explicit caveat and a
  reason to keep status Proposed; the verdict is directional, not a basis for
  retiring the agent form.
- **Per-fixture skill data not persisted (critic, analyst).** `report.json`
  per-fixture breakdown carries only `agent` and `baseline`; the skill aggregate
  is in the `form_factor` block but per-fixture skill rows are not in the report
  schema. Recorded as a caveat. The aggregate numbers verified exact against the
  artifacts.

### P2 (documented)

- CI-width promotion threshold (directional vs confirmed) is not encoded;
  deferred to a confirmatory rerun per #2678.
- Cost unit is tokens, not dollars or wall-clock; stated in the cost-accounting
  section.
- REPORT.md standalone CI section reports the agent-vs-baseline interval, a
  different comparison from the agent-vs-skill CI the ADR uses; no factual error.

### Security (ACCEPT, no blocks)

- `--skill-path` has a three-layer path-traversal guard (regex allow-list,
  literal `..` rejection, resolved-path containment under REPO_ROOT). Verified in
  `scripts/eval/eval-agent-vs-baseline.py`.
- Committed run artifacts contain no real secrets; fixtures are synthetic.
- `explainer: null` frontmatter is the safe default per ADR-073 no-auto-fetch.

### Analyst verification (numbers exact)

| ADR Claim | Artifact | Match |
|-----------|----------|-------|
| Agent recall 82.4% | form_factor.agent_recall 0.823529 | yes |
| Skill recall 84.3% | form_factor.skill_recall 0.843137 | yes |
| Agent tokens 362,804 | 356040 + 6764 | exact |
| Skill tokens 123,853 | 117816 + 6037 | exact |
| Agent-skill CI [-26.67, +26.67] | [-0.2667, 0.2667] | exact |
| Verdict prefer-skill-form | form_factor.verdict | exact |
| 0 errors | error_count 0 | exact |

## Resolution

Status stays **Proposed**. The ADR records a methodology and a directional first
verdict with explicit confound and power caveats. Promotion to Accepted is gated
on a confirmatory, content-controlled rerun (independent-thinker P0,
issue #2678). The methodology itself has full consensus.

Disagree-and-Commit dissent (critic, independent-thinker): the "prefer-skill-form"
label should not drive retiring the agent form until the content confound is
removed and the CI narrowed. Captured in the ADR Confirmation caveats.
