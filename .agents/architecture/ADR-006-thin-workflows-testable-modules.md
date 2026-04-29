# ADR-006: Thin Workflows, Testable Modules

**Status**: Accepted
**Date**: 2025-12-18
**Deciders**: User, High-Level-Advisor Agent
**Context**: [PR #60](https://github.com/rjmurillo/ai-agents/pull/60) AI workflow implementation
**Related**: [ADR-005](./ADR-005-powershell-only-scripting.md) (PowerShell-Only Scripting), [PR #60 Remediation Plan](../planning/PR-60/002-pr-60-remediation-plan.md)

---

## Context and Problem Statement

GitHub Actions workflows cannot be tested locally. The feedback loop is:

1. Edit workflow YAML
2. Commit and push
3. Wait for CI to run (1-5 minutes)
4. Check results
5. If failed, repeat from step 1

This **slow OODA loop** makes workflow debugging painful and time-consuming.

**Key Question**: How should we structure workflows to enable fast local testing?

---

## Decision Drivers

1. **Testing Gap**: Workflows can't be tested with Pester locally
2. **Slow Feedback**: 1-5 minute wait per iteration vs seconds for local tests
3. **Business Logic**: Complex parsing, validation, and formatting logic needs testing
4. **DRY Principle**: Logic duplicated across workflows is error-prone
5. **Maintainability**: Bugs in workflows require slow fix-test-deploy cycle
6. **Developer Experience**: Frustration with slow feedback loop

---

## Considered Options

### Option 1: Thin Workflows, Testable Modules (CHOSEN)

**Workflows orchestrate only; all logic in PowerShell modules**

**Architecture**:
```
Workflow (YAML) - Orchestration only
  ↓ calls
PowerShell Module (.psm1) - Business logic
  ↓ tested by
Pester Tests (.Tests.ps1) - Fast local feedback
```

**Pros**:
- ✅ Fast OODA loop: Edit module → Run Pester → Get feedback (seconds)
- ✅ Full test coverage for business logic
- ✅ DRY: Reusable modules across workflows
- ✅ Debugging: Can debug PowerShell locally with breakpoints
- ✅ Separation of concerns: Orchestration vs logic

**Cons**:
- ❌ More files to maintain (module + tests)
- ❌ Requires discipline to keep workflows thin

### Option 2: All Logic in Workflows

**Put business logic directly in workflow YAML `run:` blocks**

**Pros**:
- ✅ Fewer files (everything in YAML)
- ✅ No module/workflow boundary to maintain

**Cons**:
- ❌ Slow OODA loop: Must push to test
- ❌ No local testing possible
- ❌ Logic duplication across workflows
- ❌ Difficult to debug (no breakpoints, limited logging)
- ❌ YAML is poor language for complex logic

### Option 3: Hybrid (Simple Logic in Workflows)

**Simple logic in workflows, complex logic in modules**

**Pros**:
- ✅ Flexibility for one-liners

**Cons**:
- ❌ Ambiguous boundary: What's "simple" vs "complex"?
- ❌ "Simple" logic often becomes complex over time
- ❌ Still have slow OODA loop for workflow changes
- ❌ Inconsistent: Some workflows thin, others fat

---

## Decision Outcome

**Chosen option: Option 1 - Thin Workflows, Testable Modules**

### Rationale

1. **Empirical Evidence**: PR #60 workflows initially had logic in YAML. Debugging required 5+ push-wait-check cycles. After extracting to modules, bugs fixed locally in minutes.

2. **Testability**: Business logic (verdict parsing, label extraction, formatting) requires tests. Pester tests caught 6+ bugs before CI.

3. **DRY**: 4 workflows share comment posting logic. Single module ([`AIReviewCommon.psm1`](../../.github/scripts/AIReviewCommon.psm1)) serves all 4.

4. **Speed**: Local Pester runs in ~2 seconds. CI runs in ~3 minutes. 90x faster feedback loop.

5. **Maintainability**: Logic changes require module edit + Pester test, not workflow edit + push + wait.

### Implementation Rules

#### Workflows (YAML)

**DO**:
- Orchestrate: Call scripts, pass parameters, handle success/failure
- Set environment variables for modules to consume
- Handle artifacts (upload/download)
- Manage concurrency, timeouts, triggers

**DON'T**:
- Parse complex strings (verdict, labels, etc.) - delegate to module
- Validate business rules - delegate to module
- Format output - delegate to module
- Duplicate logic from other workflows - use shared module

**Maximum workflow size**: 100 lines (orchestration only)

#### Modules (.psm1)

**DO**:
- Contain ALL business logic
- Be pure functions where possible (input → output, no side effects)
- Have comprehensive Pester tests (80%+ coverage)
- Use meaningful function names (verb-noun format)
- Export only public functions

**DON'T**:
- Directly call GitHub CLI (`gh`) - use `.claude/skills/github/` wrappers
- Depend on workflow environment variables where avoidable (pass as parameters)
- Duplicate functionality from Claude skills

**Test coverage requirement**: 80% for all exported functions

#### Example Pattern

**BAD** (Logic in workflow):
```yaml
- name: Parse verdict
  shell: bash
  run: |
    # 20 lines of complex bash parsing
    VERDICT=$(echo "$OUTPUT" | grep -oP '(?<=VERDICT:\s*)[A-Z_]+')
    if [ -z "$VERDICT" ]; then
      # 10 lines of fallback parsing
    fi
    if [ "$VERDICT" = "CRITICAL_FAIL" ]; then
      exit 1
    fi
```

**Problem**: 30 lines of untestable bash. Must push to test.

**GOOD** (Logic in module):
```yaml
- name: Parse verdict
  shell: pwsh
  run: |
    Import-Module .github/scripts/AIReviewCommon.psm1
    $result = Get-VerdictFromOutput -Output $env:AI_OUTPUT
    if ($result.Verdict -eq 'CRITICAL_FAIL') {
      exit 1
    }
```

**Benefit**: `Get-VerdictFromOutput` has Pester tests. Edit → Test locally → Deploy.

---

## Consequences

### Positive

1. **Fast Feedback**: Seconds vs minutes for testing changes
2. **Higher Quality**: Bugs caught by Pester before CI
3. **Maintainability**: Logic changes don't require workflow edits
4. **Reusability**: Modules shared across workflows
5. **Debuggability**: Can set breakpoints in PowerShell
6. **Confidence**: 80%+ test coverage provides safety net

### Negative

1. **More Files**: Each workflow needs companion module + tests
   - **Mitigation**: Modules are reusable across workflows
2. **Learning Curve**: Developers must understand module boundary
   - **Mitigation**: Clear rules in this ADR
3. **Initial Effort**: Extracting logic to modules takes time
   - **Mitigation**: Faster iteration pays back quickly

### Neutral

1. **Existing Workflows**: Some existing workflows have logic in YAML
   - **Action**: Refactor when touching those workflows
   - **No** retroactive refactoring required unless workflow needs changes

---

## Validation Checklist

Before merging workflow changes:

- [ ] Workflow YAML < 100 lines
- [ ] No complex parsing/formatting in YAML `run:` blocks
- [ ] Business logic extracted to `.psm1` module
- [ ] Module has Pester tests (`.Tests.ps1`)
- [ ] Tests achieve 80%+ coverage
- [ ] Tests can run locally: `pwsh ./build/scripts/Invoke-PesterTests.ps1`
- [ ] Module functions use verb-noun naming
- [ ] GitHub operations use `.claude/skills/github/` (not direct `gh` calls)

---

## Related Decisions

- [ADR-005: PowerShell-Only Scripting](./ADR-005-powershell-only-scripting.md) (all modules must be PowerShell)
- **Pattern**: `pattern-thin-workflows` memory (use `mcp__serena__read_memory` with `memory_file_name="pattern-thin-workflows"`) - detailed pattern documentation
- **Skill**: [`.claude/skills/github/`](../../.claude/skills/github/) (reusable GitHub operations)

---

## References

- [PR #60](https://github.com/rjmurillo/ai-agents/pull/60): Workflows refactored from bash-in-YAML to PowerShell modules
- [`.github/scripts/AIReviewCommon.psm1`](../../.github/scripts/AIReviewCommon.psm1): 708 lines, 93 Pester tests
- [`.github/scripts/AIReviewCommon.Tests.ps1`](../../.github/scripts/AIReviewCommon.Tests.ps1): Comprehensive test suite
- [Session log](../sessions/2025-12-18-session-15-pr-60-response.md): `.agents/sessions/2025-12-18-session-15-pr-60-response.md`

---

## Migration Strategy

For existing workflows with embedded logic:

1. **No Forced Refactoring**: Don't refactor working workflows unless changing them
2. **On Touch**: When modifying a workflow, extract logic to module at that time
3. **Gradual**: Refactor one workflow at a time as needed
4. **Test First**: Create Pester tests for extracted logic before changing workflow

---

**Supersedes**: None (new decision)
**Amended by**: [Amendment 2026-04-28](#amendment-2026-04-28-config-data-exception-for-build-pipelines) — Config-data exception for build pipelines

---

## Amendment 2026-04-28: Config-Data Exception for Build Pipelines

**Status**: Accepted (Round 2 consensus — all `/adr-review` agent findings incorporated)
**Date**: 2026-04-28
**Deciders**: Richard, Claude (planning)
**Triggering context**: [REQ-003 Multi-Tool Artifact Build System](../specs/requirements/REQ-003-multi-tool-artifact-build.md)
**Related incident**: [PIR PR #1773 plugin manifest schema regression](../incidents/2026-04-27-pir-plugin-manifest-schema-1773.md)
**Multi-agent review**: architect (APPROVE_WITH_CHANGES) + critic (NEEDS_REVISION → addressed in Round 2) + independent-thinker (D&C) + security (D&C w/ 5 hardening fixes) + analyst (D&C w/ 3 factual corrections) + high-level-advisor (ACCEPT). Round 2 incorporates: forward-looking-policy framing, grandfathering, security conditions 6-7, structural complexity limit, REQ-003-002 dependency.

### Anchor: original rationale (verbatim, lines 13-21)

> "GitHub Actions workflows cannot be tested locally. The feedback loop is: 1. Edit workflow YAML 2. Commit and push 3. Wait for CI to run (1-5 minutes) 4. Check results 5. If failed, repeat from step 1. This **slow OODA loop** makes workflow debugging painful and time-consuming."

The original ADR-006 forbids logic in YAML **because workflow YAML cannot be tested locally**. The amendment narrows the rule to apply only where that testability gap exists. Build-pipeline config files do NOT exhibit the gap — they are read by Python modules that ARE testable.

### Context

REQ-003 introduces `templates/platforms/copilot-cli.yaml` to declare per-platform substitution rules consumed by Python build scripts (`build/scripts/generate_<artifact>.py`). The file holds:

- Filename suffix maps (`.md` → `.agent.md`, `.md` → `.instructions.md`)
- Output path tables (`.claude/agents` → `src/copilot-cli/agents`)
- Frontmatter key remap (`paths` → `applyTo`)
- Hook event remap (`PreToolUse` → `preToolUse`)
- Drop lists (events Copilot CLI does not support)
- Schema versioning (`schemaVersion: "1.0"` for forward evolution)
- Audit blocklist patterns

Reading the original ADR-006 strictly, "no logic in YAML" could be interpreted to forbid this. The amendment clarifies the boundary.

### Decision

ADR-006's "no logic in YAML" rule applies to **GitHub Actions workflow files** (`.github/workflows/*.yml`), NOT to **build-pipeline configuration files** consumed by tested modules. Pure-data YAML is permitted when ALL SEVEN conditions hold:

1. **Data, not control flow.** YAML carries lookup tables, filename maps, regex patterns, drop lists. It does NOT carry conditionals, loops, function calls, expressions, or `${{ }}` interpolation. **YAML anchors (`&`) and aliases (`*`) referencing computed values are also forbidden.**
2. **Consumed by tested code (≥80% line coverage, enforced).** A Python module (or PowerShell module) parses the YAML, applies the data, and is itself covered by unit tests at the ≥80% line coverage bar from ADR-006 line 142. **The threshold MUST be enforced by `fail_under = 80` in `pyproject.toml` and a CI gate.** Today the threshold is documented but not enforced; bringing the gate online is a REQ-003 follow-on obligation tracked in the plan.
3. **Schema-validated by named CI gate (REQ-003-002).** The YAML conforms to a documented schema enforced by `build/scripts/validate_templates_schema.py`. The validator MUST: (a) parse with `yaml.safe_load` first, then schema-check, then run semantic checks (parse-order locked to prevent TOCTOU); (b) require a `schemaVersion` key with SemVer value; (c) reject unknown top-level keys and unknown nested keys per artifact stanza; (d) run in CI on every PR touching the YAML.
4. **Path-traversal safe per REQ-003-009, both at load time AND post-substitution.** Path values are validated at load time (`..`, absolute paths → exit 2). Additionally, when the YAML carries regex patterns or template strings later substituted to produce paths, the **consumer module MUST re-validate the substituted result before use** (post-substitution check). Asserted by REQ-003-009 verification tests + a consumer-side test fixture per generator.
5. **Discoverable in permitted prefix.** Lives under one of: `templates/platforms/`, `build/`. (`.github/instructions/` was previously listed; **dropped in Round 2** because Copilot CLI doc-verified support is conditional per REQ-003 D8 and the prefix risks shipping dead artifacts. If REQ-003 D8 resolves to confirm CLI consumption, a follow-up amendment may add it back.)
6. **NEW (security): Safe deserialization mandate.** Consumers MUST use `yaml.safe_load()` (Python) or `ConvertFrom-Yaml -ScalarOnly` equivalent (PowerShell). The validator MUST reject all YAML tags except plain scalars, sequences, and mappings — explicitly rejecting `!python/`, `!!python/`, `!!binary`, and any non-spec tag. Consumers MUST never call `yaml.load()` (unsafe).
7. **NEW (security): Pattern hardening.** Regex patterns embedded in YAML are subject to: (a) max length 200 characters; (b) no nested quantifiers (e.g. `(a+)+`); (c) entropy + pattern scan to reject lines matching common secret formats (AWS keys, GitHub tokens `ghp_/gho_/ghs_`, private key headers, high-entropy strings >40 chars). Validator runs all three checks and exits 2 on violation.

### Negative test case (loophole closure)

The amendment does NOT permit logic in `.github/workflows/*.yml` `run:` blocks regardless of how the logic is dressed up. Specifically still banned:

- `run: |` blocks containing parsing, validation, formatting, or business rules
- Reusable workflow inputs that carry GitHub Actions expressions used as control flow
- Composite action `run:` steps with embedded shell logic
- Inline JavaScript in `actions/github-script@v7` that exceeds orchestration

If a workflow needs logic, extract it to a PowerShell or Python module under `.claude/skills/` or `build/scripts/` per the original ADR-006.

### Rationale

**Correct framing of PR #1773 motivation** (analyst correction): PR #1773's regression was schema invalidity in JSON manifests (`hooks` shape wrong against Anthropic's schema). The bug was NOT a Python-dict shape. PR #1795 fixed it with a Python schema validator + pytest — exactly what condition 2 requires. The relevance of #1773 to this amendment is the structural lesson it taught: **adding a new artifact class without a schema-validation gate** is the failure pattern. Hard-coded `PLUGIN_COUNTERS = {...}` in `validate_marketplace_counts.py` is a separate latent risk that REQ-003-004 addresses by making it config-driven; treating that risk as if it were proven by #1773 conflates two distinct failure modes. The amendment cites #1773 only for the structural lesson (need for schema gates on new artifact classes), not as proof that Python dicts caused that specific regression.

Forbidding all YAML config would force one of these worse alternatives:

- **Hard-coded Python dicts** (`PLUGIN_COUNTERS = {...}`) — adding a new artifact type requires Python edits and offers no schema-validation gate, the same structural gap that allowed PR #1773's invalid JSON to reach production undetected.
- **JSON instead of YAML** — TOML or JSON5 offer comment support and remain candidates if YAML proves insufficient (see Reversibility/Exit). Plain JSON's lack of comments rules it out for human-edited tables.
- **Typed Python data module** (`copilot_cli_config.py` with `dataclass`) — viable; rejected because every (provider, artifact) pair would still require Python edits, recreating the gap. The schema-validated YAML approach lets non-Python contributors propose changes safely.
- **Duplicating maps across multiple Python files** — DRY violation per ADR-006's own decision driver #4.

The config-data exception preserves ADR-006's intent (testable, fast OODA) while permitting a configuration pattern that is **safer** than the alternatives. The seven conditions form a Chesterton's Fence test: each gates a specific failure mode (untestable code → C2; schema drift → C3; CWE-22 path traversal → C4; scope creep → C5; logic-in-YAML smuggle → C1; CWE-502 deserialization RCE → C6; CWE-1333 ReDoS + secret leakage → C7).

### Implementation rules (additions to ADR-006)

**Build-pipeline YAML files** (`templates/platforms/*.yaml`, similar):

**DO**:
- Hold lookup tables, filename suffixes, path mappings, regex patterns, drop lists
- Declare `schemaVersion` for forward evolution
- Live under `templates/platforms/` or `build/` (`.github/instructions/` was dropped in Round 2 — see Condition 5)
- Pass schema validation enforced by `validate_templates_schema.py` in CI

**DO NOT**:
- Embed Jinja templates, `${{ }}` expressions, or conditionals
- Reference shell or Python code (eval, exec, import statements)
- Carry credentials or secrets
- Skip schema validation (every YAML in permitted prefixes MUST be schema-covered)
- Use this exception to put logic in `.github/workflows/*.yml`

**Structural complexity limits** (replaces the prior "O(1) lookups" guidance, which was not measurable from a YAML diff):

- **No list-of-objects with > 2 keys per object** (e.g., `[{matcher, command}]` is fine; `[{matcher, command, when, env, cwd}]` is too rich for config).
- **Total YAML file size ≤ 200 lines** (anything larger likely encodes logic not data).
- **No anchors (`&`) or aliases (`*`) referencing computed values** (per Condition 1).

**Note (amendment-of-amendment, 2026-04-28 PM)**: The original Round 2 condition included a "nesting depth ≤ 3" rule. Dropped during M1 implementation: the canonical REQ-003-002 schema needs depth 4 for legitimate two-level mappings (`frontmatterRemap.paths`, `eventRemap.PreToolUse`, `appendFrontmatter.user-invocable`). Depth limits are aesthetic, not behavioral — they catch nothing the line-count cap and list-of-object key cap don't already catch, and PR review handles semantic intent ("does this encode logic?") better than a numeric threshold. Honest framing: the depth cap was speculative rigor. Removed.

If any limit is exceeded, extract the data into a Python module with `dataclass` types and pytest coverage. The schema validator (`validate_templates_schema.py`) MUST enforce these limits and exit 2 on violation.

### Grandfathering and migration (Round 2)

The three existing files in `templates/platforms/` (`copilot-cli.yaml`, `visual-studio.yaml`, `vscode.yaml`) **predate this amendment** and do NOT yet satisfy all seven conditions:

- They lack a `schemaVersion` key (Condition 3).
- The schema validator (`validate_templates_schema.py`) does not yet exist (Condition 3).
- The post-substitution path-validation tests do not exist (Condition 4).
- The `fail_under = 80` coverage gate is not yet enforced in `pyproject.toml` (Condition 2).
- The pattern-hardening rejection logic does not exist (Condition 7).

These files are **grandfathered as legacy until REQ-003-002 (Phase 1) ships**. The amendment is a **forward-looking policy**:

1. **Today (amendment accepted)**: existing files documented as legacy in `templates/platforms/README.md`; the seven conditions describe the target state.
2. **REQ-003 M1 (Phase 1)**: `validate_templates_schema.py`, `schemaVersion` key, and the canonical `copilot-cli.yaml` schema land. Existing files migrate to satisfy Conditions 1, 3, 6.
3. **REQ-003 M2 (Phase 2)**: counter generalization wires the validator into CI; `fail_under = 80` added to `pyproject.toml`; consumer-side path tests added. Conditions 2, 4 satisfied.
4. **REQ-003 M3 onward**: any NEW YAML in permitted prefixes MUST satisfy ALL seven conditions before merge.

Until step 4, the amendment is enforceable only as a written rule reviewed by humans. After step 4, CI gates make it deterministic.

### Reversibility Assessment

- **Rollback path**: revert the YAML file + the schema validator. Re-introduce hard-coded `PLUGIN_COUNTERS` dict. Cost: one PR; no data loss.
- **Vendor lock-in**: none. YAML is a portable, well-specified format with mature parsers in every major language.
- **Exit strategy**: if YAML proves insufficient (e.g., need schema unions, anchors), migrate to TOML or JSON5 with a one-shot migration script. The schema validator is the only consumer that reads the format directly.
- **Forward compat**: `schemaVersion: "1.0"` (SemVer) per REQ-003-002 enables additive evolution; breaking changes require a major bump and per-generator update.
- **Decision is REVERSIBLE pre-M3-adoption (single-PR rollback); EVOLVABLE post-adoption via `schemaVersion` major bump per REQ-003-002.** Once M3-M5 generators consume the schema, rollback cost = N PRs touching production code paths. Honest framing: amendment is reversible while existing YAMLs are still grandfathered; once new generators ship, evolution via SemVer is the practical exit path.

### Confirmation Method

Enforcement is **staged**. Today the gates are written-rule + human review; REQ-003 M1-M2 ship the deterministic CI checks. The grandfathering note above describes the staged rollout.

**Target state** (post-REQ-003 M2):

1. **CI gate**: `validate_templates_schema.py` runs on every PR touching `templates/**/*.yaml`. Schema violations fail the build. **NOT YET WIRED — REQ-003 M1 deliverable.**
2. **Lint rule**: `build/scripts/validate_yaml_locations.py` blocks new YAML outside permitted prefixes that contains lookup-table-shaped content. **NOT YET WIRED — REQ-003-002 follow-on.**
3. **Coverage gate**: pytest coverage on consuming modules (`build/scripts/generate_*.py`) enforced ≥80% per ADR-006 line 142. **`fail_under = 80` NOT YET in `pyproject.toml`** — REQ-003 M2 deliverable. Today the 80% requirement is documented but not enforced; humans must verify until the gate is wired.
4. **Audit trail**: every PR that adds or modifies a permitted-prefix YAML must reference this amendment in the description.

### Consequences

**Positive**:
- Adding a new (provider, artifact-type) pair requires zero Python edits — config-only change
- Schema evolution is explicit (`schemaVersion`) instead of implicit
- DRY: one source of truth for per-platform mappings consumed by all generators
- PR #1773 regression class is structurally prevented (config validated by CI gate before merge)

**Negative**:
- One more file format to learn (YAML schema vs Python module)
- Schema validator is itself code that must be maintained

**Neutral**:
- The line between "config data" and "logic" requires judgment at the boundaries (e.g., a regex pattern is data; an `if/else` chain in YAML is logic). The five conditions tighten the judgment surface but do not eliminate it.

### Out of scope

This amendment does NOT permit:
- Logic in `.github/workflows/*.yml` `run:` blocks (see Negative Test Case above)
- Reusable workflow inputs containing GitHub Actions expressions used as control flow
- Composite action steps with embedded shell logic
- Inline JavaScript in `actions/github-script@v7` exceeding orchestration
- Configuration in YAML for **runtime** behavior consumed by untested code
- YAML files outside `templates/platforms/`, `build/`, or `.github/instructions/` carrying mappings

### References

- Spec: `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md`
- Plan: `.agents/plans/active/req-003-multi-tool-artifact-build.md`
- Regression that motivated REQ-003: `.agents/incidents/2026-04-27-pir-plugin-manifest-schema-1773.md`
- Existing build-pipeline YAML following the proposed pattern: `templates/platforms/{copilot-cli,visual-studio,vscode}.yaml`
- Architect review: completed 2026-04-28; verdict APPROVE_WITH_CHANGES; all 10 revisions incorporated
