# Control-plane baseline

- Commit: `c27d98b724d7776cdee40be16e0bd2dbd25bcd3b`
- Captured at: `2026-09-11T17:20:11.858615+00:00`
- Command: `scripts/metrics/control_plane_baseline.py --repo . --json .agents/metrics/control-plane-baseline-v0.7.0.json --markdown .agents/metrics/control-plane-baseline-v0.7.0.md --allow-dirty`

## accepted_tasks

- **other**: 0
- **total**: 22
- **unverified**: 22
- **verified**: 0

## activation

- **referenced_count**: 30
- **referenced_names**:
  - adr-generator
  - adr-review
  - agent-harness-reference
  - ai-agents-portability-campaign
  - analyze
  - autoplan
  - build
  - buy-vs-build-framework
  - context-gather
  - github
  - memory
  - memory-search
  - merge-resolver
  - plan
  - pr-comment-responder
  - push-pr
  - quality-grades
  - reflect
  - research
  - retro
  - review
  - security-detection
  - security-review
  - security-scan
  - ship
  - skillforge
  - software-engineering-library
  - spec
  - sync
  - test
- **tested_count**: 35
- **tested_names**:
  - adr-review
  - business-strategy
  - chestertons-fence
  - codebase_documenter
  - codeql-scan
  - context-gather
  - curating-memories
  - doc-accuracy
  - dx-review
  - fix-markdown-fences
  - github
  - github_url_intercept
  - golden-principles
  - memory
  - memory-consolidate
  - merge-resolver
  - metrics
  - orphan-ref-validator
  - panning-for-gold
  - pipeline_validator
  - pr-autofix
  - pr-comment-responder
  - prose-self-check
  - requirements_interview
  - retrospective
  - review
  - reviewer-findings
  - security-detection
  - security-review
  - skillforge
  - slashcommandcreator
  - steering-matcher
  - stuck-detection
  - taste-lints
  - work-operating-model

## always_loaded

- **claude_code**:
  - **bytes**: 63290
  - **files**:
    - .claude/CLAUDE.md
    - .claude/rules/builder-ethos.md
    - .claude/rules/claude-model-patches.md
    - .claude/rules/search-before-building.md
    - .claude/rules/universal.md
    - .claude/rules/voice.md
    - AGENTS.md
    - CLAUDE.md
  - **tokens**: 16879
- **codex**:
  - **bytes**: 2999
  - **files**:
    - AGENTS.md
  - **tokens**: 965
- **copilot**:
  - **bytes**: 64595
  - **files**:
    - .github/copilot-instructions.md
    - .github/instructions/builder-ethos.instructions.md
    - .github/instructions/claude-model-patches.instructions.md
    - .github/instructions/search-before-building.instructions.md
    - .github/instructions/universal.instructions.md
    - .github/instructions/voice.instructions.md
    - AGENTS.md
  - **tokens**: 17281

## canonical

- **agents**: 31
- **hooks**: 19
- **hooks_by_event**:
  - **PreCompact**: 1
  - **SessionEnd**: 1
  - **SessionStart**: 4
  - **UserPromptSubmit**: 1
- **hooks_python_files**: 12
- **lefthook_jobs**: 76
- **lefthook_jobs_by_hook**:
  - **commit-msg**: 1
  - **pre-commit**: 45
  - **pre-merge-commit**: 1
  - **pre-push**: 29
- **rules**: 30
- **skills**: 111
- **validators**: 73
- **workflows**: 58

## fanout_residue

- **prunable**: 8
- **total**: 27

## gate_budget

- **seconds_by_hook**:
  - **commit-msg**: 30.0
  - **pre-commit**: 6230.0
  - **pre-merge-commit**: 120.0
  - **pre-push**: 3450.0

## generated_historical

- **archive**:
  - **bytes**: 6206564
  - **count**: 816
- **episodes**:
  - **bytes**: 3280080
  - **count**: 752
- **eval_results**:
  - **bytes**: 50403
  - **count**: 4
- **generated_projections**:
  - **copilot_cli_src**:
    - **bytes**: 20632637
    - **count**: 747
  - **github_instructions**:
    - **bytes**: 277702
    - **count**: 30
- **serena_memories**:
  - **bytes**: 3133171
  - **count**: 1041
- **sessions**:
  - **bytes**: 8854391
  - **count**: 1538

## policy_owners

- **adrs**: 108
- **always_on**:
  - **claude_rules**:
    - .claude/rules/builder-ethos.md
    - .claude/rules/claude-model-patches.md
    - .claude/rules/search-before-building.md
    - .claude/rules/universal.md
    - .claude/rules/voice.md
  - **github_instructions**:
    - .github/instructions/builder-ethos.instructions.md
    - .github/instructions/claude-model-patches.instructions.md
    - .github/instructions/search-before-building.instructions.md
    - .github/instructions/universal.instructions.md
    - .github/instructions/voice.instructions.md
- **governance_docs**: 42
- **rule_mirrors**:
  - **copilot_cli_instructions**: 24
  - **github_instructions**: 30
- **serena_memories**: 1037

## Exclusions

No per-dimension data was missing on this run (the script's own exclusion
list above is empty). The measurement design itself excludes four things
the epic's Baseline section names, none of which this script can close
without becoming the sampler, router, telemetry probe, or paid-eval
harness it is explicitly not (epic Abort-if clause 3; REQ-021 Out of
Scope):

- **Gate p50/p95**: no sampler exists. `gate_budget` above is the
  *declared* worst case (`lefthook.yml`'s configured timeouts), not a
  measured distribution. The only real numbers on record are two single
  pushes cited in ADR-104: 142.39s, against 679s recorded for a comparable
  push on the same container class. Both are provisional evidence, not a
  statistically sound p50/p95.
- **Fan-out**: `fanout_residue` above is a worktree-residue count only
  (total worktrees, prunable count). Fan-out routing itself is owned by
  issue #5651, which routes #5436's fix to the harness; this baseline does
  not measure routing behavior.
- **Activation**: `activation` above is two static proxies (named in
  `AGENTS.md`/`CLAUDE.md`/the autoplan routing table, and presence of a
  `tests/skills/<name>/` directory), not invocation telemetry. This repo
  has no record of which skills actually fired in a session.
- **Accepted-task outcomes**: `accepted_tasks` above counts
  `VERIFIED`/`UNVERIFIED` cells in
  `scripts/eval/examples/harness-capability-matrix.json`, not task
  outcomes. Per issue #5423, every cell in that matrix is `UNVERIFIED` at
  authoring time; the paid live-harness probes needed to verify any cell
  are unavailable in this environment.

## Measurement command

```
scripts/metrics/control_plane_baseline.py --repo . --json .agents/metrics/control-plane-baseline-v0.7.0.json --markdown .agents/metrics/control-plane-baseline-v0.7.0.md --allow-dirty
```

`--allow-dirty` was required because sibling spec files for this same
epic cohort (REQ-022/DESIGN-021/TASK-025, REQ-023/DESIGN-022/TASK-026)
were present untracked in this worktree at capture time, per this task's
explicit instruction not to commit or move them from this branch. They
carry no path this script measures (`.agents/specs/**` is not a
dimension source), so they do not change any number above; the commit
SHA in this document's header is the pinned, reproducible anchor, not the
working tree state.

## Release targets for v0.7.0

Targets are relative to this document's own numbers, captured at commit
`c27d98b724d7776cdee40be16e0bd2dbd25bcd3b`.

- **Canonical owner total** (`canonical.agents + skills + rules + hooks +
  validators + workflows + lefthook_jobs`) must decrease from 398
  (31 + 111 + 30 + 19 + 73 + 58 + 76), per the epic's Release gates
  checklist first item.
- **Always-loaded estimated tokens** must decrease, per harness, from this
  baseline's `always_loaded.<harness>.tokens`: Claude Code 16,879, Copilot
  17,281, Codex 965.
- **Declared pre-push budget** (`gate_budget.seconds_by_hook.pre-push`)
  must not rise above 3,450.0 seconds.
- **Once real push samples exist** (the p50/p95 sampler this baseline
  explicitly excludes, above), no measured push may exceed ADR-104's
  300-second ceiling. This target cannot be checked from this document
  alone; it is recorded here because the epic's Release gates checklist
  names it, not because this baseline measures it.

