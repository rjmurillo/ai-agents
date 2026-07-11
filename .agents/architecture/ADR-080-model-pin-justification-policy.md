---
id: ADR-080
status: proposed
date: 2026-07-11
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-080: Model Pins Require Cited Eval Evidence

## Status

Proposed

## Date

2026-07-11

## Context

Skills, agents, and commands carry a `model:` frontmatter pin that forces a
specific model and version for that unit of work. Scanning unit frontmatter on
`main` (excluding the `AGENTS.md` and `CLAUDE.md` doc examples) finds roughly
108 pins across `.claude/skills`, `.claude/agents`, and `.claude/commands`.
None cites evidence that the pinned model beats the harness-inherited default
for that unit.

The pins cost us three concrete things, and all three trace to **versioned**
ids, not to rolling aliases:

- **Format drift.** The same intended model is spelled two ways: `claude-opus-4-6`
  (hyphen) in skills, `claude-opus-4.6` (dot) in agents.
- **Version drift.** One skill sits on `claude-opus-4-8` while others sit on
  `claude-opus-4-6`. No decision produced the split.
- **Retirement CI-break class.** A retired pinned id (`claude-opus-4.5`) broke
  CI and motivated issue #2839. Every versioned pin is a latent break waiting
  for the next model retirement. Rolling aliases (`sonnet`, `opus`, `haiku`)
  do not retire and do not drift, so they carry none of these three costs.

The pins encode a guess, not a measurement. This ADR is criterion 1 of issue
#2840: the policy that says when a `model:` pin is allowed.

### What measurement is actually possible

Issue #2901 delivered the sweep harness (`scripts/eval/eval-model-sweep.py`
plus `_model_sweep_core.py`) and #2902 completed the pricing table. But the
harness is **agent-shaped**: it builds child arguments only for `--agent`,
`--fixtures`, `--model`, `--n-runs` (`eval-model-sweep.py:158-184`) and the
base evaluator reads `templates/agents/{agent}.shared.md`
(`eval-agent-vs-baseline.py:104,394-406`). It cannot evaluate a skill or a
command.

Grounding the consequence: only **1 of 74 pinned skills** and **17 of 31
pinned agents** have an `evals/<name>-spike/fixtures` directory. About 90 of
the ~108 pinned units cannot produce a sweep at all. Any policy that says
"pin only with a sweep" without acknowledging this would be unenforceable for
83 percent of the pins. The adversarial review of this decision
(`.agents/critique/ADR-080-model-pin-policy-debate.md`) treated this as the
decisive finding.

## Decision

Default every skill, agent, and command to the harness-inherited model. The
absence of a `model:` line is correct and needs no justification. Beyond that,
the rule splits by unit kind, because only agents can be measured:

1. **Skills and commands may not carry a versioned model id.** They cannot be
   swept, so a version pin can never be justified. Their only allowed states
   are: no `model:` line (inherit), or a bare rolling alias
   (`sonnet` / `opus` / `haiku`) that carries a `model-rationale:` field. This
   removes format drift, version drift, and the retirement break from all
   skill and command pins with no eval spend.

2. **Agents may carry a versioned pin only with a cited KEEP_PIN sweep.** A
   versioned agent pin (for example `claude-opus-4-6`) is allowed only when a
   committed sweep artifact justifies it, recorded in a sidecar manifest (see
   point 4). The evidence bar is the harness verdict as it actually computes:
   `delta >= 0.05` mean recall **and** the paired bootstrap CI lower bound
   `> 0` (`_model_sweep_core.py:277`, `DEFAULT_MIN_EFFECT = 0.05`), from a
   single-candidate-versus-default sweep (so the CI is a plain 95 percent
   interval, not Bonferroni-widened) over **at least 8 shared fixtures**. A
   sweep with fewer shared fixtures, or one that returns DROP_PIN, is
   inconclusive and does not justify a pin: the pin is removed. Removing a pin
   returns the unit to the harness default, the same baseline the majority of
   units already run.

3. **Rolling aliases are never minted from versioned ids, and the cost
   exception is narrow.** Converting a bare alias to a versioned id (as #2891
   did for `haiku`) downgrades the unit and re-arms the #2839 retirement risk;
   do not do it for `sonnet` or `opus`. A `model-rationale:` cost exception is
   valid only for an alias that prices strictly below the harness default in
   `MODEL_PRICING_RATES_USD_PER_1K_TOKENS` (in practice `haiku`); it is not a
   general escape hatch, and it never applies to a versioned pin.

4. **Evidence lives in a sidecar manifest, not in frontmatter.** A committed
   `.agents/governance/model-pin-evidence.json` maps each versioned agent pin
   to its justifying artifact: unit name, pinned model id, artifact path,
   `fixtures_sha`, harness/pricing date. Frontmatter is not used because the
   generators copy unknown frontmatter keys straight into the customer-facing
   mirrors (`copilot_body_translation.py:192-203`), which would ship internal
   CI-artifact paths to Copilot and VS Code consumers.

5. **The generator must stop injecting a default model.** The Copilot agent
   generator currently injects `model: "claude-opus-4.6"` for every agent
   (`templates/platforms/copilot-cli.yaml:95`,
   `build/generate_agents_common.py:211-233`). While it does, removing a pin
   from source does not remove it from the generated mirror. The migration
   must change the generator to inherit (emit no `model:` unless the source
   unit carries a justified one), or the policy is toothless for generated
   agents.

6. **A governance check enforces the rule as a draining ratchet.** A new
   `scripts/validation/check_model_pins.py` scans unit frontmatter (excluding
   `AGENTS.md` / `CLAUDE.md` examples) and fails: a skill or command with a
   versioned id; a versioned agent pin without a valid manifest entry; a bare
   alias without `model-rationale:`; a cost rationale on an alias that does not
   price below the default. Because the pins predate the policy, the check
   ships against a frozen baseline (`dict[str, str]` of unit-path to model-id),
   grandfathering current pins and failing only on a new pin or a baselined pin
   whose value changed without evidence. Unlike a pure freeze, the baseline
   carries a burn-down obligation: its entry count must not grow and should
   shrink each release until it is empty, at which point the check flips to
   enforce. A `--update-baseline` flow plus a documented label escape hatch
   handles legitimate exceptions with an audit trail.

## Prior Art Investigation (Required when changing existing systems)

### What Currently Exists

- **Structure/pattern being changed**: `model:` frontmatter pins across
  `.claude/skills/*/SKILL.md`, `.claude/agents/*.md`,
  `.claude/commands/**/*.md`, mirrored into `src/copilot-cli` (copy) and
  `.github/agents` (hand-maintained install copy, `build/AGENTS.md:246`).
- **When introduced**: pins predate the eval harness; they accreted by hand.
  The retirement break was #2839; the first cleanup was #2891 (merged); the
  sweep harness was #2901 (merged).
- **Original author and context**: various; the pins were hand-tuned guesses,
  never measured.

### Historical Rationale

- **Why was it built this way?** No eval harness existed, so authors pinned
  the model they believed best.
- **What alternatives were considered?** None formally; incremental hand edits.
- **What constraints drove the design?** Absence of a per-unit model
  comparison, now lifted for agents by #2901.

### Why Change Now

- **Has the original problem changed?** Yes for agents (#2901 makes the
  comparison runnable); no for skills and commands (still no evaluator).
- **Is there a better solution now?** Yes: default-to-inherit plus a
  kind-split evidence rule replaces 108 guesses with a measured, ratcheted
  policy.
- **What are the risks of change?** Broad blast radius. Mitigated by
  defaulting to remove only where no evidence exists, sweeping only the ~17
  fixture-backed agents, and shipping the check warn-then-enforce so no
  existing pin breaks CI on landing.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep all pins, fix only spelling drift | Smallest change | Leaves 108 guesses and the retirement class in place | Does not solve pins that no evidence justifies |
| Strip all pins now, re-pin later | Immediately uniform | Discards correct pins; re-pinning is the same churn reversed; pre-empts measurement | Owner rejected bulk-stripping without evidence |
| Ban versioned ids entirely; allow only no-line or rolling alias; sweeps only for rare exceptions (the pure-simpler alternative) | No eval machinery, no stale artifacts, no migration spend; kills all three drift costs | Discards the owner's measured-keep goal and the harness built for it (#2901) | Partially adopted: this IS the rule for skills and commands; agents keep the evidence path per owner direction |
| Require a sweep for every unit including skills and commands | Uniform rule | The harness cannot evaluate skills or commands; unenforceable for 83 percent of pins | Physically impossible with current tooling |
| Default-to-inherit, kind-split evidence rule, draining ratchet (chosen) | Cheap where measurement is impossible, measured where it is possible; no flag day; drains over time | Two-kind rule is more complex than one; needs a manifest and a generator change | Matches the owner Definition of Done and what the tooling can actually do |

### Trade-offs

The rule is split by unit kind, which is more complex than a single sentence,
but it is the split reality imposes: agents are measurable, skills and commands
are not. The draining ratchet trades a clean immediate end state for a
shippable one, and the sidecar manifest plus the generator change are one-time
implementation costs that buy a policy that cannot be satisfied by a dangling
frontmatter string.

## Consequences

### Positive

- A new versioned pin cannot land without evidence (agents) or is banned
  outright (skills, commands), so the backlog stops growing and drains.
- Every kept agent pin cites a reproducible, identity-bound, freshness-checked
  sweep, replacing a guess with a measurement.
- The retirement-break class shrinks toward zero as versioned pins clear.
- Enforcement is a gate, not prose, matching the repo's verify-over-trust
  posture.

### Negative

- The migration is staged and costs API budget for the ~17 agent sweeps.
- Two new surfaces appear: the sidecar manifest and the generator default
  change.
- The kind-split rule is harder to state than a single blanket rule.

### Neutral

- Rolling aliases remain legal (with a cost rationale where they undercut the
  default), so intentional cheap-tier units are not forced onto the default.
- The baseline file becomes a tracked artifact that only ratchets down.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `scripts/validation/check_model_pins.py` (new) | Direct | Scanner, manifest and rationale validation, draining baseline | Medium |
| `.agents/governance/model-pin-evidence.json` (new) | Direct | Manifest schema and initial (empty) content | Low |
| Copilot agent generator config | Direct | Stop injecting `model: claude-opus-4.6`; inherit unless justified | Medium |
| Skill / command copiers | Direct | Confirm no versioned `model:` survives into mirrors | Low |
| CI workflow | Direct | Wire the check warn-then-enforce | Low |
| Existing ~108 pinned units | Indirect | Grandfathered until swept (agents) or de-versioned (skills, commands) | Low at landing, Medium over migration |
| Plugin manifests (`.claude`, `src/copilot-cli`) | Direct | Paired version bump in each migration PR | Low |

## Implementation Notes

Suggested sequence, each its own PR:

1. **This ADR** (policy only).
2. **Manifest schema plus the generator default change** so a justified pin
   can be expressed and an unjustified one actually disappears from mirrors.
3. **The governance check** `scripts/validation/check_model_pins.py` with a
   scanner-derived frozen baseline, wired in warn mode, with tests.
4. **Migration in batches**: de-version skill and command pins (remove or drop
   to a cost-justified alias); sweep the ~17 fixture-backed agents and either
   record a manifest entry (KEEP_PIN over >= 8 fixtures) or remove the pin.
   Regenerate mirrors, run `build_all.py --check` and install parity, bump both
   plugin manifests in the same PR. Flip the check to enforce once the baseline
   drains.

### Governance-check acceptance criteria (TESTING-RIGOR: positive, negative, edge)

- Positive: versioned agent pin with a valid manifest entry (KEEP_PIN, unit
  match, model match, `fixtures_sha` present, within max age) passes; bare
  alias with a below-default cost rationale passes; unit with no `model:` line
  passes.
- Negative: versioned skill or command pin fails; versioned agent pin with no
  manifest entry fails; manifest entry with `decision != KEEP_PIN`, wrong unit,
  wrong model, or a missing artifact fails; bare alias without rationale fails;
  cost rationale on a not-cheaper alias fails.
- Edge: `model:` lines inside `AGENTS.md` / `CLAUDE.md` examples are ignored;
  a stale manifest entry (past max age or default-model changed) fails; a
  path-traversal artifact path is rejected; baseline known-pin passes, new pin
  fails, baseline that grows fails the burn-down rule; warn mode reports but
  exits zero, enforce mode exits nonzero.

## Related Decisions

- Issue #2840 (criterion 1 this ADR satisfies), #2839 (retirement break),
  #2891 (bare-alias down-payment this ADR bounds), #2901 (sweep harness),
  #2902 (pricing table).
- ADR-034 (eval methodology), ADR-079 (plugin version bump ships with content).

## References

- `scripts/eval/eval-model-sweep.py`, `scripts/eval/_model_sweep_core.py`
  (`qualifies = delta >= min_effect and ci_low > 0.0`, `DEFAULT_MIN_EFFECT`)
- `scripts/eval/_eval_common.py` (`MODEL_PRICING_RATES_USD_PER_1K_TOKENS`)
- `templates/platforms/copilot-cli.yaml`, `build/generate_agents_common.py`
  (injected model default)
- `scripts/validation/check_skill_md_exec_portability.py`,
  `scripts/validation/check_vendor_portability.py` (ratchet patterns)
- `.agents/critique/ADR-080-model-pin-policy-debate.md` (the review this ADR
  incorporates)
