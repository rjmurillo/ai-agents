# PRD: ai-agents — The Open Standard for AI Development Teams

**Author:** Richard Murillo
**Date:** 2026-03-31
**Status:** Draft
**Version:** 1.0

---

## 1. Problem Statement

AI-assisted software development is moving from single-agent prompting to multi-agent team coordination. Developers need specialized AI agents (architect, implementer, tester, security reviewer) working together on real codebases. The tooling that coordinates these teams is fragmented, proprietary, and vendor-locked.

**The specific problem:** There is no open, agent-agnostic standard for how AI development teams organize knowledge, coordinate work, and persist learning across sessions. Every tool (Squad, Cursor teams, Copilot Workspace) builds its own format, creating silos. When you outgrow the tool, you lose everything.

### What Exists Today

| Tool | Strength | Limitation |
|------|----------|------------|
| **Squad** (Brady Gaster) | Easy onramp (`squad init`), themed agents, Copilot integration | Copilot-only, no governance, shallow knowledge (`history.md` per agent), no session protocol, no security model |
| **Copilot Workspace** | GitHub-native | Closed platform, single-agent mental model |
| **Cursor Teams** | IDE-integrated | Proprietary, no cross-tool portability |
| **ai-agents** (this project) | 21 agents, 53 ADRs, 1,558 closed issues, RFC-2119 session protocol, governance, security audits, multi-tool support | No CLI onramp, no npm package, high learning curve |

### The Gap

Nobody owns the **knowledge layer**. The directory structure, the session protocol, the handoff format, the governance model — that's what compounds across sessions and survives tool changes. Every existing tool bundles this with a specific runtime, making it non-portable.

---

## 2. Vision

**ai-agents is the open standard for AI development teams — what OpenClaw is to single agents, ai-agents becomes to multi-agent development.**

The product is not the agents. The product is the **harness**: the `.agents/` directory spec, the session protocol, the knowledge accumulation format, and the governance framework. Agents and orchestrators are pluggable. The knowledge layer is the platform.

### Core Thesis

> Products get replaced. Platforms get adopted. Squad is a product. ai-agents is a platform.

---

## 3. Target Users

### Primary: Senior/Staff Engineers Running AI Dev Workflows (Segment A)

- Already using Claude Code, Copilot CLI, or VS Code with Copilot
- Have hit limits of single-agent prompting
- Need audit trails, governance, reproducibility
- Willing to invest in setup for compounding returns
- **Size estimate:** ~50K developers actively using multi-agent workflows (growing 10x/year)

### Secondary: Squad Graduates (Segment B)

- Started with Squad, hit the ceiling
- Need multi-tool support (not just Copilot)
- Need governance beyond `decisions.md`
- Want knowledge portability
- **Size estimate:** Squad users who've been using it 3+ months and feel the constraints

### Tertiary: Dev Tool Builders (Segment C)

- Building IDE extensions, CI/CD integrations, or orchestration layers
- Need a standard to read/write agent team state
- Don't want to invent their own format
- **Size estimate:** ~500 dev tool teams building agent-related features

### Non-Target

- Beginners who want a chatbot
- Teams without git-based workflows
- Organizations requiring SaaS (this is repo-local, git-committed)

---

## 4. Product Definition

### 4.1 The Three-Layer Architecture

```
┌─────────────────────────────────────────┐
│  CLI / IDE / Chat                       │  ← Surfaces (anyone can build)
│  (npx ai-agents, VS Code, Copilot)     │
├─────────────────────────────────────────┤
│  Orchestration Protocol                 │  ← Pluggable dispatch layer
│  (DevClaw, Squad, custom, Copilot)      │
├─────────────────────────────────────────┤
│  .agents/ + .serena/                    │  ← THE STANDARD (this is the product)
│  Knowledge, sessions, skills,           │
│  governance, memory, ADRs               │
└─────────────────────────────────────────┘
```

**The bottom layer is the spec.** Everything above is pluggable. Squad can be an orchestrator. DevClaw can be an orchestrator. A VS Code extension nobody's built yet can be an orchestrator. They all read/write the same `.agents/` format.

### 4.2 CLI — The Onramp

The CLI is the entry point. Match Squad's simplicity, then reveal depth progressively.

#### Commands

| Command | What It Does | Squad Equivalent |
|---------|-------------|------------------|
| `npx ai-agents init` | Scaffold `.agents/` with sensible defaults, one pre-built team | `squad init` |
| `npx ai-agents init --from squad` | Import `.squad/` directory, map to `.agents/` format | (none) |
| `npx ai-agents status` | Dashboard: team knowledge, session count, governance health | `squad status` |
| `npx ai-agents doctor` | Health check: validate directory structure, detect issues | `squad doctor` |
| `npx ai-agents export` | Portable JSON snapshot | `squad export` |
| `npx ai-agents import <file>` | Restore from snapshot | `squad import` |
| `npx ai-agents nap` | Context hygiene: compress, prune, archive old sessions | `squad nap` |
| `npx ai-agents upgrade` | Update framework files, preserve team state | `squad upgrade` |

#### `init` — What Gets Scaffolded

```
.agents/
├── AGENTS.md                  # Team roster + agent instructions
├── SESSION-PROTOCOL.md        # How sessions start, run, and end
├── HANDOFF.md                 # Cross-session continuity
├── governance/
│   └── PROJECT-CONSTRAINTS.md # Guardrails
├── architecture/
│   └── ADR-001-init.md        # First architectural decision
├── agents/
│   ├── orchestrator.md        # Coordination
│   ├── implementer.md         # Code generation
│   ├── reviewer.md            # Code review
│   └── tester.md              # QA
└── sessions/                  # Session logs (auto-generated)

.serena/                       # Memory layer (optional)
├── project.yml
└── memories/
```

**Zero-config default:** 4 agents (orchestrator, implementer, reviewer, tester), basic session protocol, one ADR template. Works immediately with Claude Code or Copilot.

**Progressive disclosure:** As needs grow, add governance policies, security agents, ADRs, custom skills. The framework grows with the project.

### 4.3 The `.agents/` Spec (v1.0)

The spec defines:

1. **Directory structure** — Required and optional paths
2. **File formats** — Markdown with YAML frontmatter (human-readable, git-friendly)
3. **Agent definition schema** — Name, role, model preference, capabilities, boundaries
4. **Session protocol** — Start gates, mid-session checkpoints, end gates, handoff format
5. **Governance model** — Constraints, ADR format, security policy, review requirements
6. **Knowledge format** — How memories, decisions, and learnings are stored
7. **Interop contract** — How external tools read/write the format

**Design principles:**
- Everything is Markdown (readable without tooling)
- Everything is in git (versioned, auditable, portable)
- No runtime dependency (any agent framework can read/write this)
- Progressive complexity (start with 3 files, grow to 500+)

### 4.4 Competitive Moats

| Capability | ai-agents | Squad |
|-----------|-----------|-------|
| Agent count | 21 specialized agents | 4-6 themed characters |
| Session protocol | RFC 2119-grade gates, start/end prompts, handoff | Crash recovery only |
| Governance | 10+ policy files, ADR exceptions, consensus model | None |
| Security | Dedicated security agent, OWASP checks, security audits | None |
| Knowledge depth | 22MB structured memory, 2,847 markdown files | `history.md` per agent |
| Multi-tool support | Claude Code, Copilot, Gemini, VS Code | Copilot only |
| ADR system | 53 architectural decision records | None |
| Production evidence | 1,555 merged PRs, 1,552 closed issues | Alpha software |
| Memory model | Serena (semantic memory), session continuity | Basic persistence |
| Git integration | Branch validation, pre-commit hooks, PR quality gates | Basic git |

---

## 5. Success Metrics

### Phase 1 (CLI Ship — Week 1-2)

| Metric | Target | Measurement |
|--------|--------|-------------|
| `npx ai-agents init` works | 100% | CI test |
| npm weekly downloads | 500 in first month | npm stats |
| GitHub stars | 100 in first month | GitHub API |
| Init-to-first-session time | < 5 minutes | User testing |

### Phase 2 (Migration — Week 3-6)

| Metric | Target | Measurement |
|--------|--------|-------------|
| `--from squad` imports | 50 in first month | Telemetry (opt-in) |
| Blog post views | 5K | Analytics |
| Squad → ai-agents conversions | 20% of importers | Follow-up survey |

### Phase 3 (Spec Adoption — Month 2-6)

| Metric | Target | Measurement |
|--------|--------|-------------|
| External tools reading `.agents/` | 3 | GitHub integrations |
| Spec contributors | 10 | GitHub contributors |
| Monthly active repos | 1,000 | Telemetry |

### Phase 4 (Marketplace — Month 6-12)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Published team templates | 50 | Marketplace count |
| Shared skill packages | 100 | Package registry |
| Revenue (if applicable) | $10K MRR from premium templates | Stripe |

---

## 6. Technical Architecture

### Package Structure

```
packages/
├── ai-agents-cli/        # npm package: @rjmurillo/ai-agents
│   ├── src/
│   │   ├── commands/
│   │   │   ├── init.ts   # Scaffold .agents/
│   │   │   ├── status.ts # Dashboard
│   │   │   ├── doctor.ts # Health check
│   │   │   ├── import.ts # Import from Squad/JSON
│   │   │   ├── export.ts # Export snapshot
│   │   │   ├── nap.ts    # Context hygiene
│   │   │   └── upgrade.ts# Framework update
│   │   ├── importers/
│   │   │   └── squad.ts  # .squad/ → .agents/ mapper
│   │   └── templates/
│   │       ├── minimal/  # 4 agents, basic protocol
│   │       ├── standard/ # 12 agents, governance
│   │       └── full/     # 21 agents, security, ADRs
│   └── package.json
├── ai-agents-spec/       # The .agents/ format spec (separate repo?)
│   ├── spec.md
│   ├── schemas/          # JSON Schema for validation
│   └── examples/
└── ai-agents-sdk/        # Optional: programmatic API
    └── src/
```

### Squad Import Mapping

```
.squad/team.md          → .agents/AGENTS.md
.squad/decisions.md     → .agents/decisions/
.squad/routing.md       → .agents/governance/ROUTING.md
.squad/agents/{name}/
  charter.md            → .agents/agents/{name}.md
  history.md            → .serena/memories/{name}/
.squad/skills/          → .agents/skills/ (1:1)
.squad/identity/now.md  → .agents/HANDOFF.md
.squad/identity/wisdom.md → .agents/governance/PATTERNS.md
.squad/log/             → .agents/sessions/
```

---

## 7. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Squad ships governance features first | Medium | High | Ship fast. Week 1 is CLI. The 22MB of existing knowledge is the evidence. |
| Spec is too complex for adoption | Medium | High | Progressive disclosure. Minimal init is 3 files. Full spec is optional. |
| GitHub changes Copilot agent format | Low | Medium | Spec is format-agnostic. Adapter layer handles platform-specific mapping. |
| No organic discovery | High | Medium | Blog post, HN launch, dev.to article, "awesome-ai-agents" lists. Target Squad community directly. |
| Maintenance burden of CLI | Medium | Low | Lean CLI (commander.js + templates). Most value is in the spec, not the tool. |

---

## 8. Open Questions

1. **Package name:** `@rjmurillo/ai-agents` or `ai-agents` (global)? The global name is stronger for adoption but may conflict.
2. **Spec governance:** Should the `.agents/` spec live in its own repo with an RFC process?
3. **Telemetry:** Opt-in usage telemetry for understanding adoption? (Privacy-first design)
4. **Pricing:** Should advanced templates or team configurations be paid? Or fully open source?
5. **Copilot agent integration:** Should we register as an official Copilot agent (like Squad does)?

---

*This document is the foundation. The GTM plan follows.*
