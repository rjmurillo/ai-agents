# AGENTS.md

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`

## Retrieval-Led Reasoning

Read first, reason second. Pre-training last resort.

|APIs: Context7, DeepWiki, WebSearch
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
|Patterns: Serena `mcp__serena__read_memory`
|ADRs: `.agents/architecture/ADR-*.md`
|Protocol: `.agents/SESSION-PROTOCOL.md`
|Skills: `.claude/skills/{name}/SKILL.md`

## Session Gates

**Start**: Init Serena|Read HANDOFF.md + latest issue handoff + Verify-on-Resume|Session log|Search memories|Verify git
**Mid**: `Commit X/20 (ADR-008)`|Warn at 15+
**Pre-PR**: `python3 scripts/validation/pre_pr.py`|No BLOCKING|Security scan
**End**: Complete log|Preserve HANDOFF.md|Issue handoff (template) if open|Update Serena|Lint|Commit|Validate JSON

## Boundaries

**Always**: Python new scripts (ADR-042)|Verify branch|Update Serena|Check skills|Assign issues|PR template|Atomic commits (≤5 files)|Scoped lint|Pin Actions to SHA|`gh act` locally
**Ask First**: Architecture changes|New ADRs|Breaking changes|Security-sensitive
**Autonomy Guardrail**: Internal+reversible (read,edit,memory): act|External/Irreversible: confirm|Ambiguous: act minimal, flag rest
**Never**: Commit secrets|Update HANDOFF.md|Use bash|Skip validation|Logic in YAML (ADR-006)|Raw gh when skills exist|Force push|Skip hooks|Internal refs in src/|Scratch in working tree (use `$TMPDIR`/`mktemp`)

## Context Type Decision

Knowledge → passive context (@imports). Actions → skills.

|Passive: ref every turn, outside training, <8KB
|Skills: tool access, workflows, user-triggered, file mutation

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Conflicts: merge-resolver
|Session: session-init, session-end|CI fix: session-log-fixer|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect
|Lifecycle: /spec, /plan, /build, /test, /review, /ship
|New capability (Context/module/scanner/validator/pipeline): run buy-vs-build-framework Quick tier min BEFORE spec-generator|Skip: bug fixes, doc-only, refactors w/o new capability, already-approved extensions

### ADR Review (BLOCKING)

Any `ADR-*.md` or `SESSION-PROTOCOL.md` create/edit fires adr-review skill.

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
