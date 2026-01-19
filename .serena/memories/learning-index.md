# Learning Index

**Purpose**: Master catalog of all observation files for efficient knowledge retrieval

**Last Updated**: 2026-01-18
**Total Observation Files**: 34
**Total Sessions Analyzed**: 415

---

## Quick Reference by Domain

### Development Workflow
- [agent-workflow-observations.md](#agent-workflow) - Agent coordination patterns
- [git-observations.md](#git) - Git operations and workflows
- [session-observations.md](#session) - Session management patterns
- [session-protocol-observations.md](#session-protocol) - Session protocol compliance

### Code Quality & Testing
- [testing-observations.md](#testing) - Testing strategies and coverage
- [qa-observations.md](#qa) - QA processes and validation
- [quality-gates-observations.md](#quality-gates) - Quality gate patterns
- [validation-observations.md](#validation) - Validation strategies

### Platform & Infrastructure
- [ci-infrastructure-observations.md](#ci-infrastructure) - CI/CD patterns
- [environment-observations.md](#environment) - Environment setup and compatibility
- [performance-observations.md](#performance) - Performance optimization
- [cost-optimization-observations.md](#cost-optimization) - Cost management

### Code & Scripting
- [powershell-observations.md](#powershell) - PowerShell patterns
- [bash-integration-observations.md](#bash-integration) - Bash scripting patterns
- [error-handling-observations.md](#error-handling) - Error handling anti-patterns

### Architecture & Design
- [architecture-observations.md](#architecture) - Architecture decisions
- [skills-architecture-observations.md](#skills-architecture) - Skill-level architecture
- [memory-observations.md](#memory) - Memory system patterns

### GitHub & PR Workflow
- [github-observations.md](#github) - GitHub API patterns
- [pr-review-observations.md](#pr-review) - PR review workflows
- [pr-comment-responder-observations.md](#pr-comment-responder) - PR comment handling

### Documentation & Communication
- [documentation-observations.md](#documentation) - Documentation standards
- [prompting-observations.md](#prompting) - Prompt engineering patterns

### Security
- [security-observations.md](#security) - Security patterns and hardening

### Skills & Meta-Learning
- [skills-critique-observations.md](#skills-critique) - Skill critique patterns
- [skills-mcp-observations.md](#skills-mcp) - MCP integration patterns
- [skills-powershell-observations.md](#skills-powershell) - PowerShell skill patterns
- [skills-quantitative-observations.md](#skills-quantitative) - Quantitative analysis
- [skills-retrospective-observations.md](#skills-retrospective) - Retrospective patterns
- [skills-validation-observations.md](#skills-validation) - Skill validation patterns
- [reflect-observations.md](#reflect) - Reflection skill patterns
- [retrospective-observations.md](#retrospective) - Retrospective learnings
- [SkillForge-observations.md](#skillforge) - SkillForge patterns
- [tool-usage-observations.md](#tool-usage) - Tool usage patterns
- [enforcement-patterns-observations.md](#enforcement-patterns) - Enforcement patterns

---

## Detailed Catalog

### Agent Workflow
**File**: `agent-workflow-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 2
**Focus**: Multi-agent coordination, handoff protocols, review patterns

**Key Learnings**:
- Multi-agent spec/plan review pattern (14-agent synthesis)
- Implementation summary as retrospective artifact

---

### Architecture
**File**: `architecture-observations.md`
**Last Updated**: 2026-01-17
**Sessions**: 10
**Focus**: System design, ADR patterns, composite actions

**Key Learnings**:
- MCP agent isolation (40+ tools firewalled)
- GitHub MCP architecture analysis
- DISAGREE_AND_COMMIT ADR workflow

---

### Bash Integration
**File**: `bash-integration-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 3
**Focus**: Bash scripting, shell patterns, glob patterns

**Key Learnings**:
- Glob patterns require recursive ** for nested directories
- Exit code testing and validation

---

### CI Infrastructure
**File**: `ci-infrastructure-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 5
**Focus**: CI/CD patterns, workflow automation, infrastructure

**Key Learnings**:
- Self-referential copy prevention
- Cross-platform testing matrix needed
- Workflow validation patterns

---

### Cost Optimization
**File**: `cost-optimization-observations.md`
**Last Updated**: 2026-01-17
**Sessions**: 2
**Focus**: Token efficiency, model selection, cost management

**Key Learnings**:
- Model selection for different task complexities
- Token usage optimization strategies

---

### Documentation
**File**: `documentation-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 6
**Focus**: Documentation standards, ADR structure, research patterns

**Key Learnings**:
- ADR implementation notes belong in dedicated subsection
- Research documentation pattern (main doc + atomic memories + index)
- Comprehensive documentation suite for feature rollouts

---

### Enforcement Patterns
**File**: `enforcement-patterns-observations.md`
**Last Updated**: 2026-01-16
**Sessions**: 3
**Focus**: Validation enforcement, compliance patterns

**Key Learnings**:
- Protocol enforcement strategies
- Validation automation

---

### Environment
**File**: `environment-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 3
**Focus**: Environment setup, compatibility, dependencies

**Key Learnings**:
- Python 3.13.x breaks CodeQL (use 3.12.8 via pyenv)
- Serena MCP fallback to file-based memory
- Platform compatibility patterns

---

### Error Handling
**File**: `error-handling-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 1
**Focus**: Error handling anti-patterns, suppression issues

**Key Learnings**:
- Error suppression anti-pattern (stderr to Write-Verbose before $LASTEXITCODE)
- Silent catch blocks without logging

---

### Git
**File**: `git-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 7
**Focus**: Git operations, commit patterns, merge workflows

**Key Learnings**:
- --no-verify usage requires explicit justification
- Pre-commit hook stack overflow with large file counts
- Branch verification patterns

---

### GitHub
**File**: `github-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 7
**Focus**: GitHub API, GraphQL, reactions, code scanning

**Key Learnings**:
- Code scanning reactions API not supported (HTTP 422)
- CommentId vs ThreadId distinction for PR replies
- GraphQL pagination edge cases

---

### Memory
**File**: `memory-observations.md`
**Last Updated**: 2026-01-17
**Sessions**: 6
**Focus**: Memory system patterns, knowledge management

**Key Learnings**:
- Atomic memories with auto-linking
- superseded_by links for graceful deprecation
- Memory-first architecture

---

### Performance
**File**: `performance-observations.md`
**Last Updated**: 2026-01-16
**Sessions**: Unknown
**Focus**: Performance optimization, caching, process management

**Key Learnings**:
- Process spawn overhead as architectural root cause
- Cache validation with metadata beyond timestamps
- -NoProfile performance improvements

---

### PowerShell
**File**: `powershell-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 10
**Focus**: PowerShell patterns, scripting best practices

**Key Learnings**:
- Scripts need conditional execution check for Pester testing
- PSAvoidUsingWriteHost suppression for user-facing scripts
- PowerShell pipeline scalar vs array issues

---

### PR Comment Responder
**File**: `pr-comment-responder-observations.md`
**Last Updated**: Unknown
**Sessions**: Unknown
**Focus**: PR comment handling, response patterns

**Key Learnings**:
- PR comment response workflows
- Bot comment handling

---

### PR Review
**File**: `pr-review-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 13
**Focus**: PR review workflows, bot comments, thread management

**Key Learnings**:
- ALL PR comments are blocking (bot and human)
- Thread resolution requires explicit GraphQL mutation
- Bot review comments require individual acknowledgment
- Batch response pattern for multiple comments
- Bot false positives require code verification

---

### Prompting
**File**: `prompting-observations.md`
**Last Updated**: Unknown
**Sessions**: Unknown
**Focus**: Prompt engineering, LLM interactions

**Key Learnings**:
- Prompt optimization strategies
- Context management

---

### QA
**File**: `qa-observations.md`
**Last Updated**: Unknown
**Sessions**: Unknown
**Focus**: Quality assurance processes, validation

**Key Learnings**:
- QA workflow patterns
- Validation strategies

---

### Quality Gates
**File**: `quality-gates-observations.md`
**Last Updated**: Unknown
**Sessions**: Unknown
**Focus**: Quality gate implementation, blocking conditions

**Key Learnings**:
- Quality gate patterns
- Blocking conditions

---

### Reflect
**File**: `reflect-observations.md`
**Last Updated**: Unknown
**Sessions**: Unknown
**Focus**: Reflection skill patterns, learning capture

**Key Learnings**:
- Iterative reflection more accurate than batch
- User feedback critical for analysis depth

---

### Retrospective
**File**: `retrospective-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 2
**Focus**: Retrospective patterns, learning extraction

**Key Learnings**:
- User feedback critical for analysis depth
- Iterative reflection patterns
- Chesterton's Fence before infrastructure changes

---

### Security
**File**: `security-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 4
**Focus**: Security patterns, vulnerability prevention, hardening

**Key Learnings**:
- Path traversal prevention with GetFullPath() + trailing separator
- Strict allowlist validation before path operations
- Security hardening for Python hooks
- CodeQL CLI extraction requires zstd

---

### Session
**File**: `session-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 1
**Focus**: Session management, protocol compliance

**Key Learnings**:
- Serena MCP unavailability documentation

---

### Session Protocol
**File**: `session-protocol-observations.md`
**Last Updated**: Unknown
**Sessions**: Unknown
**Focus**: Session protocol compliance, checklist patterns

**Key Learnings**:
- Protocol compliance patterns
- Session checklist enforcement

---

### SkillForge
**File**: `SkillForge-observations.md`
**Last Updated**: Unknown
**Sessions**: Unknown
**Focus**: SkillForge patterns, skill creation

**Key Learnings**:
- Skill creation patterns
- SkillForge workflows

---

### Skills - Architecture
**File**: `skills-architecture-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: Unknown
**Focus**: Skill-level architecture patterns

**Key Learnings**:
- MCP agent isolation pattern
- GitHub MCP architecture

---

### Skills - Critique
**File**: `skills-critique-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: Unknown
**Focus**: Skill critique patterns

**Key Learnings**:
- Design principle vs requirement distinction
- ADR critique patterns

---

### Skills - MCP
**File**: `skills-mcp-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: Unknown
**Focus**: MCP integration patterns

**Key Learnings**:
- GitHub MCP gaps requiring GraphQL fallback
- MCP server capabilities

---

### Skills - PowerShell
**File**: `skills-powershell-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: Unknown
**Focus**: PowerShell skill patterns

**Key Learnings**:
- Performance optimization patterns
- Process spawn overhead

---

### Skills - Quantitative
**File**: `skills-quantitative-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: Unknown
**Focus**: Quantitative analysis patterns

**Key Learnings**:
- Break-even point modeling
- File overhead at scale
- ADR-017 caching dependencies

---

### Skills - Retrospective
**File**: `skills-retrospective-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: Unknown
**Focus**: Retrospective skill patterns

**Key Learnings**:
- Chesterton's Fence pattern
- Autonomous agent safety

---

### Skills - Validation
**File**: `skills-validation-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: Unknown
**Focus**: Validation skill patterns

**Key Learnings**:
- Cross-validation gaps
- Orphan detection blindness

---

### Testing
**File**: `testing-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 17
**Focus**: Testing strategies, Pester patterns, coverage

**Key Learnings**:
- 100% pass rate mandatory (user: "73% is not production-ready")
- PowerShell pipeline scalar vs array (@() wrapper)
- Write-Host output cannot be captured
- Pester assertions don't support -Or
- ParameterAttribute requires type filtering
- Interactive prompts break CI
- ANSI codes break XML export
- Mock CLI Unix shell compatibility

---

### Tool Usage
**File**: `tool-usage-observations.md`
**Last Updated**: Unknown
**Sessions**: Unknown
**Focus**: Tool usage patterns, best practices

**Key Learnings**:
- Tool selection strategies
- Usage optimization

---

### Validation
**File**: `validation-observations.md`
**Last Updated**: 2026-01-18
**Sessions**: 7
**Focus**: Validation strategies, error messaging, verification

**Key Learnings**:
- Background agent work requires completion verification
- Recursive validation catches implementation gaps
- Pagination off-by-one errors
- Pre-commit hooks must skip index files
- Directory precondition validation for external tools

---

## Usage Patterns

### By Frequency (Sessions Analyzed)
1. **testing-observations.md** - 17 sessions
2. **pr-review-observations.md** - 13 sessions
3. **architecture-observations.md** - 10 sessions
4. **powershell-observations.md** - 10 sessions
5. **git-observations.md** - 7 sessions
6. **github-observations.md** - 7 sessions
7. **validation-observations.md** - 7 sessions

### By Confidence Level

**HIGH Confidence (Constraints - MUST follow)**:
- testing-observations.md (10+ HIGH learnings)
- pr-review-observations.md (6+ HIGH learnings)
- error-handling-observations.md (1 critical anti-pattern)
- environment-observations.md (2 HIGH learnings)
- security-observations.md (2+ HIGH learnings)

**MED Confidence (Preferences - SHOULD follow)**:
- Most observation files contain MED confidence patterns
- Focus on repeated patterns (≥2 signals)

**LOW Confidence (Notes for review)**:
- Track for future validation
- Promote to MED when pattern repeats

---

## Search Strategies

### By Problem Domain
- **Testing issues**: Check testing-observations.md first
- **PR workflow**: Check pr-review-observations.md
- **Git operations**: Check git-observations.md
- **Environment setup**: Check environment-observations.md
- **Security concerns**: Check security-observations.md

### By Technology
- **PowerShell**: powershell-observations.md, skills-powershell-observations.md
- **GitHub API**: github-observations.md, pr-review-observations.md
- **CI/CD**: ci-infrastructure-observations.md
- **MCP**: skills-mcp-observations.md, memory-observations.md

### By Workflow Phase
- **Session Start**: session-protocol-observations.md, environment-observations.md
- **Implementation**: architecture-observations.md, powershell-observations.md
- **Testing**: testing-observations.md, qa-observations.md
- **PR Review**: pr-review-observations.md, pr-comment-responder-observations.md
- **Session End**: retrospective-observations.md, validation-observations.md

---

## Maintenance

### Last Bootstrap: 2026-01-18
- **Sessions Analyzed**: 415 (Batches 1-38)
- **Date Range**: 2024-12-15 to 2026-01-16
- **Learnings Extracted**: 118+ (from high-quality sessions)

### Next Review: 2026-04-18 (Quarterly)
- Mark obsolete learnings
- Update with new patterns
- Consolidate redundant entries
- Verify session counts

### Quality Metrics
- **Coverage**: 34 observation files across all major domains
- **Freshness**: Last updated 2026-01-18
- **Completeness**: All 415 sessions systematically analyzed

---

## Related Documentation
- `.agents/SESSION-PROTOCOL.md` - Session protocol requirements
- `.agents/HANDOFF.md` - Project dashboard (read-only)
- `.agents/governance/PROJECT-CONSTRAINTS.md` - Hard constraints
- `AGENTS.md` - Primary agent system reference
