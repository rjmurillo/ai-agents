# Phase 3 Consistency Validation Skills

Extracted from session: 2025-12-16

## Skill-PowerShell-001: Case-Sensitive Regex Matching

**Statement**: Use `-cmatch` instead of `-match` when pattern requires case-sensitive matching (e.g., EPIC vs epic)

**Context**: When writing PowerShell validation scripts that enforce naming conventions with specific case requirements

**Evidence**: Test suite for Validate-Consistency.ps1 failed with `-match`, passed with `-cmatch` for EPIC pattern validation

**Atomicity**: 95%

**Tags**: powershell, regex, validation, testing

**Root Cause**: PowerShell `-match` operator is case-insensitive by default, but naming conventions require case-sensitive validation

---

## Skill-PowerShell-002: Pester Hashtable Initialization

**Statement**: Pre-compute collections before Pester hashtable initialization; pipeline operators inside hashtable index expressions fail

**Context**: When writing Pester tests that use hashtables with computed values or collections

**Evidence**: Pester test failed with 'Cannot use a pipeline operator inside a hashtable index expression' error; resolved by pre-computing

**Atomicity**: 92%

**Tags**: powershell, pester, testing, hashtable

**Root Cause**: Pester processes hashtables specially for test parameters and assertions, restricting inline pipeline syntax

**Example Fix**:

```powershell
# WRONG - Pipeline in hashtable
$testCases = @{
    Values = Get-Items | Select-Object Name
}

# RIGHT - Pre-compute
$values = Get-Items | Select-Object Name
$testCases = @{
    Values = $values
}
```

---

## Skill-Organization-001: Script Placement Convention

**Statement**: Validation scripts belong ONLY in `scripts/` directory; never duplicate to `.agents/utilities/`

**Context**: When creating new validation or utility scripts for the project

**Evidence**: Validate-Consistency.ps1 placed in scripts/ following PowerShell conventions; duplicate in .agents/utilities/ removed to maintain single source of truth

**Atomicity**: 95%

**Tags**: organization, conventions, file-structure, DRY

**Note**: All agent references should use `scripts/Validate-Consistency.ps1` directly

**Directory Structure**:

```text
scripts/               # Single source of truth for all scripts
├── Validate-*.ps1    # Validation scripts
└── tests/            # Pester tests

.agents/utilities/     # Agent-specific utilities ONLY (not duplicates)
├── fix-markdown-fences/  # Markdown repair tools
├── metrics/              # Metrics collection
└── security-detection/   # Security file detection
```

---

## Skill-DevOps-002: Non-Blocking Pre-Commit Validation

**Statement**: New validation rules should warn (not block) in pre-commit hooks to avoid disrupting existing workflows

**Context**: When integrating new validation tools into pre-commit hooks

**Evidence**: Consistency validation integrated as non-blocking warnings in .githooks/pre-commit; provides feedback without failing commits

**Atomicity**: 93%

**Tags**: devops, git-hooks, validation, workflow

**Pattern**: Use warning output and don't fail commit; allows gradual adoption of new validation rules

**Example**:

```bash
if ! pwsh -File "$VALIDATION_SCRIPT" -Path "$REPO_ROOT" 2>&1; then
    echo_warning "Validation found issues (see above)."
    echo_info "  Consider running: pwsh scripts/Validate-Consistency.ps1 -All"
    # Non-blocking: just warn, don't fail the commit
else
    echo_success "Validation OK."
fi
```

---

## Skill-Documentation-001: Template-First Documentation Workflow

**Statement**: Agent document changes must go through templates then Generate-Agents.ps1 to maintain consistency

**Context**: When updating agent guidelines, protocols, or documentation that affects multiple agent variants

**Evidence**: AGENTS.md naming conventions section added via templates/agents/orchestrator.shared.md then Generate-Agents.ps1

**Atomicity**: 94%

**Tags**: documentation, workflow, templates, agents

**Rationale**: Maintains consistency across Claude Code, Copilot CLI, and VS Code agent variants

**Workflow**:

1. Edit `templates/agents/[agent].shared.md`
2. Run `pwsh scripts/Generate-Agents.ps1`
3. Verify changes in all agent variants:
   - `src/claude/*.md`
   - `src/copilot-cli/*.agent.md`
   - `src/vs-code-agents/*.agent.md`
4. Commit all updated files together

---

## Success Patterns Validated

### Test-Driven Development for Validation Scripts

- **Evidence**: Both bugs (case-sensitivity, hashtable syntax) caught by tests before integration
- **Impact**: High - prevented production issues
- **Validation Count**: 1

### Atomic Commits with Conventional Format

- **Evidence**: 3 commits, all atomic and well-formatted
- **Impact**: High - enables easy review and rollback
- **Validation Count**: 3

### Non-Blocking Pre-Commit Warnings

- **Evidence**: No workflow disruption reported, users receive feedback
- **Impact**: Medium - raises awareness without blocking
- **Validation Count**: 2 (this validation + previous planning validation)

---

## Related Artifacts

- Retrospective: `.agents/retrospective/2025-12-16-phase3-consistency-validation.md`
- Implementation: `scripts/Validate-Consistency.ps1`
- Tests: `scripts/tests/Validate-Consistency.Tests.ps1`
- Integration: `.githooks/pre-commit`
- Documentation: `AGENTS.md` (Naming Conventions section)

---

## Improvement Opportunities

1. **PSScriptAnalyzer**: Add linting rules to catch case-sensitivity issues automatically
2. **CI Integration**: Run validation in CI pipeline, not just pre-commit
3. **Metrics Collection**: Track validation failure rates to identify common issues
4. **Automated Blocking**: Once validated in production, convert pre-commit warnings to blocking errors
