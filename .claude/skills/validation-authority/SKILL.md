---
name: validation-authority
description: Treat upstream validators as authoritative. Align local config to them. Use when validation fails unexpectedly, before modifying validator behavior, or when tempted to change upstream tool code.
license: MIT
metadata:
  version: 1.0.0
  source: Session 366 retrospective
  id: Validation-Authority-001
---

# Validation Authority

When integrating external validators (PSScriptAnalyzer, markdownlint, ESLint, etc.), respect upstream defaults. Modify local configuration to match upstream behavior. Do not modify upstream tool code.

## Triggers

Activate when:

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
| PSScriptAnalyzer rule fails | Update `.psscriptanalyzerrc` | Suppress `PSAvoidUsingWriteHost` with rationale |
| markdownlint rule fails | Update `.markdownlint.json` | Disable `MD013` line-length for generated docs |
| ESLint rule conflicts | Update `.eslintrc` | Override `no-console` for CLI tools |
| Upstream tool has a bug | File issue upstream, add workaround in config | Pin tool version, suppress specific rule |
| Tool default changed after upgrade | Review and align local config to new default | Update config after major version bump |

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
- [ ] Validation passes with the updated config

## Examples

### Example 1: PSScriptAnalyzer Rule Failure

**Problem**: `PSAvoidUsingWriteHost` fails on a CLI script that intentionally uses `Write-Host`.

**Wrong approach**: Modify PSScriptAnalyzer source or remove the rule globally.

**Correct approach**:

```json
// .psscriptanalyzerrc
{
  "Rules": {
    "PSAvoidUsingWriteHost": {
      "Enable": false
      // Rationale: CLI scripts use Write-Host for user-facing output
    }
  }
}
```

### Example 2: markdownlint Conflict

**Problem**: `MD013` (line length) fails on auto-generated documentation.

**Wrong approach**: Fork markdownlint to increase default line length.

**Correct approach**:

```json
// .markdownlint.json
{
  "MD013": {
    "line_length": 200,
    "tables": false
  }
  // Rationale: Generated docs have long lines from tool output
}
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
| [incoherence](../incoherence/SKILL.md) | Detects contradictions between config and behavior |

## Timelessness: 9/10

External tool integration is a universal software engineering concern. The principle of respecting upstream authority applies to any validator, linter, or static analysis tool regardless of language or framework.
