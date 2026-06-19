---
name: programming-advisor
version: 1.0.0
model: claude-opus-4-6
description: Evaluate existing solutions (libraries, SaaS, open source) AND internal prior-art before custom development to avoid reinventing the wheel. Use when considering building new features, asking "should I build or use existing", "do we already have this", "is there existing code for X in this repo", "is there a library for this", or need build vs buy cost analysis with token estimates. Checks internal reuse (leverage/extend) before external. Do NOT use for strategic multi-option TCO (use buy-vs-build-framework).
license: MIT
---

# Programming Advisor - "Reinventing the Wheel" Detector

## Triggers

| Trigger Phrase | Action |
|----------------|--------|
| "should I build X or use a library" | Search internal prior-art first (Step 2a), then external solutions, provide comparison |
| "find existing solutions for X" | Search internal prior-art first (Step 2a), then web search, categorize findings |
| "is there a package for X" | Check existing dependencies first (Step 2a), then search npm/pip/cargo/etc |
| "build vs buy for X" | Tactical: generate cost comparison table; Strategic (>$50K, multi-year, partner/defer options): delegate to `buy-vs-build-framework` |
| "check if X exists before building" | Run full wheel detection workflow |
| "do we already have X" / "is there existing code for X in this repo" | Search internal prior-art first (leverage/extend), then external |

## Core Philosophy

Before writing a single line of code, determine if the wheel already exists. Vibe coding burns tokens, time, and creates maintenance burden. Existing solutions often provide better quality, security patches, and community support.

## Workflow

### Step 1: Capture Intent

Extract from user request:

- **What**: Core functionality needed
- **Why**: Use case / problem being solved
- **Constraints**: Language, platform, budget, licensing requirements

### Step 2: Search for Existing Solutions

**Search internal prior-art FIRST (leverage/extend), then external.** The cheapest option is code you already have.

#### 2a. Internal prior-art

Before any web search, check whether the capability already exists in the current repo or org:

- grep the codebase for the capability's keywords and likely symbol names
- if Serena is available, run a symbol search; if Forgetful memory is available, query it
- check existing dependencies (`package.json` / `requirements.txt` / `Cargo.toml` / `go.mod`) for a library already pulled in

If an internal implementation exists, recommend **Leverage** (use as-is) or **Extend** (adapt it) before proposing a build or an external buy. Internal reuse beats both a new dependency and a rewrite.

#### 2b. External solutions

Search strategy (use web_search):

1. `"{functionality} library {language}"`
2. `"{functionality} open source"`
3. `"{functionality} SaaS tool"`
4. `"best {functionality} solution 2024"`
5. `"{functionality} npm/pip/cargo package"` (based on ecosystem)

Categorize findings:

- **Libraries/Packages**: npm, pip, cargo, etc. (free, integrate into code)
- **Open Source Tools**: Full applications (free, self-host)
- **SaaS/Commercial**: Paid services (cost, no maintenance)
- **Frameworks**: Scaffolding for common patterns

### Step 3: Estimate Vibe Coding Cost

Use the token estimation reference: [references/token-estimates.md](references/token-estimates.md)

Factors to estimate:

| Factor | Low | Medium | High |
|--------|-----|--------|------|
| Lines of Code | <200 | 200-1000 | >1000 |
| Token Burn (est.) | 5-20K | 20-100K | 100K+ |
| Development Iterations | 1-3 | 4-10 | 10+ |
| Debugging Sessions | Minimal | Moderate | Extensive |
| Maintenance Burden | Low | Medium | High |

### Step 4: Generate Comparison Table

Always present a decision table. **Include internal rows only if Step 2a found prior-art:**

```markdown
| Option | Type | Cost | Setup Time | Maintenance | Token Burn | Verdict |
|--------|------|------|------------|-------------|------------|---------|
| Existing internal | Leverage | Free | minutes | Shared | 0 | ♻️ Reuse first |  <!-- only if Step 2a found match -->
| Existing internal | Extend | Free | hrs | You own the delta | low | 🔧 Adapt existing |  <!-- only if Step 2a found match -->
| [Solution A] | Library | Free | 5 min | Updates only | 0 | ✅ Recommended |
| [Solution B] | SaaS | $X/mo | Instant | None | 0 | ⚡ Fastest |
| Vibe Code | Custom | Free | X hrs | You own it | ~XK tokens | 🔧 Full control |
```

### Step 5: Strategic build/buy/partner/defer (delegate)

This skill is **tactical**: "use an existing library/SaaS vs write glue code." When the decision is **strategic** (a capability investment needing Core-vs-Context classification, a weighted decision matrix, multi-year TCO, partner/defer options, or multi-stakeholder sign-off), STOP here and use the `buy-vs-build-framework` skill. It owns that decision and backs it with scripts (`calculate_tco.py`, `score_decision.py`, `score_vendor.py`). Do not re-derive that analysis here.

Hand off when any of these is true:

- Budget impact > ~$50K, or a 2+ year horizon
- The capability may be a competitive differentiator (a strategic core-versus-commodity call)
- Partner or defer is a live option (not just build vs use-existing)
- Multiple stakeholders must align on the choice

Otherwise continue below for the tactical recommendation.

### Step 6: Recommendation Framework (Quick Reference)

Recommend **internal reuse (Leverage/Extend)** when:

- Step 2a found existing internal implementation
- Capability already exists in repo or org codebase
- Existing dependency already provides the functionality
- Internal code covers ≥80% of the requirement (extend for the rest)

Recommend **existing solutions** when:

- No internal prior-art found in Step 2a
- Mature library exists with >1K GitHub stars
- SaaS solves it for <$20/mo
- Common problem with well-tested solutions
- Security-sensitive (auth, crypto, payments)

Recommend **vibe coding** when:

- Highly specific business logic
- Simple glue code (<50 lines)
- Learning exercise (explicitly stated)
- No good existing solution found
- Integration requirements are unusual

### Step 7: If Vibe Coding Proceeds

If user chooses to build after seeing alternatives:

1. Acknowledge the valid reasons
2. Suggest existing code as reference/inspiration
3. Recommend libraries for sub-components
4. Provide a hybrid approach when possible

### Step 8: Integration Planning (When User Accepts Recommendation)

When the user accepts a recommended solution, provide a complete integration plan:

#### 8.1 Detect Project Context

Before generating the plan, analyze the user's project:

- **Package manager**: Check for `package.json` (npm/yarn/pnpm), `requirements.txt`/`pyproject.toml` (pip/poetry), `Cargo.toml` (cargo), `go.mod` (go)
- **Framework**: Identify React, Vue, Next.js, Rails, Django, FastAPI, etc.
- **Existing dependencies**: Check for conflicts or complementary packages
- **Project structure**: Understand where new code should live (src/, lib/, app/, etc.)
- **Code style**: Match existing patterns (TypeScript vs JS, ESM vs CJS, etc.)

#### 8.2 Generate Installation Commands

Provide ready-to-run commands for the detected package manager:

```bash
# npm
npm install <package>

# yarn
yarn add <package>

# pnpm
pnpm add <package>

# pip
pip install <package>

# poetry
poetry add <package>
```

#### 8.3 Provide Integration Steps

Create a numbered action plan:

1. **Install dependencies** - Exact commands
2. **Create/update config files** - If the library needs configuration
3. **Add to existing code** - Where to import and initialize
4. **Create new files** - With suggested file paths matching project structure
5. **Update related files** - Any existing files that need modification

#### 8.4 Generate Starter Code

Provide code scaffolding that:

- Matches the user's detected code style (TypeScript/JavaScript, etc.)
- Uses their existing patterns and conventions
- Includes necessary imports
- Shows basic usage with comments
- Handles common edge cases

#### 8.5 Warn About Potential Issues

Flag any concerns:

- **Dependency conflicts**: "Note: This requires React 18+, you have React 17"
- **Breaking changes**: "This library had major changes in v3, examples are for v3"
- **Peer dependencies**: "You'll also need to install X"
- **Config requirements**: "Requires adding to your tsconfig/babel/webpack config"

### Step 9: Cost Analysis (For Significant Decisions)

For features with meaningful cost implications (auth, payments, email, infrastructure), provide a quick tactical cost comparison (9.3). For a multi-year TCO/NPV, delegate to the `buy-vs-build-framework` skill (9.2); do not produce that analysis here.

#### 9.1 When to Include Cost Analysis

Include cost table when:

- SaaS options have monthly fees > $10
- DIY token estimate > 50K tokens
- User asks about costs or "is it worth it"
- Comparing multiple paid services
- Security-sensitive features (auth, payments)

#### 9.2 Multi-year TCO: delegate

For a multi-year TCO/NPV comparison (Year 1/3/5, discount rate, break-even, maintenance), use the `buy-vs-build-framework` skill's `calculate_tco.py`. Do not re-derive the NPV math here.

#### 9.3 Tactical cost note

For the tactical "library vs glue code" choice, a one-line comparison is enough: SaaS monthly fee vs the DIY token-burn from Step 4 (pricing in [references/pricing-data.md](references/pricing-data.md)).

```markdown
## 💰 Cost Note

| Option | Setup | Monthly | Notes |
|--------|-------|---------|-------|
| [SaaS A] | 10min | $25 | Free tier: 10K MAU |
| [Free/OSS] | 1hr | $0 | Self-host required |
| DIY | Xhrs | $0 | ~XK tokens + maintenance |

💡 Beyond a quick estimate, hand the multi-year TCO to buy-vs-build-framework.
```

#### 9.4 Hidden Costs to Surface

Always mention relevant hidden costs:

- **Security audits**: $5K-50K for custom auth systems
- **Compliance**: SOC2, GDPR, PCI implementation time
- **On-call burden**: DIY = you're the support team
- **Opportunity cost**: Time not spent on core product
- **Technical debt**: Custom code needs maintenance forever

#### 9.5 Red Flags to Call Out

Warn users when they say:

- "It's just a simple auth system" → Auth is never simple
- "We can build it in a weekend" → You can't, securely
- "We'll add security later" → Security debt is expensive
- "It's cheaper long-term" → Usually false under 10K users

## Response Template

```markdown
## 🔍 Existing Solutions Found

I found [N] existing solutions before we write custom code:

### Libraries/Packages
- **[Name]**: [one-line description] | [stars/downloads] | [link]

### Open Source Tools  
- **[Name]**: [one-line description] | [stars] | [link]

### SaaS Options
- **[Name]**: [one-line description] | [pricing] | [link]

## 📊 Build vs Buy Comparison

| Option | Type | Cost | Setup | Maintenance | Est. Tokens |
|--------|------|------|-------|-------------|-------------|
| ... | ... | ... | ... | ... | ... |

## 💰 Cost Note (tactical)

| Option | Setup | Monthly | Notes |
|--------|-------|---------|-------|
| ... | ... | ... | ... |

⚠️ **Hidden costs:** [security, compliance, maintenance]
💡 For a multi-year TCO/NPV, hand off to `buy-vs-build-framework` (`calculate_tco.py`).

## 💡 Recommendation

[Clear recommendation with reasoning]

## 🔧 If You Still Want to Build

[Only if user wants custom solution - suggest hybrid approach]
```

### Integration Plan Template (When User Accepts)

When the user says "let's use [recommended solution]" or "how do I add this?", respond with:

```markdown
## 🚀 Integration Plan: [Solution Name]

### Your Project Context
- **Detected**: [framework], [package manager], [language]
- **Project structure**: [src/app/lib layout]

### Step 1: Install Dependencies

\`\`\`bash
[exact install command for their package manager]
\`\`\`

### Step 2: Configuration (if needed)

[Any config file changes needed]

### Step 3: Create New Files

📁 `[suggested/file/path.ts]`
\`\`\`typescript
[starter code matching their project style]
\`\`\`

### Step 4: Update Existing Files

📝 `[existing/file/to/modify.ts]`
\`\`\`typescript
// Add this import
import { X } from '[package]'

// Use it like this
[integration code]
\`\`\`

### ⚠️ Notes
- [Any warnings about versions, conflicts, or requirements]

### 📚 Resources
- [Official docs link]
- [Relevant examples]
```

## Anti-Patterns to Flag

Alert users when they're about to reinvent:

- Authentication systems → "Use Auth0, Clerk, Supabase Auth"
- State management → "Consider Zustand, Redux Toolkit, Jotai"
- Form validation → "Check out Zod, Yup, React Hook Form"
- API clients → "Look at Axios, ky, ofetch"
- Date handling → "Use date-fns, dayjs, Luxon"
- CLI tools → "Consider Commander, yargs, oclif"
- PDF generation → "Use pdf-lib, jsPDF, Puppeteer"
- Email sending → "Check Resend, SendGrid, Nodemailer"
- Cron jobs → "Use node-cron, Bull, Agenda"
- Database ORMs → "Consider Prisma, Drizzle, TypeORM"

## Quick Reference: Common Token Burns

| Task Complexity | Typical Token Burn | Time Equivalent |
|-----------------|-------------------|-----------------|
| Simple script (<100 LOC) | 5-15K | 30min-1hr |
| Utility module (100-500 LOC) | 15-50K | 2-4hrs |
| Feature component (500-2K LOC) | 50-150K | 1-2 days |
| Full application | 150K-500K+ | Days-weeks |

See [references/token-estimates.md](references/token-estimates.md) for detailed breakdowns.

See [references/common-solutions.md](references/common-solutions.md) for exhaustive list of commonly reinvented wheels.

See [references/integration-patterns.md](references/integration-patterns.md) for project detection and starter code patterns.

See [references/pricing-data.md](references/pricing-data.md) for SaaS pricing and cost calculation data.

See [references/bitter-lesson-llms.md](references/bitter-lesson-llms.md) for why simpler integrations with better models beat complex scaffolding.
