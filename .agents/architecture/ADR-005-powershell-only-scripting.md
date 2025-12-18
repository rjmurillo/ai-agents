# ADR-005: PowerShell-Only Scripting Standard

**Status**: Accepted
**Date**: 2025-12-18
**Deciders**: User, Orchestrator Agent, Implementer Agent
**Context**: PR #60 AI workflow implementation

---

## Context and Problem Statement

During PR #60 implementation, agents repeatedly generated bash and Python scripts despite:
1. PowerShell being the established project standard
2. All existing infrastructure using PowerShell (install scripts, test runner, modules)
3. Pester tests providing mature testing framework for PowerShell
4. Windows-first development environment

This resulted in:
- **Token waste**: Generating bash/Python code that was later replaced with PowerShell
- **Inconsistent tooling**: Mix of bash, Python, and PowerShell across codebase
- **Testing fragmentation**: Pester tests for PowerShell, bats/pytest for bash/Python
- **Time waste**: Agents "give up" on bash/Python and re-implement in PowerShell anyway

**Key Question**: Should agents be allowed to generate bash or Python scripts in this repository?

---

## Decision Drivers

1. **Existing Infrastructure**: 100% of build, install, and test scripts are PowerShell
2. **Testing Maturity**: Pester provides excellent testing for PowerShell; bats/pytest add complexity
3. **Developer Experience**: Primary development environment is Windows with PowerShell
4. **Cross-Platform**: PowerShell Core (pwsh) runs on Linux, macOS, and Windows
5. **Token Efficiency**: Avoiding bash/Python generation saves tokens
6. **Consistency**: Single scripting language reduces cognitive load
7. **Agent Behavior**: Agents eventually implement in PowerShell after trying bash/Python

---

## Considered Options

### Option 1: PowerShell-Only (CHOSEN)

**All scripts must be PowerShell (.ps1, .psm1)**

**Pros**:
- ✅ Consistent with existing infrastructure (100% PowerShell)
- ✅ Single testing framework (Pester)
- ✅ Cross-platform (PowerShell Core)
- ✅ Agents don't waste tokens on bash/Python attempts
- ✅ Windows-native, excellent tooling
- ✅ Type safety, object pipelines, structured error handling

**Cons**:
- ❌ Less familiar to Linux-first developers
- ❌ Slightly more verbose than bash for simple tasks
- ❌ Requires `pwsh` on Linux/macOS (but already required by project)

### Option 2: Bash-First with PowerShell Fallback

**Use bash for simple scripts, PowerShell for complex logic**

**Pros**:
- ✅ Bash familiar to Linux developers
- ✅ Shorter syntax for one-liners

**Cons**:
- ❌ Fragments testing across bats and Pester
- ❌ Adds cognitive overhead (which language for what?)
- ❌ Agents waste tokens trying bash first
- ❌ "Simple" scripts often become complex over time
- ❌ Inconsistent with existing 100% PowerShell infrastructure

### Option 3: Python for Complex Logic

**Use Python for data processing, PowerShell for automation**

**Pros**:
- ✅ Python excellent for data processing
- ✅ Rich ecosystem (pandas, numpy)

**Cons**:
- ❌ Requires Python runtime (not currently a project dependency)
- ❌ Fragments testing across pytest and Pester
- ❌ PowerShell handles data processing adequately for our use cases
- ❌ Adds another language to maintain
- ❌ Agents waste tokens trying Python first

### Option 4: Best Tool for the Job

**Allow any language based on task requirements**

**Pros**:
- ✅ Maximum flexibility

**Cons**:
- ❌ Maximum inconsistency
- ❌ Maximum testing fragmentation
- ❌ Maximum token waste (agents try multiple approaches)
- ❌ No clear guidance for agents
- ❌ Maintenance nightmare (3+ languages to maintain)

---

## Decision Outcome

**Chosen option: Option 1 - PowerShell-Only**

### Rationale

1. **Existing Infrastructure**: Project already standardized on PowerShell (install scripts, test runner, build scripts all use .ps1)

2. **Token Efficiency**: During PR #60, agents generated:
   - 329 lines of bash (`.github/scripts/ai-review-common.sh`) - DELETED
   - 501 lines of bats tests - DELETED
   - Re-implemented as 300 lines of PowerShell (`.github/scripts/AIReviewCommon.psm1`) with Pester tests
   - **Wasted**: ~830 lines of bash code and tokens generating it

3. **Agent Behavior**: Agents "give up" on bash/Python and re-implement in PowerShell without issue, proving PowerShell is sufficient

4. **Testing Maturity**: Pester is mature, well-documented, and integrated into CI

5. **Cross-Platform**: PowerShell Core runs everywhere this project needs to run

### Enforcement

1. **Agent Memory**: `.serena/memories/user-preference-no-bash-python.md` documents preference
2. **This ADR**: Canonical reference for architecture decision
3. **Code Review**: Reject PRs with bash (.sh) or Python (.py) scripts
4. **Agent Prompts**: Update agent instructions to prefer PowerShell

### Exceptions

**NONE**. All scripts must be PowerShell.

If a task genuinely cannot be done in PowerShell:
1. Document why PowerShell is insufficient
2. Get explicit approval before using another language
3. Expect heavy scrutiny (PowerShell is Turing-complete; almost nothing is impossible)

---

## Consequences

### Positive

1. **Consistency**: Single scripting language across entire codebase
2. **Testing**: Single test framework (Pester) with consistent patterns
3. **Token Efficiency**: Agents don't waste tokens on bash/Python attempts
4. **Developer Experience**: Predictable tooling, no "which language for this?" decisions
5. **Maintenance**: Fewer languages to maintain, update, and secure
6. **CI Simplicity**: No need to install Python, bash utilities, etc.

### Negative

1. **Learning Curve**: Developers unfamiliar with PowerShell must learn it
   - **Mitigation**: PowerShell is readable; abundant documentation; similar to Python/bash
2. **Verbosity**: PowerShell more verbose than bash one-liners
   - **Mitigation**: Verbosity improves readability and maintainability
3. **Linux Developers**: May prefer bash
   - **Mitigation**: PowerShell Core is cross-platform; works identically on Linux

### Neutral

1. **Existing bash in GitHub Actions**: GitHub Actions workflow syntax uses bash-like shell commands
   - **Clarification**: This ADR applies to **script files**, not YAML `run:` blocks
   - Workflow `run:` blocks should be kept minimal (see ADR-006: Thin Workflows)
   - Complex logic should be extracted to PowerShell modules

---

## Related Decisions

- **ADR-006**: Thin Workflows, Testable Modules (companion to this ADR)
- **Pattern**: Thin workflows (`.serena/memories/pattern-thin-workflows.md`)
- **User Preference**: No bash/Python (`.serena/memories/user-preference-no-bash-python.md`)

---

## References

- PR #60: 829 lines of bash code generated and then deleted
- `.github/scripts/`: 100% PowerShell modules with Pester tests
- `scripts/`: 100% PowerShell install scripts with Pester tests
- `.claude/skills/github/`: 100% PowerShell skills with tests
- Session log: `.agents/sessions/2025-12-18-session-15-pr-60-response.md`

---

## Validation

Before merging code:
- [ ] No `.sh` files in `.github/scripts/`
- [ ] No `.py` files in `.github/scripts/`
- [ ] All scripts are `.ps1` or `.psm1`
- [ ] All scripts have Pester tests (`.Tests.ps1`)
- [ ] Agents reference this ADR when choosing scripting language

---

**Supersedes**: None (new decision)
**Amended by**: None
