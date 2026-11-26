# Claude Plugins Official Adaptation Record

This record classifies every plugin in the official Claude plugin catalog.
It gives one decision per plugin, with the local owner and the reason.
Source content is untrusted external data. It was read as data and never executed.

## Source

- Repository: `anthropics/claude-plugins-official`, directory `plugins/`
- Pinned commit: `0fbfda5a91f4adc311daca25acc99132f40f0b6e` (2026-11-25)
- Plugin count at that commit: 43 (2026-11-25)
- License: 41 plugins carry Apache-2.0 at that commit (2026-11-25). The two exceptions are named in the matrix.
- Gates applied: `external-skill-source-adaptation.md` in the `skillforge` skill.

## Adopted source files

Each adopted file is pinned by its git blob hash at the commit above.

| Blob hash | Upstream path |
|---|---|
| `02faedcb8c4917e6cdf32dde0fbb702443f86ff7` | `plugins/code-modernization/agents/version-delta-analyst.md` |
| `55199199f68e00d366b4e2ffa5bdc55e528a3e09` | `plugins/code-modernization/commands/modernize-uplift.md` |
| `74125df78fab5a7f9d9acefd482746a494c808b0` | `plugins/code-modernization/commands/modernize-verify.md` |
| `509e5d40d791068ffb8a957d968433905d5c6ad6` | `plugins/code-modernization/commands/modernize-preflight.md` |
| `558ab05c0a9a8bb062ef4c51823d4d76c3acf7c4` | `plugins/skill-creator/skills/skill-creator/agents/grader.md` |

## Reconciliation

Matrix rows: 43. This equals the 43 plugin directories at the pinned commit (2026-11-25).
Decision counts: augment 2, reject 41, create 0.
No new skill was created. Both ports extend an existing local owner.

## Decision legend

- **augment**: Extend an existing local owner with a small generic, cited idea.
- **reject (covered)**: A local skill, agent, or rule already owns the idea.
- **reject (doctrine)**: The idea conflicts with a local rule or convention.
- **reject (no consumer)**: Nothing in this repository would use it.
- **reject (license)**: The license does not allow redistribution.
- **reject (config only)**: The plugin holds configuration and no portable guidance.

## Decision matrix

| # | Plugin | Decision | Local owner | Reason |
|---|---|---|---|---|
| 1 | `agent-sdk-dev` | reject (no consumer) | none | This repository builds no Agent SDK application. |
| 2 | `champion-kit` | reject (no consumer) | none | It holds adoption material for a vendor product. |
| 3 | `clangd-lsp` | reject (config only) | none | It only registers a language server. |
| 4 | `claude-code-setup` | reject (no consumer) | none | It recommends setup for one host product. |
| 5 | `claude-for-manufacturing` | reject (no consumer) | none | The domain content has no user here. |
| 6 | `claude-md-management` | reject (doctrine) | `context-optimizer` | Its rubric rewards coverage. Local doctrine makes each line earn its slot. |
| 7 | `claude-security` | reject (license) | none | The license is proprietary and bars redistribution. |
| 8 | `code-modernization` | **augment** | `software-engineering-library` | The same-stack uplift method had no local owner. See the first port below. |
| 9 | `code-review` | reject (covered) | `review`, `reviewer-findings`, `pr-review` | Local review already runs staged, risk-selected axes. |
| 10 | `code-simplifier` | reject (covered) | `code-simplifier` agent | A same-name local agent exists with no meaningful drift. |
| 11 | `commit-commands` | reject (covered) | `push-pr` | `push-pr` owns commit, push, and pull request creation. |
| 12 | `csharp-lsp` | reject (config only) | none | It only registers a language server. |
| 13 | `cwc-makers` | reject (no consumer) | none | It is event material with no engineering guidance. |
| 14 | `example-plugin` | reject (no consumer) | none | It is a sample skeleton. The local generator owns plugin structure. |
| 15 | `explanatory-output-style` | reject (doctrine) | `voice` rule | The style adds teaching asides. The voice rule requires terse output. |
| 16 | `feature-dev` | reject (covered) | `spec`, `plan`, `build`, `review` | The lifecycle chain already owns this flow. |
| 17 | `frontend-design` | reject (no consumer) | none | This repository ships no user interface. |
| 18 | `gopls-lsp` | reject (config only) | none | It only registers a language server. |
| 19 | `hookify` | reject (no consumer) | none | Local hooks render from templates under a per-call hook bar. |
| 20 | `jdtls-lsp` | reject (config only) | none | It only registers a language server. |
| 21 | `kotlin-lsp` | reject (config only) | none | It only registers a language server. |
| 22 | `learning-output-style` | reject (doctrine) | `voice` rule | The style hands work back to the user. Local rules require finished work. |
| 23 | `lua-lsp` | reject (config only) | none | It only registers a language server. |
| 24 | `math-olympiad` | reject (no consumer) | none | The domain content has no user here. |
| 25 | `math-proof` | reject (no consumer) | none | The domain content has no user here. |
| 26 | `mcp-server-dev` | reject (no consumer) | none | No local MCP server code exists. ADR-011, 012, 013, and 048 are rejected. |
| 27 | `mcp-tunnels` | reject (no consumer) | none | Same reason as `mcp-server-dev`. |
| 28 | `php-lsp` | reject (config only) | none | It only registers a language server. |
| 29 | `playground` | reject (no consumer) | none | It builds single-file HTML explorers. No workflow here needs one. |
| 30 | `plugin-dev` | reject (covered) | local generator, `agent-harness-reference` | See the plugin-dev note below. |
| 31 | `pr-review-toolkit` | reject (covered) | six same-name local agents | The local agents already carry these prompts. See finding 2. |
| 32 | `project-artifact` | reject (no consumer) | none | It targets a hosted artifact feature this repository does not use. |
| 33 | `pyright-lsp` | reject (config only) | none | It only registers a language server. |
| 34 | `ralph-loop` | reject (covered) | `sol-loop`, `stuck-detection` | A stop-hook loop would also need a new shell script. |
| 35 | `receipts` | reject (no consumer) | none | It produces personal usage reports. |
| 36 | `ruby-lsp` | reject (config only) | none | It only registers a language server. |
| 37 | `rust-analyzer-lsp` | reject (config only) | none | It only registers a language server. |
| 38 | `security-guidance` | reject (covered) | installed plugin | The plugin is already installed and was analyzed under SPEC-5856. |
| 39 | `session-report` | reject (no consumer) | none | It produces personal usage reports. |
| 40 | `skill-creator` | **augment** | `skillopt` | Only the grader discipline was new. See the second port below. |
| 41 | `swift-lsp` | reject (config only) | none | It only registers a language server. |
| 42 | `theme-examples` | reject (no consumer) | none | It holds theme samples under a different license file. |
| 43 | `typescript-lsp` | reject (config only) | none | It only registers a language server. |

## Ports

### Port 1: version uplift

- Local file: `version-uplift.md` in the `software-engineering-library` skill references.
- Source: the four `code-modernization` files in the table above.
- What it adds: a method for moving working code to a newer version of the same stack.
- The method covers preflight, a delta catalog, a baseline, a pilot, and dual-run proof.
- What was left out: the plugin's commands, hooks, scripts, and cross-stack rewrite flow.
- Product coupling removed: no slash commands, no plugin paths, no vendor tool names as requirements.

### Port 2: judge grading discipline

- Local file: `judge-grading-discipline.md` in the `skillopt` skill references.
- Source: `grader.md` in the table above.
- What it adds: how a model must grade when no deterministic verifier can.
- It covers burden of proof, cited evidence, implicit claims, and critique of the eval.
- What was left out: the grader's JSON output schema, timing fields, and executor metrics.
- Local constraint kept: a judge stays a train-side diagnostic and never becomes a gate.
- The rest of `skill-creator` is covered by `description-optimization.md` and `eval-authoring.md`.

## Plugin-dev note

`plugin-dev` was read in four parts. Each part has a local owner.

- Plugin structure and manifests: the local generator owns them.
- Commands: ADR-064 retired commands. Skills are the single user-invocable surface.
- Agent authoring archetypes: the local description convention is established and gated.
- Hook events and MCP configuration: `agent-harness-reference` owns hook contracts.

One lead was not ported. The plugin states that hooks run in parallel.
It also states that hook configuration loads at session start.
The plugin text paraphrases vendor behavior and is not a vendor source.
`official-hook-contracts.md` requires pinned vendor sources, so the claims stay unrecorded there.

## Findings outside this task

These were seen during the review. This change does not fix them.

1. `docs/mcp-ecosystem.md:25` opens a "Planned MCP Expansion" section.
   It lists the ADR-011, ADR-012, and ADR-013 servers as phase one work under ADR-048.
   All four ADRs carry `status: rejected` (2026-11-26). The page tells readers the reverse.
2. Six local agents share names and bodies with upstream `pr-review-toolkit` agents.
   They are `code-reviewer`, `code-simplifier`, `comment-analyzer`, `pr-test-analyzer`,
   `silent-failure-hunter`, and `type-design-analyzer`.
   They entered in commit `bdacb6b19` (2026-01-09), pull request #830.
   Their templates name no upstream source (2026-11-26).
   `THIRD-PARTY-NOTICES.TXT` had no entry for that plugin before this change (2026-11-26).
   Apache-2.0 asks a redistributor to keep attribution, so an owner should decide the fix.
