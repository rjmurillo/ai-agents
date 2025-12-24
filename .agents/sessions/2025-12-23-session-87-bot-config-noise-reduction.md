# Session 87: Bot Configuration Noise Reduction

**Date**: 2025-12-23
**Agent**: devops
**Issue**: #326 - Tune bot review configurations to reduce noise
**Branch**: docs/velocity

## Objective

Reduce bot review noise from 97 comments (PR #249) to <20 per PR by tuning CodeRabbit, Gemini, and Copilot configurations.

## Context

- **Problem**: PR #249 had 97 review comments (target: <20)
- **Bot Actionability**:
  - cursor[bot]: 95% (keep as-is)
  - Copilot: 21-34% (needs tuning)
  - gemini-code-assist: 24% (needs tuning)
  - CodeRabbit: 49% (needs tuning)
- **Noise Sources**: ~5 duplicate comments per PR, bots review generated files
- **Analysis Source**: `.agents/analysis/085-velocity-bottleneck-analysis.md`

## Implementation Plan

1. **CodeRabbit Configuration** - Update `.coderabbit.yaml`:
   - Add path_filters to ignore `.agents/sessions/**`, `.agents/analysis/**`
   - Research chill profile for noise reduction
   - Suppress duplicate findings

2. **Gemini Configuration** - Update `.gemini/config.yaml`:
   - Already excludes `.agents/**` and `.serena/**`
   - Tune max_review_comments to reduce volume
   - Research severity filtering options

3. **Copilot Configuration**:
   - Research available configuration options
   - No standard config file found (uses workflow integration)
   - Document limitations

4. **Documentation** - Create `.agents/devops/BOT-CONFIGURATION.md`:
   - What each bot does
   - How configs were tuned
   - How to verify effectiveness

## Session Start Checklist

- [x] Serena initialization (initial_instructions called)
- [x] Read HANDOFF.md
- [x] Read relevant memories: coderabbit-config-strategy, gemini-path-exclusions, pr-review-bot-triage
- [x] Session log created at `.agents/sessions/2025-12-23-session-87-bot-config-noise-reduction.md`

## Work Log

### Phase 1: Research Existing Configurations

**Files Found**:
- `.coderabbit.yaml` - Existing config with markdownlint disabled, path_instructions for agent prompts
- `.gemini/config.yaml` - Existing config with ignore_patterns for `.agents/**` and `.serena/**`
- No Copilot-specific config file (workflow-based integration)

**Memory Context**:
- `coderabbit-config-strategy`: Recommends `profile: chill`, path_instructions with IGNORE, path_filters
- `gemini-path-exclusions`: Already implemented ignore_patterns correctly
- `pr-review-bot-triage`: cursor 100%, Copilot 90%, CodeRabbit ~50%, gemini 0%

### Phase 2: Update Configurations

**CodeRabbit (.coderabbit.yaml)**:

- Set profile to `chill` (reduces nitpicky feedback)
- Added path_filters to exclude:
  - `.agents/sessions/**`
  - `.agents/analysis/**`
  - `.serena/memories/**`
  - `**/*.generated.*`
  - `**/bin/**`, `**/obj/**`
- Reduced supplementary content (collapsed walkthrough, disabled poetry, related issues/PRs)
- Added high-confidence instructions to path_instructions

**Gemini (.gemini/config.yaml)**:

- Raised severity threshold from MEDIUM to HIGH
- Capped max_review_comments at 10 (was unlimited)
- Path exclusions already configured correctly

**Copilot (.github/copilot-code-review.md)**:

- Added Review Quality Guidelines section
- High-confidence instruction (>80% confidence required)
- Explicit focus areas and exclusions
- Conciseness requirement

**Documentation (.agents/devops/BOT-CONFIGURATION.md)**:

- Created comprehensive bot configuration guide
- Documented what each bot does
- Explained tuning rationale
- Verification strategy and metrics
- Future improvements section

### Phase 3: Linting and Commit

- Pre-existing linting errors in `.claude/skills/adr-review/agent-prompts.md` (not my changes)
- Reverted unintended changes to adr-review skill
- My new files are lint-compliant

## Decisions Made

1. **CodeRabbit Profile**: Chose `chill` over `assertive` based on analysis showing 66% noise ratio
2. **Gemini Severity**: Raised to HIGH (from MEDIUM) to focus on critical issues only
3. **Gemini Comment Limit**: Set to 10 to force prioritization (actionability was 24%)
4. **Copilot Configuration**: Instruction-based (no hard limits available)
5. **Path Exclusions**: Excluded all agent artifacts, sessions, memories, generated files

## Session End Checklist

**Completion Criteria**:

- [ ] CodeRabbit configuration updated with path_filters
- [ ] Gemini configuration tuned for reduced noise
- [ ] Copilot limitations documented
- [ ] BOT-CONFIGURATION.md created
- [ ] All markdown files linted
- [ ] Changes committed with conventional commit message
- [ ] Serena memory updated

**Evidence**:

| Requirement | Evidence | Status |
|-------------|----------|--------|
| Session log early | This file created | ✓ |
| Serena initialization | initial_instructions called | ✓ |
| HANDOFF.md read | Content reviewed | ✓ |
| Memories consulted | 3 memories read | ✓ |
| Linting | Command: `npx markdownlint-cli2 --fix "**/*.md"` | Pending |
| Commit | SHA: [pending] | Pending |
| Memory update | Tool: mcp__serena__write_memory | Pending |

## Protocol Compliance

**SESSION-PROTOCOL.md v1.4**:

- [x] Phase 1: Serena initialization (BLOCKING)
- [x] Phase 2: Context retrieval (BLOCKING)
- [x] Phase 3: Session log created (REQUIRED)
- [ ] Session End: Validation PASS (BLOCKING)

---

**Status**: 🟡 IN PROGRESS
