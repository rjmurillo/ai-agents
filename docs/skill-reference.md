# Skill Reference

Skills are reusable workflow components that agents and users invoke for common tasks. The AI Agents system includes 49 skills organized by category.

## How to Use Skills

Skills are invoked differently depending on your platform:

**Claude Code:**

```text
/skill-name
```

Or the agent invokes the skill automatically when it matches the task.

**VS Code / Copilot CLI:**

Agents invoke skills internally. You do not call skills directly.

## Skill Categories

| Category | Skills | Purpose |
|----------|--------|---------|
| [GitHub Operations](#github-operations) | 3 | PR management, issue operations, URL handling |
| [Session Management](#session-management) | 6 | Session lifecycle, validation, migration |
| [Memory and Knowledge](#memory-and-knowledge) | 6 | Memory search, curation, exploration, enhancement |
| [Security](#security) | 4 | Scanning, detection, threat modeling, CodeQL |
| [Code Quality](#code-quality) | 5 | Style enforcement, linting, doc coverage, analysis |
| [Architecture and Design](#architecture-and-design) | 7 | ADR review, CVA, decisions, architecture analysis |
| [Planning and Strategy](#planning-and-strategy) | 4 | Planning, pre-mortem, buy-vs-build, Cynefin |
| [Documentation](#documentation) | 3 | Doc sync, markdown fixes, context optimization |
| [Development Workflows](#development-workflows) | 5 | Git workflows, merge resolution, metrics, encoding |
| [Agent and Skill Management](#agent-and-skill-management) | 3 | Skill creation, Serena symbols, reflection |
| [Research](#research) | 3 | Research, programming advice, prompt engineering |

## GitHub Operations

### github

Execute GitHub operations including PRs, issues, labels, comments, merges, and milestones. Wraps `gh` CLI commands with structured output and error handling.

**Subcommands:** Create PR, merge PR, get PR context, get issue context, add labels, create comments.

### pr-comment-responder

PR review coordinator. Gathers comment context, acknowledges feedback, and tracks resolution status for all reviewer comments.

### github-url-intercept

Intercepts GitHub URLs in user input and routes them to the appropriate skill or `gh` CLI command instead of raw web fetches.

## Session Management

### session-init

Creates protocol-compliant JSON session logs with verification gates. Run at the start of every session.

### session-end

Validates and completes session logs before commit. Auto-populates required fields and runs validation checks.

### session-log-fixer

Fixes session protocol validation failures in GitHub Actions. Diagnoses and repairs malformed session log JSON.

### session

Session management and protocol compliance. Provides session lifecycle operations and status queries.

### session-qa-eligibility

Checks investigation session QA skip eligibility per ADR-034. Validates whether a session qualifies for reduced QA gates.

### session-migration

Migrates session logs from markdown to JSON format. Use when processing legacy session logs.

## Memory and Knowledge

### memory

Unified four-tier memory system for AI agents. Supports semantic search, knowledge graphs, and cross-session context persistence via Serena and Forgetful.

### memory-enhancement

Manages memory citations, verifies code references, and tracks content freshness across the knowledge base.

### memory-documentary

Generates evidence-based documentary reports by searching across the full memory system. Synthesizes findings from multiple memory tiers.

### curating-memories

Guidance for maintaining memory quality through curation. Covers deduplication, freshness scoring, and relevance assessment.

### exploring-knowledge-graph

Guidance for deep knowledge graph traversal across memories, entities, and relationships.

### using-forgetful-memory

Guidance for using Forgetful semantic memory effectively. Covers query formulation, result interpretation, and storage patterns.

## Security

### security-scan

Scans code content for CWE-22 (path traversal) and CWE-78 (command injection) vulnerabilities. Returns structured findings with severity ratings.

### security-detection

Detects infrastructure and security-critical file changes to trigger appropriate review workflows.

### threat-modeling

Structured security analysis using the OWASP Four-Question Framework. Produces threat models with attack trees, risk ratings, and mitigations.

### codeql-scan

Executes CodeQL security scans with language detection, database creation, and result analysis. Integrates with GitHub's code scanning.

## Code Quality

### style-enforcement

Validates code against style rules from .editorconfig, StyleCop, and project conventions. Reports violations with fix suggestions.

### analyze

Analyzes codebase architecture, security posture, or code quality. Produces structured assessment reports.

### code-qualities-assessment

Assesses code maintainability through 5 foundational qualities: cohesion, coupling, DRY, encapsulation, and testability.

### doc-coverage

Detects missing documentation in code (XML docs, docstrings, JSDoc). Reports coverage gaps by file and symbol.

### incoherence

Detects contradictions between documentation and code, ambiguous definitions, and inconsistent patterns across the codebase.

## Architecture and Design

### adr-review

Multi-agent debate orchestration for Architecture Decision Records. Coordinates architect, critic, and independent-thinker to review ADRs.

### cva-analysis

Systematic abstraction discovery using Commonality Variability Analysis. Identifies shared behavior and variation points across implementations.

### decision-critic

Structured decision critic that systematically stress-tests recommendations. Evaluates evidence quality, alternative coverage, and risk assessment.

### serena-code-architecture

Architectural analysis workflow using Serena symbols and knowledge graphs. Maps dependencies, coupling, and cohesion across the codebase.

### chaos-experiment

Designs and documents chaos engineering experiments. Guides steady-state hypothesis definition, blast radius planning, and result analysis.

### slo-designer

Designs Service Level Objectives with SLIs, targets, alerting thresholds, and error budget policies.

### using-serena-symbols

Guidance for using Serena's LSP-powered symbol analysis. Covers symbol search, reference finding, and code navigation.

## Planning and Strategy

### planner

Interactive planning and execution for complex tasks. Breaks down work, tracks progress, and manages dependencies.

### pre-mortem

Guides prospective hindsight analysis to identify project risks before they materialize. Surfaces failure modes and mitigations.

### buy-vs-build-framework

Strategic framework for evaluating build, buy, partner, or defer decisions. Scores options across cost, time, risk, and control dimensions.

### cynefin-classifier

Classifies problems into Cynefin Framework domains (Clear, Complicated, Complex, Chaotic). Recommends appropriate response strategies per domain.

## Documentation

### doc-sync

Synchronizes CLAUDE.md navigation indexes and README.md architecture diagrams with the current codebase state.

### fix-markdown-fences

Repairs malformed markdown code fence closings. Fixes common authoring errors in fenced code blocks.

### context-optimizer

Analyzes skill content for optimal placement (Skill vs Passive Context). Recommends whether content should be loaded on-demand or always present.

## Development Workflows

### git-advanced-workflows

Master advanced Git workflows including rebasing, cherry-picking, worktree management, and conflict resolution strategies.

### merge-resolver

Resolves merge conflicts by analyzing git history and commit intent. Produces clean merges with preserved intent.

### metrics

Collects agent usage metrics from git history and generates health dashboards for monitoring agent effectiveness.

### encode-repo-serena

Systematically populates the knowledge base using Serena's code analysis tools. Maps symbols, relationships, and patterns.

### steering-matcher

Matches file paths against steering file glob patterns to determine which governance rules apply to changed files.

## Agent and Skill Management

### SkillForge

Intelligent skill router and creator. Analyzes input to recommend existing skills or creates new ones following project conventions.

### slashcommandcreator

Autonomous meta-skill for creating high-quality custom slash commands. Follows frontmatter standards and testing patterns.

### reflect

Critical learning capture. Extracts HIGH/MED/LOW confidence patterns from session work and stores them as reusable knowledge.

## Research

### research-and-incorporate

Researches external topics, creates comprehensive analysis, and determines how findings should be incorporated into the project.

### programming-advisor

Evaluates existing solutions (libraries, SaaS, open source) before writing new software. Prevents NIH syndrome.

### prompt-engineer

Optimizes system prompts for Claude Code agents using proven prompt engineering patterns and evaluation frameworks.
