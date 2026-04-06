# GTM Plan: ai-agents Platform Launch

**Date:** 2026-03-31
**Author:** Richard Murillo
**Objective:** Position ai-agents as the open standard for AI development teams. Capture developer mindshare before Squad or any other tool defines the format.

---

## Executive Summary

ai-agents has 6 months of production evidence (1,555+ merged PRs, 57+ ADRs, 22MB+ of structured knowledge as of 2026-03-31) that no competitor can match. The problem: nobody knows it exists outside the repo. The GTM is four phases over 6 months, starting with a CLI that matches Squad's onramp, then systematically converting Squad users, publishing the spec as an open standard, and building network effects through a marketplace.

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
   - `npx ai-agents init --from squad` — imports `.squad/` directory
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

4. **Spec v1.0 (Parallel Track)**
   - Publish `.agents/` spec document + JSON Schema in Week 2
   - Establishes standard before HN launch
   - Blog post: "The .agents/ standard" accompanies Beta release

### Success Criteria
- `npx ai-agents init` runs in < 3 seconds
- Generated `.agents/` passes `doctor` check
- Works with Claude Code, Copilot CLI, and VS Code out of the box

### Timeline (Aligned with CEO Review)

**Week 1:**
- Day 1-2: Set up `packages/ai-agents-cli/` with commander.js
- Day 3-4: Implement `init` (minimal template) + `--from squad` parser
- Day 5: Implement `status`
- Day 6-7: Alpha publish to npm (`--tag alpha`)

**Week 2:**
- Day 8-9: Implement `doctor` + standard/full templates
- Day 10-11: Spec v1.0 document + JSON Schema
- Day 12: Beta publish to npm (`--tag beta`)
- Day 13-14: Blog post: "The .agents/ standard"

---

## Phase 2: Seed Community + Full CLI (Week 3-4)

### Goal
Build social proof before public launch. Complete CLI feature parity with Squad.

### Deliverables

1. **Seed Community (CRITICAL — Week 3)**
   - Recruit 5-10 developers to use ai-agents for 2 weeks before HN launch
   - Target: Senior engineers already frustrated with AI tooling fragmentation
   - Sources: Twitter DMs, Discord AI communities, personal network
   - Ask: "Try ai-agents for 2 weeks, share honest feedback"
   - Outcome: Genuine testimonials + bug fixes before public launch
   - **Why this matters:** 60% risk of "no organic discovery" — social proof on day 1 is the mitigation

2. **Remaining CLI Commands (Week 3-4)**
   - `npx ai-agents export` — portable JSON snapshot
   - `npx ai-agents import` — restore from snapshot
   - `npx ai-agents nap` — context hygiene (compress, prune, archive)
   - `npx ai-agents upgrade` — update framework files, preserve team state
   - Beta 2 publish (Week 3), GA publish (Week 4)

3. **Squad Community Outreach (Week 3)**
   - Join Squad Discord/community channels
   - Help users with genuine questions (don't shill)
   - Let `--from squad` speak for itself when relevant

4. **Blog post: "What Your AI Team Looks Like After 6 Months"**
   - Side-by-side comparison: `.squad/` (fresh init) vs `.agents/` (6 months of real use)
   - Concrete examples: session protocols, ADRs, governance policies, security audits
   - Numbers: 1,555+ PRs, 57+ ADRs, 2,847+ knowledge files, 25+ specialized agents
   - Include testimonials from seed community
   - Ends with: `npx ai-agents init --from squad` — try it, keep your Squad state, see what you gain
   - **Target:** Hacker News front page, dev.to trending

5. **Comparison page in docs**
   - Feature matrix: ai-agents vs. Squad vs. Copilot Workspace vs. Cursor Teams
   - Honest: "Squad wins on simplicity. ai-agents wins on everything else."
   - Include "When to use Squad" (genuinely small projects that won't need governance)

### Timeline (Aligned with CEO Review)

**Week 3:**
- Day 15-16: Implement `export` + `import`
- Day 17-18: Seed community recruitment (5-10 developers)
- Day 19-20: Squad community outreach (join, observe, help)
- Day 21: Beta 2 publish

**Week 4:**
- Day 22-23: Implement `nap` + `upgrade`
- Day 24-25: Collect seed community testimonials
- Day 26: GA publish to npm (`--tag latest`)
- Day 27: Write blog post with testimonials
- Day 28: **LAUNCH DAY** — HN, dev.to, Reddit, Twitter (coordinated)

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
| **Seed community** | Personal testimonials on launch day | **Social proof multiplier** |

### Success Criteria
- 5-10 seed community members with genuine testimonials
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
   - Contact [OpenClaw](https://github.com/nichochar/open-claw) team about native `.agents/` support
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

Squad shows a fresh `squad init` with themed names and a cute CLI. We show what `.agents/` looks like after **1,555+ pull requests**. Session protocols. 57+ architectural decisions. Governance policies. Security audits. Pre-commit hooks that actually enforce quality.

One is a demo. The other is production.

### The Kill Shot: `--from squad`

Don't announce it. Just ship it. Let Squad users discover that ai-agents can eat their `.squad/` directory and produce something 10x richer. Word of mouth handles the rest.

---

## Budget & Resources

| Item | Cost | Timeline |
|------|------|----------|
| CLI development (8 commands) | $0 (DevClaw workers) | Week 1-4 |
| npm publishing | $0 | Week 1-4 |
| Spec v1.0 document | $0 (self) | Week 2 |
| Blog post writing | $0 (self) | Week 4 |
| Domain for docs site | $12/year | Week 1 |
| Seed community recruitment | $0 (personal outreach) | Week 3 |
| HN / dev.to / Reddit posting | $0 | Week 4 |
| Template creation | $0 (DevClaw workers) | Month 2-4 |
| Video content | $0 (self) | Week 4 |
| **Total Phase 1-2** | **~$12** | **4 weeks** |

---

## Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Squad ships governance before us | 30% | High | Ship fast. Our evidence (1,555+ PRs) is the moat. They cannot fabricate 6 months of production use. |
| npm name conflict | 20% | Medium | Register `@rjmurillo/ai-agents` immediately. Consider `ai-dev-team` as fallback. |
| No organic discovery | 60% → 40% | High | **Seed community (5-10 devs) provides day-1 social proof.** Multi-channel launch. HN + dev.to + Reddit + Twitter coordinated. Testimonials in blog post. |
| Spec is ignored by ecosystem | 40% | Medium | Get 1-2 early adopters ([OpenClaw](https://github.com/nichochar/open-claw), Continue.dev) before public announcement. Social proof. |
| Maintenance burden | 30% | Low | CLI is thin (templates + validation). Most value is in the spec, not the tool. |

---

## 4-Week Sprint Plan (Aligned with CEO Review)

### Week 1: Alpha
- [ ] Set up `packages/ai-agents-cli/` with commander.js
- [ ] Implement `init` command (minimal template)
- [ ] Implement `--from squad` parser
- [ ] Implement `status` command
- [ ] Alpha publish to npm (`--tag alpha`)
- [ ] Rewrite README with three-line quickstart

### Week 2: Beta + Spec
- [ ] Implement `doctor` command
- [ ] Create standard + full templates
- [ ] Write Spec v1.0 document + JSON Schema
- [ ] Beta publish to npm (`--tag beta`)
- [ ] Blog post: "The .agents/ standard"

### Week 3: Seed Community + Beta 2
- [ ] Implement `export` + `import` commands
- [ ] Recruit 5-10 seed community developers
- [ ] Join Squad community (observe, help, don't shill)
- [ ] Beta 2 publish
- [ ] Collect early feedback, fix bugs

### Week 4: GA + Launch
- [ ] Implement `nap` + `upgrade` commands
- [ ] Collect seed community testimonials
- [ ] GA publish to npm (`--tag latest`)
- [ ] Write "6 Months of AI Team Knowledge" blog post (with testimonials)
- [ ] **LAUNCH DAY:** HN + dev.to + Reddit + Twitter (coordinated)
- [ ] YouTube Short: init comparison

### Month 2-4: Spec Adoption
- [ ] Create `agents-spec` repo with formal spec
- [ ] Ship `agents-spec validate` CLI tool
- [ ] Reach out to 5 dev tool teams for adoption
- [ ] Submit to awesome-ai lists
- [ ] First batch of team templates
- [ ] Create comparison page in docs

---

*The advantage is real. The evidence is 22MB of battle scars. Now we need the onramp.*
