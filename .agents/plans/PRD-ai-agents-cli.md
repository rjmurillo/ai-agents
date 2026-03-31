# PRD: ai-agents CLI Platform

**Version:** 1.0  
**Date:** 2025-03-31  
**Author:** Claude + Richard Murillo  
**Status:** Draft  
**Slack Thread:** https://richardoss.slack.com/archives/C0A71GL17DL/p1774928243250079?thread_ts=1774922984.514159&cid=C0A71GL17DL

---

## Executive Summary

**The Problem:** Developer tooling for AI agents is fragmented. Teams cobble together prompts, scripts, and configurations without standardization. New entrants like Squad CLI offer simplicity but lock users into proprietary formats with shallow capabilities.

**The Opportunity:** ai-agents has 18+ months of battle-tested multi-agent orchestration patterns, 61 production skills, and a comprehensive `.agents/` specification. We're not building from scratch—we're packaging proven infrastructure as an open platform.

**The Product:** A unified CLI (`npx ai-agents`) that initializes, manages, and orchestrates AI agent teams across Claude Code, Copilot CLI, and VS Code. The `.agents/` directory format becomes an open standard.

**The Strategy:** Squad is a product. ai-agents is a platform. We win by being the open standard that Squad eventually has to support.

---

## 1. Problem Statement

### 1.1 User Pain Points

| Pain Point | Who Feels It | Current Workaround | Cost |
|------------|--------------|-------------------|------|
| No standard agent organization | Teams adopting AI | Custom folder structures, READMEs | Onboarding friction, tribal knowledge |
| Agent sprawl | Mature AI users | Manual tracking in docs | Lost work, duplication |
| No cross-platform portability | Multi-tool shops | Rewrite prompts per platform | 2-5x effort |
| No governance framework | Enterprise | Policy documents, manual review | Compliance gaps, security risk |
| No session continuity | Individual devs | Copy-paste context | Lost momentum, repeated mistakes |

### 1.2 Competitive Landscape

| Product | Strengths | Weaknesses | Our Position |
|---------|-----------|------------|--------------|
| **Squad CLI** | Great DX, simple onramp, Brady's audience | Shallow depth, proprietary format, single-platform | Beat on depth, match on DX, win on openness |
| **Cursor Rules** | IDE-native, popular | File-only, no orchestration | Different category (single vs. team) |
| **Raw prompts** | Flexible | No structure, no reuse | We formalize what people do manually |

### 1.3 Why Now

1. **Squad shipped** — market education happening, category exists
2. **Claude Code mature** — stable platform to build on
3. **ai-agents proven** — 18 months of real use, patterns validated
4. **Open wins** — developers prefer open standards (see: OpenAPI, JSON Schema)

---

## 2. Product Vision

### 2.1 One-Liner

**The Git of AI agent orchestration** — a portable, open format for organizing AI agents that works across every platform.

### 2.2 North Star Metrics

| Metric | Target (6mo) | Target (12mo) |
|--------|--------------|---------------|
| Weekly active repos | 100 | 1,000 |
| `--from squad` migrations | 50 | 500 |
| `.agents/` spec adopters | 3 platforms | 10 platforms |
| Community skills contributed | 20 | 100 |

### 2.3 Success Criteria

1. **Adoption:** `npx ai-agents init` becomes the default way to set up AI tooling
2. **Migration:** Squad users can convert in <5 minutes
3. **Standard:** At least one other tool adopts `.agents/` format
4. **Depth:** Users cite "governance" and "skills" as reasons to choose ai-agents

---

## 3. User Personas

### 3.1 Primary: "Alex the AI-Native Dev"

- Uses Claude Code daily, experiments with Copilot
- 2-5 years experience, startup or mid-size company
- Frustrated by context loss between sessions
- Wants: Structure without bureaucracy

**Jobs to Be Done:**
- Set up AI tooling in a new repo (<2 minutes)
- Reuse patterns across projects
- Track what agents did and why

### 3.2 Secondary: "Sam the Tech Lead"

- Manages team of 5-15 engineers
- Evaluating AI adoption strategy
- Worried about: security, consistency, costs
- Wants: Guardrails that don't slow people down

**Jobs to Be Done:**
- Enforce team conventions
- Review agent actions before merge
- Understand AI usage patterns

### 3.3 Tertiary: "Casey the Platform Engineer"

- Builds internal developer tools
- Needs to integrate AI into existing workflows
- Wants: Extensibility, APIs, hooks

**Jobs to Be Done:**
- Customize agent behavior per team
- Connect agents to internal systems
- Build dashboards and controls

---

## 4. Feature Requirements

### 4.1 MVP (Phase 1) — "Match Squad"

**Goal:** Feature parity with Squad CLI in 2 weeks

| Feature | Command | Description | Priority |
|---------|---------|-------------|----------|
| Initialize repo | `npx ai-agents init` | Scaffold `.agents/` directory | P0 |
| Status check | `npx ai-agents status` | Show installed agents, skills, health | P0 |
| Add agent | `npx ai-agents add <agent>` | Install from registry or local | P0 |
| List agents | `npx ai-agents list` | Show available agents with descriptions | P0 |
| Doctor | `npx ai-agents doctor` | Validate setup, check for issues | P0 |
| Squad import | `npx ai-agents init --from squad` | Convert `.squad/` to `.agents/` | P0 |

**Acceptance Criteria:**
- [ ] `init` completes in <5 seconds
- [ ] `--from squad` handles 100% of Squad's documented features
- [ ] Works on Mac, Linux, Windows (WSL)
- [ ] Zero runtime dependencies beyond Node 18+

### 4.2 Phase 2 — "Win on Depth"

**Goal:** Showcase what 18 months of real usage enables

| Feature | Command | Description | Priority |
|---------|---------|-------------|----------|
| Skill marketplace | `npx ai-agents skill search/add/publish` | Browse and install skills | P1 |
| Session management | `npx ai-agents session init/end/list` | Structured session logs | P1 |
| Memory integration | `npx ai-agents memory search/sync` | Cross-session knowledge | P1 |
| Governance templates | `npx ai-agents init --template enterprise` | Pre-configured guardrails | P1 |
| Cost tracking | `npx ai-agents cost` | Token usage and model costs | P1 |

### 4.3 Phase 3 — "Platform Play"

**Goal:** Enable ecosystem and third-party adoption

| Feature | Command | Description | Priority |
|---------|---------|-------------|----------|
| Plugin system | `npx ai-agents plugin` | Third-party extensions | P2 |
| Remote triggers | `npx ai-agents trigger` | Scheduled/webhook agent execution | P2 |
| Multi-repo orchestration | `npx ai-agents workspace` | Monorepo and multi-repo support | P2 |
| Spec export | `npx ai-agents spec export --format openagents` | Export to other formats | P2 |
| IDE extensions | VS Code, JetBrains | GUI for CLI commands | P2 |

---

## 5. Technical Architecture

### 5.1 Directory Structure (`.agents/` Spec v1.0)

```
.agents/
├── manifest.json              # Metadata, version, dependencies
├── agents/                    # Agent definitions
│   ├── orchestrator.md       # Multi-agent coordinator
│   ├── implementer.md        # Code-focused agent
│   └── [custom]/             # User-defined agents
├── skills/                    # Reusable workflows
│   ├── commit/SKILL.md       # Skill with frontmatter
│   └── [custom]/
├── governance/                # Policies and constraints
│   ├── security.md           # Security review requirements
│   ├── cost.md               # Token budgets
│   └── naming.md             # Conventions
├── architecture/              # Decision records
│   └── ADR-*.md              # Architecture Decision Records
├── sessions/                  # Session logs
│   └── 2025-03-31-*.json     # Structured session data
├── specs/                     # Requirements (optional)
│   ├── requirements/
│   ├── design/
│   └── tasks/
└── hooks/                     # Lifecycle hooks
    ├── pre-commit.sh
    └── session-start.sh
```

### 5.2 CLI Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ai-agents CLI                        │
├─────────────────────────────────────────────────────────┤
│  Commands:  init | status | add | list | doctor | ...   │
├─────────────────────────────────────────────────────────┤
│  Core Services:                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Registry │ │ Scaffold │ │ Validate │ │ Migrate  │   │
│  │ Service  │ │ Service  │ │ Service  │ │ Service  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
├─────────────────────────────────────────────────────────┤
│  Platform Adapters:                                     │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐          │
│  │ Claude Code│ │ Copilot CLI│ │  VS Code   │          │
│  └────────────┘ └────────────┘ └────────────┘          │
├─────────────────────────────────────────────────────────┤
│  File System | Git | HTTP (registry)                    │
└─────────────────────────────────────────────────────────┘
```

### 5.3 Technology Choices

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | TypeScript | Ecosystem fit, type safety, npx distribution |
| Package manager | npm/npx | Zero-install for users |
| Config format | JSON + Markdown | Human-readable, parseable |
| Registry | GitHub Releases | Free, familiar, no infra |
| Testing | Vitest | Fast, modern, good DX |

### 5.4 Migration Path (`--from squad`)

```
.squad/                    →    .agents/
├── agents.yaml           →    ├── manifest.json + agents/
├── prompts/              →    ├── agents/*.md
├── tools/                →    ├── skills/
└── config.yaml           →    └── governance/ + hooks/
```

**Conversion Rules:**
1. Squad agent definitions → ai-agents Markdown format with frontmatter
2. Squad tools → ai-agents skills (SKILL.md format)
3. Squad config → split into governance policies
4. Preserve all user content, add structure

---

## 6. Go-to-Market Strategy

### 6.1 Positioning

**Tagline:** "Squad gets you started. ai-agents gets you there."

**Key Messages:**
1. **Open standard** — Your agent configs aren't locked in
2. **Battle-tested** — 18 months of real-world orchestration patterns
3. **Depth when you need it** — Start simple, scale to enterprise
4. **Platform-native** — Works with Claude Code, Copilot CLI, not around them

### 6.2 Launch Sequence

```
Week 0: Announce intent (Twitter/X thread, Brady call-out)
        ↓
Week 1: Ship `npx ai-agents init` (MVP)
        ↓
Week 2: Ship `--from squad` migration
        Blog post: ".agents/ after 18 months of real use"
        ↓
Week 3: Publish `.agents/` spec v1.0 (open standard)
        ↓
Week 4: Community skill contributions open
        ↓
Week 8: Phase 2 features (skills, sessions, memory)
        ↓
Week 12: Phase 3 features (plugins, triggers)
```

### 6.3 Content Strategy

| Asset | Goal | Timeline |
|-------|------|----------|
| **Launch thread** | Announce, position vs. Squad | Day 0 |
| **"18 months of .agents/"** blog | Credibility, depth showcase | Week 2 |
| **Spec document** | Legitimize as standard | Week 3 |
| **Migration guide** | Reduce Squad switching costs | Week 2 |
| **Video demo** | Show DX, compare to Squad | Week 1 |
| **"Why open matters"** blog | Platform vs. product narrative | Week 4 |

### 6.4 Distribution Channels

| Channel | Approach | Expected Reach |
|---------|----------|----------------|
| Twitter/X | Direct engagement, Brady debate | 10K impressions |
| Hacker News | Launch post, spec announcement | 5K visits |
| Reddit (r/programming, r/ClaudeAI) | Community posts | 2K visits |
| Discord (Claude, Copilot communities) | Help Squad users migrate | 500 conversions |
| Dev.to / Hashnode | SEO-optimized tutorials | Long-tail traffic |
| GitHub | README, marketplace listing | Organic discovery |

### 6.5 Competitive Response Plan

**If Squad adds features:**
- Emphasize open standard, no lock-in
- Show governance/enterprise features they don't have

**If Squad copies .agents/:**
- Declare victory, welcome interoperability
- Focus on skill ecosystem depth

**If Brady responds publicly:**
- Stay friendly, frame as "rising tide"
- Avoid defensive posture

---

## 7. Success Metrics & Milestones

### 7.1 Phase 1 (Weeks 1-4)

| Metric | Target | Measurement |
|--------|--------|-------------|
| npm downloads | 500 | npm stats |
| GitHub stars | 200 | GitHub |
| Squad migrations | 25 | CLI telemetry (opt-in) |
| Blog post views | 2,000 | Analytics |

### 7.2 Phase 2 (Weeks 5-12)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Weekly active users | 100 | CLI telemetry |
| Community skills published | 10 | Registry |
| Enterprise template adoptions | 5 | GitHub issues/discussions |

### 7.3 Phase 3 (Months 4-6)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Third-party spec adopters | 2 | Public announcements |
| Plugin ecosystem | 5 plugins | Registry |
| Revenue (sponsorships/enterprise) | $5K MRR | Billing |

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Squad moves faster | High | Medium | Ship MVP in 2 weeks, iterate fast |
| Low adoption | Medium | High | Focus on migration path, reduce friction |
| Spec too complex | Medium | Medium | Start minimal, add features gradually |
| Platform changes break us | Low | High | Adapter pattern, quick response team |
| Community doesn't contribute | Medium | Medium | Seed with our 61 skills, lower contribution bar |

---

## 9. Open Questions

1. **Pricing model:** Free forever? Freemium? Enterprise tier?
2. **Telemetry:** What's acceptable to collect? Opt-in only?
3. **Governance:** Who maintains the spec? Foundation? Company?
4. **Partnerships:** Approach Anthropic/Microsoft for endorsement?

---

## 10. Appendices

### A. Existing Assets to Leverage

- 25 specialized agents (orchestrator, implementer, analyst, etc.)
- 61 production skills (commit, pr-review, security-scan, etc.)
- 40+ Architecture Decision Records
- Comprehensive governance framework
- Session protocol with evidence tracking
- Memory enhancement CLI (Python, ready to port)
- Semantic hooks system
- Marketplace manifest format

### B. Squad CLI Feature Parity Checklist

- [ ] Initialize workspace
- [ ] Add agents
- [ ] List agents
- [ ] Run agents
- [ ] Configure settings
- [ ] Import/export

### C. Related Documents

- `.agents/AGENT-SYSTEM.md` — Current agent registry spec
- `.agents/SESSION-PROTOCOL.md` — Session logging spec
- `docs/architecture.md` — Template system
- `docs/skill-reference.md` — 61 skills documented

---

*Document Status: Ready for CEO Review*
