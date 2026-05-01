# AGENTS.md

Cross-platform agent instructions.

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`

## Retrieval-Led Reasoning

Read first, reason second. Pre-training as last resort.

|APIs: Context7, DeepWiki, WebSearch
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
|Patterns: Serena `mcp__serena__read_memory`
|ADRs: `.agents/architecture/ADR-*.md`
|Protocol: `.agents/SESSION-PROTOCOL.md`
|Skills: `.claude/skills/{name}/SKILL.md`

## Session Gates

**Start**: Init Serena|Read HANDOFF.md|Read latest issue handoff + Verify-on-Resume|Session log|Search memories|Verify git
**Mid**: `Commit X/20 (ADR-008)`|Warn at 15+
**Pre-PR**: `python3 scripts/validation/pre_pr.py`|No BLOCKING|Security scan
**End**: Complete log|Preserve HANDOFF.md|Write issue handoff from template if open|Update Serena|Lint|Commit|Validate JSON

## Boundaries

**Always**: Python for new scripts (ADR-042)|Verify branch|Update Serena|Check skills|Assign issues|Use PR template|Atomic commits (≤5 files)|Scoped lint|Pin Actions to SHA|Run `gh act` locally
**Ask First**: Architecture changes|New ADRs|Breaking changes|Security-sensitive
**Autonomy Guardrail**: Internal+reversible (read, edit, delegate-internal, memory write): act|External (PR, post, side-effect) or Irreversible (delete, overwrite, revoke): confirm first|Ambiguous (could expand routing): act on minimal scope, flag remainder|Source: exp-026|Overrides "act immediately" guidance in agent prompts. Distinct from `agent-design-principles.md` Principle 6 (Consistent Interface).
**Never**: Commit secrets|Update HANDOFF.md|Use bash|Skip validation|Logic in YAML (ADR-006)|Raw gh when skills exist|Force push|Skip hooks|Internal refs in src/

## Context Type Decision

Knowledge → passive context (@imports). Actions → skills.

|Passive: ref every turn, outside training, <8KB
|Skills: tool access, workflows, user-triggered, file mutation

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Conflicts: merge-resolver
|Session: session-init, session-end|CI fix: session-log-fixer|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect
|Lifecycle: /spec, /plan, /build, /test, /review, /ship

### ADR Review (BLOCKING)

Any `ADR-*.md` or `SESSION-PROTOCOL.md` create/edit fires adr-review skill.

## Agents

|orchestrator: coordination (opus)|analyst: research|architect: ADRs, governance
|implementer: code, tests|critic: validation|qa: testing
|security: threats, OWASP|devops: CI/CD|pr-comment-responder: review triage
|merge-resolver: conflict resolution|retrospective: learning (haiku)|memory: cross-session (haiku)

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `tests/`|`.claude/skills/<name>/tests/`|`.agents/security/benchmarks/`
Tests (BLOCKING): pos+neg+edge|every branch|mock I/O|CLI argv exits. See `.agents/governance/TESTING-RIGOR.md`.

## Stack

Python 3.14|UV|PowerShell 7.5.4+|Node LTS|Pester 5.7.1|pytest 8+|gh 2.60+

## Refs

`.agents/SESSION-PROTOCOL.md`|`.agents/HANDOFF.md`|`.agents/governance/`|`.gemini/styleguide.md`
