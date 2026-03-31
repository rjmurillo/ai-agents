# GTM Plan: ai-agents Platform Launch

**Date:** 2026-03-31
**Author:** Richard Murillo
**Objective:** Position ai-agents as the open standard for AI development teams. Capture developer mindshare before Squad or any other tool defines the format.

---

## Executive Summary

ai-agents has 6 months of production evidence (1,555 merged PRs, 53 ADRs, 22MB of structured knowledge) that no competitor can match. The problem: nobody knows it exists outside the repo. The GTM is four phases over 6 months, starting with a CLI that matches Squad's onramp, then systematically converting Squad users, publishing the spec as an open standard, and building network effects through a marketplace.

**The core insight:** We're not launching a product. We're formalizing a standard that already works and has 6 months of proof. Everything else is distribution.

---

## Phase 1: The CLI (Week 1-2)

### Goal
Match Squad's three-step onramp. Remove the only advantage they have.

### Deliverables

1. **npm package: `@rjmurillo/ai-agents`**
   - `npx ai-agents init` — scaffolds `.agents/` + `.serena/` with 4 default agents
   - `npx ai-agents status` — shows team knowledge, session count, health
   - `npx ai-agents doctor` — validates setup, checks for common issues
   - Ships as single ESM bundle via esbuild, zero runtime dependencies

2. **Updated README**
   - Three-line quickstart (matches Squad's):
     ```
     npx ai-agents init
     # Open your AI coding tool (Claude Code, Copilot, Cursor)
     # Start building. Your team learns as you go.
     ```
   - "Is this for you?" section targeting senior engineers
   - Migration section for Squad users

3. **Init Templates**
   - `--template minimal` — 4 agents, basic protocol (default)
   - `--template standard` — 12 agents, governance policies
   - `--template full` — 21 agents, security, ADRs, complete governance

### Success Criteria
- `npx ai-agents init` runs in < 3 seconds
- Generated `.agents/` passes `doctor` check
- Works with Claude Code, Copilot CLI, and VS Code out of the box

### Timeline
- Day 1-3: CLI scaffolding (commander.js, init command, templates)
- Day 4-5: status + doctor commands
- Day 6-7: npm publish, README rewrite, CI for the package
- Day 8: Soft launch (tweet, Discord mention, r/ChatGPTCoding)

---

## Phase 2: The Migration (Week 3-6)

### Goal
Convert Squad users by making migration frictionless and showing the depth gap.

### Deliverables

1. **`npx ai-agents init --from squad`**
   - Auto-detects `.squad/` directory
   - Maps Squad format → `.agents/` format:
     - `team.md` → `AGENTS.md`
     - `agents/{name}/charter.md` → `agents/{name}.md`
     - `agents/{name}/history.md` → `.serena/memories/{name}/`
     - `decisions.md` → `decisions/`
     - `routing.md` → `governance/ROUTING.md`
     - `skills/` → skills/ (1:1 copy)
   - Preserves all Squad state (non-destructive, `.squad/` is not deleted)
   - Prints diff summary: "Imported 4 agents, 12 decisions, 3 skills. Added: session protocol, governance framework, ADR template, security policy."

2. **Blog post: "What Your AI Team Looks Like After 6 Months"**
   - Side-by-side comparison: `.squad/` (fresh init) vs `.agents/` (6 months of real use)
   - Concrete examples: session protocols, ADRs, governance policies, security audits
   - Numbers: 1,555 PRs, 53 ADRs, 2,847 knowledge files, 21 specialized agents
   - Ends with: `npx ai-agents init --from squad` — try it, keep your Squad state, see what you gain
   - **Target:** Hacker News front page, dev.to trending

3. **Comparison page in docs**
   - Feature matrix: ai-agents vs. Squad vs. Copilot Workspace vs. Cursor Teams
   - Honest: "Squad wins on simplicity. ai-agents wins on everything else."
   - Include "When to use Squad" (genuinely small projects that won't need governance)

### Distribution Channels

| Channel | Action | Expected Reach |
|---------|--------|----------------|
| Hacker News | "Show HN: What 6 months of AI agent team knowledge looks like" | 50K views if front page |
| dev.to | Full blog post with code samples | 10K views |
| r/ChatGPTCoding | "I built a Squad alternative with 21 agents and 53 ADRs" | 5K views |
| Twitter/X | Thread showing `.agents/` directory evolution over 6 months | 20K impressions |
| LinkedIn | Professional angle: "Why governance matters for AI dev teams" | 5K views |
| Discord (AI/dev servers) | Direct community engagement | 1K reach |
| YouTube Short | 60-second "init Squad vs init ai-agents" comparison | 10K views |

### Success Criteria
- 50+ Squad imports in first month
- Blog post gets > 5K views
- 20% of importers continue using ai-agents after 2 weeks

---

## Phase 3: The Spec (Month 2-4)

### Goal
Publish the `.agents/` directory format as an open standard. Make other tools conform to your format.

### Deliverables

1. **`.agents/` Spec v1.0**
   - Published as a separate GitHub repo: `rjmurillo/agents-spec`
   - Formal spec document with:
     - Required files (`AGENTS.md`, session protocol)
     - Optional directories (governance, security, architecture)
     - Agent definition schema (YAML frontmatter in Markdown)
     - Session protocol format (start gates, checkpoints, end gates)
     - Knowledge format (how memories and decisions are stored)
     - Interop contract (how external tools read/write)
   - JSON Schema files for validation
   - Reference implementation (the ai-agents repo itself)

2. **Validator tool**
   - `npx agents-spec validate .agents/` — checks conformance
   - Returns structured results (pass/warn/fail per section)
   - Usable in CI pipelines

3. **Integration outreach**
   - Contact OpenClaw team about native `.agents/` support
   - Reach out to Cursor, Continue.dev, Aider for format adoption
   - Submit to awesome-ai-coding-agents lists

### Success Criteria
- 3 external tools announce `.agents/` format support
- 10 contributors to the spec repo
- 1,000 repos with `.agents/` directories (tracked via GitHub search)

---

## Phase 4: Marketplace & Network Effects (Month 4-12)

### Goal
Build switching cost through shared knowledge and network effects.

### Deliverables

1. **Team templates marketplace**
   - Pre-configured team definitions for common stacks:
     - "React + Node.js Full Stack" (6 agents, frontend/backend/test/deploy)
     - "Python Data Science" (4 agents, analyst/engineer/reviewer/ops)
     - "Rust Systems" (5 agents, architect/implementer/safety/benchmark/docs)
     - "Enterprise .NET" (8 agents, full governance, security, compliance)
   - Templates include accumulated knowledge from real projects
   - Free tier (basic templates) + paid tier ($5-20 for battle-tested templates with months of embedded knowledge)

2. **Skill packages**
   - Portable, cross-orchestrator skills (PR review, security scan, architecture review)
   - Registry (npm-style or GitHub-based)
   - Skills work with any tool that reads `.agents/` format

3. **Knowledge sharing**
   - Anonymous, opt-in sharing of governance patterns and ADR templates
   - "What are the most common ADRs across 500 repos?" — aggregate insights

### Success Criteria
- 50 published templates
- 100 shared skills
- $10K MRR from premium templates (stretch goal)

---

## Competitive Positioning

### Messaging by Audience

**To Squad users:**
> "Love Squad? Keep using it. ai-agents makes your team portable, governable, and deeper. Run `npx ai-agents init --from squad` and see what you've been missing."

**To greenfield users:**
> "One command. A team that learns. And when you need governance, security, or multi-tool support — it's already there. `npx ai-agents init`"

**To dev tool builders:**
> "The `.agents/` spec is open. Build on it. Your users' knowledge is portable."

**To engineering leaders:**
> "Your AI dev team's knowledge shouldn't be locked in a vendor. ai-agents is git-native, auditable, and yours."

### Differentiation Narrative

Don't compete on charm. Compete on depth.

Squad shows a fresh `squad init` with themed names and a cute CLI. We show what `.agents/` looks like after **1,555 pull requests**. Session protocols. 53 architectural decisions. Governance policies. Security audits. Pre-commit hooks that actually enforce quality.

One is a demo. The other is production.

### The Kill Shot: `--from squad`

Don't announce it. Just ship it. Let Squad users discover that ai-agents can eat their `.squad/` directory and produce something 10x richer. Word of mouth handles the rest.

---

## Budget & Resources

| Item | Cost | Timeline |
|------|------|----------|
| CLI development | $0 (DevClaw workers) | Week 1-2 |
| npm publishing | $0 | Week 1 |
| Blog post writing | $0 (self) | Week 3 |
| Domain for docs site | $12/year | Week 1 |
| Dev.to / HN posting | $0 | Week 3 |
| Template creation | $0 (DevClaw workers) | Month 2-4 |
| Video content | $0 (self) | Month 2 |
| **Total Phase 1-2** | **~$12** | **6 weeks** |

---

## Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Squad ships governance before us | 30% | High | Ship fast. Our evidence (1,555 PRs) is the moat — they can't fabricate 6 months of production use. |
| npm name conflict | 20% | Medium | Register `@rjmurillo/ai-agents` immediately. Consider `ai-dev-team` as fallback. |
| No organic discovery | 60% | High | Multi-channel launch. HN + dev.to + Reddit + Twitter on same day. Target Squad's community directly. |
| Spec is ignored by ecosystem | 40% | Medium | Get 1-2 early adopters (OpenClaw, Continue.dev) before public announcement. Social proof. |
| Maintenance burden | 30% | Low | CLI is thin (templates + validation). Most value is in the spec, not the tool. |

---

## 30-60-90 Day Plan

### Day 1-30: Ship the CLI
- [ ] Scaffold `packages/ai-agents-cli/` with commander.js
- [ ] Implement `init`, `status`, `doctor` commands
- [ ] Create minimal, standard, full templates
- [ ] Publish to npm
- [ ] Rewrite README with three-line quickstart
- [ ] Soft launch on Twitter + Discord

### Day 30-60: Convert Squad Users
- [ ] Implement `--from squad` importer
- [ ] Write "6 Months of AI Team Knowledge" blog post
- [ ] Launch on HN, dev.to, Reddit (coordinated, same day)
- [ ] Create comparison page in docs
- [ ] YouTube Short: init comparison

### Day 60-90: Publish the Spec
- [ ] Create `agents-spec` repo with formal spec
- [ ] Ship `agents-spec validate` CLI tool
- [ ] Reach out to 5 dev tool teams for adoption
- [ ] Submit to awesome-ai lists
- [ ] First batch of team templates

---

*The advantage is real. The evidence is 22MB of battle scars. Now we need the onramp.*
