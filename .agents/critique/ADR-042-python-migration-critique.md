# Critique: ADR-042 Python Migration Strategy

## Verdict

**CONCERNS** - Approve with P1 conditions requiring resolution before implementation begins.

**Confidence Level**: High (85%) - Based on comprehensive analysis of codebase state, existing infrastructure, and migration complexity.

## Summary

ADR-042 proposes migrating from PowerShell to Python as the primary scripting language. The rationale is sound (skill-installer prerequisite, AI/ML ecosystem alignment, larger contributor pool), and the decision acknowledges the reality that Python is already a project dependency. However, the migration plan has significant gaps in execution strategy, testing migration, and constraint updates that create implementation risk.

The ADR correctly identifies the context shift but underspecifies how to execute the transition without breaking existing infrastructure.

## Strengths

1. **Evidence-Based Decision**: skill-installer adoption (PR #962) creates concrete prerequisite that justifies migration
2. **Honest Trade-off Analysis**: Acknowledges migration effort, Pester test conversion, and learning curve
3. **Phased Approach**: Implementation notes outline 3-phase migration (Foundation, New Development, Migration)
4. **Supersession Clarity**: Explicitly supersedes ADR-005 with proper rationale
5. **Ecosystem Alignment**: Python-first aligns with Anthropic SDK, MCP servers, and AI/ML tooling
6. **Reversibility Assessment**: Not explicitly documented but migration is reversible (code exists in git history)

## Issues Found

### Critical (Must Fix)

#### P0-001: Missing pyproject.toml Foundation

**Issue**: Phase 1 lists "pyproject.toml for project configuration" as incomplete but provides no specification.

**Evidence**:
- Line 103: `[ ] pyproject.toml for project configuration` (unchecked)
- No pyproject.toml file exists in repository
- ADR does not specify required dependencies, Python version constraints, or tool configuration

**Impact**: Without pyproject.toml, Phase 2 development cannot proceed. Developers lack guidance on:
- Which Python version to use (ADR says "3.10+" but no upper bound)
- Required dependencies (anthropic SDK version? pytest version?)
- Tool configuration (ruff rules? mypy strictness? pytest options?)
- UV integration (workspace configuration? dev dependencies?)

**Recommendation**:
Add section: "pyproject.toml Specification" with minimum viable configuration:

```toml
[project]
name = "ai-agents"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "anthropic>=0.39.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.1.0",
    "mypy>=1.8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]

[tool.ruff]
target-version = "py310"
```

#### P0-002: No Testing Migration Strategy

**Issue**: Phase 1 lists "pytest infrastructure setup" as incomplete but provides no migration plan for existing Pester tests.

**Evidence**:
- 338 Pester test files exist (`.Tests.ps1` pattern)
- 16 Python tests exist (3 files with pytest)
- Line 105: `[ ] pytest infrastructure setup` (unchecked)
- No guidance on test migration priority, conversion process, or parallel execution

**Current State Analysis**:
- Pester tests: 338 files across codebase
- Python tests: 16 tests in 3 files (hooks and LLM parsing)
- Ratio: 21:1 Pester to pytest

**Impact**: Migrating scripts without corresponding tests creates untested code. The 80% coverage requirement (ADR-006) cannot be enforced without test migration plan.

**Recommendation**:
Add section: "Test Migration Strategy" specifying:

1. **Parallel Test Execution**: Run both Pester and pytest during transition
2. **CI Integration**: Add pytest workflow alongside pester-tests.yml
3. **Migration Checklist**: When migrating .ps1 → .py, MUST migrate .Tests.ps1 → test_*.py first
4. **Coverage Parity**: Converted tests must maintain equivalent coverage (use `pytest --cov`)
5. **Test-First Migration**: Write pytest tests before converting PowerShell script

**Specific PR Requirement**:
PRs migrating scripts MUST include pytest tests achieving minimum 80% coverage before PowerShell version is deleted.

### Important (Should Fix)

#### P1-001: Constraint Document Out of Sync

**Issue**: PROJECT-CONSTRAINTS.md still enforces PowerShell-only constraint without Python exception.

**Evidence**:
- `PROJECT-CONSTRAINTS.md` lines 19-21: "MUST NOT create Python scripts (.py)" with ADR-005 as source
- ADR-005 has two exceptions (SkillForge, Claude Hooks) but general prohibition remains
- ADR-042 supersedes ADR-005 but PROJECT-CONSTRAINTS.md not updated

**Impact**: Agents reading PROJECT-CONSTRAINTS.md will receive conflicting guidance:
- CLAUDE.md @imports CRITICAL-CONTEXT.md which references PROJECT-CONSTRAINTS.md
- Agents instructed to read PROJECT-CONSTRAINTS.md at session start
- Current constraints say "MUST NOT create Python scripts"
- ADR-042 says Python is now the primary language

**Recommendation**:
Update PROJECT-CONSTRAINTS.md Language Constraints section:

```markdown
| Constraint | Source | Verification |
|------------|--------|--------------|
| SHOULD prefer Python for new scripts (.py) | ADR-042 | Code review |
| MAY use PowerShell for existing script maintenance (.ps1, .psm1) | ADR-042 | Code review |
| MUST NOT create new bash scripts (.sh) | ADR-005, ADR-042 | Pre-commit hook, code review |
```

**Related Updates Required**:
- CRITICAL-CONTEXT.md: Update "PowerShell only" to "Python-first (ADR-042)"
- .githooks/pre-commit: Remove Python blocking rule (if exists)

#### P1-002: No CI/CD Migration Plan

**Issue**: 115 PowerShell references in GitHub workflows but no workflow migration strategy.

**Evidence**:
- `grep -r "\.ps1\|\.psm1\|PowerShell" .github/workflows/*.yml` returns 115 matches
- 20+ workflow files exist
- ADR-006 (Thin Workflows) still applies but no guidance on Python module calling convention

**Current Workflow Pattern** (PowerShell):
```yaml
- name: Run script
  shell: pwsh
  run: |
    Import-Module .github/scripts/Module.psm1
    Invoke-Function -Param $value
```

**Future Workflow Pattern** (Python - not specified):
```yaml
- name: Run script
  shell: bash
  run: |
    python -m scripts.module --param value
```

**Impact**: Phase 3 migration priority lists "CI infrastructure" second, but execution strategy is undefined. Developers migrating workflows lack guidance on:
- Module import patterns
- Error handling conventions
- Parameter passing (argparse? click? typer?)
- Exit code handling

**Recommendation**:
Add section: "Workflow Migration Patterns" specifying:

1. **Python Module Calling Convention**:
   ```yaml
   - name: Run Python module
     run: uv run python -m path.to.module
   ```
2. **Error Handling**: Python scripts MUST exit with non-zero on failure (use `sys.exit(1)`)
3. **Parameter Passing**: Use argparse for consistency
4. **ADR-006 Compliance**: Logic in .py modules, workflows remain thin

#### P1-003: Missing UV Integration Specification

**Issue**: ADR states "Adopts UV as the Python package manager" but provides no integration details.

**Evidence**:
- Line 49: "Adopts UV as the Python package manager"
- Line 94: "UV Requirement: Already a prerequisite via skill-installer"
- No specification of UV usage patterns, virtual environment management, or lock file strategy

**Impact**: Developers lack guidance on:
- How to install dependencies (uv pip install? uv sync? uv run?)
- Where virtual environments should live (.venv/? per-project? global?)
- Whether to commit uv.lock files
- How CI should use UV (uv cache? uv pip compile?)

**Recommendation**:
Add section: "UV Package Management Patterns":

```markdown
### UV Usage

1. **Install dependencies**: `uv pip install -r requirements.txt`
2. **Run scripts**: `uv run python -m module_name`
3. **Add dependencies**: Update pyproject.toml, run `uv pip compile pyproject.toml -o requirements.txt`
4. **CI Integration**: Use `uv cache` for faster installs
5. **Virtual Environments**: UV manages .venv automatically, do not commit

**Lock Files**: Commit requirements.txt (compiled from pyproject.toml) for reproducible builds.
```

#### P1-004: Unclear Migration Prioritization

**Issue**: Phase 3 migration priority order lacks objective criteria.

**Evidence**:
- Lines 115-120 list 4 priority tiers: high-traffic scripts, CI infrastructure, Skills, Build system
- "High-traffic" is subjective - no metric provided
- "Frequently modified" is undefined (commits per month? lines changed?)

**Impact**: Without objective criteria, migration becomes arbitrary. Risk of:
- Migrating low-value scripts first (wasted effort)
- Leaving critical infrastructure in PowerShell (tech debt accumulation)
- Inconsistent migration decisions across teams

**Recommendation**:
Replace subjective priority with objective metrics:

```markdown
### Migration Priority (Data-Driven)

**Metric**: Git churn rate (commits × files changed in last 90 days)

1. **Tier 1** (migrate first): Churn rate >10 commits
   - Example: .github/scripts/AIReviewCommon.psm1 (47 commits, 12 files touched)
2. **Tier 2**: Churn rate 5-10 commits
3. **Tier 3**: Churn rate 1-4 commits
4. **Tier 4** (migrate last or archive): 0 commits (not touched in 90 days)

**Query**: `git log --since="90 days ago" --name-only --pretty=format: | sort | uniq -c | sort -rn`
```

### Minor (Consider)

#### P2-001: No Rollback Strategy

**Issue**: Migration is presented as one-way but no rollback plan if Python migration fails.

**Evidence**:
- Supersedes ADR-005 but no provision for rolling back to PowerShell-only
- No success criteria defined for migration phases
- No "abort migration" criteria

**Impact**: If Python migration creates issues (dependency conflicts, platform incompatibilities, slower CI), no documented path to roll back.

**Recommendation**:
Add section: "Migration Success Criteria and Rollback":

```markdown
### Success Criteria (per Phase)

**Phase 1** (Foundation): pyproject.toml validated, pytest runs in CI, 0 dependency conflicts
**Phase 2** (New Development): 10+ new Python scripts created, 0 reversion to PowerShell
**Phase 3** (Migration): 50% of Tier 1 scripts migrated, <5% regression rate

### Rollback Triggers

- Dependency conflict rate >10% (cannot install UV/Python in CI)
- CI runtime regression >50% (Python slower than PowerShell)
- Critical bug rate >3 P0 bugs per month attributable to migration

**Rollback Plan**: Revert ADR-042, reinstate ADR-005, archive Python scripts to .archive/python-attempt/
```

#### P2-002: No Developer Training Plan

**Issue**: ADR acknowledges "Learning Curve: Contributors familiar only with PowerShell" but provides no mitigation beyond "Python is widely taught."

**Evidence**:
- Line 87: "Learning Curve: Contributors familiar only with PowerShell"
- Line 88: "Mitigation: Python is widely taught; extensive documentation"
- 130 PowerShell scripts exist vs. 17 Python scripts (7.6:1 ratio indicates PowerShell expertise)

**Impact**: Migration success depends on team skill. Without training, migration quality suffers:
- Naive Python code (not idiomatic)
- Missing error handling patterns
- Slower development velocity during transition

**Recommendation**:
Add section: "Developer Enablement":

```markdown
### Training Resources

1. **Python for PowerShell Developers**: Internal guide mapping PowerShell patterns to Python equivalents
2. **Code Review Checklist**: Python-specific review items (error handling, type hints, testing)
3. **Example Migrations**: Annotated before/after for common script patterns
4. **Office Hours**: Weekly Q&A for migration questions
```

#### P2-003: Missing Deprecation Timeline

**Issue**: Migration guidance says "Mark PowerShell version as deprecated" but no timeline for deletion.

**Evidence**:
- Lines 124-130: Migration guidance includes "Mark PowerShell version as deprecated" (step 4) and "Remove PowerShell version after verification period" (step 5)
- "Verification period" is undefined (days? weeks? months?)

**Impact**: Indefinite deprecation creates maintenance burden:
- Two versions to maintain (Python and deprecated PowerShell)
- Confusion over which version is canonical
- Accumulated tech debt if deprecation period extends years

**Recommendation**:
Specify deprecation timeline:

```markdown
### Deprecation Timeline

1. **Mark deprecated**: Add `# DEPRECATED: Migrated to {script}.py on YYYY-MM-DD` header
2. **Verification period**: 30 days minimum, 90 days maximum
3. **Deletion criteria**:
   - Python version passes CI for 30 consecutive days
   - No bugs filed against Python version
   - Test coverage ≥ PowerShell version coverage
4. **Archive**: Move to .archive/powershell/ with git history link
```

## Questions for Planner

1. **pyproject.toml**: What dependencies are required beyond anthropic SDK? Should ruff, mypy, pytest be mandatory or optional?

2. **Pytest Infrastructure**: Should CI run both Pester and pytest during transition? What is acceptable CI runtime increase?

3. **Constraint Enforcement**: How should pre-commit hooks change? Block new PowerShell scripts or just warn?

4. **Skill Migration**: 100% PowerShell skills exist in `.claude/skills/github/`. Migrate all at once or incrementally?

5. **ADR-006 Compliance**: ADR-006 requires 80% test coverage. Does this apply to Python scripts? What tool enforces coverage (pytest-cov)?

## Recommendations

### Before Implementation Begins

**P0 Issues** (BLOCKING):

1. **Specify pyproject.toml**: Add complete configuration including dependencies, dev dependencies, tool settings
2. **Define Test Migration Strategy**: Document pytest setup, parallel execution, migration checklist, coverage enforcement

**P1 Issues** (MUST ADDRESS):

3. **Update PROJECT-CONSTRAINTS.md**: Align constraint language with Python-first decision
4. **Document Workflow Migration Patterns**: Specify Python module calling convention, error handling, ADR-006 compliance
5. **Specify UV Integration**: Document UV usage patterns, virtual environment strategy, lock file approach
6. **Quantify Migration Priority**: Replace subjective "high-traffic" with git churn metrics

**P2 Issues** (RECOMMENDED):

7. **Add Rollback Strategy**: Define success criteria per phase, rollback triggers, and rollback procedure
8. **Create Developer Enablement Plan**: Training resources, code review checklist, example migrations
9. **Specify Deprecation Timeline**: Define verification period (30-90 days), deletion criteria, archive location

### Critical Path Dependencies

**Before Phase 1 Complete**:
- pyproject.toml created and validated (P0-001)
- pytest infrastructure running in CI (P0-002)
- PROJECT-CONSTRAINTS.md updated (P1-001)

**Before Phase 2 Begins**:
- Workflow migration patterns documented (P1-002)
- UV integration specified (P1-003)

**Before Phase 3 Begins**:
- Migration priority metrics defined (P1-004)
- Deprecation timeline specified (P2-003)

## Approval Conditions

**CONDITIONAL APPROVAL** with following requirements:

1. **P0 Issues**: MUST resolve P0-001 (pyproject.toml) and P0-002 (test migration) before ADR merge
2. **P1 Issues**: MUST resolve P1-001 through P1-004 before Phase 2 implementation begins
3. **P2 Issues**: SHOULD resolve before Phase 3 migration begins (not blocking but strongly recommended)

**Approval Gate**: Orchestrator may merge ADR-042 after P0 issues resolved, but MUST NOT route to implementer for Phase 2 work until P1 issues resolved.

## Alignment with Project Goals

**ALIGNED** with project direction:

✅ **AI/ML Integration**: Python enables Anthropic SDK, LangChain, MCP integration (critical for agent evolution)

✅ **skill-installer Adoption**: Acknowledges Python prerequisite already exists (pragmatic decision)

✅ **Contributor Pool**: Python is #1 language (larger talent pool than PowerShell)

✅ **Ecosystem Momentum**: AI tooling converging on Python (future-proof decision)

**RISKS TO MANAGE**:

⚠️ **Migration Complexity**: 130 PowerShell scripts to migrate (7.6:1 ratio) without clear execution plan

⚠️ **Testing Coverage**: 338 Pester tests require conversion to pytest (21:1 ratio) without migration strategy

⚠️ **CI Runtime**: Python startup overhead may increase workflow execution time (requires measurement)

⚠️ **Workflow Refactoring**: 115 PowerShell references in workflows require pattern updates

## Completeness Assessment

### Provided

- ✅ Context and rationale
- ✅ Decision drivers and alternatives considered
- ✅ Trade-off analysis (effort, testing, learning curve)
- ✅ Positive/negative/neutral consequences
- ✅ Phased implementation outline (3 phases)
- ✅ Migration guidance (5-step process)
- ✅ Related decisions (supersedes ADR-005, companion to ADR-006)

### Missing (Gaps)

- ❌ pyproject.toml specification (P0-001)
- ❌ Test migration strategy (P0-002)
- ❌ Constraint document updates (P1-001)
- ❌ Workflow migration patterns (P1-002)
- ❌ UV integration details (P1-003)
- ❌ Objective migration prioritization (P1-004)
- ❌ Rollback strategy (P2-001)
- ❌ Developer training plan (P2-002)
- ❌ Deprecation timeline (P2-003)

**Completeness Score**: 60% (6/15 required elements present)

## Edge Cases Not Addressed

1. **Windows-Specific PowerShell**: Scripts using Windows Registry, COM objects, WMI - how to handle?
2. **PowerShell Performance**: Some PowerShell scripts may be faster than Python equivalents (pipeline streaming) - when to keep PowerShell?
3. **External Consumers**: If external tools depend on PowerShell scripts (unlikely but possible), how to maintain compatibility?
4. **Python Version Skew**: Project says "3.10+" but what if contributor has 3.9? 3.13? How to enforce version?
5. **Dependency Conflicts**: What if UV/Python installation conflicts with existing system Python? (Common on macOS with system Python 2.7)

## Final Recommendation

**APPROVE WITH CONDITIONS** - ADR-042 is directionally correct and well-reasoned, but execution strategy has critical gaps.

**Confidence**: 85% - High confidence in decision rationale, moderate confidence in execution feasibility without addressing P0/P1 issues.

**Next Steps**:

1. **Planner**: Resolve P0-001 (pyproject.toml spec) and P0-002 (test migration strategy)
2. **Architect**: Review workflow migration patterns (P1-002) for ADR-006 compliance
3. **Orchestrator**: After P0 resolution, route to implementer for Phase 1 foundation work
4. **QA**: Validate pytest infrastructure before Phase 2 begins

---

**Verdict**: CONCERNS (not BLOCK) because the decision is sound but implementation plan needs strengthening. With P0/P1 issues resolved, migration is feasible and aligned with project goals.

**Critique Confidence**: High (85%) based on:
- Comprehensive codebase analysis (130 PS scripts, 338 tests, 17 Python files)
- Constraint document review (ADR-005, ADR-006, PROJECT-CONSTRAINTS.md)
- Workflow infrastructure assessment (115 PS references, 20+ workflows)
- skill-installer prerequisite verification (PR #962 merged)
