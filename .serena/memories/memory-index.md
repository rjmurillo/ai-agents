# Memory Index

**Created**: 2025-12-23
**Updated**: 2025-12-23
**Purpose**: Quick reference to find relevant memories by topic
**Total Memories**: ~97 (reduced from 115 via consolidation)
**Related Issue**: #307

---

## How to Use This Index

1. Find your task category in the index below
2. Read the "Essential" memories first (highest value)
3. Read "Related" memories if you need deeper context
4. Skip memories marked with staleness warnings

---

## Task-Based Memory Routing

### Starting a New Session

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `project-overview` | Project purpose, tech stack, agent catalog |
| ✅ ESSENTIAL | `codebase-structure` | Directory layout, key files |
| ✅ ESSENTIAL | `skills-protocol` | BLOCKING gates, RFC 2119 evidence, templates |
| ⚠️ CHECK | `user-preference-*` | User's coding preferences |

### Working with GitHub (PRs, Issues, CLI)

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-github-cli` | Comprehensive gh CLI patterns (API, GraphQL, extensions) |
| ✅ ESSENTIAL | `skills-pr-review` | PR workflow, bot triage, acknowledgment protocol |
| Related | `skills-github-workflow-patterns` | Workflow YAML patterns |

### Writing PowerShell Code

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-powershell` | PS001-008: Variable interpolation, null safety, Import-Module paths |
| ✅ ESSENTIAL | `user-preference-no-bash-python` | No bash/Python - PowerShell only |
| ✅ ESSENTIAL | `pattern-thin-workflows` | Keep logic in modules, not workflows |
| Related | `skills-pester-testing` | Pester test patterns |
| Related | `powershell-testing-patterns` | Cross-platform test patterns |

### Writing Tests

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-testing` | Test-first development, basic execution validation |
| ✅ ESSENTIAL | `skills-qa` | QA routing decisions, test strategy gaps |
| Related | `pester-test-isolation-pattern` | Test isolation patterns |
| Related | `skills-pester-testing` | Pester 5.x discovery patterns |

### Security Work

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-security` | Security001-010: Validation chain, secret detection, TOCTOU |
| Related | `skills-powershell` (PS-Security-001) | Hardened regex for AI output |

### Planning & Architecture

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-planning` | 7 skills: file paths, self-contained tasks, parallel explore, multi-platform scope |
| ✅ ESSENTIAL | `skills-architecture` | Role-specific tools, model selection, composite actions |
| Related | `skills-design` | Agent design principles |
| Related | `skills-critique` | Conflict escalation protocol |

### Implementation

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-implementation` | Pre-implementation test discovery, proactive linting |
| ✅ ESSENTIAL | `skills-workflow` | Full pipeline for large changes, atomic commits |
| Related | `skills-execution` | Scope discipline, ship MVP |

### Multi-Agent Coordination

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-orchestration` | 4 skills: parallel execution, HANDOFF coordination, validation gate |
| Related | `skills-collaboration-patterns` | User additions as learning signals |

### Documentation

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-documentation` | 7 skills: migration search, taxonomy, fallbacks, user-facing, self-contained |
| Related | `user-facing-content-restrictions` | No internal refs in src/ |

### Validation & Quality

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-validation` | False positive handling, PR feedback gates |
| ✅ ESSENTIAL | `skills-linting` | Autofix first, configuration before fixes |

### Protocol Compliance

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `skills-protocol` | 4 skills: BLOCKING gates, RFC 2119 evidence, template enforcement, legacy |
| Related | `skill-init-001-session-initialization` | Session start requirements |

### CI/CD & DevOps

| Read First | Memory | Summary |
|------------|--------|---------|
| ✅ ESSENTIAL | `pattern-thin-workflows` | Thin workflows, testable modules |
| ✅ ESSENTIAL | `skills-ci-infrastructure` | CI patterns, ARM runner compatibility |
| Related | `skills-github-workflow-patterns` | Workflow trigger patterns |

---

## Category Index

### skills-* (Consolidated Domain Skills)

| Memory | # Skills | Topics |
|--------|----------|--------|
| `skills-security` | 10 | Multi-agent validation, secret detection, TOCTOU |
| `skills-linting` | 9 | Autofix, config-first, language identifiers |
| `skills-design` | 9 | Agent design principles, Mermaid diagrams |
| `skills-validation` | 10+ | False positives, PR feedback gates, skepticism |
| `skills-qa` | 3 | Test strategy gaps, QA routing, BLOCKING gate |
| `skills-roadmap` | 1 | RICE-KANO prioritization |
| `skills-collaboration-patterns` | 1 | User additions as learning signals |
| `skills-workflow` | 10 | Full pipeline, atomic commits, batch verification |
| `skills-testing` | 3 | Basic execution validation |
| `skills-documentation` | 7 | Migration search, taxonomy, fallbacks, user-facing, self-contained |
| `skills-architecture` | 4 | Role-specific tools, composite actions |
| `skills-planning` | 7 | File paths, self-contained tasks, parallel explore, multi-platform |
| `skills-implementation` | 5 | Test discovery, proactive linting, additive features |
| `skills-execution` | 2 | Scope discipline, ship MVP |
| `skills-analysis` | 3 | Gap template, comprehensive analysis, git blame |
| `skills-powershell` | 8 | Variable interpolation, null safety, Import-Module |
| `skills-github-cli` | 30+ | Comprehensive gh CLI reference |
| `skills-orchestration` | 4 | Parallel execution, HANDOFF coordination, validation gate |
| `skills-critique` | 1 | Conflict escalation |
| `skills-pr-review` | 6 parts | Conversation resolution, bot triage, acknowledgment, false positives |
| `skills-protocol` | 4 | **NEW**: BLOCKING gates, RFC 2119 evidence, templates, legacy |

### skill-* (Remaining Atomic Skills)

> **Note**: Most atomic skills have been consolidated into `skills-*` collections.

| Memory | Topic |
|--------|-------|
| `skill-init-001-session-initialization` | Session initialization requirements |
| `skill-testing-002-test-first-development` | Test-first patterns |
| `skill-architecture-*` | Architecture patterns |
| `skill-verification-*` | Verification patterns |
| `skill-deployment-*` | Deployment patterns |
| `skill-coordination-*` | Coordination patterns |

> **Consolidated** (2025-12-23):
> - `skill-documentation-*` → `skills-documentation`
> - `skill-planning-*` → `skills-planning`
> - `skill-orchestration-*` → `skills-orchestration`
> - `skill-protocol-*` → `skills-protocol`

### pattern-* (Architectural Patterns)

| Memory | Summary |
|--------|---------|
| `pattern-thin-workflows` | Keep logic in modules, workflows orchestrate only |
| `pattern-handoff-merge-session-histories` | Session merging patterns |
| `pattern-git-hooks-grep-patterns` | Pre-commit hook patterns |
| `pattern-agent-generation-three-platforms` | Multi-platform agent generation |

### user-preference-* (User Constraints)

| Memory | Summary |
|--------|---------|
| `user-preference-no-bash-python` | **CRITICAL**: PowerShell only, no bash/Python |
| `user-preference-no-auto-headers` | **MANDATORY**: No auto-generated headers, timestamps, or "do not edit" comments |

### retrospective-* (Historical Learning)

| Memory | Summary |
|--------|---------|
| `retrospective-2025-12-17-*` | Protocol compliance, CI failures |
| `retrospective-2025-12-18-*` | Session failures, parallel implementation |

### project-* (Project Context)

| Memory | Summary |
|--------|---------|
| `project-overview` | Project purpose, tech stack, workflows |
| `codebase-structure` | Directory layout, key files |

### pr-* (PR-Specific Patterns)

| Memory | Summary |
|--------|---------|
| `pr-52-*` | Symlink security retrospective |

### research-* (Research Findings)

| Memory | Summary |
|--------|---------|
| `research-agent-templating-*` | Agent templating approaches |
| `coderabbit-*` | CodeRabbit configuration research |
| `copilot-*` | Copilot patterns and decisions |

---

## Consolidation Log

| Date | Group | Before | After | Result |
|------|-------|--------|-------|--------|
| 2025-12-23 | User Prefs | 2 | 1 | `user-preference-no-auto-headers` |
| 2025-12-23 | Session Init | 2 | 1 | `skill-init-001-session-initialization` |
| 2025-12-23 | PR Review | 3 | 1 | `skills-pr-review` (6 parts) |
| 2025-12-23 | Documentation | 4 | 1 | `skills-documentation` (7 skills) |
| 2025-12-23 | Planning | 3 | 1 | `skills-planning` (7 skills) |
| 2025-12-23 | Orchestration | 3 | 1 | `skills-orchestration` (4 skills) |
| 2025-12-23 | Protocol | 4 | 1 | `skills-protocol` (4 skills) **NEW** |

**Total removed**: 18 duplicate memories

---

## Quick Reference: Top 10 Essential Memories

For any session, these memories provide the most value:

1. `project-overview` - What is this project?
2. `codebase-structure` - Where is everything?
3. `user-preference-no-bash-python` - PowerShell only!
4. `pattern-thin-workflows` - Architecture pattern
5. `skills-powershell` - PowerShell gotchas
6. `skills-github-cli` - GitHub operations
7. `skills-documentation` - Self-contained artifacts (7 skills)
8. `skills-protocol` - Session compliance (4 skills) **NEW**
9. `skills-orchestration` - Multi-agent coordination (4 skills)
10. `skills-pr-review` - PR workflow (6 parts)

---

## Maintenance Notes

- **Last indexed**: 2025-12-23
- **Last consolidation**: 2025-12-23 (115 → ~97 memories)
- **Index author**: Claude Opus 4.5
- **Next review**: When memory count exceeds 120

### Adding New Memories

When creating new memories:
1. Check this index for existing coverage
2. Prefer adding to existing `skills-*` collection over new atomic file
3. Update this index with 1-line summary
4. Consider consolidation if topic overlaps
