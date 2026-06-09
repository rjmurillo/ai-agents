# Issue #2479 Phase 2: Per-Agent Principle Gap Audit

> Phase 2 of the 3-phase Angie Jones principle audit (#2478 -> #2479 -> #2480).
> Audits the Phase-1 top-3 noisiest quality-gate agents (roadmap, analyst, devops)
> against the 4 principles, grounded in each agent's canonical prompt at
> `.claude/skills/review/references/<role>.md`. Phase-1 baseline: issue #2478 deliverable.

## Method

Each agent prompt was read and scored against the 4 principles (confidence
threshold, actionable examples, CI awareness, iteration loop). `present` is the
prompt's current coverage (absent / weak / adequate); `evidence` cites file:line;
`fix` is the concrete prompt change; `leverage` is expected noise reduction vs
effort, grounded in the Phase-1 pattern.

## roadmap

| Principle | Present | Evidence (file:line) | Fix | Leverage |
|-----------|---------|----------------------|-----|----------|
| Confidence threshold | absent | roadmap.md:25-29 mandates 'When CONTEXT_MODE is not full, you MUST NOT emit PASS... Emit WARN'. No confidence floor, no abstain path, no instruction to suppress a WARN it cannot back with evidence. | Add: 'Under summary/partial context, if you find no concrete strategic conflict in the metadata you DID receive, emit PASS with a note that line-level review was unavailable; raise WARN only when the available metadata (title, file list, PR description) shows a specific scope or alignment problem you can name.' | high |
| Actionable examples | weak | roadmap.md:184 requires 'location: file:line ... Required for every finding' and :185 a one-sentence fix, but every Analysis Focus question (roadmap.md:47-85) is an open-ended prompt ('Could this effort be better spent elsewhere?') with zero worked examples of a valuable vs noise roadmap finding for this domain. | Add a two-row worked example contrasting a backed finding ('PR adds telemetry module not on the Q3 roadmap; orchestrator.py:120 introduces a new dependency; recommend deferring per ADR-NNN') against a noise finding ('investment may be disproportionate'), and require strategic findings cite the contradicted goal/ADR/issue. | high |
| CI awareness | absent | roadmap.md mentions CI only in the harness header (roadmap.md:14) and dependency-update grounding (roadmap.md:40); it has no deterministic-CI coverage map or 'do not restate automated gates' list. | Add a 'Do not restate' clause naming what deterministic CI covers (lint, type, tests, schema, secret scan, dash guard) so the axis confines itself to strategy/scope/value and never emits a WARN about a class already gated. | medium |
| Iteration loop | absent | roadmap.md:116-120 (Concerns table) and :122-124 (Recommendations) invite emitting non-blocking discussion points as findings; nothing forbids 'acceptable, no action required' confirmations or duplicating a sibling axis (analyst/architect/qa), which is the exact Phase-1 self-resolving-WARN pattern. | Add: 'Do not emit findings that another axis owns (correctness->qa, design->architect, security->security); do not emit confirmations, acknowledgements, or any finding whose recommendation is no-op / acceptable / no action required. If you have nothing strategically blocking to say, emit PASS with an empty findings list.' | high |

**Highest-leverage gap:** roadmap.md:25-29 forces WARN whenever CONTEXT_MODE != full; replace the mandatory-WARN with an abstain-to-PASS-with-note path so the axis stops firing evidence-free WARNs it then self-resolves to "no action required".

## analyst

| Principle | Present | Evidence (file:line) | Fix | Leverage |
|-----------|---------|----------------------|-----|----------|
| Confidence threshold | weak | analyst.md:25-29 forbids PASS when CONTEXT_MODE is not full and forces a WARN instead; analyst.md:47 (falsifiability) tells it to flag unmetricked claims. But nowhere does it set a confidence bar for emitting a finding, or say to abstain/stay silent when evidence is thin. The only non-full-context instruction does the opposite of suppression: it mandates a WARN it cannot back ('Emit WARN ... and name the specific evidence you would need'). | Add a rule: 'Emit a finding only when you can cite the file:line and the concrete defect; if confidence is below ~80% or the evidence is summary/partial, omit the finding rather than raising a speculative WARN, and note the unreviewed area in MESSAGE instead.' | medium |
| Actionable examples | weak | analyst.md:110 and 164-170 require a location 'file:line' and a one-sentence recommendation per finding (structurally enforced). But the prompt gives zero worked examples of a valuable analyst finding vs. a noise finding for this domain, and the focus areas (analyst.md:53-83) are generic yes/no prompts ('Is the code easy to understand?') that invite subjective, non-actionable observations. | Add a worked example pair for this domain (one valuable finding with file:line and a concrete fix; one noise finding to suppress, e.g. 'restating a QA test-coverage gap' or 'a no-action-required confirmation') so the model has a positive and negative template. | medium |
| CI awareness | absent | Grep of analyst.md for 'deterministic\|CI (covers\|runs)\|other ax\|sibling' returns zero matches. The prompt names CONTEXT_MODE and pre-run test results exist for QA (qa.md:80-95) but analyst.md never tells the analyst what deterministic CI (lint, type-check, dash-guard, pre_pr.py) or the other 10 Stage-2 axes already cover. Its focus areas (analyst.md:65-70) are a near-verbatim duplicate of architect.md:57-67 (anti-patterns, separation of concerns, module boundaries respected), with no instruction to defer. | Add a 'Scope and non-overlap' section: 'Architectural alignment, coupling/cohesion, anti-patterns, and breaking-change/blast-radius belong to the architect axis; test coverage and error-handling belong to QA; deterministic CI covers lint/type/format/dash rules. Do not restate them; review only code-quality readability/maintainability/simplicity that no other axis or CI gate owns.' | high |
| Iteration loop | absent | Grep for 'duplicat\|already (raised\|covered)\|no action\|suppress' returns zero matches in analyst.md. Nothing forbids restating a sibling-axis finding (the Phase-1 '(duplicates QA finding)' pattern) and nothing forbids emitting 'no action required' confirmations as findings. The Findings table (analyst.md:106-110) and JSON schema (analyst.md:143-159) accept any finding with no positive-finding filter, so confirmations and duplicates pass through. | Add a MUST-NOT: 'Do not emit a finding that duplicates another axis (no "(duplicates X finding)" entries) and do not emit confirmations or "no action required" notes as findings; the empty-findings/PASS case is the correct output when nothing code-quality-specific is wrong.' | high |

**Highest-leverage gap:** analyst.md:65-70 (Architectural Alignment focus area) duplicates architect.md:57-67 verbatim with no defer/non-overlap instruction; add a "Scope and non-overlap" section telling the analyst to skip architecture/QA/CI-owned concerns and review only code-quality readability/maintainability/simplicity no other axis owns. This is the single root cause of the 39-noise verbatim-duplication pattern.

## devops

| Principle | Present | Evidence (file:line) | Fix | Leverage |
|-----------|---------|----------------------|-----|----------|
| Confidence threshold | absent | devops.md:25-29 "When CONTEXT_MODE is not full, you MUST NOT emit PASS ... Emit WARN ... and name the specific evidence you would need to clear the PR." | Replace the mandatory-WARN rule with an abstain path: when context is not full and no concrete defect is visible in the metadata, emit PASS-with-note (or a no-finding WARN that carries zero findings) instead of a WARN that names absent evidence, and add an explicit instruction to suppress any finding the agent cannot back with a file:line from the received diff. | high |
| Actionable examples | weak | devops.md:300-307 already requires `location: file:line` for every finding, but the prompt lacks examples and suppression rules for evidence-free WARNs or non-actionable findings; devops.md:60-72 ("Expected Patterns Do NOT Flag") is the only worked list and it covers patterns-to-ignore, not valuable-vs-noise finding examples. | Add two worked DevOps examples (valuable: "hooks.json:12 uses bare ./hooks path; set $GITHUB_ACTION_PATH prefix"; noise: "cannot verify caching strategy without full diff") plus a suppression rule that drops evidence-free WARNs and no-op rows before they reach the findings list. | high |
| CI awareness | weak | devops.md:178-184 CI/CD Quality Checks table asks the agent to manually mark "YAML syntax valid" and "Actions pinned" with ✅/❌, work that deterministic CI (actionlint, the SHA-pin validator, shellcheck) already gates; devops.md:38-42 only mentions "If CI tests pass, the tooling works" without naming what CI covers. | Add a short "Already covered by deterministic CI, do not restate" list (YAML/actionlint syntax, SHA-pinning validator, shellcheck, dash-prohibition) and instruct the agent to only flag what those gates miss. | medium |
| Iteration loop | absent | devops.md:94, 113-118, and 233-236 make the devops axis review secrets-in-logs and shell-injection, which the sibling security axis (.claude/skills/review/references/security.md) owns; the ✅/❌ status columns at devops.md:178-184 and the PASS-with-confirmation framing at devops.md:248-255 invite "no action required" rows emitted as findings. | Add a rule to defer secrets/injection findings to the security axis (flag only build/pipeline-specific exposure) and forbid emitting any ✅ / "no action required" / "verified OK" row as a finding; confirmations belong in the verdict line only. | medium |

**Highest-leverage gap:** devops.md:25-29 forces a WARN-and-name-the-missing-evidence on every non-full context, which manufactures the Phase-1 noise; replace it with an abstain/PASS-with-note path and a MUST to suppress any finding not backed by a received-diff file:line.

## Top-3 highest-leverage gaps for Phase 3 (#2480)

One patch per agent, in priority order. Each is a separate PR in Phase 3 to keep the review surface small.

1. **roadmap** (.claude/skills/review/references/roadmap.md): roadmap.md:25-29 forces WARN whenever CONTEXT_MODE != full; replace the mandatory-WARN with an abstain-to-PASS-with-note path so the axis stops firing evidence-free WARNs it then self-resolves to "no action required".
2. **analyst** (.claude/skills/review/references/analyst.md): analyst.md:65-70 (Architectural Alignment focus area) duplicates architect.md:57-67 verbatim with no defer/non-overlap instruction; add a "Scope and non-overlap" section telling the analyst to skip architecture/QA/CI-owned concerns and review only code-quality readability/maintainability/simplicity no other axis owns. This is the single root cause of the 39-noise verbatim-duplication pattern.
3. **devops** (.claude/skills/review/references/devops.md): devops.md:25-29 forces a WARN-and-name-the-missing-evidence on every non-full context, which manufactures the Phase-1 noise; replace it with an abstain/PASS-with-note path and a MUST to suppress any finding not backed by a received-diff file:line.

These three carry the bulk of the Phase-1 noise (analyst 39, devops 27, roadmap 27;
71% of total). Phase 3 patches the canonical `references/<role>.md` source (the
`.github/prompts/pr-quality-gate-<role>.md` mirrors regenerate from it) and re-runs
the gate on a fresh sample to confirm the noise drop. Control for the
`CONTEXT_MODE: summary` infra confound named in Phase 1 before attributing the delta.
