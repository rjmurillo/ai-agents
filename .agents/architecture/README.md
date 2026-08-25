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
import pathlib, re, yaml

_ADR_FILENAME_RE = re.compile(r'^ADR-(\d{2,})-[^/]+\.md$')
_OPENING_FENCE = re.compile(r'^---\r?\n')
_CLOSING_FENCE = re.compile(r'\r?\n---\r?\n')

for path in sorted(pathlib.Path('.agents/architecture').glob('ADR-*.md')):
    if not _ADR_FILENAME_RE.match(path.name):
        continue  # not a canonical ADR record filename
    text = path.read_text(encoding='utf-8')
    if not _OPENING_FENCE.match(text):
        continue  # no frontmatter: see Needs backfill below
    closing = _CLOSING_FENCE.search(text, 3)
    if closing is None:
        raise ValueError(f'{path.name}: opens with --- but never closes it')
    front = yaml.safe_load(text[3 : closing.start()]) or {}
    if str(front.get('status', '')).strip().lower() == 'accepted':
        print(front.get('id') or path.name)
```

**Normalise before comparing, as above.** This generator's own `_status_of`
strips and lower-cases a string value before bucketing a record
(`raw.strip().lower()`, after confirming `raw` is a string; see the next
paragraph), so `status: Accepted` lands under Accepted in the table below,
while a bare `== 'accepted'` misses it. Every record carries a lowercase
value today, which is exactly why the mismatch would not announce itself.

**This snippet trusts the corpus; the generator does not.** `_status_of`
raises when a `status` value is present but not a string, before it ever
strips or lower-cases anything, so `status: true` or `status: 1` fails the
committed index loudly. The bare `str(front.get('status', ''))` above has no
such check: it silently stringifies whatever YAML parsed, so a non-string
value it happens to compare unequal to `'accepted'` passes through unnoticed
instead of raising. This snippet is a read of a corpus the generator has
already validated, not a second validator; regenerate the index (which does
raise) before trusting a bare frontmatter query on a tree you have not.

**This snippet does not detect duplicate keys, and the generator does.**
`yaml.safe_load` resolves a repeated `status:` last-wins and silently, so a
record declaring `proposed` in the line a human reads and `accepted` lower in
the same block would print as accepted here. This generator's own frontmatter
parser rejects that at the parser (a strict YAML loader that raises on a
duplicate mapping key), so the committed index has none. Regenerate before
trusting a query on a tree you have not; the snippet is a convenience for
reading a known-good corpus, not an independent check.

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
drop it.** `_OPENING_FENCE.match(text)` is false only for a record with no
schema at all (including a malformed opening line such as `--- ` with
trailing text before the newline, which this exact-fence regex rejects the
same way the generator's `_FRONTMATTER_RE` does), so those `continue` past.
A record whose opening `---` fence is well-formed but never closes still
matches `_OPENING_FENCE`, so it skips that `continue`, finds no match for
`_CLOSING_FENCE`, and raises `ValueError` (verified by running both cases;
Copilot found the original claim backwards on PR #5209). The real
generator's `parse_frontmatter` raises the same way, on purpose: a
malformed schema is an author's defect to see, not a record to drop
quietly into Needs backfill. Run the gate rather than this snippet when
that distinction matters.

**The closing fence must occupy its own line, not just start one.**
`generate_adr_index.py`'s `_FRONTMATTER_RE` is
``r"^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$"``: the closing fence is
three dashes immediately followed by `\r?\n`, nothing else. An earlier
version of this snippet used `text.index('\n---', 3)`, which finds any
line merely starting with three dashes, trailing characters or not. A
closing line padded with one trailing space (`"--- \n"` instead of
`"---\n"`, a plausible editor artifact) does not match `_FRONTMATTER_RE`,
so `parse_frontmatter` finds no valid closing fence and raises
`AdrIndexError`, the same as a fence that never closes at all. The old
`.index` call could not tell the difference: it matched the padded line
anyway and printed an answer with no error, silently disagreeing with the
generator's correctly-loud rejection of the same file (Copilot, PR #5209
round-5 review). `_CLOSING_FENCE` above requires the same `\r?\n` on both
sides of the dashes as `_FRONTMATTER_RE`, so a padded or otherwise
malformed fence now raises here too.

## Accepted

These bind today.

| ADR | Title | Date | Decision |
| --- | --- | --- | --- |
| [ADR-001](ADR-001-markdown-linting.md) | Markdown Linting Configuration | 2025-12-13 | Create `.markdownlint-cli2.yaml` in the repository root with rules appropriate for agent templates: |
| [ADR-003](ADR-003-agent-tool-selection-criteria.md) | Role-Specific Tool Allocation for Multi-Agent System | 2025-12-16 | Chosen option: "Option 2: Role-specific tool allocation", because it provides the optimal balance of context efficiency, role clarity, and operational capability. |
| [ADR-006](ADR-006-thin-workflows-testable-modules.md) | Thin Workflows, Testable Modules | 2026-04-29 | Chosen option: Option 1 - Thin Workflows, Testable Modules |
| [ADR-007](ADR-007-memory-first-architecture.md) | Memory-First Architecture | 2026-08-16 | Memory retrieval MUST precede reasoning in all agent workflows. |
| [ADR-008](ADR-008-protocol-automation-lifecycle-hooks.md) | Protocol Automation via Lifecycle Hooks | 2026-08-19 | Lifecycle hooks MUST automate SESSION-PROTOCOL enforcement. |
| [ADR-009](ADR-009-parallel-safe-multi-agent-design.md) | Parallel-Safe Multi-Agent Design | 2025-12-20 | Multi-agent coordination MUST include consensus mechanisms for conflict resolution. |
| [ADR-010](ADR-010-quality-gates-evaluator-optimizer.md) | Quality Gates with Evaluator-Optimizer Pattern | 2025-12-20 | All significant outputs MUST pass through a formalized evaluator-optimizer loop. |
| [ADR-014](ADR-014-distributed-handoff-architecture.md) | Distributed Handoff Architecture | 2026-08-16 | Implement a three-tier distributed handoff architecture that eliminates centralized HANDOFF.md as a write target: |
| [ADR-015](ADR-015-artifact-storage-minimization.md) | Artifact Storage Minimization Strategy | 2025-12-22 | Reduce artifact retention to minimum necessary duration: |
| [ADR-016](ADR-016-workflow-execution-optimization.md) | Workflow Execution Optimization Strategy | 2025-12-22 | Implement two complementary optimizations: |
| [ADR-017](ADR-017-tiered-memory-index-architecture.md) | Tiered Memory Index Architecture | 2025-12-28 | Chosen option: Option 3 - Tiered Index Architecture |
| [ADR-018](ADR-018-cache-invalidation-strategy.md) | Cache Invalidation Strategy for GitHub Data | 2025-12-23 | Primary: Option 2 (Session-Local Cache) for simplicity Secondary: Option 3 (cloudmcp) when cross-session benefit is critical |
| [ADR-019](ADR-019-script-organization.md) | Script Organization and Usage Patterns | 2025-12-23 | Establish a hierarchical script organization based on intended audience and execution context: |
| [ADR-021](ADR-021-model-routing-strategy.md) | AI Review Model Routing Strategy | 2025-12-23 | Adopt an evidence-aware, tiered model routing strategy that routes AI review requests to specialized models based on: |
| [ADR-023](ADR-023-quality-gate-prompt-testing.md) | Quality Gate Prompt Structural Validation | 2025-12-26 | Chosen option: "Pester Structural Tests", because it provides immediate, repeatable validation of prompt structure with minimal infrastructure overhead, while acknowledging that runtime behavioral... |
| [ADR-026](ADR-026-pr-automation-concurrency-and-safety.md) | PR Automation Concurrency and Safety Controls | 2026-07-27 | Decision: Use GitHub Actions `concurrency` group instead of file-based locking. |
| [ADR-028](ADR-028-powershell-output-schema-consistency.md) | PowerShell Output Schema Consistency | 2025-12-23 | Include all properties in output objects with null/0 values when not populated, rather than conditionally excluding properties from the output schema. |
| [ADR-029](ADR-029-skill-file-line-ending-normalization.md) | Skill File Line Ending Normalization | 2025-12-27 | Force LF line endings for all `*.skill` files using git attributes: |
| [ADR-032](ADR-032-ears-requirements-syntax.md) | EARS Requirements Syntax Standard | 2025-12-30 | Adopt the EARS (Easy Approach to Requirements Syntax) format as the standard for all formal requirements in the ai-agents project. |
| [ADR-033](ADR-033-routing-level-enforcement-gates.md) | Routing-Level Enforcement Gates | 2026-08-16 | Implement routing-level enforcement gates using Claude Code hooks. |
| [ADR-034](ADR-034-investigation-session-qa-exemption.md) | Investigation Session QA Exemption | 2026-07-08 | Add investigation-only session exemption to pre-commit QA validation with staged-file guardrails. |
| [ADR-035](ADR-035-exit-code-standardization.md) | Exit Code Standardization | 2025-12-30 | Chosen option: Option 1 - POSIX-Style Standard |
| [ADR-036](ADR-036-two-source-agent-template-architecture.md) | Two-Source Agent Template Architecture | 2026-08-25 | Adopt a two-source architecture: |
| [ADR-037](ADR-037-memory-router-architecture.md) | Memory Router Architecture | 2026-07-20 | Implement a Memory Router that provides: |
| [ADR-040](ADR-040-skill-frontmatter-standardization.md) | Skill Frontmatter Standardization and Model Identifier Strategy | 2026-08-14 | Adopt the following standardization for all 27 Claude Code skills: |
| [ADR-041](ADR-041-codeql-integration.md) | CodeQL Integration Multi-Tier Strategy | 2026-07-21 | Chosen option: Option 4 - Multi-Tier with Shared Configuration |
| [ADR-042](ADR-042-python-migration-strategy.md) | Python Migration Strategy | 2026-04-13 | Migrate the ai-agents project from PowerShell to Python as the primary scripting language over a 12-24 month phased migration period. |
| [ADR-043](ADR-043-scoped-tool-execution.md) | Scoped Tool Execution | 2026-01-21 | Session protocol tools MUST scope to changed files rather than the entire repository. |
| [ADR-045](ADR-045-framework-extraction-via-plugin-marketplace.md) | Framework Extraction via Plugin Marketplace | 2026-02-07 | Extract the reusable multi-agent framework from `rjmurillo/ai-agents` into a new repository `rjmurillo/awesome-ai`, published as a Claude Code plugin marketplace with 4 plugins. |
| [ADR-046](ADR-046-planning-agent-rename.md) | Planning Agent Rename for Role Clarity | 2026-02-08 | Rename all three planning agents to reflect their distinct roles: |
| [ADR-047](ADR-047-plugin-mode-hook-behavior.md) | Plugin-Mode Hook Behavior | 2026-04-29 | All hooks and skills run in plugin mode. |
| [ADR-050](ADR-050-adr-protocol-sync.md) | ADR-to-Protocol Sync Process | 2026-02-21 | Establish a two-tier ADR-to-Protocol sync process: an automated audit script and a manual integration checklist. |
| [ADR-051](ADR-051-synthesis-panel-frontmatter-standard.md) | Synthesis Panel Frontmatter Standard | 2026-03-07 | All DESIGN-REVIEW documents MUST include YAML frontmatter with structured metadata. |
| [ADR-053](ADR-053-adr-exception-criteria.md) | ADR Exception Criteria (Chesterton's Fence) | 2026-03-07 | ADR exceptions MUST include a Chesterton's Fence analysis before approval. |
| [ADR-054](ADR-054-local-security-scanning.md) | Local Security Scanning | 2026-07-20 | Add a Lefthook pre-push job that scans changed code files. |
| [ADR-055](ADR-055-github-actions-runner-selection.md) | GitHub Actions Runner Selection | 2026-08-25 | Default to ARM64 runners for all Linux workflows unless documented architectural constraints exist. |
| [ADR-056](ADR-056-skill-output-format-standardization.md) | Skill Output Format Standardization | 2026-03-08 | All skill scripts MUST wrap output in a standard envelope with `Success`, `Data`, `Error`, and `Metadata` fields |
| [ADR-057](ADR-057-prompt-behavioral-evaluation.md) | Prompt Behavioral Evaluation Methodology | 2026-07-22 | Adopt scenario-based LLM evaluation as the standard method for validating behavioral correctness of prompt changes. |
| [ADR-060](ADR-060-rework-warning-session-log-persistence.md) | Rework Warning Evidence Persistence in Session Log JSON | 2026-07-27 | Add an optional `reworkWarning` object under `protocolCompliance.sessionEnd` in the session log JSON. |
| [ADR-062](ADR-062-conditional-lsp-first-enforcement.md) | Conditional LSP-First Navigation Enforcement | 2026-07-27 | Adopt a conditional, availability-gated LSP-first enforcement layer, ported to Python, wired into both harnesses, covering every LSP-navigable file type. |
| [ADR-063](ADR-063-memory-skill-decomposition.md) | Decompose the Memory Skill Into Focused Sub-Skills | 2026-07-27 | Decompose the monolithic `memory` skill into focused sub-skills split by operation, keep `memory` as a thin router that delegates, and preserve the `memory` skill name so existing callers do not... |
| [ADR-066](ADR-066-hook-fail-open-reconciliation.md) | Hook Fail-Open Reconciliation (Prevention-First, Fail-Closed-and-Loud) | 2026-07-19 | Chosen option: 3 - prevention-first, fail-closed-and-loud, because the #2205 incident proved that launcher-level fail-open does not protect users. |
| [ADR-068](ADR-068-consolidated-hook-dispatcher.md) | Consolidated Per-Event Hook Dispatcher | 2026-07-31 | Generate one dispatcher host entry per active, safely consolidatable Copilot hook event. |
| [ADR-071](ADR-071-plugin-hook-runtime-contract-verification.md) | Plugin Hook Runtime-Contract Verification | 2026-08-19 | Anchor every plugin hook command to the plugin root. |
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
| [ADR-011](ADR-011-session-state-mcp.md) | Session State MCP | 2025-12-21 | Create a Session State MCP that: | - |
| [ADR-012](ADR-012-skill-catalog-mcp.md) | Skill Catalog MCP | 2025-12-21 | Create a Skill Catalog MCP that: | - |
| [ADR-013](ADR-013-agent-orchestration-mcp.md) | Agent Orchestration MCP | 2025-12-21 | Create an Agent Orchestration MCP that: | - |
| [ADR-020](ADR-020-feature-request-review-step.md) | Feature Request Review Step in Issue Triage Workflow | 2025-12-19 | Chosen option: Option 1 - New Conditional Step with Analyst Agent | - |
| [ADR-022](ADR-022-architecture-governance-split-criteria.md) | Architecture vs Governance Decision Split Criteria | 2025-12-23 | Adopt a hybrid approach with explicit split criteria: | - |
| [ADR-027](ADR-027-github-mcp-agent-isolation.md) | GitHub MCP Server with Agent Isolation Pattern | 2025-12-23 | Chosen option: Phased Hybrid Approach with GitHub MCP as Target Architecture | - |
| [ADR-031](ADR-031-hybrid-powershell-architecture.md) | Hybrid PowerShell Architecture for Claude Code Performance | 2025-12-29 | Implement a hybrid architecture for PowerShell skill execution: | - |
| [ADR-038](ADR-038-reflexion-memory-schema.md) | Reflexion Memory Schema | 2026-01-01 | Implement a Four-Tier Reflexion Memory Schema with episodic replay and causal graph capabilities. | - |
| [ADR-048](ADR-048-mcp-tool-ecosystem-expansion.md) | MCP Tool Ecosystem Expansion | 2026-02-23 | Expand the MCP tool ecosystem in four phases, building on existing ADRs: | - |
| [ADR-049](ADR-049-pre-pr-validation-gates.md) | Pre-PR Validation Gates | 2026-02-24 | All PRs MUST pass a local validation gate before creation. | - |
| [ADR-058](ADR-058-agent-eval-discipline.md) | Agent Eval Discipline (Agent-vs-Baseline Efficacy) | 2026-05-03 | Adopt the agent-vs-baseline efficacy methodology defined below as the standard for empirical validation of agent specialization. | - |
| [ADR-059](ADR-059-pr-review-completion-gate-dispatcher.md) | /pr-review Completion Gate Dispatcher and pass_when DSL | 2026-05-08 | Replace the narrative completion gate with a dispatcher. | - |
| [ADR-064](ADR-064-commands-to-skills-migration.md) | Retire `.claude/commands/` as a Canonical Authoring Surface; Skills Are the Single User-Invocable Surface | 2026-06-01 | Retire `.claude/commands/` as a canonical authoring surface. | - |
| [ADR-065](ADR-065-orchestrator-as-router.md) | Orchestrator Is a Deterministic Router and Retry Policy, Not a Supervisor | 2026-05-29 | The orchestrator is a deterministic router with a retry policy. | - |
| [ADR-067](ADR-067-validate-pr-change-claim-context.md) | validate-pr Check 1 default-flip - change-claim context required | 2026-06-02 | Adopt Option (c) Hybrid: keep patterns 1 (bold `path.ext`) and 2 (bullet-list `^[-*+] path.ext`) firing in any context. | - |
| [ADR-069](ADR-069-context-corpus-is-the-product.md) | The Curated Context Corpus IS the Product, Orchestration Is Plumbing | 2026-05-02 | Adopt the following architectural principle: | - |
| [ADR-070](ADR-070-memory-first-gate-spec-pipeline.md) | Memory-First Gate Is a BLOCKING Step in the Spec Pipeline | 2026-07-27 | The Memory-First Gate is a BLOCKING step (Step 0.5) in the `/spec` pipeline, running after Step 0 and before Step 1. | - |
| [ADR-072](ADR-072-jtbd-plugin-architecture.md) | JTBD-Based Plugin Architecture with Per-Harness Emission | 2026-06-09 | Adopt two coupled changes. | Architect design review completed (verdict: APPROVE WITH CHANGES); this ADR may exist as `Proposed` but MUST clear the five approval conditions in "Conditions to reach Accepted" before its status... |
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
| [ADR-002](ADR-002-agent-model-selection-optimization.md) | Agent Model Selection Optimization | deprecated | not recorded |
| [ADR-004](ADR-004-pre-commit-hook-architecture.md) | Pre-Commit Hook as Validation Orchestration Point | superseded | [ADR-086](ADR-086-lefthook-local-hook-orchestration.md) |
| [ADR-005](ADR-005-powershell-only-scripting.md) | PowerShell-Only Scripting Standard | superseded | [ADR-042](ADR-042-python-migration-strategy.md) |
| [ADR-039](ADR-039-agent-model-cost-optimization.md) | Agent Model Cost Optimization | deprecated | not recorded |
| [ADR-044](ADR-044-copilot-cli-frontmatter-compatibility.md) | Copilot CLI Frontmatter Compatibility | superseded | [ADR-094](ADR-094-govern-copilot-cli-compatibility.md) |
| [ADR-079](ADR-079-merge-time-plugin-version-bump.md) | Plugin Version Bump Stays at PR Time (Reject Merge-Time Automation) | superseded | [ADR-092](ADR-092-omit-plugin-manifest-version.md) |
| [ADR-091](ADR-091-post-merge-version-bot.md) | Post-Merge Bot Owns Plugin Version and Count Baselines | superseded | [ADR-092](ADR-092-omit-plugin-manifest-version.md) |

## Rejected

Considered and declined. Kept visible so the proposal is findable and does not return.

| ADR | Title | Date | Decision |
| --- | --- | --- | --- |
| [ADR-030](ADR-030-skills-pattern-superiority.md) | Skills Pattern Superiority | 2026-08-25 | - |
| [ADR-052](ADR-052-template-strategy.md) | Template Strategy for Multi-Platform Agent Distribution | 2026-08-25 | Option B: Claude-First. |
| [ADR-061](ADR-061-hook-matcher-shims-delegate-pattern.md) | Hook Matcher Shims Delegate to Canonical Body | 2026-08-25 | Amend REQ-003-007 step 5 so the generator emits delegate shims, not inline-body shims. |
| [ADR-095](ADR-095-scoped-re-review-axes.md) | Scoped re-review runs only the axes that flagged (rejected) | 2026-08-15 | - |

## Needs backfill

No machine-readable lifecycle status: either the record carries no frontmatter block at all, or its frontmatter is present but omits the `status` key. Either way this index has nothing to report. Nothing is inferred for these: open the record and read its `## Status` section. ADR-073 Phase 2 closes this section.

| ADR | Title |
| --- | --- |
| [ADR-024](ADR-024-github-actions-runner-selection.md) | GitHub Actions Runner Selection |
| [ADR-025](ADR-025-github-actions-arm-runners.md) | GitHub Actions ARM Runner Migration |
