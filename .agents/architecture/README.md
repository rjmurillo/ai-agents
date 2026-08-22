# Architecture Decision Records

Current state of the decision corpus, grouped by lifecycle status. Start here
rather than grepping `ADR-*.md`: a keyword match in a superseded record reads
exactly like a keyword match in an accepted one.

Status comes from each record's YAML frontmatter (ADR-073), never from its prose.
Regenerate after any ADR change with `uv run python build/scripts/build_all.py`.

## Querying the corpus directly

This table is a convenience, not the source of truth. The frontmatter is, and
Python reads it with no extra dependency:

```python
import pathlib, yaml

for path in sorted(pathlib.Path('.agents/architecture').glob('ADR-[0-9]*.md')):
    text = path.read_text(encoding='utf-8')
    if not text.startswith('---'):
        continue  # no frontmatter: see Needs backfill below
    front = yaml.safe_load(text[3 : text.index('\n---', 3)]) or {}
    if str(front.get('status', '')).strip().lower() == 'accepted':
        print(front.get('id') or path.name)
```

**Normalise before comparing, as above.** Both gates that bucket a record by
status lower and strip it first: `_status_of` in
`scripts/validation/check_adr_lifecycle.py` returns
`str(value).strip().lower()`, and this generator does the same. So
`status: Accepted` passes the `status-enum` gate and lands under Accepted in
the table below, while a bare `== 'accepted'` misses it. Every record carries
a lowercase value today, which is exactly why the mismatch would not announce
itself.

**This snippet does not detect duplicate keys, and the gates do.**
`yaml.safe_load` resolves a repeated `status:` last-wins and silently, so a
record declaring `proposed` in the line a human reads and `accepted` lower in
the same block would print as accepted here. `check_adr_lifecycle` and this
generator both reject that at the parser, so a corpus passing the gates has
none. Run the gate before trusting a query on a tree you have not validated;
the snippet is a convenience for reading a known-good corpus, not an
independent check.

Python rather than `yq` deliberately. Python is the repo's native tooling
(ADR-042) and `yaml` is already a dependency, so this adds nothing. The `yq` on
PATH here is the jq wrapper, which has no front-matter mode and fails on a
markdown file; it needs a `sed` pre-extract and a subprocess per record. One
documented method, not two, because a second one is redundancy that drifts.

**Read the `continue` above before trusting any query.** A record with no
frontmatter is invisible to every frontmatter query, so a count answers for the
records that have it while appearing to answer for all of them. The Needs
backfill section below is the honest denominator, and issue #5190 closes it.

**This snippet crashes on unterminated frontmatter; it does not silently
drop it.** `text.startswith('---')` is false only for a record with no
schema at all, which `continue`s past. A record whose opening `---` fence
never closes still starts with `---`, so it skips that `continue` and
reaches `text.index('\n---', 3)`, which raises `ValueError` (verified by
running both cases; Copilot found the original claim backwards on PR
#5209). The real generator's `parse_frontmatter` raises the same way, on
purpose: a malformed schema is an author's defect to see, not a record to
drop quietly into Needs backfill. Run the gate rather than this snippet
when that distinction matters.

## Accepted

These bind today.

| ADR | Title | Date | Decision |
| --- | --- | --- | --- |
| [ADR-003](ADR-003-agent-tool-selection-criteria.md) | Role-Specific Tool Allocation for Multi-Agent System | 2025-12-16 | Chosen option: "Option 2: Role-specific tool allocation", because it provides the optimal balance of context efficiency, role clarity, and operational capability. |
| [ADR-023](ADR-023-quality-gate-prompt-testing.md) | Quality Gate Prompt Structural Validation | 2025-12-26 | Chosen option: "Pester Structural Tests", because it provides immediate, repeatable validation of prompt structure with minimal infrastructure overhead, while acknowledging that runtime behavioral... |
| [ADR-034](ADR-034-investigation-session-qa-exemption.md) | Investigation Session QA Exemption | 2025-12-30 | Add investigation-only session exemption to pre-commit QA validation with staged-file guardrails. |
| [ADR-042](ADR-042-python-migration-strategy.md) | Python Migration Strategy | 2026-01-17 | Migrate the ai-agents project from PowerShell to Python as the primary scripting language over a 12-24 month phased migration period. |
| [ADR-055](ADR-055-github-actions-runner-selection.md) | GitHub Actions Runner Selection | 2025-12-29 | Default to ARM64 runners for all Linux workflows unless documented architectural constraints exist. |
| [ADR-057](ADR-057-prompt-behavioral-evaluation.md) | Prompt Behavioral Evaluation Methodology | 2026-04-19 | Adopt scenario-based LLM evaluation as the standard method for validating behavioral correctness of prompt changes. |
| [ADR-063](ADR-063-memory-skill-decomposition.md) | Decompose the Memory Skill Into Focused Sub-Skills | 2026-06-01 | Decompose the monolithic `memory` skill into focused sub-skills split by operation, keep `memory` as a thin router that delegates, and preserve the `memory` skill name so existing callers do not... |
| [ADR-066](ADR-066-hook-fail-open-reconciliation.md) | Hook Fail-Open Reconciliation (Prevention-First, Fail-Closed-and-Loud) | 2026-06-02 | Chosen option: 3 - prevention-first, fail-closed-and-loud, because the #2205 incident proved that launcher-level fail-open does not protect users. |
| [ADR-068](ADR-068-consolidated-hook-dispatcher.md) | Consolidated Per-Event Hook Dispatcher | 2026-07-31 | Generate one dispatcher host entry per active, safely consolidatable Copilot hook event. |
| [ADR-071](ADR-071-plugin-hook-runtime-contract-verification.md) | Plugin Hook Runtime-Contract Verification | - | Anchor every plugin hook command to the plugin root. |
| [ADR-073](ADR-073-adr-lifecycle-frontmatter.md) | Machine-Readable ADR Lifecycle Frontmatter | 2026-06-19 | Adopt a queryable lifecycle frontmatter schema as the machine-readable source of truth for ADR state, retaining the human-readable `## Status` prose section as a secondary rendering. |
| [ADR-074](ADR-074-security-review-quick-pass-mode.md) | Bounded Security-Review Quick-Pass Mode | 2026-06-17 | Add a bounded quick-pass mode to security review, governed by a diff-scope classifier, a caller-enforced deadline, and an extended verdict taxonomy. |
| [ADR-076](ADR-076-pr-autofix-branch-ownership-lease.md) | PR-Autofix Branch-Ownership Lease | 2026-06-17 | Adopt a PR-comment-backed, advisory, fail-open branch-ownership lease that `pr-autofix` (local) and remote review/autofix routines acquire before committing fix work to a shared PR branch, and... |
| [ADR-080](ADR-080-model-pin-justification-policy.md) | Model Pins Require Cited Eval Evidence | 2026-07-11 | Default every skill, agent, and command to the harness-inherited model. |
| [ADR-081](ADR-081-confidence-elicitation-experiment.md) | Confidence Elicitation Is a Shadow Study, Not a Shipped Gate | 2026-07-11 | Do not ship confidence elicitation as a blocking PreToolUse hook. |
| [ADR-082](ADR-082-claude-hook-group-dispatch.md) | Claude-Side Consolidated Hook Group Dispatch | 2026-07-16 | One process per (event, matcher) group on the Claude side. |
| [ADR-083](ADR-083-copilot-dogfood-surface-separation.md) | Dogfood the Shipped Copilot Base and Separate Ship-vs-Internal Surface | 2026-07-20 | Adopt a per-item surface tag, split the Copilot form-factor into a shipped base plus a local-only internal overlay, and dogfood both by installing them the way a customer installs the base. |
| [ADR-084](ADR-084-vendored-hook-roi-bar.md) | Vendored-Hook ROI Bar | 2026-07-20 | A hook may ship in a vendored plugin surface only if it delivers value in a consumer's own repository. |
| [ADR-085](ADR-085-cross-harness-permission-surface-asymmetry.md) | Cross-Harness Permission-Surface Asymmetry and Hook Survivor Disposition | 2026-07-31 | A vendored guard hook may be replaced by host-native permissions only when all three hold: |
| [ADR-086](ADR-086-lefthook-local-hook-orchestration.md) | Lefthook for Local Git Hook Orchestration | 2026-07-20 | Use Lefthook 2.1.10 as the only local Git hook orchestrator. |
| [ADR-092](ADR-092-omit-plugin-manifest-version.md) | Omit `version` From Plugin Manifests and Resolve Freshness From the Commit SHA | 2026-08-01 | Delete `version` from all three packaged plugin manifests and keep it deleted. |
| [ADR-094](ADR-094-govern-copilot-cli-compatibility.md) | Govern Copilot CLI Compatibility Through Executable Surfaces | 2026-08-15 | Supersede ADR-044 in full. |
| [ADR-096](ADR-096-relax-qa-evidence-commit-equality.md) | Relax QA-Evidence Commit Equality to a Code-Change-Aware Check | 2026-08-19 | Redesign `validate_qa_report()` to require an explicit `head` argument and to perform the staleness check itself, rather than leaving staleness detection as a second call a caller can forget: |
| [ADR-097](ADR-097-zero-tool-use-hooks.md) | Zero Tool-Use Hooks | 2026-08-19 | Retire all five currently-registered tool-call hooks, and retire the generated Copilot dispatcher machinery that their removal leaves with nothing to run. |
| [ADR-099](ADR-099-remove-commit-limit-bypass-gate.md) | Remove the commit-count block and its commit-limit-bypass label | 2026-08-21 | Remove the commit-count block and the `commit-limit-bypass` label mechanism entirely, from both the CI workflow (`pr-validation.yml`, `scripts/ci/enforce_pr_validation.py`) and the local pre-push... |
| [ADR-102](ADR-102-session-qa-binding-field-precedence.md) | Replace session_qa_binding()'s Field-Equality Raise with Documented Precedence and a Diagnostic | 2026-08-21 | Delete the equality raise. |

## Proposed

Recorded, not yet binding. The last column is what each record says is holding it short of acceptance.

| ADR | Title | Date | Decision | Blocking acceptance |
| --- | --- | --- | --- | --- |
| [ADR-020](ADR-020-feature-request-review-step.md) | Feature Request Review Step in Issue Triage Workflow | 2025-12-19 | Chosen option: Option 1 - New Conditional Step with Analyst Agent | - |
| [ADR-027](ADR-027-github-mcp-agent-isolation.md) | GitHub MCP Server with Agent Isolation Pattern | 2025-12-23 | Chosen option: Phased Hybrid Approach with GitHub MCP as Target Architecture | - |
| [ADR-058](ADR-058-agent-eval-discipline.md) | Agent Eval Discipline (Agent-vs-Baseline Efficacy) | 2026-05-03 | Adopt the agent-vs-baseline efficacy methodology defined below as the standard for empirical validation of agent specialization. | - |
| [ADR-069](ADR-069-context-corpus-is-the-product.md) | The Curated Context Corpus IS the Product, Orchestration Is Plumbing | 2026-05-02 | Adopt the following architectural principle: | - |
| [ADR-075](ADR-075-form-factor-eval-methodology.md) | Form-Factor Evaluation Methodology (Agent vs Skill) | 2026-07-20 | Adopt a three-variant eval. | Requested by issue [#1875](https://github.com/rjmurillo/ai-agents/issues/1875). Follow-on to ADR-058 (agent eval discipline), which scoped the form-factor question out and tracked it here. |
| [ADR-077](ADR-077-flip-stale-contract-tests.md) | Flip Stale Contract Tests | 2026-06-29 | Add a governance rule to `.agents/governance/TESTING-RIGOR.md`: when a change alters an observable contract, the author must find and flip stale tests in the same diff. | This is a 90-day experimental governance rule. The review checkpoint is 2026-09-27. |
| [ADR-078](ADR-078-autoplan-orchestrator-router-boundary.md) | Autoplan and Orchestrator Router Boundary | 2026-08-20 | Adopt an explicit two-layer boundary and document it in both routing surfaces: the autoplan skill and the orchestrator shared source. | - |
| [ADR-087](ADR-087-held-out-validated-improvement.md) | Held-Out Validation for Iterated Improvement Claims | 2026-07-26 | An improvement claim about an authored artifact, made by a loop that reads its own evaluation results, MUST be validated against a group whose number of consultations is bounded and counted by a... | Requested by two independent adversarial reviews on PR #3430 (gpt-5.6-sol and gemini-3.1-pro-preview), both of which concluded that the mechanism that PR adds asserts a norm the repository has not... |
| [ADR-088](ADR-088-progressive-disclosure-book-rules.md) | Progressive Disclosure for Book-Derived Rules | 2026-07-27 | Move the eight situational book-derived rules from always-on instruction files to one progressively-disclosed skill named `software-engineering-library`. | - |
| [ADR-089](ADR-089-remove-causal-memory-tier.md) | Remove the Tier 3 Causal Memory Graph | 2026-07-27 | Delete the Tier 3 causal graph and all machinery that exists only to maintain it: | The removal is implemented in the same change that files this ADR, so the document records a decision already carried out rather than one awaiting execution. On reversal, see the Consequences... |
| [ADR-090](ADR-090-pr-branch-holder-lease.md) | PR Branch Holder Lease | 2026-07-27 | Adopt a fail-closed, PR-comment-backed holder lease for PR branch mutation. | This ADR amends ADR-076 for issue #3413. It records the decision before implementation because the change controls who may mutate a PR branch. |
| [ADR-093](ADR-093-verify-red-checks-with-the-same-checker.md) | A local run clears a red remote check only when it is the same checker | 2026-08-07 | Add one MUST to `.claude/rules/universal.md`, which is always-on: | - |
| [ADR-098](ADR-098-agent-role-metadata-replaces-tier-hierarchy.md) | Agent Role Metadata Replaces the Tier Hierarchy | 2026-08-20 | Retire the four-tier agent hierarchy. | - |
| [ADR-100](ADR-100-retire-pr-size-ceilings.md) | Retire the Pull Request Size Ceilings | 2026-08-20 | Retire both size ceilings as blocking gates. | - |
| [ADR-101](ADR-101-enforcement-planes.md) | Enforcement Planes | 2026-08-20 | Adopt enforcement plane classification as this repository's rule for gate design, and treat the control plane's current gaps as prerequisites rather than as background. | - |

## Retired

Superseded or deprecated. Do not cite these. The last column is where the decision moved.

| ADR | Title | Status | Read instead |
| --- | --- | --- | --- |
| [ADR-004](ADR-004-pre-commit-hook-architecture.md) | Pre-Commit Hook as Validation Orchestration Point | superseded | [ADR-086](ADR-086-lefthook-local-hook-orchestration.md) |
| [ADR-005](ADR-005-powershell-only-scripting.md) | PowerShell-Only Scripting Standard | superseded | [ADR-042](ADR-042-python-migration-strategy.md) |
| [ADR-024](ADR-024-github-actions-runner-selection.md) | GitHub Actions Runner Selection | superseded | [ADR-055](ADR-055-github-actions-runner-selection.md) |
| [ADR-025](ADR-025-github-actions-arm-runners.md) | GitHub Actions ARM Runner Migration | superseded | [ADR-055](ADR-055-github-actions-runner-selection.md) |
| [ADR-044](ADR-044-copilot-cli-frontmatter-compatibility.md) | Copilot CLI Frontmatter Compatibility | superseded | [ADR-094](ADR-094-govern-copilot-cli-compatibility.md) |
| [ADR-079](ADR-079-merge-time-plugin-version-bump.md) | Plugin Version Bump Stays at PR Time (Reject Merge-Time Automation) | superseded | [ADR-092](ADR-092-omit-plugin-manifest-version.md) (via ADR-091) |
| [ADR-091](ADR-091-post-merge-version-bot.md) | Post-Merge Bot Owns Plugin Version and Count Baselines | superseded | [ADR-092](ADR-092-omit-plugin-manifest-version.md) |

## Rejected

Considered and declined. Kept visible so the proposal is findable and does not return.

| ADR | Title | Date | Decision |
| --- | --- | --- | --- |
| [ADR-095](ADR-095-scoped-re-review-axes.md) | Scoped re-review runs only the axes that flagged (rejected) | 2026-08-15 | - |

## Needs backfill

No lifecycle frontmatter, so this index has no status to report. Nothing is inferred for these: open the record and read its `## Status` section. ADR-073 Phase 2 closes this section.

| ADR | Title |
| --- | --- |
| [ADR-001](ADR-001-markdown-linting.md) | Markdown Linting Configuration |
| [ADR-002](ADR-002-agent-model-selection-optimization.md) | Agent Model Selection Optimization |
| [ADR-006](ADR-006-thin-workflows-testable-modules.md) | Thin Workflows, Testable Modules |
| [ADR-007](ADR-007-memory-first-architecture.md) | Memory-First Architecture |
| [ADR-008](ADR-008-protocol-automation-lifecycle-hooks.md) | Protocol Automation via Lifecycle Hooks |
| [ADR-009](ADR-009-parallel-safe-multi-agent-design.md) | Parallel-Safe Multi-Agent Design |
| [ADR-010](ADR-010-quality-gates-evaluator-optimizer.md) | Quality Gates with Evaluator-Optimizer Pattern |
| [ADR-011](ADR-011-session-state-mcp.md) | Session State MCP |
| [ADR-012](ADR-012-skill-catalog-mcp.md) | Skill Catalog MCP |
| [ADR-013](ADR-013-agent-orchestration-mcp.md) | Agent Orchestration MCP |
| [ADR-014](ADR-014-distributed-handoff-architecture.md) | Distributed Handoff Architecture |
| [ADR-015](ADR-015-artifact-storage-minimization.md) | Artifact Storage Minimization Strategy |
| [ADR-016](ADR-016-workflow-execution-optimization.md) | Workflow Execution Optimization Strategy |
| [ADR-017](ADR-017-tiered-memory-index-architecture.md) | Tiered Memory Index Architecture |
| [ADR-018](ADR-018-cache-invalidation-strategy.md) | Cache Invalidation Strategy for GitHub Data |
| [ADR-019](ADR-019-script-organization.md) | Script Organization and Usage Patterns |
| [ADR-021](ADR-021-model-routing-strategy.md) | AI Review Model Routing Strategy |
| [ADR-022](ADR-022-architecture-governance-split-criteria.md) | Architecture vs Governance Decision Split Criteria |
| [ADR-026](ADR-026-pr-automation-concurrency-and-safety.md) | PR Automation Concurrency and Safety Controls |
| [ADR-028](ADR-028-powershell-output-schema-consistency.md) | PowerShell Output Schema Consistency |
| [ADR-029](ADR-029-skill-file-line-ending-normalization.md) | Skill File Line Ending Normalization |
| [ADR-030](ADR-030-skills-pattern-superiority.md) | Skills Pattern Superiority |
| [ADR-031](ADR-031-hybrid-powershell-architecture.md) | Hybrid PowerShell Architecture for Claude Code Performance |
| [ADR-032](ADR-032-ears-requirements-syntax.md) | EARS Requirements Syntax Standard |
| [ADR-033](ADR-033-routing-level-enforcement-gates.md) | Routing-Level Enforcement Gates |
| [ADR-035](ADR-035-exit-code-standardization.md) | Exit Code Standardization |
| [ADR-036](ADR-036-two-source-agent-template-architecture.md) | Two-Source Agent Template Architecture |
| [ADR-037](ADR-037-memory-router-architecture.md) | Memory Router Architecture |
| [ADR-038](ADR-038-reflexion-memory-schema.md) | Reflexion Memory Schema |
| [ADR-039](ADR-039-agent-model-cost-optimization.md) | Agent Model Cost Optimization |
| [ADR-040](ADR-040-skill-frontmatter-standardization.md) | Skill Frontmatter Standardization and Model Identifier Strategy |
| [ADR-041](ADR-041-codeql-integration.md) | CodeQL Integration Multi-Tier Strategy |
| [ADR-043](ADR-043-scoped-tool-execution.md) | Scoped Tool Execution |
| [ADR-045](ADR-045-framework-extraction-via-plugin-marketplace.md) | Framework Extraction via Plugin Marketplace |
| [ADR-046](ADR-046-planning-agent-rename.md) | Planning Agent Rename for Role Clarity |
| [ADR-047](ADR-047-plugin-mode-hook-behavior.md) | Plugin-Mode Hook Behavior |
| [ADR-048](ADR-048-mcp-tool-ecosystem-expansion.md) | MCP Tool Ecosystem Expansion |
| [ADR-049](ADR-049-pre-pr-validation-gates.md) | Pre-PR Validation Gates |
| [ADR-050](ADR-050-adr-protocol-sync.md) | ADR-to-Protocol Sync Process |
| [ADR-051](ADR-051-synthesis-panel-frontmatter-standard.md) | Synthesis Panel Frontmatter Standard |
| [ADR-052](ADR-052-template-strategy.md) | Template Strategy for Multi-Platform Agent Distribution |
| [ADR-053](ADR-053-adr-exception-criteria.md) | ADR Exception Criteria (Chesterton's Fence) |
| [ADR-054](ADR-054-local-security-scanning.md) | Local Security Scanning |
| [ADR-056](ADR-056-skill-output-format-standardization.md) | Skill Output Format Standardization |
| [ADR-059](ADR-059-pr-review-completion-gate-dispatcher.md) | /pr-review Completion Gate Dispatcher and pass_when DSL |
| [ADR-060](ADR-060-rework-warning-session-log-persistence.md) | Rework Warning Evidence Persistence in Session Log JSON |
| [ADR-061](ADR-061-hook-matcher-shims-delegate-pattern.md) | Hook Matcher Shims Delegate to Canonical Body |
| [ADR-062](ADR-062-conditional-lsp-first-enforcement.md) | Conditional LSP-First Navigation Enforcement |
| [ADR-064](ADR-064-commands-to-skills-migration.md) | Retire `.claude/commands/` as a Canonical Authoring Surface; Skills Are the Single User-Invocable Surface |
| [ADR-065](ADR-065-orchestrator-as-router.md) | Orchestrator Is a Deterministic Router and Retry Policy, Not a Supervisor |
| [ADR-067](ADR-067-validate-pr-change-claim-context.md) | validate-pr Check 1 default-flip - change-claim context required |
| [ADR-070](ADR-070-memory-first-gate-spec-pipeline.md) | Memory-First Gate Is a BLOCKING Step in the Spec Pipeline |
| [ADR-072](ADR-072-jtbd-plugin-architecture.md) | JTBD-Based Plugin Architecture with Per-Harness Emission |
