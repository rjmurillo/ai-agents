# ADR-080 Debate Log: Model Pins Require Cited Eval Evidence

Multi-agent adversarial review of the proposed model-pin policy, run
2026-07-11 before the ADR was written. Three reviewers plus author
grounding. This log satisfies the routing-level architect-review gate on ADR writes (the PreToolUse gate implemented per ADR-033, Routing-Level Enforcement Gates) and records
the findings that shaped the final ADR.

## Participants

| Reviewer | Model | Role |
|----------|-------|------|
| architect | Claude | Architectural coherence, mechanism correctness |
| independent-thinker | GPT-5.5 | Adversarial: power, cost, simpler-policy |
| critic | GPT-5.5 | Completeness, mirror obligations, test rigor |
| author grounding | Claude | Fixture/generator/harness fact-finding |

## Consensus verdict

REVISE-then-accept. All three reviewers agree the overall shape
(default-to-inherited, pin-only-with-evidence, warn-then-enforce ratchet) is
sound. All three independently flagged that the shape is under-specified and
that one premise is wrong: the sweep harness cannot evaluate skills or
commands, only agents.

## Decisive finding: the harness is agent-only

The evidence mechanism the policy leans on (`scripts/eval/eval-model-sweep.py`)
builds child args only for `--agent`/`--fixtures`/`--model`/`--n-runs`
(`scripts/eval/eval-model-sweep.py:158-184`) and the base evaluator reads
`templates/agents/{agent}.shared.md` (`scripts/eval/eval-agent-vs-baseline.py:104,394-406`).
It has no skill or command path.

Author grounding confirmed the consequence: of the current pins, only **1 of
74 pinned skills** and **17 of 31 pinned agents** have an
`evals/<name>-spike/fixtures` directory. About 90 of ~108 pinned units cannot
produce a sweep at all.

**Resolution adopted in the ADR:** the eval-evidence path applies to agents
only. Skills and commands cannot carry a versioned pin (no way to justify
one); their allowed states are no `model:` line or a rolling alias. This
solves the three stated drift problems for ~83 skill/command pins without any
sweep, and reserves the eval machinery for the ~17 agents where it works.

## Findings and resolutions

### High severity

1. **KEEP_PIN bar was stated wrong (architect).** The verdict is
   `qualifies = delta >= min_effect and ci_low > 0.0` with
   `DEFAULT_MIN_EFFECT = 0.05` (`scripts/eval/_model_sweep_core.py:277,62`), not "CI
   excludes zero" alone. **Resolved:** ADR states both conditions.

2. **`model-evidence:` frontmatter would pollute downstream mirrors
   (architect, critic).** Generators preserve unknown frontmatter
   (`build/scripts/copilot_body_translation.py:192-203`) and the agent generator injects
   `model: "claude-opus-4.6"` as a default
   (`templates/platforms/copilot-cli.yaml:95`;
   `build/generate_agents_common.py:211-233`). Internal CI-artifact paths
   would ship to Copilot/VS Code consumers, and removing a source pin would
   not even propagate because the generator re-adds a default. **Resolved:**
   evidence lives in a sidecar manifest `.agents/governance/model-pin-evidence.json`,
   not frontmatter; and the migration must change the generator default to
   inherit (no injected `model:`), or the policy is toothless for generated
   agents.

3. **DROP_PIN means underpowered, not "safe to remove" (independent-thinker).**
   The paired bootstrap resamples fixture ids; with a 2-fixture floor
   (`scripts/eval/_model_sweep_core.py:321-335`) and 7-8 fixtures typical, the CI is
   low-powered and a real winner can still get DROP_PIN
   (`tests/eval/test_model_sweep_core.py:179-204`). **Resolved:** the ADR
   requires at least 8 shared fixtures for a KEEP verdict to justify a pin,
   treats an underpowered result as inconclusive (not evidence), and softens
   the "always safe" claim: removing a pin returns the unit to the harness
   default, the same baseline most units already run.

4. **Identity binding unspecified (architect, critic).** The check must
   verify `decision == KEEP_PIN` AND `artifact.agent == unit` AND
   `artifact.winner == pinned model`, not merely that a field is present
   (`scripts/eval/_model_sweep_core.py:430-482`). **Resolved:** ADR specifies the full
   predicate plus `fixtures_sha` and a max-age check.

5. **Mirror obligations unspecified (critic).** Skills copy to
   `src/copilot-cli`, agents generate from templates/platform config,
   `.github/agents` is a hand-maintained install copy (`build/AGENTS.md:246`).
   **Resolved:** ADR adds a source/mirror matrix and requires
   `build_all.py --check` + install-parity + paired plugin-manifest bumps in
   the same PR (ADR-079, plugin-version rule).

### Medium severity

6. **Bonferroni widening not disclosed (architect).** CI lower percentile is
   divided by candidate count (`scripts/eval/_model_sweep_core.py:340`). **Resolved:** ADR
   pins the expected single-candidate-vs-default sweep protocol for evidence.

7. **Ratchet baseline schema wrong shape (architect, independent-thinker).**
   Exec-portability ratchet is `dict[str,int]`
   (`scripts/validation/check_skill_md_exec_portability.py:213-234`); model pins need
   `dict[str,str]` (file to model-id) with new-pin and changed-value
   detection, and the frozen baseline drains nothing on its own
   (`scripts/validation/check_vendor_portability.py:321-330,401-433`). **Resolved:** ADR
   specifies the schema and adds a burn-down rule (baseline count must shrink
   each release; entries carry a removal target).

8. **Evidence staleness (architect, independent-thinker).** The sweep artifact
   lacks the pinned file path/prompt hash; a citation can go stale.
   **Resolved:** the check verifies `fixtures_sha` and a max artifact age and
   re-validates when the default model changes.

9. **Cost exception too loose (architect, independent-thinker).** `model: opus`
   is a rolling alias but not cheaper than the default
   (`.claude/agents/independent-thinker.md:4`, `.claude/commands/research.md:4`).
   **Resolved:** the cost exception applies only to aliases that price below
   the harness default (in practice `haiku`), validated against
   `MODEL_PRICING_RATES_USD_PER_1K_TOKENS`.

### Low severity

10. **Counts are estimates; naive scans hit doc examples (critic, architect).**
    `.claude/skills/CLAUDE.md:37` and `.claude/agents/AGENTS.md:187` carry
    example `model:` lines. **Resolved:** the baseline is computed by a scanner
    with explicit include/exclude rules (frontmatter only, unit files only, no
    `AGENTS.md`/`CLAUDE.md` examples), not from a hand estimate.

11. **Migration ordering (architect).** Ship generator/schema support before
    the check can be satisfied. **Resolved:** ADR reorders so schema plus
    generator support precedes enforce mode.

12. **No bypass mechanism (critic).** **Resolved:** ADR specifies a
    `--update-baseline` flow and a documented label/env escape hatch with an
    audit trail, matching existing validators.

## Strong alternative considered (independent-thinker)

"Ban versioned model ids entirely; allow only no `model:` line or a rolling
alias; require a rationale only for aliases; use sweeps only for rare version
exceptions." This addresses format drift, version drift, and the retirement
break directly, with no eval machinery, no stale artifacts, no underpowered
CI, and no migration spend.

**Disposition:** partially adopted. The final ADR bans versioned pins for
skills and commands outright (they cannot be swept), which is exactly this
alternative for ~83 of the pins. For agents, the owner's stated direction
(#2840: keep a pin only with eval evidence) and the harness the owner built
for it (#2901) are honored: a versioned agent pin is allowed only with a
KEEP_PIN artifact. This is presented to the owner as the primary decision with
the pure-simpler alternative recorded, per User Sovereignty; the owner reviews
the PR and may choose the pure alternative instead.

## Outcome

The ADR was rewritten to incorporate all twelve findings and the agent-only
scoping. High-severity gaps 1 through 5 are resolved in the decision text;
medium and low findings are resolved in the implementation-notes and
governance-check specification.
