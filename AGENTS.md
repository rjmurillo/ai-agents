# Using the Agents

## Overview

This repository provides a coordinated multi-agent system for software development, available for **VS Code (GitHub Copilot)**, **GitHub Copilot CLI**, and **Claude Code CLI**. Each agent focuses on a specific phase or concern with clear responsibilities, constraints, and handoffs.

### Typical Workflow

```text
Orchestrator (ROOT agent) coordinates all delegation:

Orchestrator → Analyst → returns to Orchestrator
Orchestrator → Architect → returns to Orchestrator
Orchestrator → Planner → returns to Orchestrator
Orchestrator → Critic → returns to Orchestrator
Orchestrator → Implementer → returns to Orchestrator
Orchestrator → QA → returns to Orchestrator
Orchestrator → Retrospective → complete
```

**Architecture**: Subagents CANNOT delegate to other subagents. They return results to orchestrator, who handles all routing decisions.

The Memory agent provides long-running context across sessions using `cloudmcp-manager` for persistent memory.

---

## Quick Start

### VS Code Installation

**Global (all workspaces):**

```powershell
.\scripts\install-vscode-global.ps1
```

**Per-repository:**

```powershell
.\scripts\install-vscode-repo.ps1 -RepoPath "C:\Path\To\Your\Repo"
```

### GitHub Copilot CLI Installation

**Per-repository (recommended):**

```powershell
.\scripts\install-copilot-cli-repo.ps1 -RepoPath "C:\Path\To\Your\Repo"
```

**Global (known issues - see [Issue #2](https://github.com/rjmurillo/vs-code-agents/issues/2)):**

```powershell
.\scripts\install-copilot-cli-global.ps1
```

> **Note:** User-level agents in `~/.copilot/agents/` are not currently loaded due to [GitHub Issue #452](https://github.com/github/copilot-cli/issues/452). Use per-repository installation.

### Claude Code Installation

**Global (all sessions):**

```powershell
.\scripts\install-claude-global.ps1
```

**Per-repository:**

```powershell
.\scripts\install-claude-repo.ps1 -RepoPath "C:\Path\To\Your\Repo"
```

---

## Directory Structure

```text
.
├── src/                      # Agent source files
│   ├── vs-code-agents/       # VS Code / GitHub Copilot agents
│   │   └── *.agent.md
│   ├── copilot-cli/          # GitHub Copilot CLI agents
│   │   └── *.agent.md
│   └── claude/               # Claude Code CLI agents
│       └── *.md
├── scripts/                  # Installation scripts
│   ├── install-vscode-global.ps1
│   ├── install-vscode-repo.ps1
│   ├── install-copilot-cli-global.ps1
│   ├── install-copilot-cli-repo.ps1
│   ├── install-claude-global.ps1
│   └── install-claude-repo.ps1
├── AGENTS.md                 # Canonical agent instructions (this file)
├── CLAUDE.md                 # Claude Code shim → AGENTS.md
└── .github/copilot-instructions.md  # Copilot shim → AGENTS.md
```

---

## Agent Catalog

### Primary Workflow Agents

| Agent | Role | Best For |
|-------|------|----------|
| **orchestrator** | Task coordination | Complex multi-step tasks |
| **analyst** | Pre-implementation research | Root cause analysis, requirements |
| **architect** | Design governance | ADRs, technical decisions |
| **planner** | Work package creation | Epic breakdown, milestones |
| **implementer** | Code execution | Production code, tests |
| **critic** | Plan validation | Review before implementation |
| **qa** | Test verification | Test strategy, coverage |
| **roadmap** | Strategic vision | Epic definition, prioritization |

### Support Agents

| Agent | Role | Best For |
|-------|------|----------|
| **memory** | Context continuity | Cross-session persistence |
| **skillbook** | Skill management | Learned strategy updates |
| **devops** | CI/CD pipelines | Build automation, deployment |
| **security** | Vulnerability assessment | Threat modeling, secure coding |
| **independent-thinker** | Assumption challenging | Alternative viewpoints |
| **high-level-advisor** | Strategic decisions | Prioritization, unblocking |
| **retrospective** | Reflector/learning | Outcome analysis, skill extraction |
| **explainer** | Documentation | PRDs, technical specs |
| **task-generator** | Task decomposition | Breaking epics into tasks |
| **pr-comment-responder** | PR review handler | Addressing bot/human review comments |

---

## Orchestrator: Task Classification & Domain Identification

The orchestrator uses a formal classification process to properly route tasks to the right agent sequences.

### Task Classification (Step 1)

Every incoming task is classified by type:

| Task Type | Definition | Signal Words |
|-----------|------------|--------------|
| **Feature** | New functionality | "add", "implement", "create" |
| **Bug Fix** | Correcting broken behavior | "fix", "broken", "error" |
| **Refactoring** | Restructuring without behavior change | "refactor", "clean up" |
| **Infrastructure** | Build, CI/CD, deployment | "pipeline", "workflow", "deploy" |
| **Security** | Vulnerability remediation | "vulnerability", "auth", "CVE" |
| **Documentation** | Docs, guides | "document", "explain" |
| **Research** | Investigation, analysis | "investigate", "why does" |
| **Strategic** | Architecture decisions | "architecture", "ADR" |
| **Ideation** | Vague ideas needing validation | URLs, "we should", "what if" |

### Domain Identification (Step 2)

Tasks are analyzed for which domains they affect:

| Domain | Scope |
|--------|-------|
| **Code** | Application source, business logic |
| **Architecture** | System design, patterns, structure |
| **Security** | Auth, data protection, vulnerabilities |
| **Operations** | CI/CD, deployment, infrastructure |
| **Quality** | Testing, coverage, verification |
| **Data** | Schema, migrations, storage |
| **API** | External interfaces, contracts |
| **UX** | User experience, frontend |

### Complexity Determination (Step 3)

| Domain Count | Complexity | Strategy |
|--------------|------------|----------|
| 1 domain | Simple | Single specialist agent |
| 2 domains | Standard | Sequential 2-3 agents |
| 3+ domains | Complex | Full orchestration with impact analysis |

Security, Strategic, and Ideation tasks are always treated as Complex.

---

## Impact Analysis Framework

For complex, multi-domain changes, orchestrator manages impact analysis consultations with specialist agents.

**Architecture Note**: Since subagents cannot delegate, planner creates the analysis plan and orchestrator executes each specialist consultation.

### When to Use Impact Analysis

- **Multi-domain changes**: Affects 3+ areas (code, architecture, CI/CD, security, quality)
- **Architecture changes**: Modifies core patterns or introduces new dependencies
- **Security-sensitive changes**: Touches authentication, authorization, data handling
- **Infrastructure changes**: Affects build, deployment, or CI/CD pipelines
- **Breaking changes**: Modifies public APIs or contracts

### Consultation Process

```text
1. Orchestrator routes to planner with impact analysis flag
2. Planner identifies change scope and affected domains, creates analysis plan
3. Planner returns plan to orchestrator
4. Orchestrator invokes specialist agents (sequentially or in parallel):
   - Orchestrator → implementer: Code impact → returns to Orchestrator
   - Orchestrator → architect: Design impact → returns to Orchestrator
   - Orchestrator → security: Security impact → returns to Orchestrator
   - Orchestrator → devops: Operations impact → returns to Orchestrator
   - Orchestrator → qa: Quality impact → returns to Orchestrator
5. Orchestrator aggregates findings
6. Orchestrator routes to critic for validation
```

### Impact Analysis Outputs

Each specialist creates: `.agents/planning/impact-analysis-[domain]-[feature].md`

---

## Disagree and Commit Protocol

When specialists have conflicting recommendations, the system applies the "Disagree and Commit" principle to avoid endless consensus-seeking.

### Protocol Phases

*Phase 1 - Decision (Dissent Encouraged)*:

- All specialists present their positions with data and rationale
- Disagreements are surfaced explicitly and documented
- Critic synthesizes positions and identifies core conflicts

*Phase 2 - Resolution*:

- If consensus emerges → proceed with agreed approach
- If conflict persists → escalate to high-level-advisor for decision
- High-level-advisor makes the call with documented rationale

*Phase 3 - Commitment (Alignment Required)*:

- Once decision is made, ALL specialists commit to execution
- No passive-aggressive execution or "I told you so" behavior
- Earlier disagreement cannot be used as excuse for poor execution

### Commitment Language

```text
"I disagree with [approach] because [reasons], but I commit to executing
[decided approach] fully. My concerns are documented for retrospective."
```

---

## VS Code Usage

### Invoking Agents

In GitHub Copilot Chat:

```text
@orchestrator Help me implement a new feature
@implementer Fix the bug in UserService.cs
@analyst Investigate why tests are failing
```

### Installation Locations

| Type | Location |
|------|----------|
| Global | `%APPDATA%\Code\User\prompts\` (Windows) |
| Global | `~/.config/Code/User/prompts/` (Linux/Mac) |
| Per-repo | `.github/agents/` |

### More Information

See the official documentation: <https://code.visualstudio.com/docs/copilot/copilot-agents>

---

## GitHub Copilot CLI Usage

### Invocation Methods

**Command-line invocation:**

```bash
copilot --agent analyst --prompt "investigate why tests are failing"
copilot --agent implementer --prompt "fix the bug in UserService.cs"
copilot --agent orchestrator --prompt "help me implement a new feature"
```

**Interactive mode:**

```bash
copilot
/agent analyst
```

### CLI Installation Locations

| Type | Location | Status |
|------|----------|--------|
| Per-repo | `.github/agents/` | **Works** |
| Global | `~/.copilot/agents/` | Known bug (#452) |

### CLI Notes

- Use per-repository installation until global agent loading is fixed
- Agents are defined with YAML frontmatter including `name`, `description`, and `tools`
- MCP servers (like `cloudmcp-manager`) need separate configuration in `~/.copilot/mcp-config.json`

See the official documentation: <https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli>

---

## Claude Code Usage

### Task Tool Invocation

Using the Task tool:

```python
Task(subagent_type="analyst", prompt="Investigate why X fails")
Task(subagent_type="implementer", prompt="Implement feature X")
Task(subagent_type="critic", prompt="Validate plan at .agents/planning/...")
```

### Claude Installation Locations

| Type | Location |
|------|----------|
| Global | `~/.claude/agents/` |
| Per-repo | `.claude/agents/` |

### Claude Notes

- Restart Claude Code after installing new agents
- Use `/agents` command to view available agents
- Project-level agents override global agents

---

## Memory System

All agents use `cloudmcp-manager` for cross-session memory (replaces Flowbaby).

### Memory Operations

| Operation | Tool | Purpose |
|-----------|------|---------|
| Search | `memory-search_nodes` | Find relevant context |
| Retrieve | `memory-open_nodes` | Get specific entities |
| Create | `memory-create_entities` | Store new knowledge |
| Update | `memory-add_observations` | Add to existing entities |
| Link | `memory-create_relations` | Connect related concepts |

### Entity Naming Conventions

| Type | Pattern | Example |
|------|---------|---------|
| Feature | `Feature-[Name]` | `Feature-Authentication` |
| Decision | `ADR-[Number]` | `ADR-001` |
| Pattern | `Pattern-[Name]` | `Pattern-StrategyTax` |
| Skill | `Skill-[Category]-[Number]` | `Skill-Build-001` |

---

## Workflow Patterns

### Standard Feature Development

```text
orchestrator → analyst → architect → planner → critic → implementer → qa → retrospective
```

### Feature Development with Impact Analysis

```text
orchestrator → analyst → architect → planner → [impact analysis] → critic → implementer → qa
```

Where impact analysis involves planner coordinating: implementer, architect, security, devops, qa

### Quick Fix Path

```text
implementer → qa
```

### Strategic Decision Path

```text
independent-thinker → high-level-advisor → task-generator
```

### Ideation Pipeline

```text
analyst → high-level-advisor → independent-thinker → critic → roadmap → explainer → task-generator
```

---

## Agent-by-Agent Guide

### Orchestrator – Task Coordination

**Role**: Routes work to specialized agents based on task classification and domain identification.

**Use when**:

- Starting complex multi-step tasks
- Unclear which agent should handle a request

**Key Capabilities**:

- Task classification (9 types)
- Domain identification (8 domains)
- Complexity assessment
- Agent sequence selection
- Impact analysis orchestration

**Handoffs to**: analyst, architect, planner, implementer (based on classification)

---

### Analyst – Deep Technical Research

**Role**: Investigates unknowns, APIs, performance questions, and tricky tradeoffs.

**Use when**:

- Technical uncertainty exists
- Need API experiments, benchmarks, or comparative analysis

**Example prompts**:

- "Investigate why the cache is causing memory issues"
- "Research options for implementing OAuth 2.0"

**Handoffs to**: architect (design decisions), planner (scope changes)

---

### Architect – System & Design Decisions

**Role**: Maintains architecture, patterns, boundaries, and high-level design decisions.

**Use when**:

- Feature affects system structure or boundaries
- Need ADRs or architectural guidance

**Outputs**: ADRs in `.agents/architecture/ADR-NNN-*.md`

**Handoffs to**: planner (approved designs), analyst (more research needed)

---

### Planner – Implementation Planning

**Role**: Turns epics into concrete, implementation-ready plans. Orchestrates impact analysis consultations for multi-domain changes.

**Use when**:

- Have a feature/epic and need a structured plan
- Requirements need to be clarified and broken into milestones

**Outputs**: Plans in `.agents/planning/NNN-*-plan.md`

**Handoffs to**: critic (REQUIRED before implementation)

---

### Critic – Plan Reviewer

**Role**: Critically reviews plans before implementation. Validates impact analyses and detects specialist disagreements.

**Use when**:

- Plan is "done" and needs quality gate
- Before any implementation begins
- Impact analysis needs validation

**Outputs**: Critiques in `.agents/critique/NNN-*-critique.md`

**Handoffs to**: planner (revision needed), implementer (approved), high-level-advisor (disagreement escalation)

---

### Implementer – Coding & Tests

**Role**: Writes and modifies code, implements approved plans, ensures tests exist and pass.

**Use when**:

- Plan has been approved
- Need to fix implementation issues

**Example prompts**:

- "Implement the UserService per the approved plan"
- "Add unit tests for the PaymentProcessor"

**Handoffs to**: qa (implementation complete), analyst (unknowns found)

---

### QA – Testing Strategy & Execution

**Role**: Designs test strategy, ensures coverage, runs tests.

**Use when**:

- Need a test plan before implementation
- Implementation done and needs test pass

**Outputs**: Test reports in `.agents/qa/NNN-*-test-report.md`

**Handoffs to**: implementer (tests fail), retrospective (all pass)

---

### Retrospective – Lessons Learned

**Role**: Runs post-implementation retrospectives focusing on process improvement.

**Use when**:

- Feature completed through QA
- Want to understand what went well/poorly

**Outputs**: Retrospectives in `.agents/retrospective/YYYY-MM-DD-*.md`

**Handoffs to**: skillbook (learnings to store), planner (process improvements)

---

### Memory – Context Management

**Role**: Retrieves/stores long-term context for coherence across sessions.

**Use when**:

- Resuming long-running effort
- Need explicit memory retrievals

---

### Skillbook – Skill Management

**Role**: Manages learned strategies with atomicity scoring and deduplication.

**Use when**:

- New strategy discovered that should be reused
- Need to update or tag existing skills

---

## Self-Improvement System

The agent system includes a continuous improvement loop:

```text
Execution → Reflection → Skill Update → Improved Execution
    ↑                                          ↓
    └──────────────────────────────────────────┘
```

### Skill Citation Protocol

When applying learned strategies, cite skills:

```markdown
**Applying**: Skill-Build-001
**Strategy**: Use /m:1 /nodeReuse:false for CI builds
**Expected**: Avoid file locking errors

[Execute...]

**Result**: Build succeeded
**Skill Validated**: Yes
```

### Atomicity Scoring

Learnings are scored 0-100% for quality:

| Score | Quality | Action |
|-------|---------|--------|
| 95-100% | Excellent | Add immediately |
| 70-94% | Good | Accept with refinement |
| 40-69% | Needs Work | Refine before adding |
| <40% | Rejected | Too vague |

---

## Customizing Agents

Each agent file defines:

- **description**: Purpose of the agent
- **tools**: Allowed tools (file editing, tests, GitHub, etc.)
- **model**: AI model to use (opus, sonnet, haiku)
- **Handoffs**: Which agents can be called next
- **Responsibilities**: What the agent should do
- **Constraints**: What the agent must NOT do

To customize, edit the relevant agent file while keeping the handoff protocol intact.

---

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

---

## Utilities

### Fix Markdown Fences

When generating or fixing markdown with code blocks, use the fix-markdown-fences utility to repair malformed closing fences automatically.

**Location**: `.agents/utilities/fix-markdown-fences/SKILL.md`

**Problem**: Closing fences should never have language identifiers (e.g., ` ` `text). This utility detects and fixes them.

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

### Memory Fallback

When `cloudmcp-manager` memory functions fail, use Serena memory tools as fallback:

- **Primary functions**: `memory-add_observations`, `memory-create_entities`, `memory-create_relations`, `memory-delete_entities`, `memory-delete_observations`, `memory-delete_relations`, `memory-open_nodes`, `memory-read_graph`, `memory-search_nodes`
- **Fallback functions**: `write_memory`, `read_memory`, `list_memories`, `delete_memory`, `edit_memory`

### Serena Toolbox

When the Serena MCP is available, agents should call the `mcp_serena_initial_instructions` tool immediately after being given their task by the user.

**Tool**: `mcp_serena_initial_instructions`

**Purpose**: Provides the "Serena Instructions Manual" which contains essential information on how to use the Serena toolbox.

**When to call**:

- At the start of any task when Serena MCP is available
- Before using other Serena tools (symbol management, file search, code insertion)
- When working with semantic coding tools

**Why it matters**: The manual provides critical context about efficient code reading strategies, symbolic navigation, and resource-efficient operations that optimize agent performance when working with large codebases.

**Note**: If the Serena MCP is not available, memories can be found in `.serena/memories`.

---

## Key Learnings from Practice

### Documentation Standards (Phase 1 Remediation, Dec 2024)

**Path Normalization**: Always use relative paths in documentation to prevent environment contamination.

- Forbidden patterns: `[A-Z]:\` (Windows), `/Users/` (macOS), `/home/` (Linux)
- Use relative paths: `docs/guide.md`, `../architecture/design.md`
- Validation automated via CI

**Two-Phase Security Review**: Security-sensitive changes require both pre-implementation and post-implementation verification.

- Phase 1 (Planning): Threat model, control design
- Phase 2 (Post-Implementation): PIV (Post-Implementation Verification)
- Implementer must flag security-relevant changes during coding

### Process Improvements

**Validation-Driven Standards**: When establishing new standards:

1. Document the standard with anti-patterns
2. Create validation script with pedagogical error messages
3. Integrate into CI
4. Baseline existing violations separately

**Template-Based Contracts**: Provide both empty templates AND filled examples to reduce ambiguity in agent outputs.

**CI Runner Performance**: Prefer `ubuntu-latest` over `windows-latest` for GitHub Actions (much faster). Use Windows runners only when PowerShell Desktop or Windows-specific features required.

---

## Putting It All Together

1. Start with **Orchestrator** for task classification and routing
2. Use **Analyst** for research and unknowns
3. Use **Planner** for concrete plans (with impact analysis for complex changes)
4. **Critic** validates plans and handles disagreement escalation
5. **Implementer** for code and tests
6. **QA** for technical quality
7. **Retrospective** and **Skillbook** for continuous improvement
8. **Memory** throughout to keep context across sessions
