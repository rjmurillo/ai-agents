---
id: ADR-094
status: accepted
date: 2026-08-15
decision-makers: [rjmurillo]
supersedes: [ADR-044]
superseded-by: null
explainer: null
implemented: true
---

# ADR-094: Govern Copilot CLI Compatibility Through Executable Surfaces

## Status

Accepted (2026-08-15). Six of six ADR reviewers accepted Round 2 after the first draft was blocked. Review evidence: `.agents/critique/ADR-094-debate-log.md`.

## Date

2026-08-15

## Context

ADR-044 combined three concerns:

1. A temporary Copilot CLI pin for a frontmatter regression.
2. Frontmatter field and model-value policy.
3. Runtime version verification.

The decision shipped on 2026-02-01. Later work changed each concern:

- `.github/actions/ai-review/action.yml` now configures `COPILOT_VERSION="1.0.63"`.
- `.github/workflows/nightly-cli-smoke.yml` independently configures a Renovate-managed smoke version.
- `scripts/validation/check_copilot_version_pin.py` blocks `0.0.397` as known bad.
- ADR-080 now governs model pins and requires evidence for versioned model identifiers.
- Session 2586 on 2026-06-17 verified agent loading on Copilot CLI 1.0.63 with `argument-hint` present and no unsupported-field warning.

ADR-044 still told contributors to install `0.0.397`, and its model and agent-count claims no longer matched the repository. The record was implemented, so the project ADR mutability rule requires a superseding ADR instead of an in-place decision rewrite.

## Decision

1. **Supersede ADR-044 in full.** Keep ADR-044 unchanged except for lifecycle metadata and its supersession notice.
2. **Treat executable configuration as the version record.**
   - `.github/actions/ai-review/action.yml` owns the required review path's `COPILOT_VERSION`.
   - `.github/workflows/nightly-cli-smoke.yml` owns its independent, Renovate-managed smoke version.
   - These versions may differ because the nightly workflow validates newer runtime behavior before the required review path adopts it.
3. **Treat `check_copilot_version_pin.py` as a known-bad guard, not an allowlist.** It validates the required review pin in `action.yml`. A passing result means the configured value is parseable and not denylisted. It does not prove compatibility, and it does not govern the nightly smoke pin.
4. **Retire `0.0.397` immediately.** Keep it in `KNOWN_BAD_VERSIONS` as historical evidence. Documentation and runbooks must not recommend installing it.
5. **Keep runtime drift detection warn-only.** `scripts/ci/install_copilot_cli.py` warns when the installed binary differs from the configured version. This ADR does not claim that mismatch blocks CI.
6. **Defer model and frontmatter policy to current owners.**
   - ADR-080 governs model pins and evidence.
   - `templates/platforms/*.yaml` and the agent generators own platform output shape.
   - Runtime compatibility requires a real-CLI smoke with the fields under test. ADR prose does not freeze model identifiers or agent counts.
7. **Use this upgrade procedure for the required review pin.**
   - Reproduce the target version locally.
   - Load an agent carrying the relevant frontmatter fields with debug logging.
   - Update `COPILOT_VERSION` in `action.yml` and the fallback in `scripts/ci/install_copilot_cli.py` together.
   - Run the known-bad validator, its tests, and the workflow dry run.
   - Update an ADR only when this policy changes, not for routine version bumps.

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: ADR-044's combined pin, frontmatter, and runtime-verification decision.
- **When introduced**: commit `03f6d858d7`, PR #1024, 2026-02-01.
- **Original context**: Copilot CLI 0.0.398 through 0.0.400 silently rejected custom-agent frontmatter, breaking six review jobs.

### Historical Rationale

The 0.0.397 pin restored review jobs while preserving `argument-hint` and `model`. `--no-auto-update` limited binary self-update risk. The workaround was rational while the regression remained active.

### Why Change Now

- The required review path has run 1.0.63 since issue #2630.
- Local evidence recorded on 2026-06-17 showed 1.0.63 loaded an agent with `argument-hint` and emitted no unsupported-field warning.
- `0.0.397` is npm-deprecated and blocked by the repository's known-bad guard.
- ADR-080 replaced ADR-044's model-pin assumptions.
- Leaving ADR-044 Accepted directs contributors to a version the repository rejects.

The main risk is replacing one stale source with another. This decision limits durable prose to ownership and verification policy. Executable files retain the actual version values.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Amend ADR-044 in place | One file; preserves inbound links | Rewrites an implemented decision; leaves unrelated stale claims mixed with current policy | Violates the adopted bounded mutability rule |
| Keep ADR-044 Accepted with a status note | Preserves surviving decisions | No partial-supersession lifecycle; readers still treat stale model and pin text as current | The whole record has drifted |
| Make the validator the version authority | Executable and testable | It is a one-target denylist, not the source of the configured version or proof of compatibility | Misstates the validator contract |
| Centralize every Copilot version in one new config file | One literal for all callers | Removes deliberate nightly-versus-required-path variation and expands this governance fix into runtime refactoring | Not required to resolve the contradiction |
| Supersede ADR-044 and name executable owners | Preserves history; matches current code; separates policy from values | Multiple executable owners remain and need clear scope | Chosen |

### Trade-offs

The decision gives up one prose location containing every current value. In exchange, routine version updates no longer require an ADR edit, and a dated ADR cannot override executable configuration.

The required review and nightly smoke paths may run different versions. That difference is intentional but increases review cost. The known-bad validator covers only the required review path today.

## Consequences

### Positive

- Contributors no longer receive instructions to install blocked version `0.0.397`.
- ADR-044 remains intact as evidence for the original incident and response.
- Version values live beside the code that consumes them.
- Model policy has one current owner, ADR-080.
- The known-bad guard's scope and limits are explicit.

### Negative

- The required review action, installer fallback, and nightly smoke retain multiple version literals.
- Runtime version mismatch remains warn-only.
- The known-bad guard does not cover the nightly smoke pin.
- Compatibility still requires a real-CLI smoke. Static validation cannot prove vendor behavior.

### Neutral

- Routine Copilot CLI version bumps do not change this ADR.
- `--no-auto-update` remains part of Copilot CLI invocations.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| ADR-044 | Direct | Mark superseded by ADR-094; preserve original decision text | Low |
| `CONTRIBUTING.md` | Direct | Remove 0.0.397 and stale model literals; point to executable owners | Medium |
| Copilot frontmatter regression runbook | Direct | Replace reinstall guidance with current diagnostic and upgrade procedure | Medium |
| ADR-080 | Indirect | Remains the model-pin authority | Low |
| `action.yml` and installer fallback | Direct | Continue changing together for required review pin bumps | Medium |
| Nightly CLI smoke workflow | Direct | Remains independently Renovate-managed | Low |
| Known-bad validator | Direct | Remains a required-review-path denylist guard | Low |

## Implementation Notes

This change updates governance and contributor guidance only. It does not change runtime pins, validator scope, or warn-only runtime drift behavior.

## Related Decisions

- ADR-044: original Copilot CLI frontmatter compatibility decision, superseded by this record.
- ADR-080: model-pin justification policy.
- ADR-093: red checks require equivalent verification evidence.

## References

- Issue #4939.
- Issue #2630.
- Session `.agents/sessions/2026-06-17-session-2586-fix-2630-bump-pinned-githubcopilot.json`.
- `scripts/validation/check_copilot_version_pin.py`.
- `.github/actions/ai-review/action.yml`.
- `.github/workflows/nightly-cli-smoke.yml`.
- `.claude/skills/adr-generator/references/adr-best-practices.md`.
