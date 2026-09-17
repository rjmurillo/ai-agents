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

Route by task shape, verifier strength, and failure cost. Do not route by vendor effort labels.
This section governs model selection only. Existing agent roles and safety gates remain authoritative.

### Default Routing

1. Luna low/medium for bounded, high-volume work:
   - repository inventory, search and extraction, classification, log triage
   - boilerplate, simple configuration, test scaffolding, straightforward documentation
   - repetitive edits with exact checks
2. Haiku non-reasoning for simple transformations and tool calls. Treat Haiku as a rolling alias under ADR-080.
3. Terra medium/high or Sonnet medium for normal implementation and review.
4. Sol or Opus for ambiguity, architecture, and failures expensive to review.
5. Escalate on failed acceptance tests, not on vendor effort labels.

Luna may produce verbose raw output. Keep its work disposable and require a compact receipt.

### Healthy Topology

1. Astra defines the objective, delegation contract, and acceptance test.
2. Luna performs disposable discovery.
3. Terra implements bounded changes.
4. Sol handles technically hard exceptions or high-recall review.
5. An independent verifier runs tests, diff checks, schema checks, and security checks.

Default flow: Astra -> Luna/Terra -> Sol on typed technical exceptions -> Astra acceptance.

These names are advisory capability labels. They do not rename registered agents.
Astra is the parent coordination label. `orchestrator` performs that role here.
`autoplan` remains the front-door router for multi-agent work.
It hands that work to `orchestrator` for coordination and synthesis.

Routing precedence:

- Astra owns the objective, decomposition, delegation, and final acceptance.
- Direct Sol is allowed for technical ambiguity with consequential tradeoffs, architecture, difficult debugging, high-recall review, or high diagnosis cost.
- After Luna or Terra starts, Sol handles only `acceptance_failed`, `cross_file_contract_missed`, `repair_repeated`, and `diff_scope_exceeded`.
- Worker-result conflicts follow ADR-009 and route hard conflicts to `high-level-advisor`, not Sol.
- Preserve mandatory `security`, `qa`, and `critic` routes from the existing algorithm.

Luna work includes repository inventory, search and extraction, classification, log triage, boilerplate, simple configuration, test scaffolding, straightforward documentation, and repetitive edits with exact checks.

Terra work includes known files, known patterns, written acceptance criteria, ordinary implementation, local test repair, and moderate analysis.

Sol work includes difficult debugging, one irreducible hard find, cross-file reasoning, high-recall technical review, and specialist work after Terra fails.

The harness may map these labels to concrete model IDs when supported.
They are not agent names or model IDs.
Before dispatch, Astra resolves each label through the active harness registry or API.
Record both label and concrete model ID in each worker receipt.
Unresolved mappings use `model_unavailable`.
Never silently substitute a vendor effort label.
The existing routing algorithm's role results remain synthesis data.
The dispatch boundary may wrap them in receipts before Astra accepts them.

Astra must:

- decide what the task means and decompose it
- select which work is worth delegating
- delegate rather than implement delegated work
- resolve consequential tradeoffs
- review whether the result satisfies the real intent
- use event-driven waits
- return deltas, not transcripts, with compact worker receipts
- accept or reject based on verifier output and compact worker receipts
- stop after acceptance

Every target delegation contract names the objective, delta scope, verifier command or immutable artifact, pass criterion, escalation type, escalation recipient, and receipt fields. A target hard verifier produces a deterministic pass or fail result without model judgment. A target typed escalation names the failed condition and its next recipient. Minimum target receipt fields: assigned routing label, concrete model ID, scope completed, changed paths, verifier command and result, acceptance status, escalation status, and escalation recipient.

These are target coordinator contracts, not claims about current runtime enforcement. Existing `autoplan`, `orchestrator`, and routing algorithm contracts remain authoritative for entry points, registered agents, mandatory routes, handoffs, and role-keyed synthesis results.

Terra requires a hard verifier and typed escalation. Encode expected diff scope in acceptance tests. Use `acceptance_failed`, `cross_file_contract_missed`, `repair_repeated`, and `diff_scope_exceeded` for technical exceptions. Escalate instead of adding more prompts.

Do not use Astra -> Sol for everything -> Terra/Luna afterward. That makes expensive coordination and execution the default, then reduces cheaper models to cleanup. Sol is expensive because persistence, retries, and replay cost output. Do not treat universal verbosity as the routing rule.

### Limit Down or Scaffold Up?

- Ambiguous, high-consequence, evolving task: limit down to Astra or Sol. Their capability is scarce. Extra instructions prune scope, but do not replace judgment.
- Well-specified, bounded, deterministic task: scaffold up Terra or Luna. Tools and verifiers can replace reasoning that does not need to happen in the model.
- Architecture, intent recovery, or consequential tradeoffs: do not scaffold Luna or Terra into that role. Missing capability becomes correction and review cost.
- Objective verifier and cheap failure: route aggressively down. Luna is the best value candidate.
- Wrong result costs an engineer an hour to diagnose: the price gap narrows. Terra may lose to Sol.

Durable rule: cheap models perform work. Expensive models decide what work means and whether it is acceptable.

## Standards

Commits: `<type>(<scope>): <desc>` + `Co-Authored-By:`
Exit codes: 0=ok|1=logic|2=config|3=external|4=auth
Coverage: 100% security|80% business|60% docs
Tests: `uv run pytest tests/ -x`|`uv run ruff check .`|new skill tests in `tests/skills/<name>/`
Tests (BLOCKING): pos+neg+edge|branches|mock I/O|CLI exits. See `.agents/governance/TESTING-RIGOR.md`

## Stack

Py 3.14 dev; floor: pyproject|UV|PS 7.5+|Node LTS|pytest 9+|gh 2.60+
