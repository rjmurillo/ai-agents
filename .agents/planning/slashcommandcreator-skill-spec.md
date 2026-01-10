# SlashCommandCreator Skill Specification

**Version**: 1.0.0
**Model**: claude-opus-4-5-20251101
**Type**: Meta-skill (orchestrator)
**Based On**: `skillcreator` 3.2.0 framework
**Created**: 2026-01-03

---

## Purpose

Systematize creation of production-quality custom Claude Code slash commands using the same rigor as `skillcreator`: deep iterative analysis, multi-agent synthesis, quality gates, and unanimous approval.

**Why This Matters**: Just as `skillcreator` prevents low-quality skills, `slashcommandcreator` prevents low-quality slash commands (missing frontmatter, overly permissive tools, unclear arguments, prompt-style vs documentation-style confusion).

---

## Skill Metadata

```yaml
---
name: slashcommandcreator
description: "Ultimate meta-skill for creating production-ready Claude Code custom slash commands. Uses deep iterative analysis, multi-agent synthesis panel for unanimous approval, quality gates for frontmatter/security/extended thinking, and automation analysis for skill migration. Fully autonomous execution produces categorically the best possible slash commands."
license: MIT
metadata:
  version: 1.0.0
  model: claude-opus-4-5-20251101
  subagent_model: claude-opus-4-5-20251101
  domains: [meta-skill, slash-commands, orchestration, quality-gates]
  type: orchestrator
  inputs: [user-goal, command-name-hint]
  outputs: [.claude/commands/{namespace}/{command}.md]
---
```

---

## Process Overview

```text
Your Request
    │
    ▼
Phase 1: DISCOVERY & ANALYSIS
  • Clarify intent (what prompt is repeated?)
  • Search for similar existing commands
  • Slash command vs skill decision
  • Apply 11 thinking models + Slash Command Lens
    │
    ▼
Phase 2: DESIGN
  • Command naming (namespace conventions)
  • Argument design (required/optional, positional/$ARGUMENTS)
  • Frontmatter schema (description, argument-hint, allowed-tools, model)
  • Dynamic context (bash !, file @)
  • Extended thinking evaluation (ultrathink)
    │
    ▼
Phase 3: MULTI-AGENT VALIDATION
  • Security: allowed-tools constraints
  • Architect: no duplication, appropriate scope
  • Independent-Thinker: challenge necessity
  • Critic: frontmatter completeness
    │
    ▼
Phase 4: IMPLEMENTATION
  • Create command file with frontmatter + prompt
  • Test invocation with various arguments
  • Documentation (catalog, CLAUDE.md)
    │
    ▼
Phase 5: QUALITY GATES
  • Frontmatter validation
  • Argument validation
  • Security validation
  • Length validation (<200 lines or convert to skill)
  • Lint validation (markdownlint-cli2)
    │
    ▼
Production-Ready Slash Command
```

---

## Triggers

- `SlashCommandCreator: {goal}` - Full autonomous command creation
- `create slash command` - Natural language activation
- `design slash command for {purpose}` - Purpose-first creation
- `slashcommandcreator --plan-only` - Generate specification without execution
- `SlashCommandCreator --quick {goal}` - Reduced depth (not recommended)

---

## Phase 1: Discovery & Analysis

### 1.1 Clarify Intent

**Questions to Answer**:
- What prompt is being repeated?
- What dynamic context is needed (git status, file contents, etc.)?
- Who will use this (project team vs personal)?
- How often will this be invoked?

**Thinking Models Applied** (adapted from `skillcreator`):

1. **First Principles**: What is the core problem being solved?
2. **Inversion**: What would make this command unusable?
3. **Second-Order Effects**: What happens when everyone uses this?
4. **Chesterton's Fence**: Why doesn't this command exist already?
5. **Jobs to Be Done**: What job is the user hiring this command for?
6. **Constraints**: What can't be done with a slash command? (scripts, multi-step workflows)
7. **Evolution**: How will this command need to change over time?
8. **Timelessness**: Will this command be useful in 6 months? 1 year?
9. **Automation**: Could this be automated instead of prompted?
10. **Substitution**: What existing command/skill does this replace?
11. **Emergence**: What new behaviors emerge from this command?

**Slash Command Lens**:
- **Simplicity**: Does this fit in one file (<200 lines)?
- **Explicitness**: Is this user-invoked or context-triggered?
- **Arguments**: Are there 1-3 simple arguments?
- **Dynamic Context**: Can bash `!` and file `@` provide needed context?

### 1.2 Existing Command Check

**Search Locations**:
- `.claude/commands/` (project commands)
- `~/.claude/commands/` (personal commands)
- `.claude/skills/` (check if similar skill exists)

**Tools**:
```bash
find .claude/commands -type f -name "*.md"
find .claude/skills -type d -maxdepth 1
grep -r "description:" .claude/commands/
```

### 1.3 Slash Command vs Skill Decision

**Decision Matrix**:

| Criterion | Slash Command | Skill |
|-----------|---------------|-------|
| **File Count** | One file | Multiple files |
| **Prompt Length** | <200 lines | Unlimited |
| **Scripts Required** | No | Yes (.ps1/.psm1) |
| **Invocation** | Explicit `/command` | Automatic (context) |
| **Arguments** | 1-3 simple args | Complex parameters |
| **Dynamic Context** | Bash `!`, File `@` | Full script logic |
| **Tool Restrictions** | Frontmatter `allowed-tools` | No restrictions |

**Migration Path**: If slash command grows beyond 200 lines or requires scripts, migrate to skill.

---

## Phase 2: Design

### 2.1 Command Naming

**Namespace Conventions**:

```text
.claude/commands/
├── pr/
│   ├── review.md          → /review (project:pr)
│   ├── merge.md           → /merge (project:pr)
│   └── comment.md         → /comment (project:pr)
├── memory/
│   ├── search.md          → /search (project:memory)
│   ├── save.md            → /save (project:memory)
│   └── explore.md         → /explore (project:memory)
├── git/
│   ├── commit.md          → /commit (project:git)
│   └── push.md            → /push (project:git)
└── architecture/
    ├── design.md          → /design (project:architecture)
    └── review.md          → /review (project:architecture)
```

**Naming Rules**:
- Use lowercase, hyphenated names: `pr-review.md` not `PRReview.md`
- Use singular nouns for entities: `commit.md` not `commits.md`
- Use verbs for actions: `review.md`, `create.md`, `analyze.md`
- Group related commands in subdirectories

### 2.2 Argument Design

**Patterns**:

1. **All Arguments**: Use `$ARGUMENTS` for single-value or variable-length arguments
   ```markdown
   Fix issue #$ARGUMENTS
   ```

2. **Positional Arguments**: Use `$1`, `$2`, `$3` for structured parameters
   ```markdown
   Review PR #$1 with priority $2 and assign to $3
   ```

3. **Optional Arguments**: Provide graceful defaults
   ```markdown
   Create a blog post titled "$ARGUMENTS".
   If no title provided, generate a draft post.
   ```

**Argument Hint Syntax**:

```yaml
# Required in angle brackets
argument-hint: <pr-number>

# Optional in square brackets
argument-hint: [message]

# Combined
argument-hint: <pr-number> [priority] [assignee]

# Multiple options with pipe
argument-hint: add [tagId] | remove [tagId] | list
```

### 2.3 Frontmatter Schema

**Required Fields**:

```yaml
---
description: {trigger-based description}
argument-hint: {expected arguments}
---
```

**Optional but Recommended Fields**:

```yaml
---
allowed-tools: {tool permissions}
model: {claude-model-id}
disable-model-invocation: {true|false}
---
```

**Description Pattern** (per `creator-001-frontmatter-trigger-specification`):

```yaml
# BAD - Capability-only
description: GitHub PR operations

# GOOD - Trigger-based
description: GitHub PR operations. Use when Claude needs to review PRs, reply to comments, or merge pull requests.
```

**Template**:

```yaml
description: |
  {Capability summary - one sentence}
  Use when Claude needs to: (1) {trigger 1}, (2) {trigger 2}, (3) {trigger 3}...
```

### 2.4 Dynamic Context Injection

**Bash Execution (`!` prefix)**:

```markdown
## Context

- Current branch: !`git branch --show-current`
- Git status: !`git status --short`
- Recent commits: !`git log --oneline -5`
- PR details: !`gh pr view $1 --json title,body,files`
```

**Security Requirements**:

```yaml
# MUST specify allowed bash commands
allowed-tools: Bash(git:*), Bash(gh:*)

# MORE SECURE - Specific commands only
allowed-tools: Bash(git branch:*), Bash(git status:*), Bash(git log:*), Bash(gh pr view:*)
```

**File References (`@` prefix)**:

```markdown
Review the implementation in @src/utils/helpers.js

Compare @src/old-version.js with @src/new-version.js
```

### 2.5 Extended Thinking Evaluation

**Use `ultrathink` For**:
- Complex architectural decisions
- Challenging bugs with multi-step debugging
- Multi-step implementation planning
- Evaluating trade-offs between approaches
- Edge case analysis

**Syntax**:

```markdown
ultrathink: Design the architecture for $ARGUMENTS.
Consider scalability, maintainability, performance, security, and cost.
Analyze trade-offs between approaches.
```

**Model Selection**:

| Task Complexity | Model | Extended Thinking |
|-----------------|-------|-------------------|
| Simple prompts | claude-3-5-haiku-20241022 | No |
| Standard operations | claude-3-5-sonnet-20241022 | Optional |
| Complex reasoning | claude-opus-4-5-20251101 | Yes (`ultrathink`) |

---

## Phase 3: Multi-Agent Validation

### 3.1 Security Agent Review

**Checklist**:

- [ ] `allowed-tools` specified for all bash commands
- [ ] No overly permissive wildcards (e.g., `Bash(*:*)`)
- [ ] Specific command patterns used (e.g., `Bash(git add:*)`)
- [ ] No execution of user-provided bash code
- [ ] File references (`@`) don't expose sensitive paths

**Example Violations**:

```yaml
# BAD - Overly permissive
allowed-tools: Bash(*:*)

# BAD - No bash permission but uses bash
---
description: Show git status
---
Status: !`git status`

# GOOD - Specific permissions
allowed-tools: Bash(git status:*), Bash(git branch:*), Bash(git log:*)
```

### 3.2 Architect Agent Review

**Checklist**:

- [ ] No duplication with existing commands
- [ ] No duplication with existing skills (if so, use skill instead)
- [ ] Appropriate scope (not too broad, not too narrow)
- [ ] Correct decision: slash command vs skill
- [ ] Namespace follows project conventions

**Example Violations**:

```markdown
# BAD - Should be a skill (requires scripts)
---
description: Run comprehensive test suite with reporting
---
Run Pester tests, generate coverage report, analyze failures...
```

### 3.3 Independent-Thinker Agent Review

**Challenge Questions**:

- Why is this command necessary? (Chesterton's Fence)
- Could this be automated instead of prompted?
- What's the simpler alternative?
- What assumptions are we making?
- What happens when this command fails?

**Example Challenge**:

```text
User Request: Create /git-commit-fast for quick commits

Independent-Thinker: Why not just git commit -m? What value does the slash command add?
If the answer is "context from git status", that's valid. If "saves typing", not worth it.
```

### 3.4 Critic Agent Review

**Checklist**:

- [ ] Frontmatter complete (`description`, `argument-hint`)
- [ ] Trigger-based description (per `creator-001`)
- [ ] Argument handling matches `argument-hint`
- [ ] Graceful defaults for optional arguments
- [ ] Extended thinking appropriate for complexity
- [ ] Model selection appropriate for task
- [ ] Length <200 lines (or recommend skill migration)
- [ ] Markdown lint compliance

**Unanimous Approval Required**: All 4 agents (security, architect, independent-thinker, critic) must approve.

---

## Phase 4: Implementation

### 4.1 Create Command File

**File Structure**:

```markdown
---
{frontmatter YAML}
---

# {Command Title}

{Prompt content with $ARGUMENTS or $1, $2, etc.}

## Context

- {Dynamic data}: !`{bash command}`
- {File reference}: @{path/to/file}

## Task

{Clear instruction for Claude}
```

**Example**:

```markdown
---
allowed-tools: Bash(git:*), Bash(gh:*), Read, Grep
argument-hint: <pr-number>
description: Review a pull request. Use when Claude needs to analyze PR changes, provide feedback on code quality, or suggest improvements.
model: claude-3-5-sonnet-20241022
---

# PR Review

Review PR #$ARGUMENTS

## Context

- PR details: !`gh pr view $ARGUMENTS --json title,body,files,commits`
- Current branch: !`git branch --show-current`
- Diff: !`gh pr diff $ARGUMENTS`

## Task

Analyze the PR and provide feedback on:
- Code quality and best practices
- Security vulnerabilities
- Performance implications
- Test coverage
```

### 4.2 Test Invocation

**Test Cases**:

1. **With Required Arguments**: `/command arg1`
2. **With Optional Arguments**: `/command arg1 arg2`
3. **Without Optional Arguments**: `/command arg1`
4. **Edge Cases**: Missing arguments, invalid arguments, special characters

**Validation**:
- Does `$ARGUMENTS` capture correctly?
- Do bash commands execute without errors?
- Do file references resolve?
- Does extended thinking activate (if `ultrathink`)?

### 4.3 Documentation

**Update Files**:

1. **Command Catalog**: `.claude/commands/README.md`
   ```markdown
   ## Available Commands

   ### PR Commands

   - `/review` - Review a pull request
   - `/merge` - Merge a pull request with validation
   ```

2. **CLAUDE.md**: Add to project instructions if project-level command
   ```markdown
   ### Slash Commands

   - `/review <pr-number>` - Review PR with code quality analysis
   ```

---

## Phase 5: Quality Gates

### 5.1 Frontmatter Validation

**PowerShell Script**: `scripts/Validate-SlashCommand.ps1`

```powershell
# Check YAML parses correctly
$frontmatter = Get-Content $CommandPath | Select-String -Pattern '^---$' -Context 0,100
$yaml = $frontmatter.Context.PostContext | ConvertFrom-Yaml

# Required fields
if (-not $yaml.description) { throw "Missing description" }
if (-not $yaml.'argument-hint' -and $commandUsesArguments) { throw "Missing argument-hint" }

# Trigger-based description
if ($yaml.description -notmatch 'Use when') {
    Write-Warning "Description should include 'Use when' trigger context"
}
```

### 5.2 Argument Validation

**Checks**:

- [ ] If command uses `$ARGUMENTS`, `argument-hint` present
- [ ] If command uses `$1`/`$2`, `argument-hint` shows positional args
- [ ] `argument-hint` uses `<required>` and `[optional]` syntax
- [ ] Prompt provides graceful defaults for optional arguments

### 5.3 Security Validation

**Checks**:

- [ ] If bash `!` used, `allowed-tools` includes `Bash(...)`
- [ ] `Bash(...)` patterns are specific (not `Bash(*:*)`)
- [ ] No user-provided bash code execution
- [ ] File references don't expose sensitive paths

**Script**:

```powershell
# Check bash commands have allowed-tools
$bashCommands = Select-String -Path $CommandPath -Pattern '!\`.*\`'
if ($bashCommands -and -not $yaml.'allowed-tools') {
    throw "Bash commands used but allowed-tools not specified"
}

# Check for overly permissive patterns
if ($yaml.'allowed-tools' -match 'Bash\(\*:\*\)') {
    throw "Overly permissive allowed-tools: Bash(*:*)"
}
```

### 5.4 Length Validation

**Check**:

```powershell
$lineCount = (Get-Content $CommandPath).Count
if ($lineCount -gt 200) {
    Write-Warning "Command is $lineCount lines. Consider converting to skill (threshold: 200)."
}
```

### 5.5 Lint Validation

**Run**:

```bash
npx markdownlint-cli2 $CommandPath
```

**Common Issues**:
- Missing language specifier in code blocks
- Inconsistent heading levels
- Trailing whitespace

---

## Quality Gates Checklist

```markdown
## Slash Command Quality Gates

### Phase 1: Discovery
- [ ] Intent clarified (what prompt is repeated?)
- [ ] Existing commands searched (no duplication)
- [ ] Slash command vs skill decision validated

### Phase 2: Design
- [ ] Command naming follows namespace conventions
- [ ] Argument design (`$ARGUMENTS` or `$1`/`$2`) documented
- [ ] Frontmatter schema complete
- [ ] Dynamic context (bash `!`, file `@`) identified
- [ ] Extended thinking (`ultrathink`) evaluated

### Phase 3: Validation
- [ ] Security: `allowed-tools` constraints validated
- [ ] Architect: No duplication, appropriate scope
- [ ] Independent-Thinker: Necessity challenged
- [ ] Critic: Frontmatter completeness verified
- [ ] **UNANIMOUS APPROVAL** from all 4 agents

### Phase 4: Implementation
- [ ] Command file created with frontmatter + prompt
- [ ] Tested with multiple argument combinations
- [ ] Documentation updated (catalog, CLAUDE.md)

### Phase 5: Quality Gates
- [ ] Frontmatter: YAML parses, required fields present
- [ ] Frontmatter: Trigger-based description (includes "Use when")
- [ ] Arguments: `argument-hint` matches usage
- [ ] Security: Bash commands have `allowed-tools` permission
- [ ] Security: No overly permissive wildcards
- [ ] Length: <200 lines (or migration to skill recommended)
- [ ] Linting: Passes `markdownlint-cli2`
```

---

## Integration with ai-agents Project

### PowerShell Script: `New-SlashCommand.ps1`

**Location**: `.claude/skills/slashcommandcreator/scripts/New-SlashCommand.ps1`

**Parameters**:

```powershell
param(
    [Parameter(Mandatory)]
    [string]$Goal,

    [Parameter()]
    [string]$Namespace,

    [Parameter()]
    [switch]$PlanOnly,

    [Parameter()]
    [ValidateSet('sonnet', 'opus', 'haiku')]
    [string]$Model = 'sonnet'
)
```

**Workflow**:

1. Discovery: Search existing commands
2. Design: Generate frontmatter + prompt
3. Validation: Multi-agent approval
4. Implementation: Create file
5. Quality Gates: Run all validations
6. Documentation: Update catalog

### Pre-Commit Hook Integration

**Hook**: `.claude/hooks/pre-commit-slash-commands.ps1`

**Checks**:

```powershell
# Get staged slash commands
$stagedCommands = git diff --cached --name-only --diff-filter=ACM | Where-Object { $_ -like "*.claude/commands/*.md" }

foreach ($command in $stagedCommands) {
    # Run quality gates
    & scripts/Validate-SlashCommand.ps1 -CommandPath $command
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Slash command validation failed: $command"
        exit 1
    }
}
```

### CI/CD Quality Gate

**Workflow**: `.github/workflows/slash-command-quality.yml`

```yaml
name: Slash Command Quality Gate

on:
  pull_request:
    paths:
      - '.claude/commands/**/*.md'

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate Slash Commands
        run: |
          pwsh scripts/Validate-SlashCommand.ps1 -Path .claude/commands/
      - name: Lint Markdown
        run: |
          npx markdownlint-cli2 ".claude/commands/**/*.md"
```

---

## Decision Criteria: Slash Command vs Skill

### Slash Command When

- ✅ Prompt fits in one file (<200 lines)
- ✅ No scripts or utilities required
- ✅ User explicitly invokes command
- ✅ 1-3 simple arguments
- ✅ Primarily prompt text with dynamic context
- ✅ Quick, frequently used prompts
- ✅ Team wants to standardize a query

### Skill When

- ✅ Multiple files needed (scripts, templates, utilities)
- ✅ Automatic context-based invocation desired
- ✅ Complex multi-step workflow
- ✅ Team workflow standardization with complex logic
- ✅ PowerShell/.psm1 modules required
- ✅ Needs to maintain state across invocations
- ✅ Requires complex orchestration

### Migration Path

If slash command grows beyond 200 lines or requires scripts:

1. Create skill directory: `.claude/skills/{name}/`
2. Move prompt content to `SKILL.md`
3. Extract complex logic to `scripts/*.ps1`
4. Update `description` frontmatter
5. Deprecate slash command with redirect

---

## Metrics for Success

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Frontmatter Coverage** | 100% | All commands have frontmatter |
| **Trigger-Based Descriptions** | 100% | All `description` fields specify WHEN |
| **Security Compliance** | 100% | Bash commands have `allowed-tools` |
| **Extended Thinking Adoption** | 50%+ | Complex commands use `ultrathink` |
| **Quality Gate Failures** | <5% | Pre-commit hook rejection rate |
| **Command to Skill Ratio** | 3:1 | More simple commands than complex skills |
| **Unanimous Approval Rate** | 100% | All commands pass multi-agent panel |

---

## Implementation Timeline

### Phase 1: Foundation (Week 1)

- [ ] Create `slashcommandcreator` skill directory
- [ ] Write `SKILL.md` with complete specification
- [ ] Implement `scripts/New-SlashCommand.ps1`
- [ ] Implement `scripts/Validate-SlashCommand.ps1`

### Phase 2: Quality Gates (Week 2)

- [ ] Create pre-commit hook for slash commands
- [ ] Create CI/CD workflow for quality validation
- [ ] Test with existing commands in `.claude/commands/`

### Phase 3: Documentation (Week 3)

- [ ] Update `CLAUDE.md` with slash command guidelines
- [ ] Create `.claude/commands/README.md` catalog
- [ ] Document decision criteria (slash command vs skill)

### Phase 4: Improvement (Week 4)

- [ ] Audit existing commands, apply quality gates
- [ ] Add `ultrathink` to complex commands
- [ ] Migrate simple skills to slash commands

---

## Related Memories

### Serena Memories to Create

1. **slashcommand-quality-gates**: Quality gate checklist and validation script
2. **slashcommand-vs-skill-decision**: Decision matrix for choosing approach
3. **slashcommand-frontmatter-patterns**: Frontmatter best practices and examples
4. **slashcommand-extended-thinking**: When to use `ultrathink` in commands
5. **slashcommand-security-patterns**: Security constraints for `allowed-tools`

### Forgetful Memories to Create

1. **Slash Command Architecture**: File structure, frontmatter schema, variable substitution
2. **Dynamic Context Injection**: Bash `!` and file `@` patterns with security
3. **Extended Thinking Integration**: `ultrathink` keyword, token budgets, performance
4. **Multi-Agent Validation Pattern**: Security, architect, independent-thinker, critic reviews
5. **Quality Gates Framework**: Frontmatter, argument, security, length, lint validations
6. **Slash Command vs Skill Decision**: Decision matrix, migration path
7. **Frontmatter Trigger-Based Descriptions**: Pattern from `creator-001` applied to slash commands
8. **Community Best Practices**: Namespacing, organization, version control
9. **SlashCommandCreator Meta-Skill**: Autonomous creation workflow
10. **ai-agents Integration**: PowerShell scripts, pre-commit hooks, CI/CD workflows

---

## Conclusion

The `slashcommandcreator` skill brings the same rigor to slash command creation as `skillcreator` brings to skill creation:

1. **Deep Analysis**: 11 thinking models + Slash Command Lens
2. **Multi-Agent Validation**: Unanimous approval from security, architect, independent-thinker, critic
3. **Quality Gates**: Frontmatter, argument, security, length, lint validations
4. **Autonomous Execution**: Fully automated workflow from user request to production-ready command
5. **Evolution and Timelessness**: Commands designed to remain useful over time

By systematizing slash command creation, the ai-agents project ensures high quality, security, and discoverability for both slash commands and skills.

---

## Next Steps

1. **Create Issue**: `#XXX - Implement slashcommandcreator skill`
2. **Milestone**: M-010 - Slash Command Quality Framework
3. **Tasks**:
   - Implement `slashcommandcreator` skill
   - Create validation scripts
   - Add pre-commit hooks
   - Update documentation
   - Audit existing commands
