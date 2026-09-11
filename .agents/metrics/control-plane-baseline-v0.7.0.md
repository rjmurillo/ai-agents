# Control-plane baseline

- Commit: `efdfe5b3190340e363737ec92033da720fc259c0`
- Captured at: `2026-09-11T17:41:27.750182+00:00`

## Measurement command

```
scripts/metrics/control_plane_baseline.py --repo /home/richard/src/GitHub/rjmurillo/ai-agents2 --json .agents/metrics/control-plane-baseline-v0.7.0.json --markdown .agents/metrics/control-plane-baseline-v0.7.0.md
```

Any clean checkout of `main` at the commit recorded above produces the same dimension values; `--repo` may point at any such checkout. The script itself lives on the branch that ran it, not necessarily on `main`.

## Definitions

- canonical owner total = agents + skills + rules + registered hook entries (canonical.hooks_by_event; canonical.hooks_python_files is excluded so a hook that is both a settings.json registration and a source file counts once) + validators + workflows + lefthook jobs.
- validators are counted by three globs, recursive under scripts/, excluding tests/ and __pycache__/ segments: `check_*.py`, `checks_*.py`, `validate_*.py`.
- activation.referenced_names matches a structured reference only: a backticked name, or a /name slash-prefixed occurrence (which also matches a skills/name path segment, since that segment contains /name as a substring). A bare word in prose does not count.

## accepted_tasks

| key | value |
|---|---|
| other | 0 |
| total | 22 |
| unverified | 22 |
| verified | 0 |

## activation

| key | value |
|---|---|
| referenced_count | 13 |
| referenced_names | autoplan, build, context-gather, memory, memory-search, plan, push-pr, research, review, ship, software-engineering-library, spec, test |
| tested_count | 35 |
| tested_names | adr-review, business-strategy, chestertons-fence, codebase_documenter, codeql-scan, context-gather, curating-memories, doc-accuracy, dx-review, fix-markdown-fences, github, github_url_intercept, golden-principles, memory, memory-consolidate, merge-resolver, metrics, orphan-ref-validator, panning-for-gold, pipeline_validator, pr-autofix, pr-comment-responder, prose-self-check, requirements_interview, retrospective, review, reviewer-findings, security-detection, security-review, skillforge, slashcommandcreator, steering-matcher, stuck-detection, taste-lints, work-operating-model |

## always_loaded

| key | value |
|---|---|
| claude_code.bytes | 63263 |
| claude_code.files | .claude/CLAUDE.md, .claude/rules/builder-ethos.md, .claude/rules/claude-model-patches.md, .claude/rules/search-before-building.md, .claude/rules/universal.md, .claude/rules/voice.md, AGENTS.md, CLAUDE.md |
| claude_code.tokens | 16870 |
| codex.bytes | 2998 |
| codex.files | AGENTS.md |
| codex.tokens | 964 |
| copilot.bytes | 64568 |
| copilot.files | .github/copilot-instructions.md, .github/instructions/builder-ethos.instructions.md, .github/instructions/claude-model-patches.instructions.md, .github/instructions/search-before-building.instructions.md, .github/instructions/universal.instructions.md, .github/instructions/voice.instructions.md, AGENTS.md |
| copilot.tokens | 17273 |

## canonical

| key | value |
|---|---|
| agents | 31 |
| hooks_by_event.PreCompact | 1 |
| hooks_by_event.SessionEnd | 1 |
| hooks_by_event.SessionStart | 4 |
| hooks_by_event.UserPromptSubmit | 1 |
| hooks_python_files | 12 |
| lefthook_jobs | 76 |
| lefthook_jobs_by_hook.commit-msg | 1 |
| lefthook_jobs_by_hook.pre-commit | 45 |
| lefthook_jobs_by_hook.pre-merge-commit | 1 |
| lefthook_jobs_by_hook.pre-push | 29 |
| rules | 30 |
| skills | 111 |
| validators | 99 |
| workflows | 58 |

## gate_budget

| key | value |
|---|---|
| seconds_by_hook.commit-msg | 30.0 |
| seconds_by_hook.pre-commit | 6230.0 |
| seconds_by_hook.pre-merge-commit | 120.0 |
| seconds_by_hook.pre-push | 3450.0 |

## generated_historical

| key | value |
|---|---|
| archive.bytes | 6206564 |
| archive.count | 816 |
| episodes.bytes | 3280080 |
| episodes.count | 752 |
| eval_results.bytes | 50403 |
| eval_results.count | 4 |
| generated_projections.copilot_cli_src.bytes | 21029511 |
| generated_projections.copilot_cli_src.count | 783 |
| generated_projections.github_instructions.bytes | 277676 |
| generated_projections.github_instructions.count | 30 |
| serena_memories.bytes | 3127483 |
| serena_memories.count | 1041 |
| sessions.bytes | 8854391 |
| sessions.count | 1538 |

## policy_owners

| key | value |
|---|---|
| adrs | 108 |
| always_on.claude_rules | .claude/rules/builder-ethos.md, .claude/rules/claude-model-patches.md, .claude/rules/search-before-building.md, .claude/rules/universal.md, .claude/rules/voice.md |
| always_on.github_instructions | .github/instructions/builder-ethos.instructions.md, .github/instructions/claude-model-patches.instructions.md, .github/instructions/search-before-building.instructions.md, .github/instructions/universal.instructions.md, .github/instructions/voice.instructions.md |
| governance_docs | 42 |
| rule_mirrors.copilot_cli_instructions | 24 |
| rule_mirrors.github_instructions | 30 |
| serena_memories | 1037 |

## Exclusions

No per-dimension data was missing on this run.

- Gate p50/p95: no sampler exists. gate_budget is the declared worst case from lefthook.yml, not a measured distribution. ADR-104 cites two single-push measurements as provisional evidence: 142.39s against 679s recorded for a comparable push on the same container class.
- Fan-out: routed to the harness per #5651; worktree residue is machine-local, not a repository property, so it is not measured (the fanout_residue dimension was removed for this reason).
- Activation: two static proxies (referenced-name matching in AGENTS.md/CLAUDE.md/the autoplan routing table, and tests/skills/<name>/ presence), not invocation telemetry.
- Accepted-task outcomes: accepted_tasks counts VERIFIED/UNVERIFIED cells in the harness-capability-matrix, not task outcomes. Per issue #5423 every cell is UNVERIFIED at authoring time; paid live-harness probes are unavailable.

## Release targets for v0.7.0

| metric | target | direction |
|---|---|---|
| canonical owner total | strictly below 412 | decrease |
| always_loaded.claude_code.tokens | strictly below 16870 | decrease |
| always_loaded.codex.tokens | strictly below 964 | decrease |
| always_loaded.copilot.tokens | strictly below 17273 | decrease |
| gate_budget.seconds_by_hook.pre-push | must not rise above 3450.0 seconds | hold |
| measured push duration (once real push samples exist) | must not exceed ADR-104's 300 second ceiling | hold |

