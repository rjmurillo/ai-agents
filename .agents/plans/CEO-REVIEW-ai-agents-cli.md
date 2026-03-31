# CEO Review: ai-agents CLI Platform

**Skill:** plan-ceo-review (Garry Tan gstack methodology)  
**Project:** ai-agents  
**Branch:** claude/slack-session-VWZ5m  
**Plan:** `.agents/plans/PRD-ai-agents-cli.md`  
**Date:** 2025-03-31  
**Mode:** SELECTIVE EXPANSION  
**Approach:** B (Plugin-First CLI)  
**Slack Thread:** https://richardoss.slack.com/archives/C0A71GL17DL/p1774928243250079?thread_ts=1774922984.514159&cid=C0A71GL17DL

---

## Executive Summary

The PRD proposes building a full CLI (`npx ai-agents`) to compete with Squad CLI. After premise challenge and alternative analysis, the recommendation is **Approach B (Plugin-First)**: a thin CLI that scaffolds `.agents/` and leverages the existing Claude Code plugin marketplace.

**Key Decisions:**
- Ship 4 commands: `init`, `status`, `doctor`, `init --from squad`
- Reuse 70%+ existing infrastructure (26 agents, 61 skills, plugin manifest)
- Timeline: 2-3 weeks to MVP (vs. 8-12 weeks for full CLI)
- P0 differentiator: `--from squad` migration (silent kill shot)

**Verdict:** CLEARED with minor gaps. No critical issues. Ready for implementation.

---

## Pre-Review System Audit

### Repository State
- **Recent commits:** 20+ in past month (active development)
- **Key recent work:** Observability skill, marketplace validation, ADR-053 (exception criteria)
- **Existing CLI tooling:** memory-enhancement (Python), semantic-hooks (Python), validation scripts (27)

### Competitive Landscape (Squad CLI)
- 15 commands (init, upgrade, triage, shell, status, export/import, nap, doctor, etc.)
- `.squad/` directory with team.md, routing.md, decisions.md, agents/{name}/
- Parallel execution, knowledge persistence, decision logging
- Markdown-first config, experimental TypeScript SDK

### Prior Art
- **ADR-045:** Framework extraction via plugin marketplace (planned for Q1 2027)
- **55+ ADRs** showing deep architectural maturity
- **119 memory files** capturing institutional knowledge

---

## Step 0: Nuclear Scope Challenge

### 0A. Premise Challenge

| Premise | Challenge | Verdict |
|---------|-----------|---------|
| "Squad is the main competitor" | Squad has mindshare, but inertia (no structure) is the real competition | Partially valid |
| "CLI is the right form factor" | 61 skills and 25 agents already work inside Claude Code | Questionable — CLI may duplicate existing capability |
| "Open standard wins" | True historically, but needs ecosystem demand | Unproven — need validation |
| "Beat Squad with depth" | Depth is a moat but also complexity burden | Valid but risky |

### 0B. Existing Code Leverage

| Sub-Problem | What Exists | Reuse Potential |
|-------------|-------------|-----------------|
| Initialize agents | Plugin marketplace manifest, 26 agents | HIGH |
| Status/health check | memory-enhancement CLI | MEDIUM |
| Add agents | Plugin marketplace system | HIGH |
| Doctor/validate | 27 validation scripts | HIGH |
| Squad migration | Nothing | LOW (net-new) |

**70%+ of MVP features exist.** The question is packaging, not building.

### 0C. Dream State (12 Months)

```
Today                              →    Dream State (2026-03)
─────────────────────────────────────────────────────────────
Fragmented CLI tools               →    Single `ai-agents` command
61 skills in one repo              →    Community marketplace (500+)
.agents/ format undocumented       →    Published spec v2.0, 3+ adopters
Single maintainer                  →    10+ external contributors
0 external users                   →    1,000+ weekly active repos
```

### 0C-bis. Implementation Alternatives

| Approach | Effort | Risk | Completeness |
|----------|--------|------|--------------|
| A: Full CLI | XL (8-12 weeks) | High | 9/10 |
| **B: Plugin-First (CHOSEN)** | M (2-3 weeks) | Low | 7/10 |
| C: Spec-Only | S (1 week) | Medium | 4/10 |
| D: Wrapper Mode | S (1 week) | Low | 5/10 |

### 0F. Mode Selection

**SELECTIVE EXPANSION** — Hold baseline (Approach B), cherry-pick `--from squad` migration and spec publication.

---

## Section 1: Architecture Review

### System Design

```
┌─────────────────────────────────────────────────────────────────┐
│                     ai-agents CLI (thin)                        │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐    │
│  │  init   │  │ status  │  │ doctor  │  │ init --from     │    │
│  │         │  │         │  │         │  │    squad        │    │
│  └────┬────┘  └────┬────┘  └────┬────┘  └───────┬─────────┘    │
├───────┼────────────┼────────────┼───────────────┼──────────────┤
│       ▼            ▼            ▼               ▼              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Scaffold Service (core)                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                         │              │
│       ▼                                         ▼              │
│  ┌───────────────┐                    ┌───────────────────┐    │
│  │ .agents/      │                    │ .squad/ → .agents │    │
│  │ (output)      │                    │ (migration)       │    │
│  └───────────────┘                    └───────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│           Claude Code Plugin Marketplace (existing)             │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐    │
│  │ core-agents│  │ framework- │  │ session-protocol       │    │
│  │ (26)       │  │ skills (28)│  │ (12 hooks, 3 skills)   │    │
│  └────────────┘  └────────────┘  └────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flows (4 Paths)

| Path | Flow |
|------|------|
| Happy | init → scaffold → install plugin ref → success |
| Nil/Empty | init in empty dir → warn (no .git) → scaffold with defaults |
| Error | init where .agents/ exists → detect conflict → prompt overwrite/abort |
| Migration | --from squad → parse .squad/ → convert → write .agents/ |

### Coupling Assessment

- CLI → Scaffold Service: LOW
- Scaffold → Claude Code plugin system: MEDIUM (marketplace format stability)
- Migration → Squad format: LOW (one-way read)
- Templates → .agents/ spec: HIGH (changes ripple)

**Rollback:** All operations additive. Delete `.agents/` to revert.

---

## Section 2: Error & Rescue Map

| Method | Exception Class | User Sees | Logged? |
|--------|-----------------|-----------|---------|
| detectContext() | ContextDetectionError | "Warning: Could not detect git root" | YES |
| scaffoldAgentsDir() | ScaffoldError | "Error: Failed to create .agents/" | YES |
| parseSquadDir() | SquadParseError | "Error: Invalid YAML at .squad/team.md:15" | YES |
| convertSquadToAgents() | MigrationError | "Error: Migration failed. .squad/ untouched." | YES |
| installPluginRef() | PluginRefError | "Warning: Could not add plugin ref" | YES |
| writeManifest() | IOError | "Error: Could not write manifest.json" | YES |

**Zero silent failures.** Every catch block logs and surfaces to user.

---

## Section 3: Security & Threat Model

| Attack Vector | Risk | Mitigation |
|---------------|------|------------|
| Path traversal in migration | HIGH | safe_resolve() with containment check |
| Malicious .squad/ content | MEDIUM | YAML safe loader, schema validation |
| Arbitrary code in templates | LOW | Templates are static, not executed |
| Supply chain (npm) | MEDIUM | Pin dependencies, lockfile, audit |

**Security Boundaries:**
- Reads: user's repo
- Writes: `.agents/` only (contained)
- Network: npm install only
- Execution: no user code executed

---

## Section 4: Data Flow Edge Cases

| Scenario | Handling |
|----------|----------|
| Double-click init | Idempotent. Prompt: "Already initialized. Overwrite?" |
| Navigate-away during scaffold | Detect incomplete on next run. Offer: "Continue?" |
| Stale .squad/ format | Version check. Warn if unsupported. |
| Empty .squad/team.md | "Error: .squad/team.md is empty. Nothing to migrate." |

---

## Section 5: Code Quality

| Dimension | Assessment |
|-----------|------------|
| DRY | Extract shared template fragments |
| Naming | Match Squad (init, status, doctor) for familiarity |
| Over-engineering risk | Keep CLI thin, resist middleware/DI |
| Under-engineering risk | Invest in error message UX |

---

## Section 6: Test Review

```
                    Test Pyramid
                   ┌───────────┐
                   │    E2E    │  5 tests
                   └─────┬─────┘
             ┌───────────┴───────────┐
             │     Integration       │  15 tests
             └───────────┬───────────┘
     ┌───────────────────┴───────────────────┐
     │              Unit Tests               │  30 tests
     └───────────────────────────────────────┘
```

- Unit: 90% coverage, LOW flakiness
- Integration: 80% coverage, MEDIUM flakiness (filesystem)
- E2E: Critical paths only, HIGH flakiness (npx, network)

**Migration path testing is critical.** Create fixtures for Squad versions.

---

## Section 7: Performance

| Concern | Assessment |
|---------|------------|
| Cold start (npx) | 2-3s acceptable |
| Large .squad/ | Stream parse, progress indicator |
| Template copy | Fast (embedded assets) |
| Memory | Low (CLI exits after command) |

No N+1 queries. No caching needed.

---

## Section 8: Observability

| Dimension | Implementation |
|-----------|----------------|
| Logging | --verbose flag, default errors+warnings |
| Metrics | Optional telemetry (opt-in) |
| Error codes | 0=success, 1=user error, 2=config, 3=external |
| Debug | DEBUG=ai-agents:* env var |

---

## Section 9: Deployment & Rollout

```
Week 1: Alpha (npm --tag alpha)
        ↓ Internal testing
Week 2: Beta (npm --tag beta)
        ↓ Early adopters
Week 3: GA (npm --tag latest)
        ↓ Full launch
```

**Feature flags:** Not needed. Version-based features.  
**Rollback:** `rm -rf .agents/` + re-run init.

---

## Section 10: Long-Term Trajectory

| Dimension | Assessment |
|-----------|------------|
| Technical debt | LOW (thin CLI) |
| Path dependency | MEDIUM (spec lock-in) |
| Reversibility | 4/5 (easy CLI changes, hard spec changes) |
| Ecosystem fit | HIGH (builds on Claude Code) |
| 1-year readability | HIGH |

**12-month trajectory:** CLI stays thin (4-6 commands), investment shifts to spec and community.

---

## Required Outputs

### NOT in Scope (Deferred)

| Feature | Deferred To |
|---------|-------------|
| ai-agents add/list/remove | Never (use native commands) |
| Skill marketplace | Phase 2 |
| Session management | Phase 2 |
| Memory integration | Phase 2 |
| Cost tracking | Phase 3 |
| Remote triggers | Phase 3 |
| IDE extensions | Phase 3+ |

### What Already Exists

| Asset | Reuse |
|-------|-------|
| 26 agent definitions | Plugin reference |
| 61 skills | Plugin reference |
| Plugin manifest | Template |
| 27 validation scripts | Doctor command basis |
| Session protocol | Template asset |
| Governance templates | Template assets |

### Squad Migration Flow

```
.squad/                    →    .agents/
├── team.md               →    ├── manifest.json
├── routing.md            →    ├── agents/routing.md
├── decisions.md          →    ├── architecture/decisions.md
├── agents/{name}/        →    ├── agents/{name}.md
├── skills/               →    ├── skills/{name}/SKILL.md
└── config.yaml           →    └── governance/config.md
```

### Completion Summary

| Section | Issues | Gaps | Critical |
|---------|--------|------|----------|
| Scope | 1 | 0 | 0 |
| Architecture | 0 | 1 | 0 |
| Error & Rescue | 0 | 0 | 0 |
| Security | 1 | 0 | 0 |
| Data Flow | 0 | 0 | 0 |
| Code Quality | 0 | 1 | 0 |
| Test | 0 | 0 | 0 |
| Performance | 0 | 0 | 0 |
| Observability | 0 | 0 | 0 |
| Deployment | 0 | 0 | 0 |
| Long-Term | 0 | 1 | 0 |

**TOTAL:** 2 issues, 3 gaps, 0 critical gaps

---

## Next Steps

### Week 1
- [ ] Create `packages/ai-agents-cli/` TypeScript project
- [ ] Implement `init` command with embedded templates
- [ ] Implement `--from squad` migration parser

### Week 2
- [ ] Implement `status` and `doctor` commands
- [ ] Write test suite (50 tests across pyramid)
- [ ] Alpha publish to npm

### Week 3
- [ ] Beta testing with early adopters
- [ ] Publish `.agents/` spec v1.0
- [ ] Write launch blog post

### Week 4 (Launch)
- [ ] GA release
- [ ] Twitter thread, HN post
- [ ] Community feedback loop

---

## Verdict

**CLEARED**

The plan is ready for implementation with the following conditions:
1. Use Approach B (Plugin-First) to ship in 2-3 weeks
2. P0 `--from squad` migration as differentiator
3. Publish `.agents/` spec v1.0 alongside launch
4. Defer Phase 2/3 features until MVP validates

No blocking issues. 3 minor gaps (plugin stability, error UX, spec versioning) are documented and mitigated.

---

*CEO Review completed: 2025-03-31*  
*Methodology: Garry Tan gstack plan-ceo-review*
