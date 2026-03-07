# Skills Index Registry

**Version**: 1.0
**Last Updated**: 2026-02-20
**Total Active Skills**: 345
**Total Deprecated Skills**: 0

## Purpose

This registry provides a central index of all skills in the ai-agents memory system. Use this index to:

- Find skills by domain in one memory read (O(1) lookup)
- Discover related skills grouped by domain
- Check for skill ID collisions before creating new skills
- Identify deprecated skills and their replacements

## Skill ID Naming Convention

**Pattern**: `Skill-{Domain}-{Number}`

**Rules**:

1. Domain: CamelCase domain name (e.g., Analysis, Documentation, Architecture)
2. Number: 3-digit zero-padded sequential (e.g., 001, 002, 010, 100)
3. Uniqueness: Skill IDs MUST be globally unique across all domains

## Quick Navigation

| Domain | Count | Index File |
|--------|-------|------------|
| [Agent Workflow](#agent-workflow-skills) | 11 | [skills-agent-workflow-index](skills-agent-workflow-index.md) |
| [Analysis](#analysis-skills) | 6 | [skills-analysis-index](skills-analysis-index.md) |
| [Architecture](#architecture-skills) | 11 | [skills-architecture-index](skills-architecture-index.md) |
| [Autonomous Execution](#autonomous-execution-skills) | 4 | [skills-autonomous-execution-index](skills-autonomous-execution-index.md) |
| [Bash Integration](#bash-integration-skills) | 3 | [skills-bash-integration-index](skills-bash-integration-index.md) |
| [CI Infrastructure](#ci-infrastructure-skills) | 19 | [skills-ci-infrastructure-index](skills-ci-infrastructure-index.md) |
| [CodeRabbit](#coderabbit-skills) | 6 | [skills-coderabbit-index](skills-coderabbit-index.md) |
| [Copilot](#copilot-skills) | 8 | [skills-copilot-index](skills-copilot-index.md) |
| [Design](#design-skills) | 10 | [skills-design-index](skills-design-index.md) |
| [Documentation](#documentation-skills) | 12 | [skills-documentation-index](skills-documentation-index.md) |
| [Gemini](#gemini-skills) | 6 | [skills-gemini-index](skills-gemini-index.md) |
| [GitHub CLI](#github-cli-skills) | 15 | [skills-github-cli-index](skills-github-cli-index.md) |
| [GitHub Extensions](#github-extensions-skills) | 12 | [skills-gh-extensions-index](skills-gh-extensions-index.md) |
| [Git](#git-skills) | 11 | [skills-git-index](skills-git-index.md) |
| [Git Hooks](#git-hooks-skills) | 12 | [skills-git-hooks-index](skills-git-hooks-index.md) |
| [GraphQL](#graphql-skills) | 4 | [skills-graphql-index](skills-graphql-index.md) |
| [Implementation](#implementation-skills) | 11 | [skills-implementation-index](skills-implementation-index.md) |
| [JQ](#jq-skills) | 14 | [skills-jq-index](skills-jq-index.md) |
| [Labeler](#labeler-skills) | 6 | [skills-labeler-index](skills-labeler-index.md) |
| [Linting](#linting-skills) | 5 | [skills-linting-index](skills-linting-index.md) |
| [Orchestration](#orchestration-skills) | 13 | [skills-orchestration-index](skills-orchestration-index.md) |
| [Pester Testing](#pester-testing-skills) | 5 | [skills-pester-testing-index](skills-pester-testing-index.md) |
| [Planning](#planning-skills) | 6 | [skills-planning-index](skills-planning-index.md) |
| [PowerShell](#powershell-skills) | 11 | [skills-powershell-index](skills-powershell-index.md) |
| [PR Review](#pr-review-skills) | 30 | [skills-pr-review-index](skills-pr-review-index.md) |
| [Protocol](#protocol-skills) | 9 | [skills-protocol-index](skills-protocol-index.md) |
| [Quality](#quality-skills) | 11 | [skills-quality-index](skills-quality-index.md) |
| [Retrospective](#retrospective-skills) | 17 | [skills-retrospective-index](skills-retrospective-index.md) |
| [Security](#security-skills) | 16 | [skills-security-index](skills-security-index.md) |
| [Serena](#serena-skills) | 14 | [skills-serena-index](skills-serena-index.md) |
| [Session Init](#session-init-skills) | 7 | [skills-session-init-index](skills-session-init-index.md) |
| [Utilities](#utilities-skills) | 6 | [skills-utilities-index](skills-utilities-index.md) |
| [Validation](#validation-skills) | 16 | [skills-validation-index](skills-validation-index.md) |
| [Workflow Patterns](#workflow-patterns-skills) | 8 | [skills-workflow-patterns-index](skills-workflow-patterns-index.md) |

## Agent Workflow Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-AgentWorkflow-001 | pipeline orchestration agent multi-step coordination | agent-workflow/agent-workflow-pipeline | Active |
| Skill-AgentWorkflow-002 | critic gate validation quality checkpoint | agent-workflow/agent-workflow-critic-gate | Active |
| Skill-AgentWorkflow-003 | MVP shipping minimal viable feature delivery | agent-workflow/agent-workflow-mvp-shipping | Active |
| Skill-AgentWorkflow-004 | scope discipline boundary enforcement limits | agent-workflow/agent-workflow-scope-discipline | Active |
| Skill-AgentWorkflow-005 | atomic commits single logical change | agent-workflow/agent-workflow-atomic-commits | Active |
| Skill-AgentWorkflow-006 | collaboration patterns multi-agent teamwork | agent-workflow/agent-workflow-collaboration | Active |
| Skill-AgentWorkflow-007 | post-implementation critic validation review | agent-workflow/agent-workflow-post-implementation-critic-validation | Active |
| Skill-AgentWorkflow-008 | proactive template sync verification | agentworkflow-004-proactive-template-sync-verification-95 | Active |
| Skill-AgentWorkflow-009 | structured handoff formats agent transitions | agentworkflow-005-structured-handoff-formats-88 | Active |
| Skill-AgentWorkflow-010 | observations patterns learnings general | agent-workflow/agent-workflow-observations | Active |
| Skill-AgentWorkflow-011 | generation edit locations agent creation | agent-workflow/agent-generation-edit-locations | Active |

## Analysis Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Analysis-001 | gap analysis template severity root cause remediation | analysis/analysis-001-capability-gap-template-88 | Active |
| Skill-Analysis-002 | comprehensive analysis standard outline recommendation | analysis/analysis-002-comprehensive-analysis-standard-95 | Active |
| Skill-Analysis-003 | RCA verify premise before implementation issue 5-whys | analysis/analysis-002-rca-before-implementation | Active |
| Skill-Analysis-004 | related issue discovery search prerequisites dependencies | analysis/analysis-003-related-issue-discovery | Active |
| Skill-Analysis-005 | verify codebase state git grep search missing code | analysis/analysis-004-verify-codebase-state | Active |
| Skill-Analysis-006 | git blame author commit PR investigation history | analysis/analysis-git-blame | Active |

## Architecture Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Architecture-001 | tool allocation role-specific agent capability | architecture/architecture-tool-allocation | Active |
| Skill-Architecture-002 | model selection complexity task routing | architecture/architecture-model-selection | Active |
| Skill-Architecture-003 | ADR compliance documentation decision records | architecture/architecture-adr-compliance | Active |
| Skill-Architecture-004 | producer-consumer pattern data flow | architecture/architecture-producer-consumer | Active |
| Skill-Architecture-005 | composite tool patterns modular design | architecture/architecture-composite-tools | Active |
| Skill-Architecture-006 | agent specialization boundaries focus | architecture/architecture-agent-specialization | Active |
| Skill-Architecture-007 | cross-cutting concerns shared patterns | architecture/architecture-cross-cutting | Active |
| Skill-Architecture-008 | tier hierarchy agent levels orchestration | architecture/architecture-tier-hierarchy | Active |
| Skill-Architecture-009 | decomposition atomic unit breakdown | architecture/architecture-decomposition | Active |
| Skill-Architecture-010 | governance constraints rules enforcement | architecture/architecture-governance | Active |
| Skill-Architecture-011 | observations patterns learnings general | architecture/architecture-observations | Active |

## Autonomous Execution Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Autonomous-001 | guardrails protocol safety limits boundaries | autonomous/autonomous-guardrails | Active |
| Skill-Autonomous-002 | circuit breaker pattern failure isolation | autonomous/autonomous-circuit-breaker | Active |
| Skill-Autonomous-003 | success metrics measurement validation | autonomous/autonomous-success-metrics | Active |
| Skill-Autonomous-004 | patch signal trust metric confidence scoring | autonomous/autonomous-trust-metrics | Active |

## Bash Integration Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Bash-001 | pattern discovery AUTOFIX pre-commit hook | bash/bash-pattern-discovery | Active |
| Skill-Bash-002 | exit code contract cross-language testing | bash/bash-exit-code-contract | Active |
| Skill-Bash-003 | shell integration PowerShell interop | bash/bash-shell-integration | Active |

## CI Infrastructure Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-CI-001 | test runner artifacts upload download | ci/ci-test-runner-artifacts | Active |
| Skill-CI-002 | runner selection ARM self-hosted labels | ci/ci-runner-selection | Active |
| Skill-CI-003 | workflow quality gates checks status | ci/ci-workflow-quality-gates | Active |
| Skill-CI-004 | matrix strategy parallel jobs fan-out | ci/ci-matrix-strategy | Active |
| Skill-CI-005 | caching optimization dependencies restore | ci/ci-caching-optimization | Active |
| Skill-CI-006 | reusable workflows composite actions DRY | ci/ci-reusable-workflows | Active |
| Skill-CI-007 | secrets management secure injection | ci/ci-secrets-management | Active |
| Skill-CI-008 | conditional execution path filtering | ci/ci-conditional-execution | Active |
| Skill-CI-009 | artifact retention cleanup policies | ci/ci-artifact-retention | Active |
| Skill-CI-010 | job dependencies needs outputs | ci/ci-job-dependencies | Active |
| Skill-CI-011 | environment protection rules approvals | ci/ci-environment-protection | Active |
| Skill-CI-012 | concurrency groups cancel-in-progress | ci/ci-concurrency-groups | Active |
| Skill-CI-013 | workflow dispatch manual triggers inputs | ci/ci-workflow-dispatch | Active |
| Skill-CI-014 | status badges README integration | ci/ci-status-badges | Active |
| Skill-CI-015 | error handling failure modes recovery | ci/ci-error-handling | Active |
| Skill-CI-016 | dorny paths-filter checkout base ref | ci/ci-infrastructure-dorny-paths-filter-checkout | Active |
| Skill-CI-017 | YAML linting validation syntax | ci/ci-yaml-linting | Active |
| Skill-CI-018 | workflow testing act local validation | ci/ci-workflow-testing | Active |
| Skill-CI-019 | observations patterns learnings general | ci/ci-observations | Active |

## CodeRabbit Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-CodeRabbit-001 | config strategy YAML schema options | coderabbit/coderabbit-config | Active |
| Skill-CodeRabbit-002 | path instructions focus review targeting | coderabbit/coderabbit-path-instructions | Active |
| Skill-CodeRabbit-003 | security false positives suppression | coderabbit/coderabbit-security-false-positives | Active |
| Skill-CodeRabbit-004 | noise reduction filtering irrelevant | coderabbit/coderabbit-noise-reduction | Active |
| Skill-CodeRabbit-005 | integration GitHub actions workflow | coderabbit/coderabbit-integration | Active |
| Skill-CodeRabbit-006 | observations patterns learnings general | coderabbit/coderabbit-learnings | Active |

## Copilot Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Copilot-001 | platform priority P0-P2 triage routing | copilot/copilot-platform-priority | Active |
| Skill-Copilot-002 | follow-up PR detection continuation tracking | copilot/copilot-followup-pr-detection | Active |
| Skill-Copilot-003 | model configuration settings optimization | copilot/copilot-model-configuration | Active |
| Skill-Copilot-004 | CLI agent frontmatter regression version | copilot/copilot-cli-frontmatter-regression-runbook | Active |
| Skill-Copilot-005 | response patterns templates formatting | copilot/copilot-response-patterns | Active |
| Skill-Copilot-006 | false positive handling suppression | copilot/copilot-false-positives | Active |
| Skill-Copilot-007 | workspace mode project context | copilot/copilot-workspace-mode | Active |
| Skill-Copilot-008 | observations patterns learnings general | copilot/copilot-observations | Active |

## Design Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Design-001 | agent specialization focus responsibility | design/design-agent-specialization | Active |
| Skill-Design-002 | entry criteria prerequisites validation | design/design-entry-criteria | Active |
| Skill-Design-003 | patterns composability modular reusable | design/design-patterns-composability | Active |
| Skill-Design-004 | limitation documentation constraints scope | design/design-limitation-documentation | Active |
| Skill-Design-005 | interface contracts API boundaries | design/design-interface-contracts | Active |
| Skill-Design-006 | state management persistence session | design/design-state-management | Active |
| Skill-Design-007 | error handling graceful degradation | design/design-error-handling | Active |
| Skill-Design-008 | testability mocking isolation | design/design-testability | Active |
| Skill-Design-009 | extensibility plugin architecture | design/design-extensibility | Active |
| Skill-Design-010 | observations patterns learnings general | design/design-observations | Active |

## Documentation Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Documentation-001 | migration search systematic grep codebase pattern | documentation/documentation-001-systematic-migration-search | Active |
| Skill-Documentation-002 | reference taxonomy instructive informational operational | documentation/documentation-002-reference-type-taxonomy | Active |
| Skill-Documentation-003 | fallback tool call graceful degradation mcp serena | documentation/documentation-003-fallback-preservation | Active |
| Skill-Documentation-004 | pattern consistency syntax identical format canonical | documentation/documentation-004-pattern-consistency | Active |
| Skill-Documentation-005 | user-facing content internal PR issue session exclude | documentation/documentation-user-facing | Active |
| Skill-Documentation-006 | self-contained operational prompts autonomous agents | documentation/documentation-006-self-contained-operational-prompts | Active |
| Skill-Documentation-007 | self-contained artifact handoff agent amnesia general | documentation/documentation-007-self-contained-artifacts | Active |
| Skill-Documentation-008 | index selection domain routing keyword overlap | documentation/documentation-memory/index-selection-decision-tree | Active |
| Skill-Documentation-009 | verification critic amnesiac completeness objective | documentation/documentation-verification-protocol | Active |
| Skill-Documentation-010 | framework constraints limitations pull push SKILL.md | documentation/documentation-008-framework-constraints | Active |
| Skill-Documentation-011 | PRD specification requirements template | documentation/documentation-prd-template | Active |
| Skill-Documentation-012 | observations patterns learnings general | documentation/documentation-observations | Active |

## Gemini Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Gemini-001 | config schema settings YAML format | gemini/gemini-config | Active |
| Skill-Gemini-002 | styleguide format coding standards | gemini/gemini-styleguide | Active |
| Skill-Gemini-003 | path exclusions ignore patterns | gemini/gemini-path-exclusions | Active |
| Skill-Gemini-004 | integration enterprise setup | gemini/gemini-integration | Active |
| Skill-Gemini-005 | model selection capability routing | gemini/gemini-model-selection | Active |
| Skill-Gemini-006 | observations patterns learnings general | gemini/gemini-observations | Active |

## GitHub CLI Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-GitHubCLI-001 | PR operations create update merge | github/github-pr-operations | Active |
| Skill-GitHubCLI-002 | issue lifecycle management labels milestones | github/github-issue-lifecycle | Active |
| Skill-GitHubCLI-003 | GraphQL patterns queries mutations | github/github-graphql-patterns | Active |
| Skill-GitHubCLI-004 | REST API endpoints pagination | github/github-rest-api | Active |
| Skill-GitHubCLI-005 | authentication tokens scopes | github/github-authentication | Active |
| Skill-GitHubCLI-006 | search queries filtering syntax | github/github-search-queries | Active |
| Skill-GitHubCLI-007 | workflow triggers dispatch events | github/github-workflow-triggers | Active |
| Skill-GitHubCLI-008 | release management tags changelog | github/github-release-management | Active |
| Skill-GitHubCLI-009 | comment operations threading replies | github/github-comment-operations | Active |
| Skill-GitHubCLI-010 | review operations approve request changes | github/github-review-operations | Active |
| Skill-GitHubCLI-011 | branch protection rules enforcement | github/github-branch-protection | Active |
| Skill-GitHubCLI-012 | check runs status reporting | github/github-check-runs | Active |
| Skill-GitHubCLI-013 | repository settings configuration | github/github-repository-settings | Active |
| Skill-GitHubCLI-014 | team permissions access control | github/github-team-permissions | Active |
| Skill-GitHubCLI-015 | observations patterns learnings general | github/github-observations | Active |

## GitHub Extensions Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-GHExtensions-001 | notification filtering gh-notify | github/gh-notify | Active |
| Skill-GHExtensions-002 | combine PRs batch operations | github/gh-combine | Active |
| Skill-GHExtensions-003 | milestone management tracking | github/gh-milestone | Active |
| Skill-GHExtensions-004 | sub-issue decomposition linking | github/gh-sub-issue | Active |
| Skill-GHExtensions-005 | grep code search repository | github/gh-grep | Active |
| Skill-GHExtensions-006 | webhook management events | github/gh-webhook | Active |
| Skill-GHExtensions-007 | metrics collection analytics | github/gh-metrics | Active |
| Skill-GHExtensions-008 | copilot integration ai assist | github/gh-copilot | Active |
| Skill-GHExtensions-009 | dash dashboard overview | github/gh-dash | Active |
| Skill-GHExtensions-010 | poi points of interest bookmarks | github/gh-poi | Active |
| Skill-GHExtensions-011 | act local workflow testing | github/gh-act | Active |
| Skill-GHExtensions-012 | observations patterns learnings general | github/gh-extensions-observations | Active |

## Git Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Git-001 | merge conflict resolution strategy | git/git-merge-conflict-resolution | Active |
| Skill-Git-002 | branch cleanup pattern stale removal | git/git-branch-cleanup | Active |
| Skill-Git-003 | worktree parallel isolation concurrent | git/git-worktree-parallel | Active |
| Skill-Git-004 | branch switch file state verification | git/git-004-branch-switch-file-verification | Active |
| Skill-Git-005 | rebase interactive squash fixup | git/git-rebase-interactive | Active |
| Skill-Git-006 | cherry-pick selective commit transfer | git/git-cherry-pick | Active |
| Skill-Git-007 | stash management temporary storage | git/git-stash-management | Active |
| Skill-Git-008 | bisect debugging binary search | git/git-bisect-debugging | Active |
| Skill-Git-009 | reflog recovery lost commits | git/git-reflog-recovery | Active |
| Skill-Git-010 | submodule management nested repos | git/git-submodule-management | Active |
| Skill-Git-011 | observations patterns learnings general | git/git-observations | Active |

## Git Hooks Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-GitHooks-001 | pre-commit category blocking validation | git/git-hooks-pre-commit | Active |
| Skill-GitHooks-002 | autofix patterns automatic corrections | git/git-hooks-autofix | Active |
| Skill-GitHooks-003 | branch validation name format rules | git/git-hooks-branch-validation | Active |
| Skill-GitHooks-004 | commit-msg format conventional commits | git/git-hooks-commit-msg | Active |
| Skill-GitHooks-005 | pre-push checks remote validation | git/git-hooks-pre-push | Active |
| Skill-GitHooks-006 | post-checkout actions setup tasks | git/git-hooks-post-checkout | Active |
| Skill-GitHooks-007 | post-merge cleanup integration | git/git-hooks-post-merge | Active |
| Skill-GitHooks-008 | prepare-commit-msg template injection | git/git-hooks-prepare-commit-msg | Active |
| Skill-GitHooks-009 | hook bypass skip verification | git/git-hooks-bypass | Active |
| Skill-GitHooks-010 | cross-platform compatibility shell | git/git-hooks-cross-platform | Active |
| Skill-GitHooks-011 | TOCTOU time-of-check race conditions | git/git-hooks-toctou | Active |
| Skill-GitHooks-012 | observations patterns learnings general | git/git-hooks-observations | Active |

## GraphQL Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-GraphQL-001 | mutation format update create delete | graphql/graphql-mutation-format | Active |
| Skill-GraphQL-002 | PR operations thread resolution | graphql/graphql-pr-operations | Active |
| Skill-GraphQL-003 | REST decision matrix when to use | graphql/graphql-rest-decision | Active |
| Skill-GraphQL-004 | batch operations efficiency | graphql/graphql-batch-operations | Active |

## Implementation Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Implementation-001 | pre-implementation test discovery TDD | implementation/implementation-test-discovery | Active |
| Skill-Implementation-002 | memory-first pattern caching strategy | implementation/implementation-memory-first | Active |
| Skill-Implementation-003 | GraphQL-first API design approach | implementation/implementation-graphql-first | Active |
| Skill-Implementation-004 | incremental delivery small PRs | implementation/implementation-incremental | Active |
| Skill-Implementation-005 | error handling patterns exceptions | implementation/implementation-error-handling | Active |
| Skill-Implementation-006 | logging observability debugging | implementation/implementation-logging | Active |
| Skill-Implementation-007 | configuration management settings | implementation/implementation-configuration | Active |
| Skill-Implementation-008 | dependency injection IoC patterns | implementation/implementation-dependency-injection | Active |
| Skill-Implementation-009 | interface segregation contracts | implementation/implementation-interfaces | Active |
| Skill-Implementation-010 | refactoring patterns safe changes | implementation/implementation-refactoring | Active |
| Skill-Implementation-011 | observations patterns learnings general | implementation/implementation-observations | Active |

## JQ Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-JQ-001 | field extraction dot notation | jq/jq-field-extraction | Active |
| Skill-JQ-002 | raw output formatting -r flag | jq/jq-raw-output | Active |
| Skill-JQ-003 | array operations map select filter | jq/jq-array-operations | Active |
| Skill-JQ-004 | object construction building | jq/jq-object-construction | Active |
| Skill-JQ-005 | string interpolation formatting | jq/jq-string-interpolation | Active |
| Skill-JQ-006 | conditional logic if-then-else | jq/jq-conditional-logic | Active |
| Skill-JQ-007 | null handling optional chaining | jq/jq-null-handling | Active |
| Skill-JQ-008 | type conversions casting | jq/jq-type-conversions | Active |
| Skill-JQ-009 | grouping aggregation group_by | jq/jq-grouping | Active |
| Skill-JQ-010 | sorting ordering sort_by | jq/jq-sorting | Active |
| Skill-JQ-011 | unique deduplication distinct | jq/jq-unique | Active |
| Skill-JQ-012 | length counting size | jq/jq-length | Active |
| Skill-JQ-013 | recursive descent traversal | jq/jq-recursive | Active |
| Skill-JQ-014 | observations patterns learnings general | jq/jq-observations | Active |

## Labeler Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Labeler-001 | negation pattern matching exclude | labeler/labeler-negation | Active |
| Skill-Labeler-002 | glob selection wildcard patterns | labeler/labeler-glob | Active |
| Skill-Labeler-003 | combined patterns any-glob all-glob | labeler/labeler-combined | Active |
| Skill-Labeler-004 | changed-files detection scope | labeler/labeler-changed-files | Active |
| Skill-Labeler-005 | priority labels P0 P1 P2 assignment | labeler/labeler-priority | Active |
| Skill-Labeler-006 | observations patterns learnings general | labeler/labeler-observations | Active |

## Linting Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Linting-001 | autofix markdownlint automatic corrections | linting/linting-autofix | Active |
| Skill-Linting-002 | config baseline rules exceptions | linting/linting-config | Active |
| Skill-Linting-003 | false positive exclusions suppression | linting/linting-false-positives | Active |
| Skill-Linting-004 | scoped linting targeted validation | linting/linting-scoped | Active |
| Skill-Linting-005 | observations patterns learnings general | linting/linting-observations | Active |

## Orchestration Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Orchestration-001 | parallel execution optimization concurrent | orchestration/orchestration-parallel | Active |
| Skill-Orchestration-002 | handoff coordination agent transitions | orchestration/orchestration-handoff | Active |
| Skill-Orchestration-003 | validation gates quality checkpoints | orchestration/orchestration-validation-gates | Active |
| Skill-Orchestration-004 | consensus mechanisms agreement voting | orchestration/orchestration-consensus | Active |
| Skill-Orchestration-005 | disagree-and-commit pattern dissent | orchestration/orchestration-disagree-commit | Active |
| Skill-Orchestration-006 | dispatch routing task assignment | orchestration/orchestration-dispatch | Active |
| Skill-Orchestration-007 | synthesis consolidation results merging | orchestration/orchestration-synthesis | Active |
| Skill-Orchestration-008 | escalation patterns expert routing | orchestration/orchestration-escalation | Active |
| Skill-Orchestration-009 | timeout handling deadline management | orchestration/orchestration-timeout | Active |
| Skill-Orchestration-010 | retry logic failure recovery | orchestration/orchestration-retry | Active |
| Skill-Orchestration-011 | process workflow gaps missing capability | orchestration/orchestration-process-workflow-gaps | Active |
| Skill-Orchestration-012 | consensus disagree-and-commit pattern | governance/consensus-disagree-and-commit-pattern | Active |
| Skill-Orchestration-013 | observations patterns learnings general | orchestration/orchestration-observations | Active |

## Pester Testing Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Pester-001 | test discovery phase BeforeAll Context | pester/pester-test-discovery | Active |
| Skill-Pester-002 | parameterized tests data-driven TestCases | pester/pester-parameterized | Active |
| Skill-Pester-003 | test isolation cleanup AfterEach scope | pester/pester-isolation | Active |
| Skill-Pester-004 | variable scoping BeforeAll visibility | powershell/pester-variable-scoping | Active |
| Skill-Pester-005 | observations patterns learnings general | pester/pester-observations | Active |

## Planning Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Planning-001 | task description file path line number | planning/planning-001-task-descriptions-with-file-paths | Active |
| Skill-Planning-002 | parallel explore agents context concurrent | planning/planning-003-parallel-exploration-pattern-95 | Active |
| Skill-Planning-003 | approval checkpoint multi-file architecture | planning/planning-004-approval-checkpoint-for-multifile-changes-100 | Active |
| Skill-Planning-004 | checklist checkbox manifest analysis | planning/planning-001-checkbox-manifest | Active |
| Skill-Planning-005 | priority consistency agent table recommendation | planning/planning-002-priority-consistency | Active |
| Skill-Planning-006 | multi-platform scope claude copilot vs-code | planning/planning-022-multi-platform-agent-scope | Active |

## PowerShell Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-PowerShell-001 | string safety interpolation quoting | powershell/powershell-string-safety | Active |
| Skill-PowerShell-002 | array contains null-safety coercion | powershell/powershell-null-safety | Active |
| Skill-PowerShell-003 | cross-platform CI compatibility paths | powershell/powershell-cross-platform | Active |
| Skill-PowerShell-004 | variable shadowing detection scope | powershell/powershell-variable-shadowing-detection | Active |
| Skill-PowerShell-005 | module import patterns dependencies | powershell/powershell-module-import | Active |
| Skill-PowerShell-006 | error handling try-catch terminating | powershell/powershell-error-handling | Active |
| Skill-PowerShell-007 | pipeline operations streaming | powershell/powershell-pipeline | Active |
| Skill-PowerShell-008 | splatting parameter passing | powershell/powershell-splatting | Active |
| Skill-PowerShell-009 | JSON conversion handling | powershell/powershell-json | Active |
| Skill-PowerShell-010 | testing patterns Pester assertions | powershell/powershell-testing | Active |
| Skill-PowerShell-011 | observations patterns learnings general | powershell/powershell-observations | Active |

## PR Review Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-PRReview-001 | reviewer enumeration unique participants | pr-review/pr-review-reviewer-enumeration | Active |
| Skill-PRReview-002 | comment parsing structure extraction | pr-review/pr-review-comment-parsing | Active |
| Skill-PRReview-003 | bot response templates formatting | pr-review/pr-review-bot-templates | Active |
| Skill-PRReview-004 | thread resolution lifecycle states | pr-review/pr-review-thread-resolution | Active |
| Skill-PRReview-005 | batch response pattern efficiency | pr-review/pr-review-batch-response-pattern | Active |
| Skill-PRReview-006 | actionability classification routing | pr-review/pr-review-actionability | Active |
| Skill-PRReview-007 | triage verification stale closure | pr-review/triage-001-verify-before-stale-closure | Active |
| Skill-PRReview-008 | bot closure verification superseded | pr-review/triage-002-bot-closure-verification | Active |
| Skill-PRReview-009 | comment categorization type routing | pr-review/pr-review-categorization | Active |
| Skill-PRReview-010 | merge readiness checks validation | pr-review/pr-review-merge-readiness | Active |
| Skill-PRReview-011 | conflict detection resolution | pr-review/pr-review-conflict-detection | Active |
| Skill-PRReview-012 | approval workflow reviewers | pr-review/pr-review-approval-workflow | Active |
| Skill-PRReview-013 | CI status interpretation checks | pr-review/pr-review-ci-status | Active |
| Skill-PRReview-014 | draft PR handling workflow | pr-review/pr-review-draft-handling | Active |
| Skill-PRReview-015 | auto-merge configuration squash | pr-review/pr-review-auto-merge | Active |
| Skill-PRReview-016 | review request assignment | pr-review/pr-review-request | Active |
| Skill-PRReview-017 | comment reactions acknowledgment | pr-review/pr-review-reactions | Active |
| Skill-PRReview-018 | suggested changes application | pr-review/pr-review-suggested-changes | Active |
| Skill-PRReview-019 | outdated comment handling stale | pr-review/pr-review-outdated-comments | Active |
| Skill-PRReview-020 | code owner validation CODEOWNERS | pr-review/pr-review-code-owners | Active |
| Skill-PRReview-021 | review timeline management SLA | pr-review/pr-review-timeline | Active |
| Skill-PRReview-022 | cross-reference linking issues | pr-review/pr-review-cross-reference | Active |
| Skill-PRReview-023 | security review patterns CWE | pr-review/pr-review-security | Active |
| Skill-PRReview-024 | performance review patterns | pr-review/pr-review-performance | Active |
| Skill-PRReview-025 | documentation review completeness | pr-review/pr-review-documentation | Active |
| Skill-PRReview-026 | test coverage review patterns | pr-review/pr-review-test-coverage | Active |
| Skill-PRReview-027 | breaking change detection | pr-review/pr-review-breaking-changes | Active |
| Skill-PRReview-028 | dependency update review | pr-review/pr-review-dependencies | Active |
| Skill-PRReview-029 | rollback planning patterns | pr-review/pr-review-rollback | Active |
| Skill-PRReview-030 | observations patterns learnings general | pr-review/pr-review-observations | Active |

## Protocol Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Protocol-001 | blocking gates RFC-2119 MUST SHOULD | protocol/protocol-blocking-gates | Active |
| Skill-Protocol-002 | template enforcement format validation | protocol/protocol-template-enforcement | Active |
| Skill-Protocol-003 | verification-based enforcement checks | protocol/protocol-verification | Active |
| Skill-Protocol-004 | session protocol compliance rules | protocol/protocol-session | Active |
| Skill-Protocol-005 | handoff protocol agent transitions | protocol/protocol-handoff | Active |
| Skill-Protocol-006 | escalation protocol routing rules | protocol/protocol-escalation | Active |
| Skill-Protocol-007 | exception handling protocol bypass | protocol/protocol-exceptions | Active |
| Skill-Protocol-008 | legacy compatibility migration | protocol/protocol-legacy | Active |
| Skill-Protocol-009 | observations patterns learnings general | protocol/protocol-observations | Active |

## Quality Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Quality-001 | definition of done DoD checklist | quality/quality-definition-of-done | Active |
| Skill-Quality-002 | QA routing agent assignment | quality/quality-qa-routing | Active |
| Skill-Quality-003 | critique escalation patterns | quality/quality-critique-escalation | Active |
| Skill-Quality-004 | test strategy design approach | quality/quality-test-strategy | Active |
| Skill-Quality-005 | coverage metrics measurement | quality/quality-coverage-metrics | Active |
| Skill-Quality-006 | code smells catalog Fowler | quality/code-smells-catalog | Active |
| Skill-Quality-007 | prompt engineering quality gates | quality/quality-prompt-engineering-gates | Active |
| Skill-Quality-008 | review checklist validation | quality/quality-review-checklist | Active |
| Skill-Quality-009 | regression testing patterns | quality/quality-regression-testing | Active |
| Skill-Quality-010 | acceptance criteria validation | quality/quality-acceptance-criteria | Active |
| Skill-Quality-011 | observations patterns learnings general | quality/quality-observations | Active |

## Retrospective Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Retrospective-001 | recursive extraction meta-learning rounds | retrospective/retrospective-001-recursive-extraction | Active |
| Skill-Retrospective-002 | PR learning extraction commit message | retrospective/retrospective-001-pr-learning-extraction | Active |
| Skill-Retrospective-003 | retrospective skill pipeline automation | retrospective/retrospective-002-retrospective-to-skill-pipeline | Active |
| Skill-Retrospective-004 | token impact documentation measurement | retrospective/retrospective-003-token-impact-documentation | Active |
| Skill-Retrospective-005 | evidence-based validation hypothesis | retrospective/retrospective-004-evidence-based-validation | Active |
| Skill-Retrospective-006 | atomic skill decomposition granularity | retrospective/retrospective-005-atomic-skill-decomposition | Active |
| Skill-Retrospective-007 | skill persistence memory durability | retrospective/retrospective-skill-persistence | Active |
| Skill-Retrospective-008 | commit threshold trigger mini-retrospective | retrospective/retrospective-commit-trigger | Active |
| Skill-Retrospective-009 | artifact efficiency concurrent documentation | retrospective/retrospective-artifact-efficiency-pattern | Active |
| Skill-Retrospective-010 | december-17 initial skill extraction | retrospective-2025-12-17 | Active |
| Skill-Retrospective-011 | december-18 linting validation format | retrospective-2025-12-18 | Active |
| Skill-Retrospective-012 | december-24 parallel agent learnings | retrospective-2025-12-24-parallel-agent-learnings | Active |
| Skill-Retrospective-013 | december-26 PR-402 thread lifecycle | retrospective-2025-12-26 | Active |
| Skill-Retrospective-014 | december-27 duplicate entry consolidated | retrospective-2025-12-27 | Active |
| Skill-Retrospective-015 | PR402 acknowledged resolved state model | retrospective-pr402-acknowledged-resolved | Active |
| Skill-Retrospective-016 | Five Whys root cause analysis | retrospective/retrospective-five-whys | Active |
| Skill-Retrospective-017 | observations patterns learnings general | retrospective/retrospective-observations | Active |

## Security Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Security-001 | multi-agent validation chain verification | security/security-multi-agent-validation | Active |
| Skill-Security-002 | input validation sanitize escape | security/security-input-validation | Active |
| Skill-Security-003 | secret detection regex patterns | security/security-secret-detection | Active |
| Skill-Security-004 | injection prevention SQL XSS command | security/security-injection-prevention | Active |
| Skill-Security-005 | authentication patterns tokens sessions | security/security-authentication | Active |
| Skill-Security-006 | authorization RBAC permissions | security/security-authorization | Active |
| Skill-Security-007 | OWASP top 10 vulnerability categories | security/security-owasp-top10 | Active |
| Skill-Security-008 | CWE patterns weakness enumeration | security/security-cwe-patterns | Active |
| Skill-Security-009 | threat modeling STRIDE framework | security/security-threat-modeling | Active |
| Skill-Security-010 | secure coding practices guidelines | security/security-secure-coding | Active |
| Skill-Security-011 | dependency scanning vulnerability | security/security-dependency-scanning | Active |
| Skill-Security-012 | secrets management vault rotation | security/security-secrets-management | Active |
| Skill-Security-013 | audit logging compliance tracking | security/security-audit-logging | Active |
| Skill-Security-014 | encryption patterns data protection | security/security-encryption | Active |
| Skill-Security-015 | API security rate limiting | security/security-api-security | Active |
| Skill-Security-016 | observations patterns learnings general | security/security-observations | Active |

## Serena Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Serena-001 | symbolic tools first LSP efficiency | serena/serena-symbolic-tools | Active |
| Skill-Serena-002 | avoid redundant reads caching | serena/serena-avoid-redundant-reads | Active |
| Skill-Serena-003 | memory-first caching strategy | serena/serena-memory-first | Active |
| Skill-Serena-004 | project activation initialization | serena/serena-project-activation | Active |
| Skill-Serena-005 | symbol navigation find_symbol | serena/serena-symbol-navigation | Active |
| Skill-Serena-006 | memory write persistence storage | serena/serena-memory-write | Active |
| Skill-Serena-007 | memory read retrieval lookup | serena/serena-memory-read | Active |
| Skill-Serena-008 | list memories discovery browsing | serena/serena-list-memories | Active |
| Skill-Serena-009 | token efficiency optimization | serena/serena-token-efficiency | Active |
| Skill-Serena-010 | replace symbol body editing | serena/serena-replace-symbol | Active |
| Skill-Serena-011 | insert before/after positioning | serena/serena-insert-symbol | Active |
| Skill-Serena-012 | find referencing symbols usage | serena/serena-find-references | Active |
| Skill-Serena-013 | get symbols overview structure | serena/serena-symbols-overview | Active |
| Skill-Serena-014 | observations patterns learnings general | serena/serena-observations | Active |

## Session Init Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-SessionInit-001 | serena activation mandatory blocking | session/session-serena-activation | Active |
| Skill-SessionInit-002 | skill validation check invocation | session/session-skill-validation | Active |
| Skill-SessionInit-003 | constraint governance rules enforcement | session/session-constraint-governance | Active |
| Skill-SessionInit-004 | handoff read protocol compliance | session/session-handoff-read | Active |
| Skill-SessionInit-005 | session log creation JSON format | session/session-log-creation | Active |
| Skill-SessionInit-006 | memory search relevant context | session/session-memory-search | Active |
| Skill-SessionInit-007 | observations patterns learnings general | session/session-observations | Active |

## Utilities Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Utilities-001 | markdown fences code block closing | utilities/utility-001-fix-markdown-code-fence-closings | Active |
| Skill-Utilities-002 | pre-commit hook autofix corrections | utilities/utility-002-precommit-hook-autofix | Active |
| Skill-Utilities-003 | security pattern library common patterns | utilities/utility-003-security-pattern-library-88 | Active |
| Skill-Utilities-004 | PathInfo string conversion PowerShell | utilities/utility-004-powershell-pathinfo-string-conversion-94 | Active |
| Skill-Utilities-005 | regex pattern matching utilities | utilities/utilities-regex | Active |
| Skill-Utilities-006 | observations patterns learnings general | utilities/utilities-observations | Active |

## Validation Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-Validation-001 | false positive allowlist suppression | validation/validation-001-validation-script-false-positives | Active |
| Skill-Validation-002 | error message pedagogy user-friendly | validation/validation-002-pedagogical-error-messages | Active |
| Skill-Validation-003 | preexisting issue triage baseline | validation/validation-003-preexisting-issue-triage | Active |
| Skill-Validation-004 | test before retrospective verification | validation/validation-004-test-before-retrospective | Active |
| Skill-Validation-005 | PR feedback gate blocking checks | validation/validation-005-pr-feedback-gate | Active |
| Skill-Validation-006 | self-report verification claims | validation/validation-006-self-report-verification | Active |
| Skill-Validation-007 | cross-reference verification linking | validation/validation-007-cross-reference-verification | Active |
| Skill-Validation-008 | frontmatter validation compliance | validation/validation-007-frontmatter-validation-compliance | Active |
| Skill-Validation-009 | domain index format structure | validation/validation-domain-index-format | Active |
| Skill-Validation-010 | anti-patterns avoid common mistakes | validation/validation-anti-patterns | Active |
| Skill-Validation-011 | baseline triage existing issues | validation/validation-baseline-triage | Active |
| Skill-Validation-012 | tooling patterns automation scripts | validation/validation-tooling-patterns | Active |
| Skill-Validation-013 | test-first verification approach | validation/validation-test-first | Active |
| Skill-Validation-014 | skepticism verification mindset | validation/validation-skepticism | Active |
| Skill-Validation-015 | PR gates validation checks | validation/validation-pr-gates | Active |
| Skill-Validation-016 | observations patterns learnings general | validation/validation-observations | Active |

## Workflow Patterns Skills

| Skill ID | Keywords | File | Status |
|----------|----------|------|--------|
| Skill-WorkflowPatterns-001 | composite action encapsulation DRY | workflow/workflow-composite-action | Active |
| Skill-WorkflowPatterns-002 | shell interpolation safety quoting | workflow/workflow-shell-safety | Active |
| Skill-WorkflowPatterns-003 | matrix artifact patterns parallel | workflow/workflow-matrix-artifacts | Active |
| Skill-WorkflowPatterns-004 | output heredoc multiline values | workflow/workflow-output-heredoc | Active |
| Skill-WorkflowPatterns-005 | verdict tokens parsing status | workflow/workflow-verdict-tokens | Active |
| Skill-WorkflowPatterns-006 | report pattern structured output | workflow/workflow-report-pattern | Active |
| Skill-WorkflowPatterns-007 | run-from-branch dynamic checkout | workflow/workflow-run-from-branch | Active |
| Skill-WorkflowPatterns-008 | batch changes reduce COGS efficiency | workflow/workflow-batch-changes-reduce-cogs | Active |

## Deprecated Skills

| Skill ID | Domain | Deprecated Date | Reason | Replacement |
|----------|--------|-----------------|--------|-------------|
| (none) | - | - | - | - |

## Skill Lifecycle

### States

1. **Draft**: Skill created but not validated
2. **Active**: Skill validated and in use
3. **Deprecated**: Skill superseded or obsolete

### Creation Process

1. Read [skills-index](skills-index.md) memory to check for ID collisions
2. Assign next available skill number in domain
3. Create skill file: `{domain}/{domain}-{number}-{name}.md`
4. Update `skills-index.md` with new entry (status: Draft)
5. After validation, update status to Active

### Deprecation Process

1. Update skill status in index to "Deprecated"
2. Add entry to "Deprecated Skills" section with reason and replacement
3. Preserve deprecated skill file (do NOT delete)
4. Update cross-references to point to replacement
