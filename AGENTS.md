# AGENTS.md

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`

## Retrieval-Led Reasoning

Read first, reason second. Pre-training last resort.

|APIs: Context7, DeepWiki, WebSearch
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
|Memory: `memory` skill, not `list_memories`
|ADRs: `.agents/architecture/ADR-*.md`
|Protocol: `.agents/SESSION-PROTOCOL.md`
|Skills: `.claude/skills/{name}/SKILL.md`
|Generators (edit source): `.agents/governance/GENERATOR-FILES.md`

## Session Gates

**Start**: Init Serena|Read HANDOFF.md + latest issue handoff + Verify-on-Resume|Session log|Search memories|Verify git
**Mid**: `Commit X/20 (ADR-008)`|Warn at 15+
**Pre-PR**: `python3 scripts/validation/pre_pr.py`|No BLOCKING|Security scan|Style: `.gemini/styleguide.md`
**End**: Complete log|Preserve HANDOFF.md|Issue handoff if open|Update Serena|Lint|Commit|Validate JSON

## Boundaries

**Always**: Python new scripts (ADR-042)|Verify branch|Update Serena|Check skills|Assign issues|PR template|Atomic commits ≤5 files|Scoped lint|Pin Actions to SHA|Run changed workflows pre-push|Bump `plugin.json` semver on plugin-source change
**Ask First**: Architecture changes|New ADRs|Breaking changes|Security
**Autonomy Guardrail**: Internal+reversible (read,edit,memory): act|External/Irreversible: confirm|Ambiguous: act minimal, flag rest
**Never**: Commit secrets|Update HANDOFF.md|Use bash|Skip validation|Logic in YAML (ADR-006)|Raw gh when skills exist|Force push|Skip hooks|Internal refs in src/|Scratch in working tree (`$TMPDIR`/`mktemp`)|Resolve security threads without vuln fix (CWE/OWASP/CVE) in code|Ship gen'd artifact unrun in target runtime

## Context Type Decision

Knowledge → passive context (@imports). Actions → skills.

|Passive: ref every turn, outside training, <8KB
|Skills: tool access, workflows, user-triggered, file mutation

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Conflicts: merge-resolver
|Session: session-init, session-end|CI fix: session-log-fixer|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect
|Lifecycle: /spec, /plan, /build, /test, /review, /ship
|CI-feedback sub-loop: see `.agents/governance/CI-FEEDBACK-SUBLOOP.md`
|New capability: run buy-vs-build-framework Quick tier BEFORE spec-generator|Skip: bug fixes, doc-only, refactors w/o new capability, approved extensions

### ADR Review (BLOCKING)

Any `ADR-*.md` or `SESSION-PROTOCOL.md` create/edit fires adr-review.

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `tests/`|`.claude/skills/<name>/tests/`|`.agents/security/benchmarks/`
Tests (BLOCKING): pos+neg+edge|every branch|mock I/O|CLI argv exits. See `.agents/governance/TESTING-RIGOR.md`

## Stack

Python 3.14|UV|PowerShell 7.5.4+|Node LTS|Pester 5.7.1|pytest 8+|gh 2.60+
