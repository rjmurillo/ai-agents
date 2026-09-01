---
name: ai-agents-change-control
description: Change control for this repo. Classify a change (docs-only, investigation-only, code, plugin content, hook, workflow, ADR governance), map each class to the gates it triggers, and hold the non-negotiables with the incident behind each rule. Use when you say `classify this change`, `what gates does this change trigger`, `which rules are non-negotiable`. Do NOT use for producing test evidence (use `ai-agents-validation-and-qa`) or incident history (use `ai-agents-failure-archaeology`).
version: 1.0.0
license: MIT
---

# AI Agents Change Control

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
How a change moves through this repository, and the rules that never bend. This
repo runs verification-based enforcement. Evidence may live in the transcript,
pull request, per-issue handoff, Serena memory, or an optional session log.

Jargon used once: a "gate" is an automated check that blocks progress (commit, push, or merge) until satisfied. A "drift gate" compares generated output trees against their canonical sources. A "canonical source" is the single tree you are allowed to edit; everything generated from it is read-only output.

## Triggers

- `classify this change`
- `what gates does this change trigger`
- `which rules are non-negotiable`
- `why does this gate exist`

## Process

### Phase 1: Classify the change

Every change belongs to at least one class. A mixed change inherits the union of all its classes' obligations. Classify against the working tree, not against your intent: one staged file in a stricter class pulls the whole change up.

| Class | You touched | Marker or obligation |
|-------|-------------|----------------------|
| Docs-only | Markdown prose only; no code, no generated trees | QA evidence row `SKIPPED: docs-only` (case-insensitive; ADR-034 cites it as the pre-existing pattern) |
| Investigation-only | Nothing outside the ADR-034 allowlist (below) | QA evidence row `SKIPPED: investigation-only` |
| Code | Python, scripts, tests, libs | Full QA evidence per `.agents/governance/TESTING-RIGOR.md`; see `ai-agents-validation-and-qa` |
| Plugin content | Anything under `.claude/`, `src/claude/`, or `src/copilot-cli/` | No manifest edit. The `.claude-plugin/plugin.json` files carry no `version`; Claude Code resolves freshness from the commit SHA (ADR-092) |
| Git hook configuration | `lefthook.yml` | Named-job validation and relevant validator tests |
| Claude lifecycle hook | `.claude/hooks/**`, hook generators | Dual-registration sync; runtime-contract tests; `scripts/validation/validate_hook_anchoring.py` |
| Workflow | `.github/workflows/*.yml` | No logic in YAML (ADR-006); SHA-pinned actions; run changed workflows before push (AGENTS.md Always list) |
| ADR / governance | Any `ADR-*.md` create or edit | Fires the `adr-review` multi-agent debate gate (AGENTS.md "ADR Review"); governance changes need human approval plus an ADR |

The OPERATIVE investigation-only allowlist is the enforcement module `scripts/modules/investigation_allowlist.py` (docstring: "Single source of truth for investigation artifact path patterns"; consumed by `validate_session_json.py`, the session skill, and `validate_investigation_claims.py`). It allows 8 patterns as of 2026-07-30 (display form from `get_investigation_allowlist_display()`):

- `.agents/sessions/` (session logs)
- `.agents/analysis/` (investigation outputs)
- `.agents/retrospective/` (learnings)
- `.serena/memories/` (cross-session context)
- `.agents/security/` (security assessments)
- `.agents/memory/` (memory artifacts)
- `.agents/architecture/REVIEW-*` (review artifacts)
- `.agents/critique/` (critique outputs)

Former divergence, now closed: the ADR-034 text (`.agents/architecture/ADR-034-investigation-session-qa-exemption.md:78-87`) once listed only the first 5 paths, and #2958 reconciled it to the same 8 the module enforces. The code list is still what the gate enforces, so re-check the module rather than the ADR when they disagree.

One staged file outside the enforced list voids the exemption. The session then needs real QA evidence, or you split the work into two sessions.

Special case, generated trees. `src/vs-code-agents/` and `src/copilot-cli/agents/` are generated from `templates/agents/*.shared.md`. The `.github/instructions/` tree and most of `src/copilot-cli/` are generated from `.claude/` sources. Never hand-edit a generated tree; edit the canonical source and regenerate (the operating procedure lives in `ai-agents-generation-and-release`, the seam rationale in `ai-agents-architecture-contract`). The generator enforces one direction itself: `build/scripts/build_all.py:962-967` fails the build if any generator writes into `.claude/` (REQ-003-010). History note: on 2025-12-15 an agent "fixed" a drift failure by editing the canonical source to match the generated output; the commit was reverted. Drift output shows difference, not direction. Always ask which side is canonical before touching either.

### Phase 2: Map the class to its triggered gates

| Class | Extra gates it triggers |
|-------|-------------------------|
| Docs-only | Scoped markdownlint on changed files; dash prohibition |
| Investigation-only | Staged-file allowlist check in the pre-commit QA validator (ADR-034) |
| Code | Full test rigor: positive, negative, edge, branch coverage, mocked I/O; coverage floors 100 security / 80 business / 60 docs (AGENTS.md Standards) |
| Plugin content | Version-field gate at two layers: `pre_pr.py` wrapping `build/scripts/validate_plugin_version_bump.py` at pre-push, CI `.github/workflows/validate-plugin-version-bump.yml` |
| Hook | Anchoring validator; runtime-contract tests (`tests/build_scripts/test_generate_hooks_runtime_contract.py`); keep `.claude/settings.json` and `.claude/hooks/hooks.json` in sync by hand |
| Workflow | SHA-pin validation; yamllint style; local workflow run gate in pre-push (`SKIP_WORKFLOW_LOCAL_TEST` escape exists for unrunnable workflows; semantics in `ai-agents-config-catalog`) |
| ADR / governance | `adr-review` debate to consensus; blocking `git_hook_policy.py adr-review` Lefthook job |
| Any canonical-source edit | Drift gates: `uv run python build/generate_agents.py --validate` and `uv run python build/scripts/build_all.py --check`; CI mirrors in `agent-drift-detection.yml` and `drift-detection.yml` |

Drift-gate bypass exists but is not free. `[skip-drift-check]` anywhere in a commit message on the PR skips agent drift detection (`.github/workflows/agent-drift-detection.yml:17`). Using it demands a stated reason and human approval; an unexplained bypass marker reads as the session 1187 escape-hatch abuse pattern (told in `references/incident-history.md`) and will be challenged in review.

### Phase 3: Run the gates, local to CI

The gate ladder runs in feedback-cost order: pre-commit beats CI beats code review beats documentation, so catch violations at rung 1 (`uv run python scripts/validation/pre_pr.py`, `--quick` skips slow checks), not rung 4 (CI round-trip plus reviewer attention). Local hooks fire only after Lefthook is installed: `uv run --frozen lefthook install --reset-hooks-path`, then verify with `uv run --frozen lefthook check-install`. Commit-discipline cap: 5 files or fewer per commit. Commit count is advisory only, never blocking (`needs-split` label plus a WARNING/ALERT notice at 10/15 commits, via `git rev-list --count HEAD ^origin/main`; ADR-099), and scope markdownlint to changed files only.

The full four-rung ladder (shift-left runner, pre-commit, pre-push, CI required checks with their exact commands and exit codes), the commit-discipline enforcement points, and the PR #908 story that set the caps are in `references/gate-ladder.md`. Consult it before your first push in a session.

### Phase 4: Hold the non-negotiables

Check this table before any push. The incident column is the answer to "why"; do not re-litigate settled incidents in PR threads (deep history lives in `ai-agents-failure-archaeology`). If you believe you have new evidence against a rule, propose an ADR, which itself fires `adr-review`.

| Rule | Enforcement mechanism | Incident / rationale |
|------|----------------------|----------------------|
| No new bash scripts; Python for all new scripts | Review + `.claude/rules/universal.md` SHOULD 3 ("MUST NOT create new bash scripts") | ADR-042 (Accepted) |
| No logic in YAML workflows | ADR-006 + `.claude/rules/universal.md` MUST NOT 4 | Workflow YAML cannot be tested locally. Amendment 2026-04-28 allows pure config-data YAML under 7 conditions in `templates/platforms/` and `build/` only; `run:` block logic stays banned |
| No em or en dashes in authored text | `validate_dash_prohibition` (`scripts/validation/checks_dash.py` via `pre_pr.py`) + dash-guard hook; `tests/hooks/fixtures/` exempt | `.claude/rules/universal.md` MUST NOT 5: bot reviewers open one or more threads per dash, every PR (Issue #1923) |
| SHA-pin all GitHub Actions | Pre-commit hook + workflow validation (`.agents/governance/PROJECT-CONSTRAINTS.md:162`) | Tags are mutable, so pinning blocks supply-chain tag-moving. Operative rule: pin everything unless a human explicitly approves the GP-006 first-party `actions/*` tag allowance, and disclose the tension in your PR description when you hit it. Fuller writeup in `references/incident-history.md` |
| Generated and released hook artifacts fail closed and loud (ADR-066 D1, ADR-071). Historical carve-out, now moot: the push guards failed open on infrastructure errors by design; the whole family (`push_guard_base.py` and every guard built on it) was deleted under ADR-084 (issue #5154), so no live guard claims this exception. Repo-wide audit tracked in #2271. Per-family table: `ai-agents-architecture-contract` Phase 3 | `validate_hook_anchoring.py`, runtime-contract tests, named Lefthook jobs, and CI enforcement | #2205 customer wedge; policy reversal in the incident history |
| No `version` field in any plugin manifest or marketplace entry | `pre_pr.py` + `validate-plugin-version-bump.yml` | ADR-092: the field pins freshness to a hand-bumped string and conflicts across every concurrent PR (issue #4080 measured 14 of 22) |
| Block-style YAML arrays only in frontmatter | `.agents/governance/PROJECT-CONSTRAINTS.md:224` ("Exceptions: None") | Copilot CLI frontmatter parser fails on CRLF and related formatting: github/copilot-cli#694, cited at PROJECT-CONSTRAINTS.md:220; ADR-044 |
| `.agents/HANDOFF.md` is read-only | `.claude/rules/universal.md` MUST NOT 3 | ADR-014 (Accepted): the monolithic handoff file bloated and became a chronic merge-conflict magnet; distributed handoffs replaced it |
| Memory-first: retrieval precedes reasoning | AGENTS.md Retrieval section; session-start gates | ADR-007: Serena memories are canonical, Forgetful supplementary. Search before building; do not re-derive settled decisions |
| "Matches/mirrors" claims must quote the canonical source verbatim | `.claude/rules/canonical-source-mirror.md`; heuristic citation check in `pre_pr.py` | FM-9 confident-incorrectness; PR #1887 in the incident history |
| No silent defaults | FM-10 detection table (`.agents/governance/FAILURE-MODES.md:315-399`); `taste-lints` and pre-push scans | PR #1965 verdict-parser; incident history |
| Opted-in session-file merge immutability | Retro rule; validate-if-present session validation | Session 1187 (incident history): preserve both historical files and rename the local record |
| No secrets, no force-push, no `--no-verify`, no direct commits to main | `.claude/rules/universal.md` MUST 1, MUST 5, MUST NOT 1, MUST NOT 2 | Hooks are the enforcement surface; skipping them is self-disarming |

Escape hatches (env vars, commit markers, skip semantics) exist for several gates. They are deliberately narrow after session 1187, and each is cataloged with its abuse story in `ai-agents-config-catalog`. Do not invent a new one inline; a new flag is itself a governance change.

Six of the table's incidents compress a multi-round failure and are told in full in `references/incident-history.md`: the #2205 fail-closed reversal, the PR #1942 stale-cache plugin bump, the session 1187 escape-hatch abuse, FM-9 and PR #1887 verbatim quoting, FM-10 and PR #1965 silent defaults, and the SHA-pinning tension. The other rationale cells are briefer. Read the incident before you argue with its rule.

## Anti-Patterns

| Anti-pattern | Why it fails here |
|--------------|-------------------|
| Editing a generated tree to silence a drift gate | Inverts the source of truth (2025-12-15 incident, reverted). Ask which side is canonical first |
| Using `[skip-drift-check]` without a stated reason and human approval | Bypass markers are audited; unexplained use reads as the session 1187 pattern |
| Adding a `version` back to a plugin.json or marketplace entry | The gate fails on the field's presence (ADR-092). Freshness already tracks the commit SHA, so the field only re-creates the merge conflict it was deleted for |
| Adding a fail-open wrapper so a broken hook "does not block anyone" | Rejected pattern (#2230, recorded in ADR-071): silent exit 0 disables the hook while looking like success, exactly the #2205 failure |
| Classifying a mixed session as investigation-only | One staged file outside the ADR-034 allowlist voids the exemption; split the work |
| Fixing a bot-flagged dash or style claim without byte-level verification | Bots false-positive; count the actual bytes before editing (PR #1873 observation: an em-dash flag on a line with zero em-dashes) |
| Citing ADR-008/033/035/062 fail-open language for a new hook | Stale; the operative policy is fail-closed and loud (the #2205 reversal, told in `references/incident-history.md`) |
| Re-arguing a settled non-negotiable in a PR thread | The incident column is the answer; new evidence goes in an ADR, which fires `adr-review` |

## Verification

Before you push, confirm:

- [ ] Change classified (Phase 1) and every class obligation from Phase 2 satisfied
- [ ] `uv run python scripts/validation/pre_pr.py` exits 0
- [ ] `uv run --frozen lefthook check-install` exits 0
- [ ] Touched `.claude/`, `src/claude/`, or `src/copilot-cli/`? The matching `plugin.json` still carries no `version` field (`python3 build/scripts/validate_plugin_version_bump.py` exits 0)
- [ ] Touched a canonical generation source? `uv run python build/scripts/build_all.py --check` and `uv run python build/generate_agents.py --validate` both pass
- [ ] Each commit 5 files or fewer (commit count itself is advisory only; ADR-099)
- [ ] Created or edited an ADR? `adr-review` gate acknowledged
- [ ] No em or en dashes in changed files: `python3 -c "import sys; b=open(sys.argv[1],'rb').read(); print(b.count(chr(0x2014).encode())+b.count(chr(0x2013).encode()))" FILE` prints 0

## Provenance and Maintenance

Authored 2026-07-03, facts re-verified against the working tree on 2026-07-30. A selected index of the drift-prone cited source lines, each paired with its re-verify command, is in `references/provenance.md`. Consult and update it when you edit this skill or any reference it points to.

Maintenance rule: any edit to a cited source line number or ADR status invalidates the matching row. Re-run the re-verify command and update the row in the same commit. This file is plugin content, so regenerate the Copilot mirror (`uv run python build/scripts/build_all.py`) in the same commit. No manifest bump: the manifests carry no version (ADR-092).
