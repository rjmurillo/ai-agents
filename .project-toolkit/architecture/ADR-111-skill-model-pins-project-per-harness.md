---
id: ADR-111
status: accepted
date: 2026-09-27
decision-makers: [rjmurillo]
supersedes: [ADR-080]
superseded-by: null
explainer: null
implemented: true
review-by: 2027-03-27
---

# ADR-111: Skill Model Pins Project Per Harness

## Status

Accepted (2026-09-27, issue #5606). Supersedes ADR-080.

`status: accepted` rests on the adr-review debate recorded in
`.project-toolkit/critique/ADR-111-debate-log.md`. Six seats voted Accept or
Disagree-and-Commit after one resolution round. The owner's merge of the pull
request is the approval of record. If the owner declines, the pull request
closes and ADR-080 stays accepted, since both status flips ship together.

ADR-080 carries `implemented: true`. Its own Migration 2026-09-05 section says
a change to its Decision takes a superseding record. This is that record.
Rules 1, 2, 4, 5, and 6 are restated in current-state wording, with no change
in meaning. Rule 3 gains one clause. ADR-080's Context, Amendment 2026-08-12,
and Migration 2026-09-05 stay the history of record.

`implemented: true` holds at merge: the projection change ships in the same
pull request as this record.

## Date

2026-09-27

## Context

ADR-080 rule 3 lets a unit keep a bare `haiku` pin with a cost
`model-rationale:`. ADR-080's Amendment, finding 4, found a gap: skills ship
that alias raw into `src/copilot-cli/skills/`. A bare alias is not a valid
Copilot model id, so the cheap-tier intent does not reach Copilot. That last
step is INFERRED: the amendment's analysis ran agent probes, not skill probes
(`.project-toolkit/analysis/2026-08-12-adr-080-copilot-model-resolution.md`,
section "Where aliases actually ship unresolved").

On `main` at `258da7207`, seven skills carry the pin:
`fix-markdown-fences`, `metrics`, `observability`, `pr-quality-all`,
`security-detection`, `steering-matcher`, and `stuck-detection`. Issue #5606
named six; `pr-quality-all` joined when ADR-064 moved commands into skills.

Issue #5606 offered two fixes, and each trades one defect for another.

1. **Resolve the alias in the skill copier.** This mints a versioned id in a
   customer-facing tree. ADR-080 finding 1 measured that a versioned pin
   overrides the operator's chosen session model on delegation.
2. **Drop rule 3's exception for skills.** This removes the pins everywhere,
   including on Claude Code, where the pin works.

### What each harness does with a skill `model:` key

**Claude Code honors it.** The skills reference documents `model` as the
"Model to use when this skill is active". The override lasts for the rest of
the current turn. A value outside the organization's `availableModels`
allowlist, or one auto mode does not support, is not used. Source:
`https://code.claude.com/docs/en/skills`, read 2026-09-27.

**Copilot CLI has no per-skill model field.** Three sources for GitHub
Copilot CLI 1.0.89-1 agree. None is a runtime probe.

- SDK schema, `copilot-sdk/generated/session-events.d.ts`.
  `SkillInvokedData.model` is "Model identifier active when the skill was
  invoked, when known": the session model, recorded on the event, not a
  frontmatter input. `SkillsLoadedSkill`, the resolved skill metadata, has no
  model field. `SkillInvokedData.content` is the skill file "injected into
  the conversation for the model", so a skill runs inside the current session.
- Shipped code. The `app.js` skill mapper builds skill records with no model
  field. The `runtime.node` frontmatter validation strings cover
  `allowed-tools`, `user-invocable`, and `disable-model-invocation`, and name
  no skill `model` key. `model-policy` appears only in the custom-agent field
  list.
- Public docs. `https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-skills`,
  read 2026-09-27, documents `license` and `allowed-tools` and no model field.

The runtime probe did not run. Copilot CLI returned "You have exceeded your
monthly quota" for the treatment, alias, and control fixtures on 2026-09-27.
The Copilot finding is therefore graded code-and-docs, runtime unverified.

This changes the choice. Option 1 would mint a versioned id that Copilot does
not read for a skill at all. It would add finding 1's risk surface to the
tree and buy no cost saving. Option 2 would remove a pin that Claude Code
honors, to fix a key that Copilot does not read.

## Decision

Default every skill, agent, and command to the harness-inherited model.

1. **Skills and commands may not carry a versioned model id.** Allowed
   states: no `model:` line, or a bare rolling alias (`sonnet`, `opus`,
   `haiku`) with a `model-rationale:` field.
2. **Agents may carry a versioned pin only with a cited KEEP_PIN sweep**
   recorded in the sidecar manifest, per ADR-080 rule 2's evidence bar:
   `delta >= 0.05` mean recall, paired bootstrap CI lower bound `> 0`, at
   least 8 shared fixtures.
3. **Versioned ids are never minted from rolling aliases, and the cost
   exception is narrow.** A `model-rationale:` cost exception is valid only for
   an alias whose `model_tiers` entry prices strictly below the harness
   default in `MODEL_PRICING_RATES_USD_PER_1K_TOKENS`; in practice `haiku`.
   The tier map is the price reference here; it is not a translation step for
   skills. The exception never applies to a versioned pin. **New: the
   exception binds only a harness that reads the key.** A platform config
   whose harness has no per-skill model field lists `model` and
   `model-rationale` under `artifacts.skills.frontmatterDrop`, and the skill
   generator omits both from that projection. It never resolves the alias to
   a versioned id there. Today `templates/platforms/copilot-cli.yaml` declares
   the drop, and the Claude Code copies keep the keys.
4. **Evidence lives in a sidecar manifest, not in frontmatter**
   (`.agents/governance/model-pin-evidence.json`).
5. **Generators inject no default model.** Issue #5313 implemented this.
6. **`scripts/validation/check_model_pins.py` enforces rules 1 to 3** over
   the authored trees in `--mode enforce`. Its baseline is drained to zero, so
   a new non-compliant pin is a hard violation.

Rule 3's new clause is a skill rule. Generated agents are out of its scope:
`build/generate_agents_common.py` still resolves `model_tier: haiku` to
`claude-haiku-4.5`, because Copilot agents do read `model:`. Whether that
override is acceptable remains the open question ADR-080 finding 4 recorded.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
| --- | --- | --- | --- |
| Option 1: resolve `haiku` to `claude-haiku-4.5` in the skill mirror | Matches the agent generator | Mints a versioned id in a customer tree; Copilot's skill schema has no field to read it; needs a runtime probe that is blocked | Adds risk and buys no saving |
| Option 2: drop rule 3's exception for skills | One rule for all harnesses | Removes a pin Claude Code honors; the seven skills lose the cheap tier there | Fixes Copilot by breaking Claude Code |
| Option 3a: hard-code the two keys in the Copilot translation function | Smallest diff | Hides a per-harness projection in code; a second harness needs a code change | Superseded by 3b in review |
| Option 3b: declared `frontmatterDrop` on the skills stanza (chosen) | Same key the rules stanza already uses; a harness opts in by config | Mirror frontmatter differs from source by two keys | Chosen |
| Keep today's raw alias | No change | Ships an invalid value that looks like a working pin | Misleads readers of the mirror |

### Trade-offs

The Copilot mirror is no longer a pure copy of skill frontmatter. That was
already true: the translation respells `allowed-tools` for Copilot. The drop
is declared in config, like the rules stanza's `frontmatterDrop`, which is the
declared-projection shape ADR-107 prefers over an imperative transform.

## Consequences

### Positive

- `git grep -n "^model:" -- src/copilot-cli/skills` returns nothing.
- Claude Code keeps the cheap tier for the seven skills.
- No versioned id enters the skill mirror, so finding 1 is not reopened there.
- The drop fails the build, not the mirror, when a cut would change any other
  frontmatter key: the generator compares the parsed mapping before and after.

### Negative

- On Claude Code, a skill's `model: haiku` overrides the operator's chosen
  model for the rest of that turn. This is the same class of cost ADR-080
  finding 1 measured for a versioned agent pin, bounded to one turn and
  skipped under an `availableModels` allowlist or auto mode. ADR-080 already
  accepted it for rule 3 skills; this record keeps it, knowingly.
- The Copilot finding rests on code and docs, not a runtime probe. If a later
  Copilot CLI adds a skill `model` field, the drop hides the pin from it.
  Revisit by `review-by`, or sooner when a Copilot CLI bump changes
  `SkillsLoadedSkill` or `SkillInvokedData`. The probe method is in
  `.project-toolkit/analysis/2026-08-12-adr-080-copilot-model-resolution.md`.

### Neutral

- Copilot runtime behavior is unchanged. Before, it did not read the key.
  Now the key is absent.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
| --- | --- | --- | --- |
| `templates/platforms/copilot-cli.yaml` | Direct | `artifacts.skills.frontmatterDrop: [model, model-rationale]` | Low |
| `build/scripts/generate_skills.py` | Direct | Reads and validates `frontmatterDrop`; passes it to the copy | Low |
| `build/scripts/copilot_body_translation.py` | Direct | `drop_frontmatter_keys` with a parse-and-compare guard | Low |
| `build/scripts/validate_templates_schema.py` | Direct | `frontmatterDrop` allowed on the skills stanza | Low |
| `src/copilot-cli/skills/*/SKILL.md` | Generated | Seven files lose two lines each | Low |
| `scripts/validation/check_model_pins.py` | None | Scans authored trees only; unchanged | Low |
| ADR-080 | Direct | `status: superseded`, `superseded-by: ADR-111` | Low |

## Implementation Notes

`drop_frontmatter_keys` drops a named top-level key, bare or quoted, plus its
value lines: indented lines, un-indented `- ` list items, and blank lines
inside a block scalar. It then parses the frontmatter before and after, and
raises `ValueError` unless the result equals the input minus the named keys.
Nested keys, `model_tier:`, and body text are left alone. Tests:
`tests/build_scripts/test_copilot_skill_model_projection.py`.

## Related Decisions

- ADR-080 (superseded by this record). Issues #5606, #5605, #5313.
- ADR-107 (canonical skill contracts and harness projections).
- ADR-109 (template-first plugin distribution).

## References

- `https://code.claude.com/docs/en/skills` (skill `model` field)
- `https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-skills`
- GitHub Copilot CLI 1.0.89-1, `copilot-sdk/generated/session-events.d.ts`
  (`SkillInvokedData`, `SkillsLoadedSkill`)
- `.project-toolkit/analysis/2026-08-12-adr-080-copilot-model-resolution.md`
