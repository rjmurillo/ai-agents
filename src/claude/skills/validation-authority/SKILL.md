---
name: validation-authority
description: Treat upstream validators as authoritative. Align local config to them. Use when validation fails unexpectedly, before modifying validator behavior, or when tempted to change upstream tool code.
license: MIT
metadata:
  version: 1.0.0
  source: Session 366 retrospective
  id: Validation-Authority-001
  routing:
    role: conditional-adjunct
    invoker: build
    trigger: build Phase 2b writes the decision record after analysis-provenance classifies a validation target
    user-facing: true
---

# Validation Authority

When integrating external validators (PSScriptAnalyzer, markdownlint, ESLint, etc.), respect upstream defaults. Modify local configuration to match upstream behavior. Do not modify upstream tool code.

## Triggers

Say `validation failed unexpectedly`, `should I change the validator`, or
`is this validator authoritative`. Activate when:

- Validation fails unexpectedly
- Before modifying validator behavior or configuration
- When tempted to change upstream tool source code
- When adding a new external validator to the project
- When suppressing validator warnings without rationale

## Decision Tree

```
Validation failure occurred
        |
        v
Is the validator upstream (external tool)?
        |               |
       YES              NO (local/custom)
        |               |
        v               v
Modify LOCAL config   Modify tool as needed
to align with tool    (you own the code)
        |
        v
Document override rationale
in config comments
```

## Process

1. **Classify the validator**: Determine if the tool is upstream (external) or local (project-owned).
2. **Identify the conflict**: Find the specific rule or default causing the failure.
3. **Check upstream defaults**: Read the tool's documentation for the default behavior.
4. **Align local config**: Update project configuration files to match or explicitly override upstream defaults.
5. **Document overrides**: Add comments explaining why any override differs from the upstream default.

## Trigger Table

| Scenario | Action | Example |
|----------|--------|---------|
| PSScriptAnalyzer rule fails | Update `.psscriptanalyzerrc.psd1` | Suppress `PSAvoidUsingWriteHost` with rationale |
| markdownlint rule fails | Update `.markdownlint.yaml` | Disable `MD013` line-length for generated docs |
| ESLint rule conflicts | Update `.eslintrc` | Override `no-console` for CLI tools |
| Upstream tool has a bug | File issue upstream, add workaround in config | Pin tool version, suppress specific rule |
| Tool default changed after upgrade | Review and align local config to new default | Update config after major version bump |

## Adjunct Mode: Build Phase 2b (issue #5387)

`/build` Phase 2b invokes this skill after `analysis-provenance` classifies
every path `validation_trigger.py` flagged as a validation target. This mode
writes the decision record; it does not replace the general decision-tree
guidance above, which still applies whenever a human asks how to treat an
upstream validator.

1. For each target, combine `analysis-provenance`'s category, owner, and
   evidence with a diagnosis of what actually happened:
   `implementation-defect` (the local check has a real bug), `local-config-defect`
   (only the project's own config needs to change), `stale-generated-output`
   (a generated mirror drifted from its template or source), `baseline-update`
   (a ratchet or baseline needs new entries), `upstream-defect` (the vendored
   or upstream tool itself is wrong), or `unknown` (evidence is insufficient).
2. Name the one `permitted_change_location` Phase 3 may edit. `GENERATED`
   always permits only the canonical source, never the mirror. `VENDOR` and
   `UPSTREAM` never permit the target itself; point at the local override or
   config instead. `unknown` diagnosis or `UNKNOWN` category permits nothing:
   the record blocks further semantic edits until ownership evidence exists.
3. For `baseline-update`, cite the existing policy that authorizes the
   refresh (`baseline_justification.policy_source`, a path that exists on
   disk), state the reason, and justify every added entry individually.
4. Write the record to
   `.project-toolkit/scratch/validation-authority-record.json` (see
   "Validation Change Record" below) and run
   `python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/validation-authority/scripts/validation_record.py" --record .project-toolkit/scratch/validation-authority-record.json --changed-path <path>`
   for every changed path. Exit `0` clears Phase 3 to edit the permitted
   locations; exit `1` names the blocking targets; exit `2` is a
   configuration error in the record or the invocation.

## Scripts

| Script | Purpose | Exit codes |
|--------|---------|------------|
| `validation_record.py` (this skill's script directory) | Checks the Phase 2b decision record: field shape, provenance/authority rules, and changed-path coverage. Emits a JSON summary of target count, categories, and defects. | `0` record passed, `1` the record has defects, `2` config error (unreadable file, invalid JSON, or the sibling `build` trigger could not be loaded when `--changed-path` needed it) |

## Validation Change Record

The record `validation-authority` writes at
`.project-toolkit/scratch/validation-authority-record.json` (git-ignored
agent scratch space; the PR body carries the summary instead of a commit).

```json
{
  "trigger": { "...": "the validation_trigger.py output, carried through unchanged" },
  "targets": [
    {
      "target": "<path>",
      "component": "<human label for the tool or config>",
      "provenance": {
        "category": "LOCAL | GENERATED | VENDOR | UPSTREAM | UNKNOWN",
        "owner": "<non-empty>",
        "evidence": "<non-empty>",
        "canonical_source": "<required, and equal to permitted_change_location, when category is GENERATED>"
      },
      "authority": {
        "contract": "<non-empty; the validator's own exit-code or pass/fail contract>",
        "diagnosis": "implementation-defect | local-config-defect | stale-generated-output | baseline-update | upstream-defect | unknown",
        "permitted_change_location": "<non-empty; never the target itself for VENDOR or UPSTREAM>",
        "escalation": "<required, non-empty, when diagnosis is upstream-defect>"
      },
      "baseline_justification": {
        "policy_source": "<path that must exist on disk; required when diagnosis is baseline-update>",
        "reason": "<non-empty>",
        "added_entries": [{ "justification": "<non-empty per entry>" }]
      }
    }
  ]
}
```

Rules `validation_record.py` enforces:

1. Every target needs `target`, `component`, `provenance`, and `authority`.
2. `UNKNOWN` category or `unknown` diagnosis is always a blocking defect: stop
   semantic edits and request ownership evidence.
3. `GENERATED` needs `provenance.canonical_source`, and
   `authority.permitted_change_location` must equal it.
4. `VENDOR` or `UPSTREAM`: `authority.permitted_change_location` must not
   equal `target`. `upstream-defect` needs a non-empty `authority.escalation`.
5. `baseline-update` needs `baseline_justification` with an existing
   `policy_source`, a non-empty `reason`, and a non-empty `justification` on
   every entry in `added_entries`.
6. With `--changed-path` supplied: every path the sibling `build` trigger's
   path cues alone would flag needs a record target; a `VENDOR` or `UPSTREAM`
   target must not itself be a changed path; a changed `GENERATED` target
   needs its canonical source changed too, never edited as a standalone
   mirror.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Forking upstream tools to change behavior | Creates maintenance burden, diverges from community | Configure locally, file upstream issues |
| Patching tool source to suppress warnings | Hides real issues, breaks on updates | Use tool's suppression mechanism |
| Disabling entire rule categories | Loses protection the rules provide | Suppress specific rules with rationale |
| Suppressing without rationale | Future maintainers cannot evaluate the override | Always document why in config comments |
| Copying tool defaults into local config | Config drift when upstream updates | Only override what you need to change |

## Verification

After applying this skill:

- [ ] Validator is classified as upstream or local
- [ ] Local config aligns with upstream defaults
- [ ] Any overrides include documented rationale
- [ ] No upstream tool source code was modified
- [ ] Reconciliation: paste the validator's exit status line (e.g., `echo "exit=$?"` output after running the validator command) to confirm the updated config passes; a claim of "validation passes" without pasted output does not count

## Examples

### Example 1: PSScriptAnalyzer Rule Failure

**Problem**: `PSAvoidUsingWriteHost` fails on a CLI script that intentionally uses `Write-Host`.

**Wrong approach**: Modify PSScriptAnalyzer source or remove the rule globally.

**Correct approach**:

```powershell
# .psscriptanalyzerrc.psd1
# Rationale: CLI scripts use Write-Host for user-facing output
@{
    Rules = @{
        PSAvoidUsingWriteHost = @{
            Enable = $false
        }
    }
}
```

### Example 2: markdownlint Conflict

**Problem**: `MD013` (line length) fails on auto-generated documentation.

**Wrong approach**: Fork markdownlint to increase default line length.

**Correct approach**:

```yaml
# .markdownlint.yaml
# Rationale: Generated docs have long lines from tool output
MD013:
  line_length: 200
  tables: false
```

### Example 3: New Tool Integration

**Problem**: Adding `ruff` to a Python project. Several existing files fail.

**Wrong approach**: Disable all failing rules immediately.

**Correct approach**:

1. Run `ruff check` with defaults to see all violations.
2. Fix violations that align with project standards.
3. Suppress remaining rules per-file with `# noqa` and rationale.
4. Document any project-wide overrides in `pyproject.toml`.

## Related Skills

| Skill | Relationship |
|-------|--------------|
| [style-enforcement](../style-enforcement/SKILL.md) | Enforces style rules that this skill governs |
| [code-qualities-assessment](../code-qualities-assessment/SKILL.md) | Quality assessment, not validator config |
| [doc-accuracy](../doc-accuracy/SKILL.md) | Detects contradictions between docs/config and behavior |

## Timelessness: 9/10

External tool integration is a universal software engineering concern. The principle of respecting upstream authority applies to any validator, linter, or static analysis tool regardless of language or framework.
