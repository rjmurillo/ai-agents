# PRD: Agent-Skill Classification Audit (issue #2003)

**Status**: Draft (v0.1.0)
**Author**: spec skill (Copilot CLI session 2026-05-10)
**Created**: 2026-05-10
**Updated**: 2026-05-10
**Tracking Issue**: #2003
**Parent Epic**: #1944 (Skill Catalog Triage Action Slate)
**Related Issues**: #2001 (closed: spec-generator skill conversion), #2002 (closed dup of #2001), #1932 (eval-skill-overlap.py), #1944 (umbrella)
**Authority**: ADR-030 (Skills Pattern Superiority), ADR-036 (Two-Source Agent Template Architecture), `.agents/governance/agent-consolidation-process.md`

---

## Prior Art / Constraints

### Direct prior art from memory

- **ADR-030 Skills Pattern Superiority** (`.agents/architecture/ADR-030-skills-pattern-superiority.md`): documents that skills have lower latency (5-20ms vs 100-200ms for subagent spawn), lower token usage (load on demand vs full agent context), and direct MCP access. Decision: **honor**. ADR-030 is the documented authority for the audit's discriminator claim that "skill is the lower-cost shape when isolation is not required."
- **ADR-036 Two-Source Agent Template Architecture** (`.agents/architecture/ADR-036-two-source-agent-template-architecture.md`): agents live in BOTH `src/claude/*.md` (manual) AND `templates/agents/*.shared.md` (auto-generates Copilot CLI + VS Code variants). Decision: **honor**. Audit table includes a `has_shared_template` column so Phase 2 refactor planning correctly targets both sources.
- **Process: agent-consolidation-process.md** (`.agents/governance/agent-consolidation-process.md`, 313 lines): defines overlap analysis matrix, recommendation thresholds (0-10% no action / 11-20% clarify / 21-40% consider / 41-70% strong / 71-100% required), and trigger conditions (>20% overlap, <5% usage, >3 routing errors/month, duplicate outputs). Decision: **adapt + extend**. The audit applies this process AND extends it with the issue #2003 4-criterion discriminator + a 5th frontmatter-bytes criterion added because of the Claude truncation context.
- **Epic #1944 Skill Catalog Triage Action Slate** (M1-M4 + Wave 2): the umbrella consolidation effort. M1 prunes doc-coverage/doc-sync/workflow (PR #1942 in flight); M2 folds session-qa-eligibility into session; M3 decomposes the memory skill (143KB = 18× ceiling); M4 runs pairwise overlap eval; Wave 2 sweeps remaining 47 skills. Decision: **honor**. Issue #2003 is filed as a child issue of #1944 (the agent-side sibling of #1944's skill-side work).
- **Issue #2001 (closed)**: spec-generator agent shipped 9-of-13 frontmatter schema violations on PR #1995 because the agent body was not forced to re-read `.agents/governance/spec-schemas.md`. Decision: **honor**. spec-generator is the canonical case in the audit; the audit's 4th criterion (schema drift evidence) directly tests for this anti-pattern in other agents.
- **Retro `.serena/memories/implementation/implementation-007-pr1989-recursive-failure-learnings.md`**: the original read-before-write constraint that relapsed in PR #1995. Decision: **honor**. The skill-vs-agent shape mismatch is the structural cause this audit addresses; the retro is the historical demand signal.
- **chestertons-fence frame**: `.claude/agents/` directory has accreted incrementally (commits 1535, 1670, 1684, 1715, 1718, 1731, 1845, 1892, 1897 etc.). MODIFY recommendation: the directory itself is preserved; misclassified agents are migrated to `.claude/skills/` per the discriminator. No PRESERVE-or-REMOVE decision on the directory.

### Connected context from exploring-knowledge-graph

- Connected entity: `src/claude/agents/` (Claude-platform agent variants, dual to `.claude/agents/`). Adjudication: **in-scope** (audited as part of `include_24th_caveman_agent: include-claude-only` decision; audit verifies dual-source presence per ADR-036).
- Connected entity: `templates/agents/*.shared.md` (cross-platform agent source per ADR-036). Adjudication: **in-scope** (audit table column `has_shared_template`).
- Connected entity: `src/copilot-cli/agents/` and `src/vs-code-agents/` (auto-generated platform variants). Adjudication: **out-of-scope** (downstream of `templates/agents/`; not directly audited).
- Connected entity: `.caveman-active` / 24th agent file under `~/.claude/`. Adjudication: **out-of-scope** (per user decision; not in `.claude/agents/`).
- Connected entity: build/scripts/generate_agents.py and similar generators. Adjudication: **out-of-scope** (audit produces a table; does not modify generators).
- Linked project: `eval-knowledge-integration.py` and proposed `eval-skill-overlap.py` (#1932). Why it matters: provides quantitative ranking that could replace the human-judgment verdict column. **Out-of-scope for this audit** (deliberate exclusion; revisit for Phase 2 when refactor candidates are sized).
- Linked project: `SKILL-CREATION-CRITERIA.md` (`.agents/governance/`). Why it matters: defines when to CREATE a new skill (frequency >3x/week, failure pattern >2 incidents). **Out-of-scope** (audit reclassifies existing agents; does not propose new skills).
- Traversal depth: deep (matched to ProvisionalTier 4, ran Phases 1-5).

### Coverage notes

- Topic `spec-generator`: searched issue tracker (matched #2001, #2002, #1812, #1925, #1953, #1959), Serena memories (matched implementation-007), and ADR index. Confidence: **high** (multi-source corroboration).
- Topic `agent-vs-skill discriminator`: searched ADR index (matched ADR-030, ADR-012, ADR-013, ADR-040, ADR-058), governance docs (matched SKILL-CREATION-CRITERIA, agent-consolidation-process). Confidence: **high**.
- Topic `consolidation effort`: searched issue tracker (matched #1944, #1946, #1949, #1950, #1932). Confidence: **high**.
- Topic `truncation / context budget`: searched session jsonl logs (matched `[N lines truncated]` markers and active context-mode plugin). Confidence: **medium** (observed truncation in tool output; user's claim of "every new session warns >1%" not directly grepped, but the truncation behavior is verifiable in session jsonl).
- Skills used: chestertons-fence (git archaeology via `git log`), memory (lexical search via grep + gh CLI), exploring-knowledge-graph (substituted with direct gh + grep + view due to skill-as-tool unavailability in this environment). Coverage note: **MCP-driven exploring-knowledge-graph not invoked**; substituted with direct issue-tracker + filesystem traversal. Result equivalent for this depth.

---

## 1. Problem Statement

The `.claude/agents/` directory contains 23 agents. Two independent failure modes exist concurrently:

1. **Misclassification**: at least one agent (`spec-generator`) shipped 9-of-13 frontmatter schema violations on PR #1995 because the agent body was not forced to re-read `.agents/governance/spec-schemas.md`. The structural cause is shape mismatch: spec-generator is ~80% reference material (format spec, validation rules, anti-pattern catalogs) and ~20% reasoning, which is textbook skill shape per ADR-030, but it ships as an agent. Issues #2001 and #2002 reached the same verdict by independent paths. Other agents may share this shape mismatch.
2. **Catalog load pressure**: Claude Code runtime truncates loaded agent/skill content when the catalog exceeds the load budget. Items get lost or not loaded. The catalog-size pressure is the broader context this audit serves.

The discriminator from #2001/#2002 (4 criteria) plus a 5th load-budget criterion gives a deterministic test for misclassification. Without an audit, refactor decisions are made one-at-a-time per spec-PR-failure cycle, which is the very anti-pattern this issue closes.

## 2. User Stories

| Story | Who | Action | Observable outcome |
|-------|-----|--------|-------------------|
| US-1 | Catalog maintainer (rjmurillo) | reads the audit table | sees one row per agent with verdict (skill / context-fork-skill / keep-as-agent / merge-into-X) and per-criterion evidence |
| US-2 | Phase 2 refactor PR author | filters audit for verdict ≠ keep-as-agent | gets a backlog of refactor candidates, each with one-line justification |
| US-3 | ADR-030 / ADR-036 reviewer | inspects the audit | can verify each verdict traces to the ADR-documented criteria |
| US-4 | Epic #1944 owner | links audit from #1944 | sees agent-side progress alongside M1-M4 + Wave 2 skill-side work |
| US-5 | CodeRabbit / future bot reviewer | reads the audit table during a PR involving an agent | can cite the audit's verdict as evidence in review comments |

## 3. Data Model

### 3.1 Audit row entity

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent` | string | yes | Agent name (filename without .md), e.g. `spec-generator` |
| `c1_orchestrated_via_task` | enum {Yes, No} | yes | Criterion 1: invoked from a slash command via `Task(subagent_type=…)` rather than spawned by a peer agent |
| `c1_evidence` | string | yes | One-line citation (e.g., `.claude/commands/spec.md:Step 6 Task(subagent_type="spec-generator")`) |
| `c2_reference_pct` | enum {≥70%, 50-69%, <50%} | yes | Criterion 2: body composition, reference material vs reasoning |
| `c2_evidence` | string | yes | One-line rationale (count of: format spec, validation rules, anti-pattern lists, decision tables) |
| `c3_sibling_is_skill` | enum {Yes, No, N/A} | yes | Criterion 3: is a sibling artifact in the same pipeline already a skill? |
| `c3_evidence` | string | yes | One-line citation (e.g., `requirements-interview is a skill in /spec pipeline`) |
| `c4_schema_drift` | enum {Yes, No, Unknown} | yes | Criterion 4: has the agent produced schema/format drift caught by review automation? |
| `c4_evidence` | string | yes | One-line citation (PR number + bot thread count, or `no PR history`) |
| `c5_frontmatter_bytes` | integer | yes | Criterion 5: bytes of agent frontmatter (always-loaded portion of the catalog) |
| `c5_full_body_bytes` | integer | yes | Bytes of full agent body (loaded on Task invocation) for context |
| `has_shared_template` | enum {Yes, No} | yes | ADR-036 dual-source: does `templates/agents/{name}.shared.md` exist? |
| `discriminator_score` | integer | yes | Count of Yes on c1, c2 (≥70%), c3, c4 (excludes Unknown) |
| `verdict` | enum {skill, context-fork-skill, keep-as-agent, merge-into-X} | yes | Recommendation per `verdict_decision_thresholds: discriminator-2-of-4` rule |
| `verdict_rationale` | string | yes | One-line justification |

### 3.2 Identity and lifecycle

- Identity: `agent` field (unique per row).
- Invariant: `discriminator_score = count(c1=Yes, c2=≥70%, c3=Yes, c4=Yes)`.
- Invariant: `verdict = skill` if `discriminator_score >= 2` AND no isolation-required exception is documented.
- Lifecycle: audit table is **point-in-time**. The committed file at `.agents/audits/2026-05-10-agent-skill-classification-audit.md` includes the date. Re-runs produce a new dated file; old files preserved for diff.

## 4. Integrations

| External system | Failure mode | Idempotency |
|-----------------|--------------|-------------|
| GitHub issue #2003 | Comment posting fails (rate limit, auth) | Comment includes a unique session marker; re-runs replace via edit, not append |
| `.agents/audits/` filesystem | Disk full, permission denied | Write-then-rename; partial writes detected via missing rename |
| `.claude/agents/*.md` reads | Files removed mid-audit | Audit captures git SHA at start; warns if SHA changes mid-run |
| `templates/agents/*.shared.md` reads | Same as above | Same |
| `.claude/commands/*.md` and `templates/commands/*.md` reads (for c1 detection) | Same as above | Same |

## 5. Failure modes

- **Audit goes stale before Phase 2 starts**: agents added or modified between Phase 1 and Phase 2. Mitigation: audit file includes git SHA; Phase 2 PRs cite SHA and re-verify the targeted agent's row before refactor.
- **c2 (reference vs reasoning) is subjective**: two reviewers might score the same agent differently. Mitigation: c2 evidence column requires *count* of structured-reference elements (format spec sections, decision tables, anti-pattern lists), not gestalt judgment. Reviewer who disagrees can re-count.
- **c3 sibling-is-skill is ambiguous when no clear "pipeline" exists**: e.g., `analyst` agent is invoked from many slash commands. Mitigation: c3=N/A when no single pipeline. N/A counts as 0 for the score.
- **Verdict assigned but agent is in active use**: refactor risk. Mitigation: verdict is a *recommendation*, not an action. Phase 2 PRs are the action; each Phase 2 PR is a separate issue per `phase_2_3_governance: separate-issues`.
- **Schema enum drift in the audit's own frontmatter**: meta-irony. Mitigation: this PRD and the REQ/DESIGN/TASK files are validated against `.agents/governance/spec-schemas.md` before commit; the audit table file uses a documented schema in its own header.
- **Truncation context worsens before audit lands**: catalog grows during the audit window. Mitigation: audit's c5 column quantifies the bytes saved by each verdict=skill recommendation, giving a load-budget impact estimate.

## 6. Security

- **No credentials handled**. Audit reads public files in `.claude/agents/` and `.agents/`.
- **No PII**. Agent files contain prompts and metadata only.
- **Input validation**: agent files are markdown; no execution. The audit does not invoke any agent.
- **Output validation**: the table commit goes through normal PR review; the issue comment is rate-limited by GitHub.

## 7. Observability

- **Logs**: audit produces a structured log of per-agent reads (file path, SHA, byte count, criteria scores). Stored under `.agents/audits/2026-05-10-agent-skill-classification-audit.log` (text).
- **Metrics**: audit emits one count to `.agents/metrics/agent-skill-audit-runs.tsv` (timestamp | agent_count | verdict_skill_count | verdict_context-fork-skill_count | verdict_keep_count | verdict_merge_count) so re-runs can be diff'd.
- **Traces**: not applicable (single-process, single-pass audit).
- **Alerts**: not applicable (manual run).

## 8. Acceptance criteria

Each criterion is independently testable as pass/fail. Criteria use EARS syntax.

1. **AC-1**: WHEN the audit is run THE SYSTEM SHALL produce a markdown file at `.agents/audits/YYYY-MM-DD-agent-skill-classification-audit.md` SO THAT the table is durable, version-controlled, and reviewable in a PR.
2. **AC-2**: WHEN the audit is run THE SYSTEM SHALL post or update a comment on issue #2003 that links to the committed file SO THAT the issue's acceptance criterion ("Phase 1 audit table posted as a comment") is satisfied without duplicating the table.
3. **AC-3**: THE SYSTEM SHALL include exactly one row per file matching `.claude/agents/*.md` excluding `AGENTS.md` and `CLAUDE.md` (expected: 23 rows on 2026-05-10) SO THAT no agent is skipped or double-counted.
4. **AC-4**: WHEN any row's c1, c2, c3, c4, or c5 columns are populated THE SYSTEM SHALL include a one-line evidence citation in the corresponding `*_evidence` column SO THAT the verdict is auditable, not assertional.
5. **AC-5**: THE SYSTEM SHALL set `verdict = skill` when `discriminator_score >= 2` AND no `keep-as-agent` exception is documented in `verdict_rationale` SO THAT the rule from issue #2003 ("Anything scoring 2+ Yes is a candidate") is applied deterministically.
6. **AC-6**: THE SYSTEM SHALL set `verdict = keep-as-agent` when the agent body documents a context-isolation requirement that cannot be satisfied by `context: fork` SO THAT genuine separate-context agents (e.g., `orchestrator`, `analyst`, `critic`, `pr-comment-responder` per #2003 counter-signal section) are correctly preserved.
7. **AC-7**: THE SYSTEM SHALL include a `has_shared_template` column populated by checking for `templates/agents/{agent}.shared.md` per ADR-036 SO THAT Phase 2 refactor planning correctly targets dual-source agents.
8. **AC-8**: THE SYSTEM SHALL include a per-row `c5_frontmatter_bytes` measurement (bytes from start of file to end of YAML frontmatter delimiter) SO THAT load-budget impact of `verdict = skill` recommendations is quantified.
9. **AC-9**: THE SYSTEM SHALL include a summary footer with: total agents, count by verdict, total `c5_frontmatter_bytes` saved if all `verdict = skill` rows were migrated, and citations to ADR-030, ADR-036, and `.agents/governance/agent-consolidation-process.md` SO THAT readers see the audit's authority and impact at a glance.
10. **AC-10**: THE SYSTEM SHALL produce a Phase 2 backlog list (one bullet per `verdict ≠ keep-as-agent` row, with one-line justification) committed alongside the audit table SO THAT the issue's second acceptance criterion ("List of refactor candidates with one-line justification per agent") is satisfied.
11. **AC-11**: THE SYSTEM SHALL record a verdict (skill / context-fork-skill / keep-as-agent / merge-into-X) for every row SO THAT the issue's third acceptance criterion ("Decision recorded for each agent") is satisfied; "no decision" is not a valid verdict.
12. **AC-12**: WHEN the Phase 3 CI check is referenced THE SYSTEM SHALL link to a separate filed GitHub issue (not implement the check) SO THAT the issue's fourth acceptance criterion ("Phase 3 CI check spec'd in separate issue if implementation is non-trivial") is satisfied without expanding this audit's scope.

## 9. Out of scope

- Phase 2 refactor PRs (one per `verdict ≠ keep-as-agent` candidate). Tracked separately per `phase_2_3_governance: separate-issues`.
- Phase 3 CI check implementation. Tracked separately per AC-12.
- Auditing the `.caveman-active` 24th agent file under `~/.claude/`. Excluded per `include_24th_caveman_agent: exclude-with-note`.
- Auditing `src/copilot-cli/agents/` and `src/vs-code-agents/` (downstream of `templates/agents/`).
- Amending `.agents/governance/SKILL-CREATION-CRITERIA.md` (about creating new skills; this audit reclassifies existing agents).
- Invoking `eval-knowledge-integration.py` or `eval-skill-overlap.py` (#1932) to score agents quantitatively. Deferred to Phase 2 if needed.
- Modifying the `.agents/governance/agent-consolidation-process.md` workflow itself (audit applies it; does not change it).
- Producing a similar audit for `.claude/skills/` (covered by epic #1944 Wave 2 #1950).

## 10. Deferred

| Decision | Owner | When to decide |
|----------|-------|----------------|
| Whether to invoke `eval-skill-overlap.py` for quantitative agent ranking | Phase 2 PR author | When sizing first refactor candidate |
| Whether to amend ADR-030 to make the discriminator more directive | architect agent | After 3+ Phase 2 refactors land successfully |
| Whether to file Wave 3 epic for periodic re-audits | rjmurillo | After Wave 2 (#1950) completes |
| Whether `merge-into-X` verdicts should propose specific X targets in Phase 1 or defer to Phase 2 | rjmurillo | At time of audit execution; default = name X if obvious, otherwise leave as `merge-into-?` |

## 11. Open questions (resolved 2026-05-10 before TASK-011 execution)

| Question | Resolution |
|----------|------------|
| For c2 (reference vs reasoning) scoring, what counts as "structured reference"? | **Count rule**: structured-reference elements are (a) markdown tables, (b) numbered/bulleted decision-tree lists, (c) anti-pattern catalogs, (d) format/schema specifications, (e) validation rule lists. Narrative paragraphs of any length count as reasoning unless they are introducing or concluding one of (a)-(e). c2 = `≥70%` if reference elements occupy ≥70% of body line count; `50-69%` if mixed; `<50%` if predominantly reasoning. |
| For c3 (sibling-is-skill), how is "same pipeline" defined when an agent is invoked from multiple slash commands? | **3-pipeline rule**: c3 = `N/A` (counts as 0 in `discriminator_score`) when an agent is invoked by 3 or more distinct slash commands. Below 3 pipelines, evaluate each pipeline; c3 = Yes if any pipeline contains a sibling skill. This avoids over-fitting multi-purpose agents like `analyst`, `critic`, `architect` into the discriminator. |
| Should the audit include an agent's *current* invocation count from session logs as additional context? | **Deferred to Phase 2**. Session-log invocation counts are interesting for usage-based pruning (per `agent-consolidation-process.md` trigger "<5% of agent invocations") but are not part of the issue #2003 discriminator. Not added as a column. |

## 12. CVA summary

- **Common across all 23 agents**: frontmatter shape (name + description + tools), markdown body, invocability via `Task(subagent_type=…)` from orchestrator or slash command, residence in `.claude/agents/`.
- **Variabilities**: body length (range observed: ~50 lines to ~500+ lines), reference-vs-reasoning ratio, presence of `templates/agents/*.shared.md` sibling per ADR-036, allowed-tools restriction, isolation-required (genuine separate-context need).
- **Relationships**: orchestrator routes to all agents; some agents are invoked directly from slash commands (skill-shape signal per c1); some have skill siblings in the same pipeline (c3); some have generated platform variants under `src/copilot-cli/` and `src/vs-code-agents/` (downstream of `templates/agents/`).

## 13. Complexity tier

**Tier 3 (Senior)**. Rationale:
- Phase 1 deliverable (this PRD) is a bounded analysis of 23 agents with a deterministic discriminator. Reversible (it's a markdown file).
- Decomposed from a Tier 4 broader effort (catalog consolidation across both agents and skills, epic #1944).
- CVA analysis applied (§12). Cross-team alignment applied (parent epic #1944).
- ADR not strictly required for the audit itself; the audit's *recommendations* may trigger follow-on ADR amendments (deferred per §10).

## 14. Traceability

| Artifact | Location |
|----------|----------|
| Requirement | `.agents/specs/requirements/REQ-011-agent-skill-classification-audit.md` |
| Design | `.agents/specs/design/DESIGN-011-agent-skill-classification-audit.md` |
| Task | `.agents/specs/tasks/TASK-011-agent-skill-classification-audit.md` |
| Audit output (Phase 1 deliverable) | `.agents/audits/2026-05-10-agent-skill-classification-audit.md` (created by TASK-011) |
| Source issue | GH-2003 |
| Parent epic | GH-1944 |
| Authority | ADR-030, ADR-036, `.agents/governance/agent-consolidation-process.md` |
