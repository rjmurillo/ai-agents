# Pre-PR Validation Workflow Diagram

## Workflow Overview

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                         EPIC #265: PRE-PR VALIDATION SYSTEM               │
│                         All 7 Sub-Issues COMPLETE                         │
└─────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: PLANNING (Issues #261, #262)                                          │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────┐                        ┌──────────┐                             │
│  │ Planner  │  Creates plan with  →  │  Critic  │  Validates plan includes   │
│  │  #261    │  Pre-PR validation     │  #262    │  all 5 validation          │
│  │          │  work package          │          │  categories                │
│  └──────────┘                        └──────────┘                             │
│       │                                    │                                   │
│       │  Plan Template:                    │  Readiness Checklist:             │
│       │  • Cross-Cutting Concerns          │  • Validation tasks included      │
│       │  • Fail-Safe Design                │  • Cross-cutting addressed        │
│       │  • Test-Implementation             │  • Fail-safe planned             │
│       │  • CI Environment Sim              │  • Test strategy complete        │
│       │  • Env Variable Check              │  • CI environment considered     │
│       │                                    │                                   │
│       └────────────────────┬───────────────┘                                   │
│                            │                                                   │
│                            ▼                                                   │
│                     APPROVED PLAN                                              │
│                            │                                                   │
└────────────────────────────┼───────────────────────────────────────────────────┘
                             │
                             │
┌────────────────────────────┼───────────────────────────────────────────────────┐
│ PHASE 2: IMPLEMENTATION (Issue #257)                                           │
├────────────────────────────┼───────────────────────────────────────────────────┤
│                            ▼                                                   │
│                  ┌─────────────────┐                                           │
│                  │  Implementer    │                                           │
│                  │     #257        │                                           │
│                  │                 │                                           │
│                  │  Executes code  │                                           │
│                  └─────────────────┘                                           │
│                           │                                                    │
│                           │                                                    │
│                           ▼                                                    │
│            ┌──────────────────────────────┐                                    │
│            │ Pre-PR Validation Gate       │                                    │
│            │ 13-Item Checklist (BLOCKING) │                                    │
│            └──────────────────────────────┘                                    │
│                           │                                                    │
│            Code Quality (5 items):         Error Handling (3 items):           │
│            • No TODO/FIXME/XXX            • No silent failures                │
│            • No hardcoded values          • Fail-safe defaults               │
│            • No duplicate code            • Exit code validation             │
│            • Complexity ≤10               Test Coverage (3 items):            │
│            • All tests pass               • Unit tests cover new methods      │
│                                           • Edge cases tested                 │
│            CI Readiness (2 items):        • No mock divergence                │
│            • Tests pass with CI flags                                          │
│            • Env vars documented                                               │
│                           │                                                    │
│                           ▼                                                    │
│                  ✅ Self-Validation PASS                                       │
│                           │                                                    │
└───────────────────────────┼────────────────────────────────────────────────────┘
                            │
                            │
┌───────────────────────────┼────────────────────────────────────────────────────┐
│ PHASE 3: ORCHESTRATOR ROUTING (Issue #259)                                     │
├───────────────────────────┼────────────────────────────────────────────────────┤
│                           ▼                                                    │
│                 ┌──────────────────┐                                           │
│                 │  Orchestrator    │                                           │
│                 │      #259        │                                           │
│                 │                  │                                           │
│                 │  Routes to QA    │                                           │
│                 └──────────────────┘                                           │
│                           │                                                    │
│            ┌──────────────┴──────────────┐                                     │
│            ▼                             ▼                                     │
│   ┌────────────────┐           ┌─────────────────────┐                        │
│   │ QA Agent #258  │           │ Security Agent #260 │                        │
│   │                │           │                     │                        │
│   │ Pre-PR Quality │           │ Post-Implementation │                        │
│   │ Gate (MAND)    │           │ Verification (PIV)  │                        │
│   └────────────────┘           │ (Conditional)       │                        │
│            │                   └─────────────────────┘                        │
│            │                             │                                     │
│            │  4-Step Protocol:           │  PIV Protocol:                      │
│            │  1. CI Test Validation      │  • Security controls verified       │
│            │  2. Fail-Safe Patterns      │  • No new vulnerabilities          │
│            │  3. Test Alignment          │  • Secrets not hardcoded           │
│            │  4. Coverage Check          │  • Input validation present        │
│            │                             │                                     │
│            ▼                             ▼                                     │
│    APPROVED / BLOCKED          APPROVED / CONDITIONAL / REJECTED              │
│            │                             │                                     │
│            └─────────────┬───────────────┘                                     │
│                          │                                                     │
│                          ▼                                                     │
│              ┌────────────────────────┐                                        │
│              │  DevOps Agent #263     │  [Optional - Advisory]                │
│              │                        │                                        │
│              │  Local CI Simulation   │  Provides guidance for:               │
│              │  Guidance              │  • CI environment setup               │
│              │                        │  • Protected branch testing           │
│              │                        │  • Secret scanning                    │
│              └────────────────────────┘                                        │
│                          │                                                     │
└──────────────────────────┼─────────────────────────────────────────────────────┘
                           │
                           │
┌──────────────────────────┼─────────────────────────────────────────────────────┐
│ PHASE 4: VERDICT AGGREGATION (Issue #259)                                      │
├──────────────────────────┼─────────────────────────────────────────────────────┤
│                          ▼                                                     │
│              ┌────────────────────────┐                                        │
│              │  Orchestrator          │                                        │
│              │  Aggregates Verdicts   │                                        │
│              └────────────────────────┘                                        │
│                          │                                                     │
│                          │                                                     │
│              ┌───────────┴────────────┐                                        │
│              │                        │                                        │
│              ▼                        ▼                                        │
│    ┌──────────────────┐    ┌──────────────────┐                              │
│    │  ALL APPROVED    │    │  ANY BLOCKED     │                              │
│    │                  │    │  or REJECTED     │                              │
│    │  QA: APPROVED    │    │                  │                              │
│    │  Security: OK    │    │  Issues found    │                              │
│    └──────────────────┘    └──────────────────┘                              │
│              │                        │                                        │
│              ▼                        ▼                                        │
│    ┌──────────────────┐    ┌──────────────────┐                              │
│    │  ✅ CREATE PR    │    │  ❌ BLOCK PR     │                              │
│    │                  │    │                  │                              │
│    │  All gates pass  │    │  Return to       │                              │
│    │  Safe to review  │    │  Implementer     │                              │
│    └──────────────────┘    │  with issues     │                              │
│                            └──────────────────┘                              │
│                                      │                                         │
│                                      └───────────┐                             │
│                                                  │                             │
└──────────────────────────────────────────────────┼─────────────────────────────┘
                                                   │
                                                   ▼
                                        ┌────────────────────┐
                                        │  Fix Issues        │
                                        │  Re-run Validation │
                                        └────────────────────┘
                                                   │
                                                   └──── (Loop back to Phase 2)
```

## Agent Interaction Matrix

| From Agent | To Agent | Trigger | Payload | Verdict |
|------------|----------|---------|---------|---------|
| Planner (#261) | Critic (#262) | Plan complete | Plan document | READY/NOT READY |
| Implementer (#257) | Orchestrator (#259) | Code complete | Self-validation checklist | Request PR |
| Orchestrator (#259) | QA (#258) | Pre-PR validation | Changed files | APPROVED/BLOCKED |
| Orchestrator (#259) | Security (#260) | Security-relevant | Changed paths | APPROVED/CONDITIONAL/REJECTED |
| Orchestrator (#259) | Implementer (#257) | Validation blocked | Blocking issues | Fix and retry |
| QA (#258) | DevOps (#263) | CI guidance needed | Validation context | Advisory guidance |

## Validation Evidence Chain

```text
┌─────────────────────────────────────────────────────────────────┐
│ EVIDENCE TRAIL (All Agents Produce Documented Artifacts)         │
└─────────────────────────────────────────────────────────────────┘

1. PLANNER (#261)
   Output: .agents/planning/NNN-feature-plan.md
   Contains: Pre-PR Validation work package with 5 tasks
   ↓

2. CRITIC (#262)
   Output: .agents/critique/NNN-feature-plan-review.md
   Contains: Pre-PR Readiness Assessment (READY/NOT READY)
   ↓

3. IMPLEMENTER (#257)
   Output: Self-validation checklist (13 items) in commit message or session log
   Contains: Evidence of all 13 items passing
   ↓

4. QA (#258)
   Output: .agents/qa/pre-pr-validation-[feature].md
   Contains:
   • CI Test Validation (PASS/FAIL)
   • Fail-Safe Pattern Verification
   • Test-Implementation Alignment
   • Coverage Metrics
   • Verdict: APPROVED or BLOCKED
   ↓

5. SECURITY (#260) [if security-relevant]
   Output: .agents/security/PIV-[feature].md
   Contains:
   • Security control verification
   • Vulnerability assessment
   • Secret scanning results
   • Verdict: APPROVED/CONDITIONAL/REJECTED
   ↓

6. DEVOPS (#263) [if CI issues found]
   Output: .agents/devops/ci-validation-[date].md
   Contains:
   • Local CI simulation results
   • Environment setup verification
   • Protected branch testing
   • Recommendation: READY FOR PR / NEEDS FIXES
   ↓

7. ORCHESTRATOR (#259)
   Output: .agents/sessions/YYYY-MM-DD-session-NN.json
   Contains:
   • Aggregated validation summary
   • QA verdict
   • Security verdict (if applicable)
   • Final decision: PR CREATED or BLOCKED
```

## Timeline Visualization (Actual Execution)

```text
Day 1: 2025-12-29
┌──────────────────────────────────────────────────────────────────┐
│ 20:21 UTC                                                         │
│   ├─ #262 (critic) CLOSED          ┐                            │
│ 20:27 UTC                           │ Parallel Execution         │
│   ├─ #260 (security) CLOSED         │ (6 issues in 8 minutes)   │
│   ├─ #261 (planner) CLOSED          │                            │
│ 20:28 UTC                           │                            │
│   ├─ #257 (implementer) CLOSED      │                            │
│   ├─ #263 (devops) CLOSED          ┘                            │
└──────────────────────────────────────────────────────────────────┘

Day 2: 2025-12-30
┌──────────────────────────────────────────────────────────────────┐
│ 04:43 UTC                                                         │
│   ├─ #259 (orchestrator) CLOSED    [Sequential after foundation] │
└──────────────────────────────────────────────────────────────────┘

Day 3: 2025-12-31
┌──────────────────────────────────────────────────────────────────┐
│ 04:30 UTC                                                         │
│   ├─ #258 (qa) CLOSED              [Final polish]               │
└──────────────────────────────────────────────────────────────────┘

Total Duration: 3 days
Critical Path: critic → planner → implementer → qa → orchestrator
Optimization: 6/7 issues executed in parallel on Day 1
```

## Success Criteria Tracking

```text
IMPLEMENTATION PHASE (COMPLETE ✅)
┌─────────────────────────────────────────────────────┐
│ ✅ All 7 agent instructions updated                  │
│ ✅ MANDATORY/BLOCKING gates documented               │
│ ✅ Evidence templates provided                       │
│ ✅ Handoff protocols defined                         │
│ ✅ End-to-end workflow documented                    │
└─────────────────────────────────────────────────────┘

VALIDATION PHASE (PENDING ⏳)
┌─────────────────────────────────────────────────────┐
│ ⏳ Test on real feature PR                           │
│ ⏳ Measure vs. PR #249 baseline                      │
│ ⏳ Confirm 70% bug reduction (7 → 2 or fewer)        │
│ ⏳ Validate workflow compliance                      │
└─────────────────────────────────────────────────────┘

TARGET METRICS (Based on PR #249 Baseline)
┌──────────────────┬─────────┬─────────┬──────────────┐
│ Metric           │ Before  │ Target  │ Measurement  │
├──────────────────┼─────────┼─────────┼──────────────┤
│ P0-P1 bugs       │ 7       │ 0-2     │ Next PR      │
│ Review comments  │ 97      │ <30     │ Next PR      │
│ Rework %         │ 43%     │ <10%    │ Next PR      │
│ Review cycles    │ Multiple│ 1-2     │ Next PR      │
│ Validation time  │ 0 hrs   │ <4 hrs  │ Next PR      │
└──────────────────┴─────────┴─────────┴──────────────┘
```

## Key Design Decisions

1. **BLOCKING Semantics**: All validation gates explicitly marked as BLOCKING to prevent bypass
2. **Evidence Templates**: Every agent produces documented artifacts for auditability
3. **Orchestrator as Hub**: All routing and aggregation centralized in orchestrator
4. **Conditional Security**: PIV only triggered for security-relevant changes
5. **Advisory DevOps**: CI simulation guidance is non-blocking, provided as needed
6. **Fail-Safe Verdicts**: Binary APPROVED/BLOCKED (QA), ternary APPROVED/CONDITIONAL/REJECTED (Security)
7. **13-Item Checklist**: Streamlined from 5 categories to prevent validation fatigue

## References

- **Comprehensive Plan**: `.agents/planning/265-pre-pr-validation-system.md` (601 lines)
- **Executive Summary**: `.agents/planning/265-pre-pr-validation-system-executive-summary.md` (139 lines)
- **Epic**: Issue #265
- **Sub-Issues**: #257, #258, #259, #260, #261, #262, #263 (all CLOSED)
- **Baseline PR**: PR #249 (97 comments, 7 P0-P1 bugs, 43% rework)

---

**Status**: ✅ Architecture complete | ⏳ Awaiting real-world validation
**Next**: Exercise workflow on next feature PR to validate 70% bug reduction target
