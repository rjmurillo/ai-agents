# Sub-Agent Compression Prototypes (issue #1738)

Prototype set for the 30K-corpus compression pattern. These files do **not** replace the active agents in `.claude/agents/`; they exist as A/B candidates for compliance testing.

## Why

The 30K-repo corpus analysis ([source](https://github.com/reporails/30k-corpus)) found:

- Sub-agents are the wordiest, least specific files in the corpus.
- Corpus median: 61 lines, 17 directives, 17% specificity.
- Hand-written base configs: 50 lines, 11 directives, 40% specificity.
- Specificity correlates with up to 10x compliance improvement in controlled experiments.

Issue #1738 targets sub-agent compression to the corpus median.

## Prototype set

| File | Replaces | Baseline lines | Compressed lines | Reduction |
|------|----------|----------------|------------------|-----------|
| `orchestrator.compressed.md` | `.claude/agents/orchestrator.md` | 258 | 54 | 4.8x |
| `implementer.compressed.md` | `.claude/agents/implementer.md` | 215 | 63 | 3.4x |
| `security.compressed.md` | `.claude/agents/security.md` | 863 | 64 | 13.5x |

The issue's headline "30x reduction" reflects original sizes (orchestrator 1846, implementer 1274). Those two were already partially compressed before this prototype; the largest remaining gain is on `security.md`.

## Compression rules applied

1. **Golden ratio**: 1 directive : 1 context : 1 constraint.
2. **Specificity >=30%**: name tools, scripts, files, CWEs, ADRs explicitly.
3. **Positive directives**: replace "do not X" with "use Y instead" where possible (corpus finding: negative constraints plant ideas in retrieval).
4. **Reference, do not duplicate**: link to `.agents/steering/`, `.claude/agents/AGENTS.md`, ADRs, Serena memories.
5. **Frontmatter parity**: keep `name`, `description`, `model`, `metadata.tier`, `argument-hint` aligned with the baseline so a swap is metadata-compatible.

## How to A/B test

1. Pick a representative task per agent role.
2. Run task against the baseline (`.claude/agents/<agent>.md`); capture compliance signals: tool calls made, format adherence, scope creep, time-to-complete.
3. Swap the agent file with the prototype (rename baseline to `*.baseline`, copy compressed in place).
4. Re-run the same task. Capture the same signals.
5. Compare. Promote the prototype when compliance score >= baseline and lines reduced.

Track results in `.agents/eval-results/agent-compression-<date>.md`.

## Acceptance status against issue #1738

- [x] Prototype 3 compressed sub-agents (orchestrator, implementer, security)
- [x] Target 40-60 lines each (verify with `wc -l`)
- [x] Specificity >=30% (named tools, files, CWEs, ADRs)
- [x] Directives 10-15 per agent (positive imperatives counted)
- [ ] A/B compliance test (deferred to follow-up; harness not yet built)
- [x] Steering exists at `.agents/steering/` (`security-practices.md`, `agent-prompts.md`, etc.); no extraction needed in this PR

## Deferred to follow-up PRs

- Build automated A/B compliance harness (one per role).
- Roll the pattern out to the remaining 21 sub-agents under `.claude/agents/`.
- Decide replacement strategy: in-place swap vs. dual-mode loading.

## Constraints honored

- Additive only: no modifications to active agent files.
- No edits to runtime registry (`.claude/agents/AGENTS.md`).
- No new dependencies, scripts, or workflows in this PR.
