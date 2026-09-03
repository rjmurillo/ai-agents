# Model Assignment Strategy: Research and Plan Basis

**Status**: Research, not yet a decision
**Date**: 2026-04-26
**Author**: Richard Murillo
**Audience**: architect, implementer, future ADR author
**Triggers**: Recurring workflow breakage when a referenced model is deprecated, retired, paywalled, or requires credits the operator does not hold.

## Problem

Hardcoded model identifiers across agents, skills, commands, and documentation create silent breakage when Anthropic rotates model versions, retires SKUs, or moves a model behind a paid tier. Symptoms observed:

1. Workflow fails because a pinned model ID returns 404 or "model not found".
2. Operator hits "credits required" because their plan does not include the pinned model.
3. Commands silently degrade because the resolver picks an unintended model.
4. Documentation references model versions that no longer exist, misleading future authors.

## Repository Audit (evidence)

Direct grep audit run on `main` at HEAD `49f05187`. **In-scope surfaces**: `.claude/` (excluding `.claude/worktrees/` ephemeral copies) and `templates/`. `.agents/` is historical archive, out of scope.

### Two distinct generation flows

`templates/AGENTS.md` and `ADR-036-two-source-agent-template-architecture.md` define two separate flows:

```
Flow A (templated, multi-platform):
  templates/agents/*.shared.md  ─►  build/Generate-Agents.ps1  ─►  src/vs-code-agents/*.agent.md
                                    ▲                              src/copilot-cli/*.agent.md
                                    │
                                    └── templates/platforms/*.yaml (per-platform model_tiers)

Flow B (hand-maintained, Claude only):
  src/claude/*.md  ─►  skill-installer (Python TUI)  ─►  .claude/agents/*.md
                                                          .claude/skills/*/SKILL.md
```

Flow A already has the indirection we want. Flow B does not.

### Flow A: templates (healthy by design)

| Surface | Count | Style | Notes |
|---|---|---|---|
| `templates/agents/*.shared.md` | 23 | no `model:` frontmatter; uses `tier: expert\|standard\|...` | Source of truth. Tier-based, platform-neutral. |
| `templates/platforms/copilot-cli.yaml` | 1 | period style: `claude-opus-4.6`, `claude-sonnet-4.6`, `claude-haiku-4.5` | Comment: "Copilot CLI model: use CLI model identifiers (not VS Code display names)". Likely correct for that platform. |
| `templates/platforms/vscode.yaml` | 1 | per `model_tiers` mapping | VS Code / GitHub Copilot Chat convention. |
| `templates/platforms/visual-studio.yaml` | 1 | reuses vscode mappings (shared output dir) | VS 2022 17.14+ / VS 2026 Copilot agent mode. |
| `build/Generate-Agents.ps1` | 1 | resolves `tier` to platform-specific model ID at build time | The translator. |

The pattern is correct: shared `tier:` declarations in `*.shared.md`, per-platform model ID maps in `platforms/*.yaml`, build-time fanout. Each platform is allowed its own ID convention (Copilot CLI period, Anthropic API hyphen, VS Code display names) because translation lives in the build.

**Open verifications** (low risk, cheap to check):
- Confirm Copilot CLI accepts `claude-opus-4.6` (period). The comment claims yes; verify against current Copilot CLI release notes.
- Confirm VS Code platform IDs in `vscode.yaml` and `visual-studio.yaml` resolve under current Copilot Chat.
- Add a build-time validator: for each platform, fetch the official model list and assert every mapped ID resolves.

### Deferred unification (issue #1774)

GitHub issue **#1774 "arch: JTBD-based plugin architecture with per-harness emission"** (parent epic #1072 v0.4.0) is the standing decision to unify the two flows. Status: open, deferred. Excerpt:

> "The repo already has the right architecture for agents: `templates/agents/*.shared.md` -> `src/{claude,copilot-cli,vs-code-agents}/`. JTBD plugins extend this to commands, rules, and hooks."

Proposed shared sources per #1774:

```
templates/
├── agents/*.shared.md      <- EXISTING
├── commands/*.shared.md    <- NEW (shared command/prompt source)
├── rules/*.shared.md       <- NEW (shared rule/instruction source)
├── hooks/*.py              <- NEW (shared hook source)
└── platforms/*.yaml        <- per-platform model + path config
```

Per-harness emission targets: `src/claude/{agents,skills,commands,rules}`, `src/copilot-cli/{agents,prompts,hooks}`, `src/vs-code-agents/`, plus `.github/{prompts,instructions,hooks}/`. Related issues: **#1769** (extract monolith `.agents/*.md` into scoped rules; ~4,200 always-loaded lines), **#1620** (Stage 2 Copilot Infrastructure, refining), proposed **ADR-052** (Claude-First template strategy).

**Implication for model strategy**: Flow B's gap (no indirection layer) is exactly what #1774 closes. The model assignment work is a forcing function for the unification, not parallel to it. Recommend: scope the model strategy work as a deliverable inside #1774, or as an immediate predecessor that proves the platform yaml pattern for one new artifact type (commands or rules) before the full unification lands.

### Flow B: Claude (the actual gap)

| Surface | Count | Style | Notes |
|---|---|---|---|
| `.claude/agents/*.md` with `model:` frontmatter | 23 of 25 | alias only (`opus`, `sonnet`, `haiku`) | Healthy. No versioned IDs. |
| `.claude/` files (excluding worktrees) with versioned IDs | 72 files | hyphen style mostly clean | The actual migration target. |
| Most-referenced versioned IDs | `claude-sonnet-4-6`, `claude-opus-4-6`, `claude-haiku-4-5`, `claude-sonnet-4-20250514` | hyphen | The May-2025 snapshot is stale; check freshness. |
| `settings.json` model config | 0 | n/a | No project-level default. |
| Existing model-related ADRs | 3 | n/a | ADR-002, ADR-021, ADR-036, ADR-039. |
| Model registry, alias map, or fallback table for Flow B | 0 | n/a | No indirection layer. |

Flow B has no equivalent of `templates/platforms/*.yaml`. Versioned IDs are inlined in 72 skills and supporting files. There is no build step that could rewrite them at install time.

Note on earlier inflated counts: a first sweep across `.claude/`, `.agents/`, and `.claude/worktrees/` returned 280+ occurrences. Worktrees are ephemeral; `.agents/analysis/` is historical. Excluding both, real Flow B surface is ~72 files. Flow A surface is 3 platform yamls plus the build script.

Agent tier distribution (intentional):
- **opus** (7): architect, high-level-advisor, implementer, independent-thinker, orchestrator, roadmap, security
- **sonnet** (14): analyst, backlog-generator, critic, devops, explainer, issue-feature-review, memory, milestone-planner, qa, quality-auditor, retrospective, skillbook, spec-generator, task-decomposer
- **haiku** (1): context-retrieval
- **dynamic** (1, in `AGENTS.md`): `sonnet|opus|haiku`

The agent layer is not the bug. The bug is in the long tail: skills, documentation, examples, and rules that pin specific versions like `claude-opus-4.5` or `claude-sonnet-4-20250514`. When Anthropic retires those snapshots, every reference rots. The `4.5` vs `4-5` mismatch is its own defect: one of the two strings has never been a valid model ID.

## Existing ADRs in Scope

Three ADRs already cover this problem. They are the starting point, not a greenfield.

- `ADR-002-agent-model-selection-optimization.md`
- `ADR-021-model-routing-strategy.md`
- `ADR-039-agent-model-cost-optimization.md`

Action item before any new ADR: re-read these three and decide whether the right move is **amend, supersede, or implement**.

## External Best Practices (2025-2026)

### 1. Anthropic's own guidance: aliases vs pinned IDs

Anthropic ships two surfaces deliberately ([Models overview](https://platform.claude.com/docs/en/about-claude/models/overview), [Model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)):

- **Aliases** (`opus`, `sonnet`, `haiku`): resolve to the current recommended version. Auto-upgrade. Used when you want to track "the best of this tier."
- **Versioned IDs** (`claude-opus-4-7`, `claude-sonnet-4-6`): pinned snapshots. Stable until retirement. Used when you need bit-stable behavior for evals or reproducibility.

Lifecycle: Active to Legacy to Deprecated to Retired. Minimum 60-day notice; weights preserved indefinitely. Recent retirements: Sonnet 3.5 (retired 2026-01-05), Sonnet 4 / Opus 4 (retiring 2026-06-15). Citation: [Anthropic deprecation commitments](https://www.anthropic.com/research/deprecation-commitments).

**Implication**: alias-by-default, pin only when reproducibility is required. The repo already does this for agents. The gap is in skills and docs.

### 2. Claude Code subagent model resolution

Per [Create custom subagents](https://code.claude.com/docs/en/sub-agents) and [Model configuration](https://code.claude.com/docs/en/model-config):

- `model:` accepts: alias (`opus|sonnet|haiku`), full ID (`claude-opus-4-7`), or `inherit`.
- Default when omitted: `inherit`.
- `CLAUDE_CODE_SUBAGENT_MODEL` env var overrides **only** subagents whose model is `inherit`. Explicit `model:` declarations win.
- Caveat: built-in subagents (Explore, Plan) cannot be model-overridden via env; you must shadow them with a custom agent file. See [issue #25546](https://github.com/anthropics/claude-code/issues/25546).

**Implication**: agent-level alias declaration is the right vehicle; env-level override is the operator escape hatch.

### 3. Three-tier routing (Haiku / Sonnet / Opus)

Industry consensus for 2026 ([Choosing the right Claude model](https://claude.com/resources/tutorials/choosing-the-right-claude-model), [Augment routing guide](https://www.augmentcode.com/guides/ai-model-routing-guide)):

| Tier | Share of traffic | Use cases |
|---|---|---|
| Haiku | 5-10% | classification, routing, extraction, summarization, lookups |
| Sonnet | 80-85% | coding, writing, multi-step reasoning, research, "daily driver" |
| Opus | 5-15% | graduate-level reasoning, novel problem solving, long-horizon agentic loops |

The OpenAI Practical Guide rule, captured in `~/Documents/Mobile/wiki/concepts/AI Strategy/`: **start with the most capable model, establish evals, then swap down for sub-tasks where the eval still passes**. Top-down beats bottom-up because you avoid debugging "did I pick the wrong model" mid-flight.

The Adviser Model Pattern (also in the wiki) is a refinement: a cheap executor (Haiku/Sonnet) calls an expensive adviser (Opus) only on the steps that need it. Reported result on SWE-bench: +2.7 pp accuracy with -12% cost vs all-Opus.

### 4. Resilience patterns for vendor churn

From production gateway docs ([LiteLLM routing](https://docs.litellm.ai/docs/routing-load-balancing), [Maxim retries/fallbacks/circuit breakers](https://www.getmaxim.ai/articles/retries-fallbacks-and-circuit-breakers-in-llm-apps-a-production-guide/), [LogRocket LLM routing](https://blog.logrocket.com/llm-routing-right-model-for-requests/)):

- **Capability tags over model IDs**: declare the *requirement* (`reasoning-heavy`, `cheap-bulk`, `vision`) and let a router resolve. The agent doesn't know or care that "reasoning-heavy" is Opus 4.7 today.
- **Fallback chains**: ordered list of acceptable substitutes. Primary fails (404, rate limit, paywall, timeout) -> try next. Bifrost example: Claude Sonnet -> GPT-4o -> Gemini 2.0.
- **Circuit breakers**: after N consecutive failures, mark a model unhealthy for a cooldown window. Avoids retry storms.
- **Centralized model registry**: one file declares logical names, real IDs, capabilities, fallbacks, deprecation date. Every caller dereferences through it.

Constraint: Claude Code is a single-vendor harness. We do not get cross-vendor fallback for free. We can still use the registry pattern to control which Anthropic alias each role resolves to.

### 5. Anti-patterns observed in the wild

- **Hardcoded versioned IDs in templates and docs**: model retires, every example breaks. ([LiteLLM issue #20521](https://github.com/BerriAI/litellm/issues/20521): 39 stale OpenRouter model entries with no deprecation marker.)
- **Stringly-typed model fields** with no enum: typos like `claude-opus-4.5` (period, invalid) vs `claude-opus-4-5` (hyphen, valid) ship to production.
- **Per-agent ad-hoc model picking**: developers copy-paste a model from a recent example. The example ages. New agents inherit dead IDs.
- **Pinning when an alias would do**: turns every Anthropic deprecation cycle into a forced migration project.
- **Aliasing when pinning was needed**: silently changes eval baselines under your feet. ([Anthropic April 23 postmortem](https://www.anthropic.com/engineering/april-23-postmortem) is a recent example of model behavior shifts that broke users.)

### 6. From the wiki: AI Subscription Pricing Collapse

`~/Documents/Mobile/wiki/concepts/AI Subscription Pricing Collapse` flags a structural risk we should design around: providers are migrating from flat-rate subscriptions to per-token billing, and gating frontier models behind credit balances. A workflow that hardcodes "use Opus" without a degrade path will break for any operator without Max-tier credits. Pair this with the **AI Accessibility Gap** entry: model availability is no longer uniform across regions or account tiers.

**Implication**: every agent that demands Opus should declare a "degraded but acceptable" Sonnet path, or document that the workflow is Opus-only and will fail without it. Silent failure is the worst outcome.

## Synthesis: Seven Principles for This Repo

These principles assume #1774 lands. If #1774 stays deferred, principle 1 still applies but Flow B has no place to put the indirection except inside `src/claude/` source files (alias-only) and `.claude/` install-time rewrites.

1. **Translation belongs to the build.** Authors write platform-neutral references (tier or capability tag). The build system resolves to platform-specific model IDs. Flow A already does this via `templates/platforms/*.yaml` + `build/Generate-Agents.ps1`. Flow B (Claude) needs the same separation, either by adding a build step or by making `.claude/skills/` author against aliases instead of versioned IDs.

2. **Alias-by-default, pin-by-exception.** Source files (templates and Claude skills) declare aliases (`opus`/`sonnet`/`haiku`) or capability tags. Pin a versioned ID only when an eval baseline requires bit-stable behavior. When pinning, document the eval, the platform, and the upgrade trigger.

3. **Per-platform model conventions are real and allowed.** Copilot CLI uses one ID style, Anthropic API another, VS Code Copilot Chat another. Do not force a single ID convention across platforms. Encode each in its platform yaml; let the build choose.

4. **One canonical tier-to-ID map per platform.** Each platform yaml is the registry for that platform: tier (or capability) -> current resolved ID -> fallback chain -> deprecation date. No skill or agent file should know the resolved ID directly.

5. **Tier routing matches the 2026 consensus.** Haiku for routing/extraction (5-10% of traffic), Sonnet daily driver (80-85%), Opus reserved for hard reasoning, governance, security, architecture (5-15%). Existing `.claude/agents/` distribution (7 opus, 14 sonnet, 1 haiku) approximates this; record it as policy.

6. **Degradation contracts.** Every Opus-tier agent declares a Sonnet fallback and the expected quality loss. Every Sonnet-tier agent declares whether Haiku is acceptable. If neither is acceptable, the agent says so and fails loudly with a useful message when the preferred tier is unavailable.

7. **No raw versioned IDs in source files.** Lint rule: any string matching `claude-(opus|sonnet|haiku)-[0-9]` in `templates/agents/`, `src/claude/`, `.claude/skills/`, `.claude/commands/`, `.claude/rules/`, or repo markdown documentation must be either inside a platform yaml, inside a registry entry, or in a code block tagged `do-not-update`. Generated outputs in `src/vs-code-agents/` and `src/copilot-cli/` are exempt because the build owns them.

## Open Questions for the Plan

- **Q1**: Do ADR-002 / ADR-021 / ADR-036 / ADR-039 already mandate this and are simply not enforced? Or do they conflict with the principles above? Read first, write later.
- **Q2**: Should Flow B (Claude) gain a build step that rewrites tier references to current versioned IDs at install time, or should `.claude/skills/` simply author against aliases (`opus`/`sonnet`/`haiku`) and rely on Claude Code's native alias resolution?
- **Q3**: Where does the `CLAUDE_CODE_SUBAGENT_MODEL` env override fit? Document it as the operator escape hatch for cost-control without editing agent files. Useful only on Flow B.
- **Q4**: For each platform yaml, is the current ID style (period for Copilot CLI, hyphen for VS Code, etc.) actually correct? Stand up a build-time validator that fetches each platform's model list and asserts.
- **Q5**: How do we handle the `claude-sonnet-4-20250514` legacy snapshot that still appears in Flow B sources? Eval baseline, copy-paste rot, or stale doc? Triage before global replace.
- **Q6**: Skills are content-as-code. If a skill references `claude-opus-4-7` as an example string in prose, is that a violation or a documentation choice? Define the rule precisely so the lint is unambiguous (e.g., allowed inside fenced code blocks tagged `do-not-update`, banned everywhere else).
- **Q7**: Should the build emit a deprecation warning if a platform yaml maps a tier to a model whose retirement date is within 60 days? Anthropic gives 60-day notice; we should react before the email.

## Proposed Plan Outline (for follow-up)

This research is the input. The plan is the next artifact. Sequence assumes #1774 unification proceeds; model strategy is a load-bearing slice of it.

Suggested skeleton:

1. **Read** ADR-002, ADR-021, ADR-036, ADR-039, proposed ADR-052. Read issues #1774, #1769, #1620. Decide for each ADR: amend, supersede, or implement. Comment on #1774 linking this research and proposing the model strategy as a v0.4.0 deliverable.
2. **Inventory** the 72 Flow B files with versioned IDs. Tag each: docs / example / eval-baseline / load-bearing. Record the legacy `claude-sonnet-4-20250514` callsites separately.
3. **Verify** Flow A platform yamls against current platform docs:
   - Copilot CLI: confirm `claude-opus-4.6` (period) is the live ID.
   - VS Code / Visual Studio: confirm `vscode.yaml` mappings.
   - Add a build-time check that fetches each platform's model list and asserts.
4. **Extend `templates/platforms/` with a Claude target** as the unification beachhead (a slice of #1774). Add `templates/platforms/claude.yaml` with:
   - `model_tiers`: opus -> alias `opus`, sonnet -> `sonnet`, haiku -> `haiku` (alias by default), or pinned IDs when an eval requires it.
   - `outputDir: src/claude` and the file extensions Claude consumes.
   - Fallback chain per tier (opus -> sonnet on unavailable; sonnet -> haiku where degradation contract permits).
   This proves the pattern for Claude before #1774's full commands/rules/hooks expansion.
5. **Decide Flow B authoring rule** (Q2):
   - Option A: `src/claude/` source files use aliases (`opus`/`sonnet`/`haiku`) only; trust Claude Code's native alias resolution. No build step needed.
   - Option B: `src/claude/` source files use tier names; `Generate-Agents.ps1` (extended) rewrites to versioned IDs at install via `claude.yaml`. Parallels Flow A. More plumbing, but enables pin-for-eval.
   Pick based on the proportion of eval-baseline tags from step 2.
6. **Lint** new versioned IDs in `templates/{agents,commands,rules,hooks}/`, `src/claude/`, `.claude/skills/`, `.claude/commands/`, `.claude/rules/`. Block PRs that introduce them. Allowlist fenced code blocks tagged `do-not-update` and the `templates/platforms/*.yaml` registry files.
7. **Migrate** the 72 Flow B occurrences in batches by tag, lowest-risk first (docs/examples) before highest-risk (eval baselines).
8. **Document** the operator escape hatch: `CLAUDE_CODE_SUBAGENT_MODEL` for cost control on Flow B without forking agents.
9. **Author or update an ADR** capturing the seven principles. Likely a successor to ADR-021 (model-routing-strategy) that incorporates per-platform yaml registries and the unification target. Cross-link ADR-036 and ADR-052.
10. **Test** by simulating a deprecation: pick an alias, force-resolve to a retired ID in a fixture, verify every agent, skill, and command either succeeds via fallback or fails with a useful error.

### Sequencing notes

- Flow A migration is small (3 yamls + build script). Do it first to prove the model-list validator.
- Step 4 (claude.yaml) is the smallest possible slice of #1774. If it ships clean, it de-risks the broader unification. If it surfaces architectural problems, surface them on #1774 before commands/rules/hooks expand.
- Flow B inventory (step 2) must complete before step 5. The Option A vs Option B decision depends on how many of the 72 occurrences are eval baselines that require pinning.
- Steps 6 (lint) and 7 (migrate) interlock: turn lint on as warn-only first, migrate to clean, then flip lint to error-only.
- Issues #1769 (monolith extraction) and #1620 (Copilot infra) are adjacent dependencies. Do not block this work on them; coordinate label and milestone with whoever owns them.

## Sources

- [Anthropic: Model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)
- [Anthropic: Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Anthropic: Deprecation commitments](https://www.anthropic.com/research/deprecation-commitments)
- [Anthropic: April 23 postmortem (Claude Code quality)](https://www.anthropic.com/engineering/april-23-postmortem)
- [Claude Code: Create custom subagents](https://code.claude.com/docs/en/sub-agents)
- [Claude Code: Model configuration](https://code.claude.com/docs/en/model-config)
- [GitHub issue #25546: configuring model for built-in agents](https://github.com/anthropics/claude-code/issues/25546)
- [Anthropic: Choosing the right Claude model](https://claude.com/resources/tutorials/choosing-the-right-claude-model)
- [Augment: AI model routing guide 2026](https://www.augmentcode.com/guides/ai-model-routing-guide)
- [LiteLLM: Routing & Load Balancing](https://docs.litellm.ai/docs/routing-load-balancing)
- [LiteLLM issue #20521: stale OpenRouter model entries](https://github.com/BerriAI/litellm/issues/20521)
- [Maxim: Retries, fallbacks, circuit breakers in LLM apps](https://www.getmaxim.ai/articles/retries-fallbacks-and-circuit-breakers-in-llm-apps-a-production-guide/)
- [LogRocket: LLM routing in production](https://blog.logrocket.com/llm-routing-right-model-for-requests/)
- Local: `~/Documents/Mobile/wiki/concepts/AI Strategy/Adviser Model Pattern`
- Local: `~/Documents/Mobile/wiki/concepts/AI Strategy/The Bitter Lesson of Building with LLMs`
- Local: `~/Documents/Mobile/wiki/concepts/AI Subscription Pricing Collapse`
- Local: `~/Documents/Mobile/wiki/concepts/AI Accessibility Gap`
- Local: `.agents/architecture/ADR-002-agent-model-selection-optimization.md`
- Local: `.agents/architecture/ADR-021-model-routing-strategy.md`
- Local: `.agents/architecture/ADR-036-two-source-agent-template-architecture.md`
- Local: `.agents/architecture/ADR-039-agent-model-cost-optimization.md`
- Local: `templates/AGENTS.md` (Flow A vs Flow B description)
- Local: `templates/README.md` (template generation system)
- Local: `templates/platforms/copilot-cli.yaml`
- Local: `templates/platforms/vscode.yaml`
- Local: `templates/platforms/visual-studio.yaml`
- Local: `build/Generate-Agents.ps1`
- GitHub issue [#1774: arch JTBD-based plugin architecture with per-harness emission](https://github.com/rjmurillo/ai-agents/issues/1774) (parent epic [#1072 v0.4.0](https://github.com/rjmurillo/ai-agents/issues/1072))
- GitHub issue [#1769: refactor extract monolith .agents/*.md into scoped rules](https://github.com/rjmurillo/ai-agents/issues/1769)
- GitHub issue [#1620: Stage 2 Copilot Infrastructure](https://github.com/rjmurillo/ai-agents/issues/1620)
- Closed reference: GitHub issue #124 (dual template system)
- Proposed: ADR-052 (Claude-First template strategy)
