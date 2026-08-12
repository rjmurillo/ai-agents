# Aspire Skill Decision Matrix (TASK-020)

Classifies every Aspire skill at the pinned commit against local skills,
agents, and commands, and records one cited keep/augment/compose/create/reject
decision per source skill. Source content is untrusted external data and was
treated as data, never executed.

## Source and routing

- Repository: `microsoft/aspire`
- Pinned commit: `d1c7add665f7e6582cdaa1b328c44172f0f96339`
- Inventory authority: `.agents/analysis/aspire-skill-source-files.json` (TASK-019)
- Routing authority: SkillForge Phase 0 thresholds (.claude/skills/SkillForge/references/phase0-triage.md)

## Reconciliation

Matrix rows: 23. This equals the TASK-019 normalized skill ID set
(23 IDs), verified by set equality in the generator. Decision counts: reject 18, reuse 5, augment 0, compose 0, create 0.

At most one candidate may be `create`; zero were. One cross-cutting `augment`
outcome (below) extends the existing owner SkillForge. Every Aspire
product-operation skill is rejected (REQ-020 AC6).

## Decision legend

- **reuse**: An existing local skill/agent/command already owns the generic idea; no change.
- **augment**: Extend an existing local owner with a small generic, cited idea.
- **compose**: The idea is covered by composing existing local owners; no change.
- **create**: A new generic skill (allowed at most once, only when no owner exists).
- **reject**: Product-specific Aspire operation or no portable generic idea; do not port.

## Decision matrix

| # | Skill ID | Decision | Local owner | SkillForge route | Product coupling |
|---|---|---|---|---|---|
| 1 | `api-review` | **reject** | review, reviewer-findings, pr-comment-responder | reject | high (.NET/Aspire API guideline enforcement over api/*.cs) |
| 2 | `azdo-internal` | **reject** | pipeline-validator | reuse | high (named Aspire pipeline, internal mirror) |
| 3 | `backport-pr` | **reject** | github | reject | high (Aspire /backport bot, shiproom template) |
| 4 | `ci-test-failures` | **reuse** | github (fix-ci.md), ai-agents-debugging-playbook, session-log-fixer | use_existing | medium (Aspire GH Actions + .trx + failing-test issue conventions) |
| 5 | `cli-channel-debugging` | **reject** | ai-agents-debugging-playbook, ai-agents-empirical-probe-toolkit | reject | high (ASPIRE_CLI_* knobs, install sidecar) |
| 6 | `cli-e2e-testing` | **reject** | ai-agents-validation-and-qa, qa | reject | high (Hex1b tool, Aspire.Cli.EndToEnd.Tests, CellPatternSearcher) |
| 7 | `code-review` | **reuse** | review, code-reviewer (agent), pr-comment-responder, /pr-review | use_existing | low-medium (GitHub PR workflow, generic) |
| 8 | `connection-properties` | **reject** | n/a | reject | high (IResourceWithConnectionString, Aspire resource model) |
| 9 | `create-pr` | **reuse** | github, /push-pr | use_existing | low (generic PR creation, Aspire template) |
| 10 | `dashboard-testing` | **reject** | ai-agents-validation-and-qa | reject | high (Aspire.Dashboard.Tests, bUnit) |
| 11 | `dependency-update` | **reject** | dependency-auditor (agent) | reject | high (NuGet, dotnet-migrate-package pipeline) |
| 12 | `deployment-e2e-testing` | **reject** | ai-agents-validation-and-qa | reject | high (Azure deploy, Aspire deploy E2E) |
| 13 | `deprecate-integration` | **reject** | n/a | reject | high (Aspire integration lifecycle) |
| 14 | `fix-flaky-test` | **reuse** | testing.md MUST 12 (concurrency stress 30x), ai-agents-debugging-playbook, ai-agents-validation-and-qa | use_existing | medium (reproduce-flaky-tests.yml, QuarantineTools, run-test-repeatedly scripts) |
| 15 | `hex1b` | **reject** | ai-agents-validation-and-qa | reject | high (Hex1b is an Aspire-authored tool/binary) |
| 16 | `hosting-integration-authoring` | **reject** | n/a | reject | high (Aspire.Hosting resource model, archetypes) |
| 17 | `issue-investigation` | **reuse** | analyze, context-gather, ai-agents-debugging-playbook, debug (agent), github | compose | medium (routes to Aspire skills, Aspire repro envs) |
| 18 | `pr-testing` | **reject** | pr-test-analyzer (agent), qa, review | use_existing | high (Aspire subsystems + eng/ pipelines test matrix) |
| 19 | `reviewing-aspire-architecture` | **reject** | architect (agent), review | reject | high (15 Aspire dimensions, hosting/Azure/dashboard/CLI folders) |
| 20 | `startup-perf` | **reject** | observability | reject | high (Aspire CLI self-profile, dashboard traces) |
| 21 | `test-management` | **reject** | none (no local quarantine infrastructure) | reject | high (QuarantineTools utility, Aspire quarantine infra) |
| 22 | `update-container-images` | **reject** | windows-image-updater | reject | high (Aspire hosting integration image tags) |
| 23 | `vscode-extension` | **reject** | n/a | reject | high (Aspire VS Code extension codebase) |

## Cited decision rows

### `api-review` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/api-review/SKILL.md`
- Purpose: Review .NET API surface PRs against .NET Framework Design Guidelines and Aspire conventions; attribute findings to the introducing commit via git blame.
- Reusable idea: Attribute a review finding to the commit/author that introduced it.
- Local owner: review, reviewer-findings, pr-comment-responder
- Rationale: Product-specific .NET/Aspire API-guideline enforcement. The one generic idea (blame-attributed findings) is minor and already reachable via git; augmenting would duplicate `review`/`pr-comment-responder` and grow the diff. No augmentation merited.

### `azdo-internal` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/azdo-internal/SKILL.md`
- Purpose: Trigger, monitor, validate the Aspire internal Azure DevOps pipeline (definition 1602 on dnceng/internal).
- Reusable idea: Discover/trigger/monitor an AzDO pipeline for the current branch.
- Local owner: pipeline-validator
- Rationale: Aspire-internal pipeline identity and mirror workflow. Generic AzDO pipeline discovery/trigger/monitor is already owned by `pipeline-validator`; no generic content to port.

### `backport-pr` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/backport-pr/SKILL.md`
- Purpose: Backport a merged PR to a release branch via the /backport bot and fill the shiproom template.
- Reusable idea: Backport a fix to a release branch and record customer-impact/risk/regression.
- Local owner: github
- Rationale: Product-specific bot and shiproom template. No generic owner gap; PR operations owned by the `github` skill.

### `ci-test-failures` - reuse

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/ci-test-failures/SKILL.md`
- Purpose: Diagnose GitHub Actions test failures, extract failed tests from runs, parse .trx, create/update failing-test issues.
- Reusable idea: Extract the specific failed tests from a CI run before debugging; update an existing tracking issue instead of creating a duplicate.
- Local owner: github (fix-ci.md), ai-agents-debugging-playbook, session-log-fixer
- Rationale: CI-failure triage is owned locally by the `github` skill's fix-ci workflow and `ai-agents-debugging-playbook` (reproduce-on-main). The .trx/failing-test-issue specifics are Aspire-coupled. No augmentation merited.

### `cli-channel-debugging` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/cli-channel-debugging/SKILL.md`
- Purpose: Emulate an Aspire CLI build identity via ASPIRE_CLI_* env vars to reproduce channel/version-specific bugs locally.
- Reusable idea: Reproduce a version/channel-specific bug locally before fixing.
- Local owner: ai-agents-debugging-playbook, ai-agents-empirical-probe-toolkit
- Rationale: Entirely Aspire CLI product mechanics. Generic 'reproduce locally before fixing' already owned by the debugging playbook.

### `cli-e2e-testing` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/cli-e2e-testing/SKILL.md`
- Purpose: Author/debug Aspire CLI end-to-end tests using Hex1b terminal automation under tests/Aspire.Cli.EndToEnd.Tests/.
- Reusable idea: End-to-end test evidence: assert on real terminal output, wait for stable prompts, handle interactive prompts.
- Local owner: ai-agents-validation-and-qa, qa
- Rationale: Bound to Aspire's Hex1b harness and CLI test project. Generic 'what counts as QA evidence' is owned by `ai-agents-validation-and-qa`; no portable content.

### `code-review` - reuse

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/code-review/SKILL.md`
- Purpose: Review a GitHub PR for problems only (no nits/praise); ensure the PR branch is local first, then categorize and post findings.
- Reusable idea: Findings-only review discipline; make the PR branch available before reviewing.
- Local owner: review, code-reviewer (agent), pr-comment-responder, /pr-review
- Rationale: Pre-merge, findings-only PR review is already owned by the local `review` skill and `code-reviewer` agent. Adding a second owner would split trigger ownership (pre-mortem R3).

### `connection-properties` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/connection-properties/SKILL.md`
- Purpose: Create/improve Aspire resource Connection Properties in resource and README files.
- Reusable idea: None portable.
- Local owner: n/a
- Rationale: Pure Aspire API/domain guidance. No generic reusable idea.

### `create-pr` - reuse

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/create-pr/SKILL.md`
- Purpose: Create a pull request using the repository PR template.
- Reusable idea: Create a PR using the repo template.
- Local owner: github, /push-pr
- Rationale: PR creation is owned by the local `github` skill and `/push-pr` command.

### `dashboard-testing` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/dashboard-testing/SKILL.md`
- Purpose: Write Aspire Dashboard unit and Blazor/bUnit component tests.
- Reusable idea: None portable.
- Local owner: ai-agents-validation-and-qa
- Rationale: Aspire Dashboard test projects and Blazor/bUnit specifics. No generic content.

### `dependency-update` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/dependency-update/SKILL.md`
- Purpose: Update external NuGet dependencies via nuget.org checks and the dotnet-migrate-package AzDO pipeline.
- Reusable idea: None portable beyond generic dependency auditing.
- Local owner: dependency-auditor (agent)
- Rationale: Aspire NuGet + AzDO pipeline mechanics. Generic dependency auditing owned by `dependency-auditor`.

### `deployment-e2e-testing` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/deployment-e2e-testing/SKILL.md`
- Purpose: Write Aspire deployment end-to-end tests that deploy to Azure.
- Reusable idea: None portable.
- Local owner: ai-agents-validation-and-qa
- Rationale: Aspire+Azure deployment test mechanics. No generic content.

### `deprecate-integration` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/deprecate-integration/SKILL.md`
- Purpose: Soft-deprecate a shipped Aspire hosting integration (Obsolete API, README banner, hide from `aspire add`, final release).
- Reusable idea: None portable.
- Local owner: n/a
- Rationale: Aspire package/integration lifecycle operation. No generic reusable idea.

### `fix-flaky-test` - reuse

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/fix-flaky-test/SKILL.md`
- Purpose: Reproduce and fix flaky/quarantined tests: local reproduction first, then CI reproduce-flaky-tests.yml; investigate->reproduce->fix->verify.
- Reusable idea: Reproduce a flake before claiming a fix; re-run many times after the fix; a single green run is not evidence.
- Local owner: testing.md MUST 12 (concurrency stress 30x), ai-agents-debugging-playbook, ai-agents-validation-and-qa
- Rationale: The generic reproduce-before-fix and re-run-to-confirm discipline is already owned by testing rule MUST 12 (quantified 30x stress) and the debugging playbook's reproduce-on-main rule. Aspire's CI workflow and QuarantineTools are product-specific.

### `hex1b` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/hex1b/SKILL.md`
- Purpose: CLI tool for automating any terminal application (launch in a virtual terminal, capture screen, inject input, record/playback).
- Reusable idea: Terminal automation for TUI/CLI E2E testing.
- Local owner: ai-agents-validation-and-qa
- Rationale: Documents a specific external tool (Hex1b). Not a reusable workflow for this repo; nothing to port.

### `hosting-integration-authoring` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/hosting-integration-authoring/SKILL.md`
- Purpose: Author/review Aspire.Hosting integration APIs; classify archetype then apply per-archetype best practices (30 resource files).
- Reusable idea: None portable.
- Local owner: n/a
- Rationale: Deeply Aspire product-domain (integration archetypes, resource model). No generic content.

### `issue-investigation` - reuse

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/issue-investigation/SKILL.md`
- Purpose: Investigate microsoft/aspire GitHub issues: build a dossier and gather context before reproduction; decide info sufficiency; draft evidence-backed or insufficient-info findings.
- Reusable idea: Context/dossier before reproduction; gate on information sufficiency before investing in a repro environment.
- Local owner: analyze, context-gather, ai-agents-debugging-playbook, debug (agent), github
- Rationale: The generic investigate-before-repro and gather-context-first discipline is already composed by local `context-gather`, `analyze`, `debug`, and the debugging playbook. Aspire routing/repro-env specifics are product-coupled.

### `pr-testing` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/pr-testing/SKILL.md`
- Purpose: Test a microsoft/aspire PR across CLI, hosting, dashboard, component, template, VS Code, and CI-infra changes.
- Reusable idea: Propose PR-specific test scenarios from the diff before testing.
- Local owner: pr-test-analyzer (agent), qa, review
- Rationale: A large Aspire-specific test matrix. Generic 'analyze a PR's diff and propose test scenarios' is owned by the `pr-test-analyzer` agent and `qa`; creating a new skill would split ownership (TASK-020 note: create only when no owner remains).

### `reviewing-aspire-architecture` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/reviewing-aspire-architecture/SKILL.md`
- Purpose: Trigger deep architectural review across 15 Aspire-specific dimensions; folder->dimension routing.
- Reusable idea: None portable (dimensions are Aspire-defined).
- Local owner: architect (agent), review
- Rationale: The 15 review dimensions and folder routing are Aspire-defined. Generic architecture review is owned by the `architect` agent and `review`.

### `startup-perf` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/startup-perf/SKILL.md`
- Purpose: Measure Aspire startup profiling via CLI self-profile capture and dashboard export traces.
- Reusable idea: None portable.
- Local owner: observability
- Rationale: Aspire-specific profiling instrumentation. No generic content.

### `test-management` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/test-management/SKILL.md`
- Purpose: Quarantine or disable flaky/problematic tests using the Aspire QuarantineTools utility.
- Reusable idea: Quarantine-then-track discipline for flaky tests.
- Local owner: none (no local quarantine infrastructure)
- Rationale: Bound to Aspire's QuarantineTools. Per TASK-020 note, reject until local quarantine infrastructure exists; there is none, so there is nothing to augment.

### `update-container-images` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/update-container-images/SKILL.md`
- Purpose: Update Docker image tags used by Aspire hosting integrations via registry queries and LLM version selection.
- Reusable idea: None portable.
- Local owner: windows-image-updater
- Rationale: Aspire hosting image-tag update mechanics. Generic image update owned by `windows-image-updater`.

### `vscode-extension` - reject

- Source: `microsoft/aspire@d1c7add665f7e6582cdaa1b328c44172f0f96339:.agents/skills/vscode-extension/SKILL.md`
- Purpose: Investigate/develop/test/review the Aspire VS Code extension under extension/ (UI, commands, debugger, RPC, DCP, MCP, CLI integration).
- Reusable idea: None portable.
- Local owner: n/a
- Rationale: Entirely the Aspire VS Code extension product. No generic content.

## Single augmentation (cross-cutting)

- Decision: **augment** (new skill created: False)
- Canonical target: `.claude/skills/SkillForge/SKILL.md`
- New reference: `.claude/skills/SkillForge/references/external-skill-source-adaptation.md`
- Generated mirrors: `src/copilot-cli/skills/SkillForge/SKILL.md`, `src/copilot-cli/skills/SkillForge/references/external-skill-source-adaptation.md`
- Eval scenarios: `tests/evals/skills/aspire-skill-review-scenarios.json`

REQ-020 names SkillForge as the owner of the classification model, so the review's recurring lesson (adapt an external skill catalog by requiring an authoritative pinned source, treating source content as untrusted data, preferring an existing local owner, rejecting product-specific operations, and allowing at most one new generic skill) is added to SkillForge Phase 0 as a small generic guardrail rather than a new external-review framework (explicitly excluded). Inspiration is cited to the Aspire catalog: product-specific exemplars (cli-e2e-testing, hex1b, hosting-integration-authoring, vscode-extension) drove the reject rule; existing-owner exemplars (code-review, create-pr, issue-investigation, fix-flaky-test) drove the reuse-over-create rule.

## Untrusted-data handling

Every source skill was read as data. No command, tool call, or scope change
found inside a source skill was executed or obeyed. Product-specific operational
commands were not copied into any local skill.

