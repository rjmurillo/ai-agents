# AGENTS.md

Cross-platform agent instructions for Claude Code, Copilot CLI, Cortex, Factory Droid.

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`

## Retrieval-Led Reasoning

Read first, reason second. Pre-training is last resort.

|APIs: Context7, DeepWiki, WebSearch
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
|Patterns: Serena `mcp__serena__read_memory`
|ADRs: `.agents/architecture/ADR-*.md`
|Protocol: `.agents/SESSION-PROTOCOL.md`
|Skills: `.claude/skills/{name}/SKILL.md`

## Session Gates

**Start**: Init Serena|Read HANDOFF.md|Create session log|Search memories|Verify git
**Mid**: Display `Commit X/20 (ADR-008)`|Warn at 15+
**Pre-PR**: `Validate-PRReadiness.ps1`|No BLOCKING verdicts|Security scan
**End**: Complete log|Preserve HANDOFF.md|Update Serena|Lint|Commit|Validate JSON

## Boundaries

**Always**: Python for new scripts (ADR-042)|Verify branch|Update Serena|Check skills|Assign issues|Use PR template|Atomic commits (≤5 files)|Scoped lint|Pin Actions to SHA|Run `gh act` locally
**Ask First**: Architecture changes|New ADRs|Breaking changes|Security-sensitive
**Never**: Commit secrets|Update HANDOFF.md|Use bash|Skip validation|Logic in YAML (ADR-006)|Raw gh when skills exist|Force push|Skip hooks|Internal refs in src/

## Context Type Decision

Knowledge goes in passive context (@imported docs). Actions stay as skills. Passive context eliminates decision points. See `.agents/analysis/vercel-passive-context-vs-skills-research.md`.

|Passive context: reference knowledge every turn, content outside training data, <8KB compressed
|Skills: tool access needed, vertical workflows, user-triggered, file mutation or API calls

## Skill-First

|PRs: GitHub|Reviews: pr-comment-responder|Conflicts: merge-resolver
|Session: session-init, session-end|CI fix: session-log-fixer|Push: /push-pr
|Security: security-detection|Quality: analyze|Learn: reflect
|Lifecycle: /spec, /plan, /build, /test, /review, /ship

### ADR Review (BLOCKING)

Any `.agents/architecture/ADR-*.md` or `.agents/SESSION-PROTOCOL.md` create/edit triggers mandatory adr-review skill.

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

## Testing Rigor (BLOCKING for code changes)

**Every new function MUST have positive AND negative tests.** Happy path alone is insufficient. Don't ship "the change works" with only success-case tests; bots will catch what tests missed (whitespace, type validation, error paths, conditional branches).

|Cases: pos (valid input → expected output) + neg (invalid → idiomatic error) + edge (whitespace, empty, null/None, type-mismatch)
|Error paths: every `raise`/`throw`/error-return branch exercised
|Conditional output: every if/else branch in user-facing strings exercised
|External I/O: mock subprocess, API calls, file reads (no live deps in unit tests)
|CLI: test argv-failure exits, exit codes, stdout vs --output

**Pattern checklist** (apply per function):

- [ ] pos test for happy path
- [ ] neg test asserts the language's idiomatic error on bad input
- [ ] edge tests: whitespace, empty, null/None, wrong type
- [ ] every error-emitting branch exercised
- [ ] every conditional branch exercised
- [ ] external dependencies mocked

**Verify before commit** with the stack's coverage tool, gated to the project target. Examples (use the right one for the file you changed):

- **Python**: `python3 -m coverage run --source=<dir> -m pytest && python3 -m coverage report -m --include='<file>' --fail-under=<target>`
- **PowerShell**: `Invoke-Pester -CodeCoverage <files> -CodeCoverageOutputFile cov.xml` then assert `(Import-Clixml cov.xml).CoveragePercent -ge <target>`
- **Node/TS**: `c8 --100 npm test` or `jest --coverage --coverageThreshold`
- **Go**: `go test -cover -coverprofile=cov.out ./... && go tool cover -func=cov.out`
- **C#/.NET**: `dotnet test --collect:"XPlat Code Coverage"` with `coverlet.runsettings` thresholds

100% block coverage on changed files. Exclude only language-equivalent unreachable defensive branches (Python `# pragma: no cover`, Go `default:` panic guards, etc.) with written justification.

## Stack

Python 3.14|UV|PowerShell 7.5.4+|Node LTS|Pester 5.7.1|pytest 8+|gh 2.60+

## Refs

`.agents/SESSION-PROTOCOL.md`|`.agents/HANDOFF.md`|`.agents/governance/`|`.gemini/styleguide.md`
