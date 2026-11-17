# programming-advisor

Checks whether a library, SaaS product, open source tool, or code already in your repository solves your problem before you write new code. You get a comparison table and a recommendation.

## When to use it

- You are about to build a new feature and want to know if something already exists.
- You ask `should I build X or use a library`, `do we already have X`, `is there a package for X`, or `check if X exists before building`.
- You want a quick build versus buy cost comparison with token estimates for writing the code yourself.
- You want to find internal code to reuse or extend before you add a dependency.

## When not to use it

- Strategic, multi-year, multi-option decisions (over about $50K, partner or defer options, several stakeholders): use [`buy-vs-build-framework`](buy-vs-build-framework.md) instead.

## Quick start

This skill is not a front door, so you rarely start it yourself. In Claude Code you can still type `/project-toolkit:programming-advisor`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the programming-advisor skill to check whether we already have a retry helper in this repo or if there is a library for it.
```

The skill searches the repository first, then external options. At the end you see a comparison table, a short cost note, and a recommendation.

## What you get

A response with these parts:

- Existing solutions found, grouped as libraries and packages, open source tools, and SaaS options.
- A decision table with columns for option, type, cost, setup time, maintenance, token burn, and verdict. Internal rows (Leverage, Extend) appear only if the repository search found prior art.
- A tactical cost note comparing SaaS fees with the token cost of writing it yourself, plus hidden costs such as security audits, compliance, and on-call burden.
- A recommendation. If you decide to build anyway, the skill suggests a hybrid approach.
- An integration plan when you accept a recommendation: detected package manager and framework, install commands, config changes, file paths, starter code, and warnings about version conflicts.

## Advanced use

The skill works in steps:

1. Capture what you need, why, and your constraints (language, platform, budget, licensing).
2. Search internal prior art first: grep the codebase, run a Serena symbol search if available, and check existing dependencies. If code exists, it recommends Leverage (use as is) or Extend (adapt it).
3. Search external options: libraries, open source tools, SaaS, and frameworks.
4. Estimate the cost of writing it yourself by lines of code, token burn, iterations, debugging, and maintenance.
5. Build the comparison table.
6. Hand off to `buy-vs-build-framework` when the decision is strategic. That skill owns multi-year TCO and scoring.

Security-sensitive capabilities (auth, crypto, payments) skip reuse-first. The skill recommends a vetted external provider over extending homegrown code, even when internal code covers most of the need.

It recommends reuse when internal code covers at least 80 percent of the requirement and the capability is not security-sensitive. It recommends an existing solution when a mature library exists or a SaaS costs under about $20 per month. It recommends writing code when the logic is highly specific, the glue is under about 50 lines, or no good option exists.

It also flags red flags such as "it's just a simple auth system" and common reinvented wheels (auth, state management, form validation, date handling, PDF generation, email sending).

The skill has no scripts. Reference files cover details:

- [`token-estimates.md`](../../src/claude/skills/programming-advisor/references/token-estimates.md): token burn by task size.
- [`pricing-data.md`](../../src/claude/skills/programming-advisor/references/pricing-data.md): SaaS pricing data.
- [`common-solutions.md`](../../src/claude/skills/programming-advisor/references/common-solutions.md): commonly reinvented wheels.
- [`integration-patterns.md`](../../src/claude/skills/programming-advisor/references/integration-patterns.md): project detection and starter code.
- [`search-before-building.md`](../../src/claude/skills/programming-advisor/references/search-before-building.md): when to search, the three layers of knowledge, and a pre-code checklist.
- [`bitter-lesson-llms.md`](../../src/claude/skills/programming-advisor/references/bitter-lesson-llms.md): why simpler integrations with better models beat complex scaffolding.

The [`autoplan`](autoplan.md) skill routes to this skill for prior-art discovery before a spec on a new capability request.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`buy-vs-build-framework`](buy-vs-build-framework.md): strategic build, buy, partner, or defer decisions with TCO scripts.
- [`autoplan`](autoplan.md): routes new capability requests here before a spec.
- Source: [`SKILL.md`](../../src/claude/skills/programming-advisor/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
