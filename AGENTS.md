# AGENTS.md

Cross-platform agent instructions for Claude Code, Copilot CLI, Cortex, Factory Droid.

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`

## Retrieval-Led Reasoning

Read first, reason second. Pre-training is last resort.

| Type | Source |
|------|--------|
| APIs | Context7, DeepWiki, WebSearch |
| Constraints | `.agents/governance/PROJECT-CONSTRAINTS.md` |
| Patterns | Serena `mcp__serena__read_memory` |
| ADRs | `.agents/architecture/ADR-*.md` |
| Protocol | `.agents/SESSION-PROTOCOL.md` |
| Skills | `.claude/skills/{name}/SKILL.md` |

## Session Gates

**Start**: Init Serena|Read HANDOFF.md|Create session log|Search memories|Verify git
**Mid**: Display `Commit X/20 (ADR-008)`|Warn at 15+
**Pre-PR**: `Validate-PRReadiness.ps1`|No BLOCKING verdicts|Security scan
**End**: Complete log|Preserve HANDOFF.md|Update Serena|Lint|Commit|Validate JSON

## Boundaries

**Always**: Python for new scripts (ADR-042)|Verify branch|Update Serena|Check skills|Assign issues|Use PR template|Atomic commits (≤5 files)|Scoped lint|Pin Actions to SHA|Run `gh act` locally
**Ask First**: Architecture changes|New ADRs|Breaking changes|Security-sensitive
**Never**: Commit secrets|Update HANDOFF.md|Use bash|Skip validation|Logic in YAML (ADR-006)|Raw gh when skills exist|Force push|Skip hooks|Internal refs in src/

## Skill-First

| Op | Skill |
|----|-------|
| PRs | github |
| Reviews | pr-comment-responder |
| Conflicts | merge-resolver |
| Session | session-init, session-end |
| CI fix | session-log-fixer |
| Push | /push-pr |
| Security | security-detection |
| Quality | analyze |
| Learn | reflect |

## Agents

| Agent | Purpose | Model |
|-------|---------|-------|
| orchestrator | coordination | opus |
| analyst | research | sonnet |
| architect | ADRs, governance | sonnet |
| implementer | code, tests | sonnet |
| critic | validation | sonnet |
| qa | testing | sonnet |
| security | threats, OWASP | sonnet |
| devops | CI/CD | sonnet |
| pr-comment-responder | review triage | sonnet |
| merge-resolver | conflict resolution | sonnet |
| retrospective | learning | haiku |
| memory | cross-session | haiku |

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `tests/`|`.claude/skills/<name>/tests/`|`.agents/security/benchmarks/`

## Stack

Python 3.12|UV|PowerShell 7.5.4+|Node LTS|Pester 5.7.1|pytest 8+|gh 2.60+

## Refs

`.agents/SESSION-PROTOCOL.md`|`.agents/HANDOFF.md`|`.agents/governance/`|`.gemini/styleguide.md`
