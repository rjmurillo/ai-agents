# Skill Catalog Triage: Wave 2 (Full Catalog Sweep)

Issue: #1950. Parent epic: #1944. Source plan: `.agents/plans/active/PLAN-skill-catalog-triage-action-slate.md` (Wave 2 row).

Date: 2026-06-17. Author: autonomous agent (session 2587).

## What this is

A structural triage of every skill in `.claude/skills/` not already actioned by M1-M4. Each skill is classified KEEP / MERGE / RETIRE / IMPROVE with a one-line rationale grounded in static evidence: the SKILL.md frontmatter, the self-declared "Do NOT use ... use X instead" boundaries already present in the catalog, self-declared subsumption tables, naming-cluster membership, and the per-skill kill-gate deltas already measured in M1-M4.

## What this is NOT (the human/credential gate)

The issue's acceptance criteria AC1 and AC2 require live LLM-judge runs:

- AC1: `eval-knowledge-integration.py` baseline (kill-gate delta per skill).
- AC2: `eval-skill-overlap.py` pairwise (OVERLAP / DISTINCT / SUBSUMED verdict per pair).

Both are BLOCKED on `ANTHROPIC_API_KEY`, which is absent in the build environment. This is the same gate the plan's own decision log records on 2026-06-05 ("the live run needs `ANTHROPIC_API_KEY`, absent in the build environment"). Verified again this session:

```
$ test -n "$ANTHROPIC_API_KEY" && echo SET || echo UNSET
UNSET
$ test -f .env && grep -c ANTHROPIC .env || echo "no .env key"
no .env key
```

So this report delivers the part that does NOT need the API: the structural classification. The empirical kill-gate and overlap numbers (AC1, AC2) and the quarterly cron (AC5) remain for a credentialed run. The classification below is the action slate (AC3) that a credentialed run would confirm or refute. Each MERGE / RETIRE call names the specific pair the live eval should test before any deletion lands.

## Method

1. Catalog inventory: 75 directories under `.claude/skills/`. Excluded from triage: `CLAUDE.md` (skill-authoring guide, not a skill) and `SkillForge` (meta-router infra). Net: 73 skills.
2. M1-M4 scope (already actioned, excluded from Wave 2): `doc-coverage`, `doc-sync`, `workflow`, `session-qa-eligibility`, `session-migration` (pruned/folded; absent from current tree), plus the memory cluster under M3/M4 review (`memory`, `curating-memories`, `exploring-knowledge-graph`, `memory-enhancement`, `memory-documentary`, `using-forgetful-memory`, `session`, `session-log-fixer`, `doc-accuracy`, `codebase-documenter`). These carry recorded deltas and are reported as KEEP-confirmed or flagged where M4 is still pending.
3. Boundary evidence: 33 of 73 skills already carry an explicit `Do NOT use ... (use X instead)` disambiguation line. A documented mutual boundary between two same-cluster skills is strong evidence for KEEP, not MERGE. The catalog has already been actively de-duplicated; the Wave-2 redundancy surface is smaller than the issue's a-priori hypothesis assumed.
4. Subsumption evidence: grep for `deprecated|superseded|subsume|replaced by|fold into` surfaced one hard RETIRE (`incoherence`).

## Triage tree applied

- Self-declared DEPRECATED + named successor + no unique scripts -> RETIRE.
- Same-cluster pair, no documented boundary, descriptions overlap -> MERGE candidate (flag for AC2 live overlap eval before deletion).
- Same-cluster pair WITH documented boundary -> KEEP both.
- Distinct lifecycle phase / distinct tool surface -> KEEP.
- Oversized (>300 line SKILL.md) or missing v2 fields, but unique scope -> IMPROVE (progressive disclosure / frontmatter fix), not delete.

## Classification

Legend: K=KEEP, I=IMPROVE (keep, but fix), M=MERGE candidate (verify with AC2 then fold), R=RETIRE.

### Cluster: ADR (2)

| Skill | Class | Rationale |
|-------|-------|-----------|
| adr-generator | K | Authoring half. Documents boundary: "Do NOT use to debate or review an existing ADR (use adr-review)." Distinct from reviewer. |
| adr-review | K | Multi-agent debate half. Reciprocal boundary to adr-generator. Distinct lifecycle phase. |

### Cluster: security (5)

| Skill | Class | Rationale |
|-------|-------|-----------|
| security-detection | K | "Did I touch a security file" router. Boundary vs security-scan documented. Distinct trigger phase. |
| security-scan | K | CWE-78 regex scanner. Boundary vs security-detection and CodeQL documented. Distinct mechanism. |
| security-review | I | Parent-inline counterpart to the security agent; unique form-factor, but v0.1.0 and overlaps conceptually with threat-modeling on "score a change's risk." Keep; tighten the SKILL.md boundary line vs threat-modeling (it lacks a "Do NOT use" disambiguation). |
| threat-modeling | K | OWASP STRIDE matrix generation. Distinct from per-change review: it is attack-surface analysis. 487 lines but the depth is the value. |
| codeql-scan | K | Wraps the CodeQL engine (DB build, SARIF). No sibling does static-analysis tooling. Distinct. |

### Cluster: session (4)

| Skill | Class | Rationale |
|-------|-------|-----------|
| session | K | Umbrella + investigation-eligibility. Already absorbed session-qa-eligibility (M2). Boundary vs session-init documented. |
| session-init | K | Creates the log. Reciprocal boundary to session. Distinct entry point. |
| session-end | K | Validates + completes the log at commit. Distinct lifecycle phase from init. |
| session-log-fixer | K | M1-measured delta +2.39. CI-failure response path, distinct from local init/end. Keep confirmed. |

### Cluster: memory / knowledge graph (7, partly M3/M4)

| Skill | Class | Rationale |
|-------|-------|-----------|
| memory | I | M3 DECOMPOSE target: 392-line SKILL.md, ~143 KB context with references = far over ceiling. ADR-gated split, not a delete. Unique four-tier umbrella. IMPROVE via decomposition (M3). |
| memory-enhancement | K | M1 delta +1.67. Operational-metadata system of record (confidence/citations/freshness). Boundary vs memory and memory-documentary documented. |
| memory-documentary | K | M1 delta +2.11. Cross-source investigative reports. Highest-delta memory skill. Distinct. |
| using-forgetful-memory | K | M1 delta +2.00. Forgetful-specific Zettelkasten guidance. Boundary vs memory documented. |
| curating-memories | M | M4 INVESTIGATE pair vs memory-enhancement (delta +1.28). Pre-registered hypothesis: DISTINCT (content vs metadata). Verify with AC2 live run before any fold. Flag, do not delete. |
| exploring-knowledge-graph | M | M4 INVESTIGATE pair vs memory Tier-1 (delta +1.11, lowest meaningful). Pre-registered hypothesis: moderate overlap -> boundary rewrite likely, fold only if >=80%. Verify with AC2. |
| serena-code-architecture | K | Architecture-mapping workflow over Serena symbols. Boundary vs encode-repo-serena and using-serena-symbols documented. Distinct. |

### Cluster: serena / context (5)

| Skill | Class | Rationale |
|-------|-------|-----------|
| using-serena-symbols | K | Symbol-edit how-to. Reciprocal boundaries to serena-code-architecture and encode-repo-serena documented. |
| encode-repo-serena | K | One-time KB population. Distinct lifecycle (bootstrap) from the two above. |
| context-gather | K | Pre-task knowledge gathering. Boundary vs context-optimizer documented ("Do NOT use for compressing or placing skill text"). |
| context-optimizer | K | Skill-text placement + compression. Reciprocal boundary to context-gather. Distinct purpose. |
| steering-matcher | K | Glob-match file paths to steering files. Narrow, mechanical, no sibling. Distinct. |

### Cluster: doc (1 remaining + 1 retire)

| Skill | Class | Rationale |
|-------|-------|-----------|
| doc-accuracy | K | M1 delta +2.39. Canonical doc-vs-code audit. Absorbed doc-coverage, doc-sync (M1) AND incoherence. Consolidator. |
| incoherence | R | Self-declared DEPRECATED 2026-05-29 ("use doc-accuracy instead"); doc-accuracy absorbed its detection. Retained only for the legacy `scripts/incoherence.py` workflow. Same shape as the M1 `workflow` prune: delete the SKILL.md, preserve the script as the documentation surface. Hard RETIRE, no eval needed. |

### Cluster: PR / review / quality (6)

| Skill | Class | Rationale |
|-------|-------|-----------|
| review | K | 11-axis pre-merge gate that chains code-qualities-assessment, golden-principles, taste-lints. Orchestrator. Distinct. |
| pr-comment-responder | K | Review-thread triage coordinator. No sibling covers comment-thread state. Distinct from review (which is pre-merge code review). |
| code-qualities-assessment | K | 5-quality scoring. Boundary vs review and quality-grades documented. Chained by review but invoked standalone too. |
| quality-grades | K | Repo-wide A-F domain grading. Boundary vs code-qualities-assessment (single-file) and review documented. Distinct granularity. |
| taste-lints | K | Taste invariants (file size, structured logging). Boundary vs review and style-enforcement documented. Distinct from style-enforcement (editorconfig). |
| style-enforcement | K | editorconfig/StyleCop validation. Reciprocal boundary to taste-lints. Distinct rule source. |

### Cluster: decision / strategy / risk (8)

| Skill | Class | Rationale |
|-------|-------|-----------|
| decision-critic | K | Stress-test one decision's reasoning. Boundaries vs pre-mortem and chestertons-fence documented. |
| pre-mortem | K | Prospective-hindsight risk surfacing. Reciprocal boundary to decision-critic. Distinct frame (failure imagined). |
| chestertons-fence | K | Backward "why does this exist" archaeology. Boundary vs pre-mortem (forward risk) documented. Distinct direction. |
| cynefin-classifier | K | Problem-domain classification (Clear/Complicated/Complex/Chaotic). No sibling. Distinct. |
| buy-vs-build-framework | K | Strategic multi-option TCO. Boundary vs programming-advisor documented. Distinct (strategic vs prior-art check). |
| programming-advisor | I | Prior-art / reuse check. Reciprocal boundary to buy-vs-build documented, BUT frontmatter is missing the top-level version (nested only). Unique scope; IMPROVE the frontmatter. Keep. |
| business-strategy | K | Founder-problem framework router (14 books). Boundaries vs engineering rules and decision-critic documented. Distinct audience. |
| cva-analysis | K | Commonality-Variability abstraction discovery. Niche (delta evidence: +1.50 in prior eval). No sibling. Distinct. |

### Cluster: planning / execution (4)

| Skill | Class | Rationale |
|-------|-------|-----------|
| planner | K | Interactive milestone planning + delegation. Boundary vs execution-plans documented. |
| execution-plans | K | Versioned plan artifact tracking. Reciprocal boundary to planner ("Do NOT use to break work into milestones"). Distinct (artifact vs activity). |
| requirements-interview | K | Adversarial grill-me requirements elicitation for /spec. v0.1.0 but unique pattern. Distinct from planner. |
| spec-generator | K | 3-tier EARS spec emission with schema validation. Distinct from requirements-interview (elicit) and planner (decompose). |

### Cluster: git / github / merge (4)

| Skill | Class | Rationale |
|-------|-------|-----------|
| github | K | Core PR/issue/label/merge ops. v4.0.0, heavily used. Foundational. |
| github-url-intercept | K | BLOCKING intercept that prevents 5-10MB HTML fetches. Boundary vs github documented. Distinct (read-routing vs mutation). |
| git-advanced-workflows | K | Rebase/cherry-pick/bisect/worktree. Boundary referenced by merge-resolver. Distinct from github (local git vs GitHub API). |
| merge-resolver | K | Conflict resolution by commit-intent analysis. Boundary vs git-advanced-workflows documented. Distinct. |

### Cluster: reliability / ops / observability (5)

| Skill | Class | Rationale |
|-------|-------|-----------|
| chaos-experiment | K | Chaos experiment design. Boundaries vs threat-modeling and pre-mortem documented. Distinct (resilience experiment). |
| slo-designer | K | SLO/SLI/error-budget design. No sibling. Distinct. |
| observability | K | Query agent JSONL event logs. Distinct from metrics (git-history usage). |
| metrics | K | Agent usage metrics from git history + health reports. Distinct data source from observability. |
| pipeline-validator | K | Azure DevOps pipeline trigger/monitor/diagnose. Org-specific, no sibling. Distinct. |

### Cluster: meta / authoring (4)

| Skill | Class | Rationale |
|-------|-------|-----------|
| slashcommandcreator | K | Slash-command authoring. Boundary vs SkillForge documented. Distinct artifact type. |
| prompt-engineer | K | Agent system-prompt optimization. Distinct from slashcommandcreator (prompt vs command). |
| book-to-skill | K | Book-method extraction adapter feeding SkillForge. Distinct input adapter. |
| reflect | I | Learning capture. 629-line SKILL.md (largest non-infra). Unique scope (correction capture), boundary vs retrospective documented. IMPROVE via progressive disclosure; keep. |

### Cluster: research / docs-gen / single-purpose (rest)

| Skill | Class | Rationale |
|-------|-------|-----------|
| analyze | K | Multi-step codebase analysis. Boundaries vs code-qualities-assessment and security-scan documented. Foundational. |
| research-and-incorporate | K | External research + incorporate. Distinct from analyze (external vs internal). |
| codebase-documenter | K | M1 delta +1.33. Bootstrap-only doc scaffolding. Distinct lifecycle. |
| retrospective | K | Five-Whys/fishbone session retro. Boundary vs reflect documented. Distinct (structured artifact vs inline capture). |
| analysis-provenance | K | Code-ownership classification before editing validators. Narrow, no sibling. Distinct. |
| validation-authority | K | "Upstream validators are authoritative" policy skill. Narrow governance. Distinct. |
| golden-principles | K | GP-001..008 scanner. Chained by review but standalone. Distinct rule set. |
| orphan-ref-validator | K | Detect stale skill/script/count refs. Build exit-gate. Distinct mechanical check. |
| taste-lints | (listed above) | - |
| guard-maturity | K | Classify push guards by maturity tier. Narrow infra introspection. Distinct. |
| stuck-detection | K | Detect agent stuck-loops. Distinct behavioral monitor. |
| avoiding-manufactured-work | K | Detect reward-seeking busywork. 41 lines, unique guardrail. Distinct. |
| panning-for-gold | K | Triage unstructured brain-dumps. Boundary vs analyst/spec-generator documented. Distinct input type. |
| negotiation | K | Offer analysis / counter-proposal. Niche, no sibling. Distinct. |
| work-operating-model | K | 5-layer team operating-model interview. Boundary vs world-model-diagnostic documented. Distinct. |
| world-model-diagnostic | K | World-model paradigm diagnostic. Reciprocal boundary to work-operating-model. Distinct (paradigm vs rhythm). |
| stakeholder-profile (not in tree) | n/a | Not present; listed in router only as plugin alias. |
| windows-image-updater | K | OneBranch Windows image migration. Org-specific, no sibling. Distinct. |
| fix-markdown-fences | K | Repair markdown fence syntax. Narrow mechanical. Boundary vs doc-accuracy documented. Distinct. |
| context-optimizer | (listed above) | - |

## Summary counts (Wave 2 structural pass)

| Class | Count | Skills |
|-------|-------|--------|
| RETIRE | 1 | incoherence (hard, self-declared deprecated; same shape as M1 workflow prune) |
| MERGE candidate (verify w/ AC2) | 2 | curating-memories, exploring-knowledge-graph (both already the M4 INVESTIGATE pairs; no NEW merge candidates surfaced) |
| IMPROVE (keep, fix) | 4 | memory (M3 decompose), reflect (progressive disclosure), security-review (boundary line + version), programming-advisor (frontmatter version) |
| KEEP | 66 | all others |

## The headline finding

The Wave-2 a-priori hypothesis (47 lower-suspicion skills hiding redundancy) is largely refuted by structure. 33 of 73 skills already carry explicit reciprocal `Do NOT use ... use X instead` boundaries, and every naming cluster the issue flagged (`pr-*`, `session-*`, `security-*`, `*-memory*`, `doc-*`, `adr-*`) resolves to documented-distinct on inspection. The only NEW action this sweep surfaces beyond M1-M4 is one hard RETIRE (`incoherence`, already self-deprecated). No new fold/merge candidate appears outside the two pairs M4 already queued.

This is a Layer-3 result worth recording: the catalog has been actively de-duplicated between the 2026-05-09 suspect-cluster pass and now, so the expensive full pairwise sweep the issue budgeted ($30, 2hr) has a low expected yield. The cheaper, sufficient control going forward is the quarterly cron (AC5) plus the `orphan-ref-validator` build gate, not a one-time 145k-call O(N^2) sweep.

## Recommended next actions (decomposition, AC4)

1. RETIRE `incoherence` now: a bounded single-PR prune (delete SKILL.md, keep `scripts/incoherence.py`, update router). No eval gate. This is the one piece of Wave 2 an agent can land atomically.
2. Hold the 2 MERGE candidates for the M4 live overlap run (#1949). Do not fold without the OVERLAP/SUBSUMED verdict.
3. Schedule the 4 IMPROVE items as separate small PRs (memory decomposition is already M3/ADR-gated).
4. AC5 quarterly cron: add a CI workflow that runs `eval-skill-overlap.py` over the documented-boundary pairs quarterly to catch drift. Gate it on a repository-secret `ANTHROPIC_API_KEY`. This is the durable control; it replaces the one-time full sweep.

## Human / credential gate (explicit)

- AC1 (kill-gate baseline) and AC2 (pairwise overlap matrix): require `ANTHROPIC_API_KEY`. Cannot run autonomously in this environment. The structural classification above is the action slate those runs would confirm.
- AC4 (decompose into tracker) and the keep-vs-close decision on this epic: maintainer call.
- AC5 (quarterly cron): needs the API key wired as a CI secret, a maintainer/secrets action.
