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
analyst -> architect -> planner -> [impact analysis consultations] -> critic -> implementer -> qa -> retrospective

Where impact analysis consultations involve planner coordinating:
- implementer (code impact)
- architect (architecture impact)
- security (security impact)
- devops (CI/CD impact)
- qa (testing impact)
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

The **Multi-Agent Impact Analysis Framework** enables comprehensive planning by having the planner orchestrate specialist consultations before finalization.

### When to Use Impact Analysis

- **Multi-domain changes**: Affects 3+ areas (code, architecture, CI/CD, security, quality)
- **Architecture changes**: Modifies core patterns or introduces new dependencies
- **Security-sensitive changes**: Touches authentication, authorization, data handling
- **Infrastructure changes**: Affects build, deployment, or CI/CD pipelines
- **Breaking changes**: Modifies public APIs or contracts

### Consultation Process

1. **Planner** identifies change scope and affected domains
2. **Planner** invokes specialist agents with structured impact analysis requests
3. **Specialists** analyze impacts in their domain and create impact analysis documents
4. **Planner** aggregates findings and integrates into plan
5. **Critic** reviews the plan including all impact analyses

### Specialist Roles in Impact Analysis

| Specialist | Focus Area | Output Document |
|------------|-----------|-----------------|
| **implementer** | Code structure, patterns, testing complexity | `impact-analysis-[feature]-code.md` |
| **architect** | Design consistency, architectural fit | `impact-analysis-[feature]-architecture.md` |
| **security** | Attack surface, threat vectors, controls | `impact-analysis-[feature]-security.md` |
| **devops** | Build pipelines, deployment, infrastructure | `impact-analysis-[feature]-devops.md` |
| **qa** | Test strategy, coverage, quality risks | `impact-analysis-[feature]-qa.md` |

### Example Workflow

```text
User: "Plan implementation of OAuth 2.0 authentication"

1. planner analyzes scope → multi-domain change detected
2. planner invokes impact analysis consultations:
   - Task(subagent_type="implementer", prompt="Impact analysis for OAuth implementation")
   - Task(subagent_type="architect", prompt="Architecture impact analysis for OAuth")
   - Task(subagent_type="security", prompt="Security impact analysis for OAuth")
   - Task(subagent_type="devops", prompt="DevOps impact analysis for OAuth")
   - Task(subagent_type="qa", prompt="QA impact analysis for OAuth")
3. Each specialist creates impact analysis document in .agents/planning/
4. planner synthesizes findings into comprehensive plan
5. planner routes to critic for validation
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
