# PRD: Skill Retrieval Instrumentation

**Version**: 1.0
**Date**: 2025-12-20
**Author**: explainer agent
**Status**: Draft

## Introduction/Overview

The ai-agents repository contains 65+ skill memory files in `.serena/memories/`. These skills capture learned patterns from retrospectives and successful implementations. However, there is no measurement system to answer critical questions:

- Which skills are agents actually reading before taking action?
- How often is each skill retrieved?
- Do agents that retrieve skills produce better outcomes than those that skip retrieval?
- Which skills have never been retrieved and are candidates for pruning?

This feature adds instrumentation to track skill retrieval patterns. The goal is to provide data for skill consolidation decisions and validate that retrospective investment produces measurable ROI.

**Problem Statement**: Skills exist and are documented, but agents may not use them. Without retrieval metrics, you cannot distinguish high-value skills from noise or prove retrospective value.

## Goals

1. Track when agents read skill memory files during sessions
2. Aggregate retrieval counts per skill file (daily and weekly)
3. Identify hot skills (frequently retrieved) vs cold skills (never retrieved over 30 days)
4. Enable correlation analysis: did retrieving skill X prevent known failure Y?
5. Provide data-driven input for skill pruning and consolidation decisions

## Non-Goals (Out of Scope)

1. Measuring skill application (whether agent followed the skill after reading it)
2. Tracking retrieval of non-skill memories (general project context, user preferences)
3. Real-time dashboards or visualization tools (weekly reports are sufficient)
4. Automated skill deletion (requires human review and approval)
5. Skill effectiveness scoring beyond retrieval frequency
6. Integration with external analytics platforms

## User Stories

As a **repository maintainer**, I want to see which skills are retrieved weekly so that I can identify valuable patterns worth preserving.

As a **retrospective agent**, I want to know if new skills are being retrieved so that I can validate that learnings are being applied.

As an **orchestrator agent**, I want data on skill retrieval correlation with session success so that I can decide whether to enforce skill checks at session start.

As a **repository maintainer**, I want to identify skills with zero retrievals over 30 days so that I can archive or consolidate stale content.

## Functional Requirements

### FR-1: Session Log Parsing

The system must parse session log files in `.agents/sessions/*.md` to identify skill retrieval events.

**Input**: Session log markdown files
**Output**: List of skill filenames retrieved during session
**Detection Method**: Search for `mcp__serena__read_memory` calls where `memory_file_name` parameter matches pattern `skill-*` or `skills-*`

**Acceptance Criteria**:

- Correctly identifies skill retrieval from session logs created after 2025-12-15 (when Serena protocol became mandatory)
- Handles multiple retrievals of same skill within one session (count each occurrence)
- Ignores non-skill memory retrievals (user preferences, project context)
- Works with session logs containing tool call errors or partial results

### FR-2: Retrieval Count Aggregation

The system must aggregate skill retrieval counts by time period (daily and weekly).

**Input**: List of skill retrieval events from session logs
**Output**: CSV or markdown table showing skill name, retrieval count, first seen date, last seen date

**Acceptance Criteria**:

- Daily report shows retrievals in last 24 hours
- Weekly report shows retrievals in last 7 days
- Report includes "days since last retrieval" column for identifying cold skills
- Report sorts by retrieval count (descending) by default
- Report includes total session count for normalization (retrievals per session ratio)

### FR-3: Cold Skill Identification

The system must identify skills with zero retrievals over configurable time period (default: 30 days).

**Input**: Aggregated retrieval data, threshold in days
**Output**: List of skill filenames meeting cold skill criteria

**Acceptance Criteria**:

- Correctly identifies skills present in `.serena/memories/` but absent from session logs
- Configurable threshold (default 30 days)
- Excludes newly created skills (created less than threshold days ago)
- Output includes skill creation date for decision context

### FR-4: Correlation Data Export

The system must export retrieval data in format enabling correlation analysis with session outcomes.

**Input**: Session logs with retrieval events and outcome markers
**Output**: CSV with columns: session_id, skills_retrieved, outcome_status, session_duration

**Acceptance Criteria**:

- Session outcome derived from presence of [FAIL], [BLOCKED], [COMPLETE] markers in session log
- Skills retrieved column contains comma-separated list of skill filenames
- Enables external analysis (e.g., "sessions retrieving skill-init-001 have 20 percent fewer [FAIL] markers")
- Missing outcome data handled gracefully (marked as "unknown")

### FR-5: Automated Weekly Report

The system must generate weekly skill retrieval report without manual intervention.

**Input**: Session logs created in last 7 days
**Output**: Markdown report saved to `.agents/metrics/skill-retrieval-YYYY-MM-DD.md`

**Acceptance Criteria**:

- Report runs automatically (GitHub Actions scheduled workflow or pre-commit hook)
- Report includes: top 10 hot skills, skills with zero retrievals in 30 days, retrieval rate trend
- Report commits to repository automatically
- Report generation failures do not block other workflows

## Design Considerations

### Option 1: Session Log Analysis (Recommended)

**Approach**: Parse existing `.agents/sessions/*.md` files to extract `mcp__serena__read_memory` calls.

**Pros**:

- Zero friction for agent workflows (no agent changes required)
- Works retroactively on existing session logs
- Low maintenance (session logs already mandatory per SESSION-PROTOCOL.md)
- PowerShell script can run locally or in GitHub Actions

**Cons**:

- Dependent on agents creating session logs (already enforced by protocol)
- Cannot track retrieval if agent skips session log creation
- Parsing markdown requires pattern matching (fragile if session log format changes)

**Implementation**:

- PowerShell script `scripts/Measure-SkillRetrieval.ps1`
- GitHub Actions workflow scheduled weekly
- Output saved to `.agents/metrics/skill-retrieval-YYYY-MM-DD.md`

### Option 2: Serena MCP Server Instrumentation

**Approach**: Add logging to Serena MCP server to record every `read_memory` call.

**Pros**:

- Most accurate (captures all retrievals regardless of session log quality)
- Real-time data collection
- Can track retrieval even if session log omitted

**Cons**:

- Requires modification to external dependency (Serena)
- Not portable (only works for users running instrumented Serena)
- Higher maintenance burden (must update with Serena version changes)
- Adds external state (log files outside repository)

**Decision**: NOT recommended due to external dependency modification.

### Option 3: Agent Prompt Instrumentation

**Approach**: Add requirement to agent prompts to log skill usage explicitly.

**Pros**:

- Agents self-report retrieval in structured format
- Could capture application intent (not just retrieval)

**Cons**:

- High friction (requires agent prompt changes)
- Trust-based (agent could skip logging)
- Retrospective analysis showed trust-based approaches fail (Session 15 findings)
- Creates additional agent work per retrieval

**Decision**: NOT recommended due to trust-based failure pattern.

### Recommended Approach

**Use Option 1 (Session Log Analysis)** with these implementation details:

- PowerShell script for cross-platform compatibility (project standard per ADR-005)
- Pester tests for parsing logic validation
- GitHub Actions scheduled workflow (weekly)
- Manual execution supported for ad-hoc analysis

## Technical Considerations

### Session Log Format Dependency

Session logs must contain tool call sections showing `mcp__serena__read_memory` invocations. Example:

```xml
<invoke name="mcp__serena__read_memory">
<parameter name="memory_file_name">skill-init-001-serena-mandatory