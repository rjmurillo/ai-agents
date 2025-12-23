# ADR-017: Script Organization and Usage Patterns

## Status

Accepted

## Date

2025-12-23

## Context

The repository has accumulated multiple types of PowerShell scripts across different locations (`scripts/`, `.github/scripts/`, `build/scripts/`, `.claude/skills/github/scripts/`) without clear organization principles. This creates confusion about:

1. **Where to place new scripts** - No clear guidance on script location based on purpose
2. **When scripts are intended for use** - CI-only vs developer-facing vs internal
3. **How scripts are discovered** - No consistent naming or organization pattern
4. **Script reusability** - Duplication risk when purpose boundaries are unclear

This came to a head with `New-ValidatedPR.ps1` where the question arose: "It's unclear to me when we'd use this. Only for CI it looks like?"

## Decision

Establish a hierarchical script organization based on **intended audience and execution context**:

### 1. Repository Root: `scripts/`

**Purpose**: Developer-facing utilities and validation scripts

**Intended Audience**: Developers, AI agents (local execution)

**Naming Convention**: `Verb-Noun.ps1` (PowerShell approved verbs)

**Categories**:
- **Validation scripts**: `Validate-*.ps1` - Protocol, consistency, session end validation
- **Detection scripts**: `Detect-*.ps1` - Skill violations, test coverage gaps
- **Utility scripts**: `New-*.ps1`, `Invoke-*.ps1` - PR creation, batch operations
- **Installation scripts**: `install*.ps1`, `Sync-*.ps1` - Environment setup

**Examples**:
- `scripts/New-ValidatedPR.ps1` - Developer wrapper for validated PR creation
- `scripts/Validate-SessionEnd.ps1` - Called by pre-commit hook and developers
- `scripts/Detect-SkillViolation.ps1` - Pre-commit hook and manual checks

### 2. GitHub Actions: `.github/scripts/`

**Purpose**: CI/CD-specific automation and workflow support

**Intended Audience**: GitHub Actions workflows (automated execution only)

**Naming Convention**: `ModuleName.psm1` for shared modules, descriptive names for scripts

**Categories**:
- **Workflow modules**: `AIReviewCommon.psm1`, `PRMaintenanceModule.psm1`
- **CI helpers**: Scripts that set GitHub outputs, parse workflow data
- **Report generators**: Scripts that format CI results for PR comments

**Examples**:
- `.github/scripts/AIReviewCommon.psm1` - Shared functions for AI review workflows
- `.github/scripts/PRMaintenanceModule.psm1` - PR automation functions

**Key Distinction**: These scripts assume GitHub Actions environment variables and should NOT be called directly by developers.

### 3. Build System: `build/scripts/`

**Purpose**: Build, test, and release automation

**Intended Audience**: CI and local build processes

**Examples**:
- `build/scripts/Validate-PlanningArtifacts.ps1` - Build-time validation

### 4. Skills: `.claude/skills/github/scripts/`

**Purpose**: Reusable GitHub API interaction patterns

**Intended Audience**: AI agents (via skill system), developers (when wrapped)

**Organization**: Grouped by resource type (`pr/`, `issue/`, `reactions/`)

**Examples**:
- `.claude/skills/github/scripts/pr/New-PR.ps1` - Core PR creation logic
- `.claude/skills/github/scripts/issue/Post-IssueComment.ps1` - Comment posting

**Key Distinction**: Skills are implementation details. Developers use wrappers in `scripts/`.

### 5. Tests: `tests/`

**Purpose**: Pester test files

**Naming Convention**: `ScriptName.Tests.ps1` matching the script under test

**Location**: Root-level `tests/` directory, NOT `scripts/tests/`

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Flat structure in `scripts/` | Simple, all in one place | Doesn't scale, hard to find scripts | No distinction between audiences |
| Purpose-based folders (`scripts/validation/`, `scripts/utils/`) | Clear categorization | Deep nesting, harder to discover | Verb-Noun naming already provides categorization |
| Context prefixes (`CI-*.ps1`, `Dev-*.ps1`) | Explicit in filename | Breaks PowerShell conventions | Violates approved verb list |
| Everything in skills | Consistent location | Conflates developer tools with internal implementation | Skills are meant for AI agent reuse, not primary developer interface |

### Trade-offs

**Chosen Approach Benefits**:
- Clear audience separation (developer vs CI vs agent)
- PowerShell naming conventions maintained
- Easy to determine script placement for new scripts
- Prevents duplication across contexts

**Chosen Approach Costs**:
- Requires documentation to understand hierarchy
- Some scripts may span multiple contexts (solved via wrappers)
- Migration needed for existing misplaced scripts

## Consequences

### Positive

- **Clear placement rules** for new scripts based on intended audience
- **Reduced duplication** through clear separation of concerns
- **Better discoverability** through consistent organization
- **Improved testing** with all tests in `tests/` directory
- **Documentation-friendly** - easy to explain in README

### Negative

- **Migration effort** for existing scripts (low priority, done incrementally)
- **Need to document** this pattern for contributors
- **Wrapper overhead** when skills need developer-facing interface

### Neutral

- **Naming conventions** already mostly aligned with this pattern
- **Test organization** moved from `scripts/tests/` to `tests/` (completed in this PR)

## Implementation Notes

### Immediate Actions

1. ✅ Move test files from `scripts/tests/` to `tests/` (completed)
2. ✅ Document `New-ValidatedPR.ps1` as developer-facing wrapper
3. ⏳ Update `scripts/README.md` with organization principles

### Script Categorization

**Developer-facing wrappers** (`scripts/`):
- `New-ValidatedPR.ps1` - Wraps skill, adds CLI conveniences
- `Validate-SessionEnd.ps1` - Called by pre-commit and developers
- `Detect-*.ps1` - Pre-commit hooks and manual validation

**CI-only scripts** (`.github/scripts/`):
- Modules: `AIReviewCommon.psm1`, `PRMaintenanceModule.psm1`
- No direct developer invocation expected

**Skills** (`.claude/skills/github/scripts/`):
- Implementation details for AI agents
- May be called by wrappers in `scripts/`

### Documentation Updates

Update `scripts/README.md` with:
```markdown
## Script Organization

Scripts are organized by intended audience:

- **scripts/** - Developer-facing utilities (manual + pre-commit)
- **.github/scripts/** - CI/CD automation (GitHub Actions only)
- **build/scripts/** - Build system automation
- **.claude/skills/** - AI agent skills (wrapped for developer use)
- **tests/** - Pester test files

See [ADR-017](../.agents/architecture/ADR-017-script-organization.md) for details.
```

## Related ADRs

- ADR-004: Pre-commit Hook Architecture - Defines hook script requirements
- ADR-005: PowerShell-Only Scripting - Establishes PowerShell as standard
- ADR-006: Thin Workflows, Testable Modules - Separates workflow and implementation

## References

- [PowerShell Approved Verbs](https://learn.microsoft.com/en-us/powershell/scripting/developer/cmdlet/approved-verbs-for-windows-powershell-commands)
- Issue #230: Technical Guardrails (motivation for clarifying organization)
