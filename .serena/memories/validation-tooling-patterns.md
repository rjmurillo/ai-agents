# Validation Tooling Patterns

Patterns identified from Phase 3 consistency validation implementation.

## Pattern: Test-Driven Validation Development

**Description**: Write comprehensive test suites during (not after) validation script implementation

**Evidence**: 31 Pester tests caught 2 bugs before integration

- Bug 1: Case-sensitivity issue (PowerShell `-match` default)
- Bug 2: Pester hashtable syntax limitation

**Benefits**:

- Catches bugs before manual testing
- Documents expected behavior
- Enables confident refactoring
- Serves as regression prevention

**Application**: All validation scripts should have corresponding Pester test suites with >90% coverage

**Related Skills**:

- Skill-PowerShell-001 (discovered via testing)
- Skill-PowerShell-002 (discovered via testing)

---

## Pattern: Progressive Validation Adoption

**Description**: Introduce new validation rules as warnings (not blockers) initially

**Evidence**:

- Consistency validation integrated as non-blocking in pre-commit
- Planning validation also non-blocking
- Pattern repeated successfully twice

**Benefits**:

- Doesn't disrupt existing workflows
- Raises awareness gradually
- Allows time for remediation
- Reduces resistance to new tooling

**Lifecycle**:

1. Initial: Warning mode (educate users)
2. Transition: Warning + metrics (measure adoption)
3. Enforcement: Error mode (after majority compliance)

**Related Skills**: Skill-DevOps-002

---

## Pattern: Single Source Script Organization

**Description**: Maintain scripts ONLY in canonical `scripts/` location; agents reference directly

**Current Implementation**:

- Canonical: `scripts/` (PowerShell conventions)
- Agents: Reference `scripts/Validate-Consistency.ps1` directly
- NO duplication to `.agents/utilities/`

**Benefits**:

- **Single source of truth**: No synchronization needed
- **DRY principle**: No duplicate maintenance
- **Clear ownership**: Scripts team owns scripts/
- **Simpler CI**: One location to test

**Anti-Pattern Avoided**: Duplicating scripts to `.agents/utilities/` for "agent access" creates maintenance burden and potential drift

**Related Skills**: Skill-Organization-001

---

## Pattern: Template-Driven Multi-Variant Documentation

**Description**: Maintain single source of truth for shared agent content via templates

**Implementation**:

1. Shared content: `templates/agents/*.shared.md`
2. Variant-specific: `templates/agents/*.copilot.md`, `*.vs-code.md`
3. Generation: `scripts/Generate-Agents.ps1`
4. Outputs: `src/claude/`, `src/copilot-cli/`, `src/vs-code-agents/`

**Benefits**:

- Consistency across agent variants
- Single edit propagates to all targets
- Prevents documentation drift
- Enforces workflow discipline

**Related Skills**: Skill-Documentation-001

---

## Anti-Patterns Avoided

### Anti-Pattern: Manual Documentation Sync

**Problem**: Editing AGENTS.md directly without template update
**Impact**: Changes lost on next generation
**Prevention**: Pre-commit hook could check for direct edits

### Anti-Pattern: Blocking New Validations

**Problem**: New validation rules that fail commits immediately
**Impact**: User frustration, resistance to tooling
**Prevention**: Always start with warning mode

### Anti-Pattern: Case-Insensitive Naming Validation

**Problem**: Using `-match` for patterns requiring exact case
**Impact**: False positives (Epic matches EPIC)
**Prevention**: Code review, linting rules, test coverage

---

## Metrics from Implementation

| Metric | Value | Notes |
|--------|-------|-------|
| Lines of validation code | 677 | Validate-Consistency.ps1 |
| Lines of test code | 401 | Comprehensive coverage |
| Test count | 31 | All functions covered |
| Bugs caught by tests | 2 | 100% detection rate |
| Time to fix bugs | <30 min each | Quick iteration |
| Validation functions | 5 | Modular design |
| Pre-commit integrations | 2 | Planning + Consistency |

---

## Future Enhancements

1. **PSScriptAnalyzer Integration**: Add custom rules for case-sensitivity
2. **CI Pipeline Integration**: Run all validations in CI, not just locally
3. **Metrics Dashboard**: Track validation failure rates over time
4. **Auto-Remediation**: Generate fixes for common validation failures
5. **Performance Optimization**: Cache file scans for large codebases

---

## Session Reference

- Date: 2025-12-16
- Retrospective: `.agents/retrospective/2025-12-16-phase3-consistency-validation.md`
- Skills Memory: `phase3-consistency-skills.md`
- Issue: #44 Phase 3 (P3-1, P3-2)

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-cross-reference-verification](validation-007-cross-reference-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
