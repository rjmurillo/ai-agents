# Claude Code Agent Instructions

This file provides instructions for Claude Code when using the agent system.

## Agent System Overview

This repository provides a coordinated multi-agent system for software development. Specialized agents handle different responsibilities with explicit handoff protocols and persistent memory using `cloudmcp-manager`.

## Agent Catalog

| Agent | Purpose | When to Use |
|-------|---------|-------------|
| **orchestrator** | Task coordination | Complex multi-step tasks |
| **implementer** | Production code, .NET patterns | Writing/reviewing C# code |
| **analyst** | Research, root cause analysis, feature review | Investigating issues, evaluating requests |
| **architect** | ADRs, design governance | Technical decisions |
| **planner** | Milestones, work packages | Breaking down epics |
| **critic** | Plan validation | Before implementation |
| **qa** | Test strategy, verification | After implementation |
| **explainer** | PRDs, feature docs | Documenting features |
| **task-generator** | Atomic task breakdown | After PRD created |
| **high-level-advisor** | Strategic decisions | Major direction choices |
| **independent-thinker** | Challenge assumptions | Getting unfiltered feedback |
| **memory** | Cross-session context | Retrieving/storing knowledge |
| **skillbook** | Skill management | Managing learned strategies |
| **retrospective** | Learning extraction | After task completion |
| **devops** | CI/CD pipelines | Build automation, deployment |
| **roadmap** | Strategic vision | Epic definition, prioritization |
| **security** | Vulnerability assessment | Threat modeling, secure coding |
| **pr-comment-responder** | PR review handler | Addressing bot/human review comments |

## Standard Workflows

**Feature Development:**

```text
analyst -> architect -> planner -> critic -> implementer -> qa -> retrospective
```

**Feature Development with Impact Analysis:**

```text
Orchestrator manages the full workflow:

Orchestrator → analyst → returns to Orchestrator
Orchestrator → architect → returns to Orchestrator
Orchestrator → planner (creates impact analysis plan) → returns to Orchestrator

Orchestrator executes impact analysis consultations:
  → implementer (code impact) → returns to Orchestrator
  → architect (design impact) → returns to Orchestrator
  → security (security impact) → returns to Orchestrator
  → devops (CI/CD impact) → returns to Orchestrator
  → qa (testing impact) → returns to Orchestrator

Orchestrator aggregates findings and continues:
  → critic → returns to Orchestrator
  → implementer → returns to Orchestrator
  → qa → returns to Orchestrator
  → retrospective → complete
```

**Quick Fix:**

```text
implementer -> qa
```

**Strategic Decision:**

```text
independent-thinker -> high-level-advisor -> task-generator
```

## Impact Analysis Framework

The **Multi-Agent Impact Analysis Framework** enables comprehensive planning through orchestrator-managed specialist consultations.

**CRITICAL**: Orchestrator is the ROOT agent. Subagents (including planner) cannot delegate to other subagents. When multi-domain analysis is needed, planner creates the analysis plan and orchestrator executes the consultations.

### When to Use Impact Analysis

- **Multi-domain changes**: Affects 3+ areas (code, architecture, CI/CD, security, quality)
- **Architecture changes**: Modifies core patterns or introduces new dependencies
- **Security-sensitive changes**: Touches authentication, authorization, data handling
- **Infrastructure changes**: Affects build, deployment, or CI/CD pipelines
- **Breaking changes**: Modifies public APIs or contracts

### Consultation Process

1. **Orchestrator** routes to planner with impact analysis flag
2. **Planner** creates structured impact analysis plan identifying domains and questions
3. **Planner** returns plan to orchestrator
4. **Orchestrator** invokes specialist agents (one at a time):
   - Orchestrator → implementer (code impact) → returns to Orchestrator
   - Orchestrator → architect (design impact) → returns to Orchestrator
   - Orchestrator → security (security impact) → returns to Orchestrator
   - Orchestrator → devops (operations impact) → returns to Orchestrator
   - Orchestrator → qa (quality impact) → returns to Orchestrator
5. **Orchestrator** aggregates findings and routes to critic for validation

### Specialist Roles in Impact Analysis

| Specialist | Focus Area | Output Document |
|------------|-----------|-----------------|
| **implementer** | Code structure, patterns, testing complexity | `impact-analysis-code-[feature].md` |
| **architect** | Design consistency, architectural fit | `impact-analysis-architecture-[feature].md` |
| **security** | Attack surface, threat vectors, controls | `impact-analysis-security-[feature].md` |
| **devops** | Build pipelines, deployment, infrastructure | `impact-analysis-devops-[feature].md` |
| **qa** | Test strategy, coverage, quality risks | `impact-analysis-qa-[feature].md` |

### Example Workflow

```text
User: "Plan implementation of OAuth 2.0 authentication"

1. Orchestrator routes to planner → planner analyzes scope → multi-domain change detected
2. Planner creates impact analysis plan, returns to orchestrator
3. Orchestrator invokes each specialist in sequence:
   - Orchestrator → implementer ("Impact analysis for OAuth implementation") → returns
   - Orchestrator → architect ("Architecture impact analysis for OAuth") → returns
   - Orchestrator → security ("Security impact analysis for OAuth") → returns
   - Orchestrator → devops ("DevOps impact analysis for OAuth") → returns
   - Orchestrator → qa ("QA impact analysis for OAuth") → returns
4. Each specialist creates impact analysis document in .agents/planning/
5. Orchestrator aggregates findings and routes to critic for validation
```

## Invocation Examples

```python
# Research before implementation
Task(subagent_type="analyst", prompt="Investigate why X fails")

# Design review before coding
Task(subagent_type="architect", prompt="Review design for feature X")

# Implementation
Task(subagent_type="implementer", prompt="Implement feature X per plan")

# Plan validation (required before implementation)
Task(subagent_type="critic", prompt="Validate plan at .agents/planning/...")

# Code review after writing
Task(subagent_type="architect", prompt="Review code quality")
Task(subagent_type="implementer", prompt="Review implementation")

# Extract learnings
Task(subagent_type="retrospective", prompt="Analyze what we learned")
```

## Memory Protocol

All agents use `cloudmcp-manager` for cross-session memory:

```python
# Search for context
mcp__cloudmcp-manager__memory-search_nodes(query="[topic]")

# Store learnings
mcp__cloudmcp-manager__memory-add_observations(...)
mcp__cloudmcp-manager__memory-create_entities(...)
```

## Skill Citation

When applying learned strategies, cite skills:

```markdown
**Applying**: Skill-Build-001
**Strategy**: Use /m:1 /nodeReuse:false for CI builds
**Expected**: Avoid file locking errors

[Execute...]

**Result**: Build succeeded
**Skill Validated**: Yes
```

## Output Directories

Agents save artifacts to `.agents/`:

- `analysis/` - Analyst findings
- `architecture/` - ADRs
- `planning/` - Plans and PRDs
- `critique/` - Plan reviews
- `qa/` - Test strategies and reports
- `retrospective/` - Learning extractions

## Best Practices

1. **Memory First**: Retrieve context before multi-step reasoning
2. **Document Outputs**: Save artifacts to appropriate directories
3. **Clear Handoffs**: Announce next agent and purpose
4. **Store Learnings**: Update memory at milestones
5. **Test Everything**: No skipping hard tests
6. **Commit Atomically**: Small, conventional commits

## Testing

### Running Pester Tests

PowerShell unit tests for installation scripts are located in `scripts/tests/`. Run them using the reusable test runner:

```powershell
# Local development (detailed output, continues on failure)
pwsh ./build/scripts/Invoke-PesterTests.ps1

# CI mode (exits with error code on failure)
pwsh ./build/scripts/Invoke-PesterTests.ps1 -CI

# Run specific test file
pwsh ./build/scripts/Invoke-PesterTests.ps1 -TestPath "./scripts/tests/Install-Common.Tests.ps1"

# Maximum verbosity for debugging
pwsh ./build/scripts/Invoke-PesterTests.ps1 -Verbosity Diagnostic
```

**Test Coverage:**

- `Install-Common.Tests.ps1` - Tests for all 11 shared module functions
- `Config.Tests.ps1` - Configuration validation tests
- `install.Tests.ps1` - Entry point parameter validation

**Output:**

Test results are saved to `artifacts/pester-results.xml` (gitignored).

**When to Run Tests:**

- Before committing changes to `scripts/`
- After modifying `scripts/lib/Install-Common.psm1` or `scripts/lib/Config.psd1`
- When the `qa` agent validates implementation

## Utilities

### Fix Markdown Fences

When generating or fixing markdown with code blocks, use the fix-markdown-fences utility to repair malformed closing fences automatically.

**Location**: `.agents/utilities/fix-markdown-fences/SKILL.md`

**Problem**: Closing fences should never have language identifiers (e.g., ` ` `text). This utility detects and fixes them:

```markdown
<!-- Wrong -->
` ` `python
def hello():
    pass
` ` `python

<!-- Correct -->
` ` `python
def hello():
    pass
` ` `
```

**Usage**:

```bash
# PowerShell
pwsh .agents/utilities/fix-markdown-fences/fix_fences.ps1

# Python
python .agents/utilities/fix-markdown-fences/fix_fences.py
```

**Benefits**:

- Prevents token waste from repeated fence fixing cycles
- Validates markdown before committing
- Handles edge cases (nested indentation, multiple blocks, unclosed blocks)
- Supports batch processing of multiple files

**Reference**: See `.agents/utilities/fix-markdown-fences/SKILL.md` for implementation details and additional language versions.

- When generating or reviewing code, use codebase-context MCP tools (`mcp__codebase-context__get_team_patterns`, `mcp__codebase-context__search_codebase`) to check team patterns first.
- When cloudmcp-manager memory functions fail, use Serena memory tools as fallback:
  - Primary functions: `memory-add_observations`, `memory-create_entities`, `memory-create_relations`, `memory-delete_entities`, `memory-delete_observations`, `memory-delete_relations`, `memory-open_nodes`, `memory-read_graph`, `memory-search_nodes`
  - Fallback functions: `write_memory`, `read_memory`, `list_memories`, `delete_memory`, `edit_memory`

### Key Learnings from Practice

#### Documentation Standards (Phase 1 Remediation, Dec 2024)

**Path Normalization**: Always use relative paths in documentation to prevent environment contamination.

- Forbidden patterns: `[A-Z]:\` (Windows), `/Users/` (macOS), `/home/` (Linux)
- Use relative paths: `docs/guide.md`, `../architecture/design.md`
- Validation automated via CI

**Two-Phase Security Review**: Security-sensitive changes require both pre-implementation and post-implementation verification.

- Phase 1 (Planning): Threat model, control design
- Phase 2 (Post-Implementation): PIV (Post-Implementation Verification)
- Implementer must flag security-relevant changes during coding

#### Process Improvements

**Validation-Driven Standards**: When establishing new standards:

1. Document the standard with anti-patterns
2. Create validation script with pedagogical error messages
3. Integrate into CI
4. Baseline existing violations separately

**Template-Based Contracts**: Provide both empty templates AND filled examples to reduce ambiguity in agent outputs.

**CI Runner Performance**: Prefer `ubuntu-latest` over `windows-latest` for GitHub Actions (much faster). Use Windows runners only when PowerShell Desktop or Windows-specific features required.
