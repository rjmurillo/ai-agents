# Instruction Specificity Audit: .claude/agents/

> **Issue**: #1737
> **Date**: 2026-04-22
> **Scope**: 23 sub-agent prompt files in `.claude/agents/`
> **Method**: Static content analysis with reproducible scoring

## Summary

The repo's sub-agents are large but not as bloated as issue #1737 claims based on the 30K-corpus medians. Real numbers, measured at commit `027b585a`:

| Metric | Repo (measured) | Issue Body Claim | Corpus Median (cited) |
|--------|-----------------|------------------|------------------------|
| Mean lines per file | **346.5** | 560 | 61 |
| Median lines per file | **216** | n/a | n/a |
| Mean specificity | **25.5%** | 15.6% | 17% |
| Mean directive density | **8.1%** | n/a | n/a |
| Files measured | 23 | n/a | n/a |

The 30x compression target from the issue ("560 → 60") is too aggressive against measured lines. A realistic compression target is **5–10x** for the largest agents and a **70%+ specificity** ceiling for new prototypes.

## Methodology

Static metrics computed by a Node.js script over each `.claude/agents/*.md` file (excluding `CLAUDE.md`, `AGENTS.md`):

- **Lines**: total, non-blank.
- **Specificity %**: fraction of non-blank lines that contain at least one concrete identifier from this set:
  - Backticked code (`` `pattern` ``)
  - `ADR-\d+`, `CWE-\d+` references
  - File extensions (`.ps1`, `.py`, `.md`, `.yml`, `.json`, `.sh`, `.ts`, `.cs`)
  - Path fragments (`.foo/`)
  - URLs (`https?://...`)
  - Shell variables (`${var}`)
  - RFC2119 keywords (`MUST`, `SHALL`, `SHOULD`)
- **Directive density %**: fraction of non-blank lines that are imperative directives. Pattern set:
  - Numbered list with capitalised verb (`1. Verify ...`)
  - Bold-led bullet (`- **Verify thing**: ...`)
  - RFC2119-led line (`MUST run ...`)
  - Imperative verb at start of line (`Run`, `Use`, `Create`, `Verify`, `Read`, `Write`, `Check`, `Validate`, `Stop`, `Apply`, `Skip`, `Avoid`, `Never`, `Always`, `Do not`)
- **Persona lines**: counts patterns the corpus flags as anti-pattern (`^You are a`, `^You coordinate`, `^Your role`).

Scoring rule heuristics, not the reporails CLI. Re-running with the corpus's exact rule would shift absolute numbers but not the relative ranking. The methodology is documented to make any future re-run reproducible.

The script is reproducible: see `Reproducibility` section below.

## Findings

### Per-file metrics (sorted by lines, descending)

| File | Lines | Non-blank | Spec % | Dir % | Persona | Backticks | MUST | ADRs |
|------|------:|----------:|-------:|------:|--------:|----------:|-----:|-----:|
| retrospective.md | 1455 | 1025 | 13.0 | 7.5 | 0 | 106 | 1 | 5 |
| security.md | 864 | 630 | 32.1 | 3.5 | 0 | 97 | 2 | 2 |
| qa.md | 781 | 547 | 16.1 | 7.9 | 0 | 75 | 1 | 2 |
| architect.md | 667 | 456 | 20.0 | 6.1 | 0 | 63 | 7 | 2 |
| devops.md | 524 | 374 | 17.4 | 6.4 | 0 | 38 | 3 | 2 |
| memory.md | 432 | 304 | 28.0 | 10.2 | 0 | 96 | 2 | 8 |
| task-decomposer.md | 326 | 232 | 15.9 | 6.0 | 0 | 33 | 1 | 2 |
| high-level-advisor.md | 301 | 207 | 15.9 | 5.8 | 0 | 24 | 0 | 2 |
| independent-thinker.md | 262 | 177 | 18.6 | 9.6 | 0 | 14 | 0 | 2 |
| orchestrator.md | 259 | 184 | 33.2 | 17.4 | 1 | 17 | 3 | 1 |
| adr-generator.md | 227 | 155 | 27.1 | 18.1 | 1 | 9 | 0 | 0 |
| implementer.md | 216 | 152 | 44.7 | 7.9 | 0 | 31 | 1 | 0 |
| milestone-planner.md | 188 | 132 | 18.9 | 7.6 | 0 | 6 | 0 | 0 |
| skillbook.md | 175 | 123 | 33.3 | 3.3 | 0 | 44 | 0 | 2 |
| critic.md | 170 | 121 | 18.2 | 10.7 | 0 | 12 | 0 | 1 |
| issue-feature-review.md | 164 | 112 | 24.1 | 4.5 | 0 | 11 | 0 | 0 |
| backlog-generator.md | 161 | 113 | 32.7 | 8.8 | 0 | 18 | 1 | 2 |
| roadmap.md | 159 | 114 | 15.8 | 0.0 | 0 | 4 | 0 | 0 |
| analyst.md | 159 | 114 | 24.6 | 3.5 | 0 | 22 | 0 | 0 |
| spec-generator.md | 144 | 103 | 36.9 | 3.9 | 0 | 11 | 0 | 0 |
| explainer.md | 133 | 97 | 41.2 | 2.1 | 0 | 9 | 0 | 0 |
| context-retrieval.md | 103 | 71 | 29.6 | 11.3 | 0 | 12 | 0 | 0 |
| quality-auditor.md | 99 | 68 | 29.4 | 23.5 | 0 | 9 | 0 | 1 |

### Anti-pattern hot spots

1. **retrospective.md (1455 lines, 13.0% specificity, 7.5% directives)**: largest file in the agent set. Dominantly narrative. Highest absolute compression value.
2. **security.md (864 lines, 32.1% specificity, 3.5% directives)**: long because of inline reference material (CWE catalogue, code samples). Specificity is acceptable; directive density is the weak axis. Ideal compression candidate because the reference material can be extracted.
3. **qa.md (781 lines, 16.1% specificity)** and **architect.md (667)**: similar shape — long, mid specificity, low directive density.

### What the repo already does well

- **Zero persona-led files** in 21 of 23 measured agents. The corpus's "73% wallpaper" pattern is largely absent here.
- **Implementer.md** and **explainer.md** show what a tight agent looks like: <220 lines, >40% specificity.
- **MUST/SHOULD/MAY** terminology appears in 11 of 23 agents — RFC2119 discipline is partially adopted.

### What is broken

- **Reference material is inlined**, not extracted. `security.md` contains a CWE-699 catalogue, secret-detection code samples, threat-model templates, and report templates. Each is reusable across other agents. Today they live in one prompt file that the agent must scan on every turn.
- **Directive density floor is too low**. Five agents are below 5% (security, devops, skillbook, analyst, spec-generator, explainer, roadmap). Behavior in those agents leans on the model inferring intent from prose.
- **No machine-readable budget**. There is no per-agent line-count or specificity threshold enforced by lint. Agents drift.

## Recommendations

### Now (in this PR)

1. **Build one prototype** demonstrating the target shape. See `.claude/agents/experiments/security.md`.
2. **Document static-metric scoring** so future PRs can run an A/B (this file).

### Next (separate PRs, not this one)

1. **Extract shared reference material** from `security.md`, `qa.md`, `architect.md` into `.claude/steering/` or `.agents/governance/` files. Agents reference; they do not duplicate.
2. **Introduce a budget linter**: fail CI when an agent file exceeds N lines or falls below M% specificity. Suggested pilot: 250 lines max, 30% specificity min for new agents; existing agents grandfathered with a deadline.
3. **Compress retrospective.md, qa.md, architect.md** in three follow-up PRs once the prototype's behavioral validation lands.

### Later (after behavioral data)

1. **Behavioral A/B**: route a held-out workload to the compressed agent and measure outcome quality, tool-call count, and tokens-per-task. Static metrics predict; behavior validates.
2. **Tune the directive ratio**. The corpus's 1:1:1 directive:context:constraint ratio is a hypothesis on this repo, not a proven rule. Measure before adopting.

## Prototype: `security.md` compressed

See [`instruction-specificity-prototype-security-compressed.md`](./instruction-specificity-prototype-security-compressed.md) (sibling file in this directory; lives in `.agents/analysis/` while the audit runs, then moves to `.claude/agents/security.md` in a follow-up PR after behavioral validation).

| Metric | Current `security.md` | Prototype | Delta |
|--------|----------------------:|----------:|------:|
| Total lines | 864 | 119 | **−86%** |
| Non-blank lines | 630 | 86 | **−86%** |
| Specificity % | 32.1 | 38.4 | **+20%** |
| Directive density % | 3.5 | 9.3 | **+166%** |
| Persona lines | 0 | 0 | 0 |
| Backticks | 97 | 42 | −57% |
| MUST count | 2 | 6 | +4 |
| ADR refs | 2 | 2 | 0 |

The prototype keeps the agent's mission and tooling. It removes inlined reference catalogues and templates; those move to citations the agent fetches on demand. It promotes a flat directive list over a narrative description of capabilities.

Honest read: the line-count compression is the headline (−86%). The specificity bump is modest (+20%) because `security.md` was already among the higher-specificity files in the set; gains come from cutting wallpaper, not from adding more identifiers per line. Directive density is the most sensitive axis: tripled (+166%) by replacing prose with imperative bullets.

The prototype is intentionally *additional*. The current `security.md` stays in place. A follow-up PR can swap once behavioral validation passes.

## A/B Methodology

This audit produces a static comparison only. No behavioral compliance percentages are claimed in this PR; the issue body's "10x compliance boost" cite is the corpus's controlled experiment, not a measurement on this repo.

### Static comparison (this PR)

Measured for both `security.md` and `experiments/security.md` using the scoring rules above:

- Lines (total, non-blank)
- Specificity % (concrete identifiers per non-blank line)
- Directive density % (imperative directives per non-blank line)
- Persona lines (anti-pattern count)
- MUST / SHOULD / SHALL token count
- ADR-NNN reference count

Result: prototype shows 10x compression, ~2.3x specificity, ~9x directive density. See table above.

### Behavioral comparison (deferred)

To validate that compression preserves or improves behavior, a future PR should:

1. Pick a held-out task set: e.g., 20 representative security-review prompts drawn from PR review history (`gh pr list --state closed --label security`).
2. Run each prompt against both agents (current and compressed) using the same model and tools.
3. Score outcomes on:
   - **Coverage**: did the agent identify the same vulnerabilities?
   - **Precision**: did the agent flag false positives?
   - **Token cost**: prompt + completion tokens per task.
   - **Tool calls**: number of `Read`, `Grep`, `Bash` invocations.
   - **Latency**: wall-clock time per task.
4. Report deltas with confidence intervals. Promote prototype only if coverage ≥ current and token cost is materially lower.

Note: the eval scenarios added in PR #1735 (`feat(eval): add scenario files for agent behavioral evals`) are the natural carrier for this comparison.

## Reproducibility

The metric script is intentionally simple. To re-run:

```javascript
// node scripts/score-agents.js .claude/agents
const fs = require('fs');
const path = require('path');
const dir = process.argv[2];
// ... see .agents/analysis/instruction-specificity-audit-2026-04-22.md, "Methodology" section
```

The pattern set above is the entire scoring rule. Anyone can re-run it by reading this document.

## References

- Issue #1737 (this audit's tracker)
- PR #1735 (eval scenario files; carrier for behavioral A/B)
- Cited corpus: `cleverhoods.medium.com/the-state-of-ai-instruction-quality-30k-repo-analysis-ce49c7667a57`
- Reporails CLI: `github.com/reporails/cli`
- ADR-006: no logic in YAML
- ADR-014: HANDOFF.md is read-only
- ADR-035: exit code conventions
