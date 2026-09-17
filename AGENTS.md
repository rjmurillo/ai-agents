# AGENTS

## Serena Init (BLOCKING)

1. `mcp__serena__activate_project`|2. `mcp__serena__initial_instructions`|fallback: `.serena/memories/<name>.md`|Post-compaction: re-run both

## Retrieval

|APIs: Context7, DeepWiki, WebSearch|Memory: `memory` skill
|Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`|ADRs: `.agents/architecture/README.md`->`ADR-*.md`
|Skills: `.claude/skills/{name}/SKILL.md`|Map: `docs/project-structure.md`->per-dir `AGENTS.md`
|Rules: read `.claude/rules/*.md` by `paths` first|Book depth: `software-engineering-library`|Generators: `.agents/governance/GENERATOR-FILES.md`

Knowledge -> context. Actions -> skills.

## Gates

**Start**:Init Serena|Read latest issue handoff|Resume check|Search mem|Verify git
**Mid**: `git rev-list --count HEAD ^origin/main` notice 10; alert 15 (advisory; issue #5233)
**Pre-PR**: `uv run python scripts/validation/pre_pr.py`|No BLOCKING|Security scan|Style `.gemini/styleguide.md`
**End**:Issue handoff if open|Update Serena|Lint|Commit|Check

## Boundaries

**Always**: Python (ADR-042)|Verify branch|Check skills|Assign issues|PR template|Atomic commits advisory|Scoped lint|Pin Actions SHA|Run changed workflows pre-push|No manifest version (ADR-092)
**Ask First**: Architecture|New ADRs|Breaking|Security
**Autonomy Guardrail**: Internal+reversible: act|External/irreversible: confirm|Ambiguous: act minimal, flag rest
**Never**: Commit secrets|New bash scripts|Logic in YAML (ADR-006)|Raw gh if skill exists|Force push|Skip hooks|Internal refs in src|Scratch in tree
**Never (BLOCKING); each needs its remedy, not just a check**:Ship unrun gen artifact (-> runtime test)|Resolve security thread w/o fix (-> code fix or owner)|Report PR blocked/conflicted w/o fix (-> resolve and re-check)|Skip validation (-> `pre_pr.py`)

## Skill-First

Routing table: `.claude/skills/autoplan/SKILL.md`. Not restated here.
|Lifecycle: /spec /plan /build /test /review /ship
|Merge blocked/conflicted: don't ask; github skill (why_pr_blocked+resolve) or merge-resolver; re-check
|CI-feedback sub-loop: cluster, ladder build->test->review->ship. See `.agents/governance/CI-FEEDBACK-SUBLOOP.md`
|No skill -> autoplan; multi-step/cross-cutting -> orchestrator agent; no return loop (ADR-078)
|New capability: buy-vs-build Quick BEFORE /spec+baseline; >13wk no baseline = prune. Skip: bug/doc/refactor/approved-cap-extension
|Harness work: read agent-harness-reference; mutate via ai-agents-portability-campaign
|Any `ADR-*.md` edit fires adr-review

## Delegation and Model Routing

Route: task shape | verifier strength | failure cost. Never vendor effort labels.
Scope: model labels only | existing roles and safety gates remain authoritative.

| Label | Effort | Route for |
|---|---|---|
| Luna | low/medium | Bounded high-volume discovery, extraction, classification, triage, boilerplate, scaffolding, docs, exact repetitive edits. |
| Haiku | non-reasoning | Simple transformations and tool calls; rolling alias under ADR-080. |
| Terra or Sonnet | medium/high or medium | Known files/patterns, ordinary implementation/review, local repair, moderate analysis. |
| Sol or Opus | medium/high | Ambiguity, architecture, difficult debugging, one irreducible hard find, cross-file or high-recall review, expensive diagnosis. |
| Escalate | acceptance failure | Failed acceptance tests, never vendor effort labels. |

Luna work is disposable; require a compact receipt.

### Healthy Topology

Astra: objective | delegation contract | acceptance test.
Luna: disposable discovery. Terra: bounded implementation. Sol: hard exceptions/high-recall review.
Verifier: tests | diff checks | schema checks | security checks.
Flow: Astra -> Luna/Terra -> Sol on typed exception -> verifier -> Astra acceptance.

Labels are advisory, not registered agents or model IDs.
`orchestrator` performs Astra's coordination after `autoplan` routes multi-agent work.
Harness: resolve supported labels to concrete IDs | unresolved=`model_unavailable` | no silent substitution | record label+ID.

Preserve: entry points | registered roles | handoffs | role-keyed results |
mandatory `security`, `qa`, `critic` routes | ADR-009 hard conflicts -> `high-level-advisor`.

Astra must: decide/decompose | select delegation | delegate, not implement |
resolve tradeoffs | event-driven waits | return deltas, not transcripts |
accept from verifier+compact receipts | stop after acceptance.

Target contract: objective | delta scope | verifier command/artifact | pass criterion |
typed escalation condition+recipient | receipt fields.
Target verifier: deterministic pass/fail without model judgment.
Target receipt: label | concrete ID | scope | changed paths | verifier result |
acceptance status | escalation status+recipient.
Target only; current runtime enforcement is not claimed.

Terra gate: hard verifier | expected diff scope | typed exception |
`acceptance_failed` | `cross_file_contract_missed` | `repair_repeated` | `diff_scope_exceeded`.
After Luna/Terra starts, Sol handles only those exceptions. Escalate, do not add prompts.
Conflicts follow ADR-009, not Sol routing.

Avoid: Astra -> Sol for everything -> Terra/Luna cleanup.
Rule: cheap models perform work | expensive models decide meaning and acceptance.

### Limit Down or Scaffold Up?

Ambiguous/high-consequence/evolving -> limit down to Astra/Sol |
bounded/deterministic/well-specified -> scaffold up Terra/Luna |
architecture/intent/tradeoffs -> do not scaffold down |
objective verifier+cheap failure -> Luna |
one engineer-hour diagnosis -> Terra may lose to Sol.

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `uv run pytest tests/ -x`|`uv run ruff check .`|new skill tests in `tests/skills/<name>/`
Tests (BLOCKING): pos+neg+edge|branches|mock I/O|CLI exits. See `.agents/governance/TESTING-RIGOR.md`

## Stack

Py 3.14 dev; floor: pyproject|UV|PS 7.5+|Node LTS|pytest 9+|gh 2.60+
