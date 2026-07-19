---
name: ai-agents-change-control
description: Change control for this repo. Classify a change (docs-only, investigation-only, code, plugin content, hook, workflow, ADR governance), map each class to the gates it triggers, and hold the non-negotiables with the incident behind each rule. Use when you say `classify this change`, `what gates does this change trigger`, `which rules are non-negotiable`. Do NOT use for producing test evidence (use `ai-agents-validation-and-qa`) or incident history (use `ai-agents-failure-archaeology`).
version: 1.0.0
license: MIT
---

# AI Agents Change Control

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
How a change moves through this repository, and the rules that never bend. This repo runs verification-based enforcement, not trust-based. The protocol states it directly: "Labels like 'MANDATORY' or 'NON-NEGOTIABLE' are insufficient. Each requirement MUST have a verification mechanism" (`.agents/SESSION-PROTOCOL.md:36`). Every rule below therefore names two things: the gate that enforces it, and the incident that created it. If you are tempted to argue with a rule, read its incident first.

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
| Plugin content | Anything under `.claude/`, `src/claude/`, or `src/copilot-cli/` | Strictly greater semver bump of that tree's `.claude-plugin/plugin.json` |
| Git hook configuration | `lefthook.yml` | Named-job validation and relevant validator tests |
| Claude lifecycle hook | `.claude/hooks/**`, hook generators | Dual-registration sync; runtime-contract tests; `scripts/validation/validate_hook_anchoring.py` |
| Workflow | `.github/workflows/*.yml` | No logic in YAML (ADR-006); SHA-pinned actions; run changed workflows before push (AGENTS.md Always list) |
| ADR / governance | Any `ADR-*.md` or `SESSION-PROTOCOL.md` create or edit | Fires the `adr-review` multi-agent debate gate (AGENTS.md "ADR Review"); governance changes need human approval plus an ADR |

The OPERATIVE investigation-only allowlist is the enforcement module `scripts/modules/investigation_allowlist.py` (docstring: "Single source of truth for investigation artifact path patterns"; consumed by `validate_session_json.py`, the session skill, and `validate_investigation_claims.py`). It allows 9 patterns (display form from `get_investigation_allowlist_display()`):

- `.agents/sessions/` (session logs)
- `.agents/analysis/` (investigation outputs)
- `.agents/retrospective/` (learnings)
- `.serena/memories/` (cross-session context)
- `.agents/security/` (security assessments)
- `.agents/memory/` (memory artifacts)
- `.agents/architecture/REVIEW-*` (review artifacts)
- `.agents/critique/` (critique outputs)
- `.agents/memory/episodes/` (listed separately in the module; subsumed by `.agents/memory/`)

Known divergence, surfaced here, not resolved: the ADR-034 text (`.agents/architecture/ADR-034-investigation-session-qa-exemption.md:79-83`) lists only the first 5 paths, so the code has drifted wider than the ADR. Reconciling that requires an ADR-034 amendment; until one lands, the code list is what the gate enforces.

One staged file outside the enforced list voids the exemption. The session then needs real QA evidence, or you split the work into two sessions.

Special case, generated trees. `src/vs-code-agents/` and `src/copilot-cli/agents/` are generated from `templates/agents/*.shared.md`. The `.github/instructions/` tree and most of `src/copilot-cli/` are generated from `.claude/` sources. Never hand-edit a generated tree; edit the canonical source and regenerate (the operating procedure lives in `ai-agents-generation-and-release`, the seam rationale in `ai-agents-architecture-contract`). The generator enforces one direction itself: `build/scripts/build_all.py:962-967` fails the build if any generator writes into `.claude/` (REQ-003-010). History note: on 2025-12-15 an agent "fixed" a drift failure by editing the canonical source to match the generated output; the commit was reverted. Drift output shows difference, not direction. Always ask which side is canonical before touching either.

### Phase 2: Map the class to its triggered gates

| Class | Extra gates it triggers |
|-------|-------------------------|
| Docs-only | Scoped markdownlint on changed files; dash prohibition; session log still required |
| Investigation-only | Staged-file allowlist check in the pre-commit QA validator (ADR-034) |
| Code | Full test rigor: positive, negative, edge, branch coverage, mocked I/O; coverage floors 100 security / 80 business / 60 docs (AGENTS.md Standards) |
| Plugin content | Version-bump gate at three layers: PreToolUse guard `.claude/hooks/PreToolUse/invoke_plugin_version_bump_guard.py`, `pre_pr.py` wrapping `build/scripts/validate_plugin_version_bump.py`, CI `.github/workflows/validate-plugin-version-bump.yml` |
| Hook | Anchoring validator; runtime-contract tests (`tests/build_scripts/test_generate_hooks_runtime_contract.py`); keep `.claude/settings.json` and `.claude/hooks/hooks.json` in sync by hand |
| Workflow | SHA-pin validation; yamllint style; local workflow run gate in pre-push (`SKIP_WORKFLOW_LOCAL_TEST` escape exists for unrunnable workflows; semantics in `ai-agents-config-catalog`) |
| ADR / governance | `adr-review` debate to consensus; PreToolUse guard `invoke_adr_review_guard.py` |
| Any canonical-source edit | Drift gates: `python3 build/generate_agents.py --validate` and `python3 build/scripts/build_all.py --check`; CI mirrors in `agent-drift-detection.yml` and `drift-detection.yml` |

Drift-gate bypass exists but is not free. `[skip-drift-check]` anywhere in a commit message on the PR skips agent drift detection (`.github/workflows/agent-drift-detection.yml:17`). Using it demands a stated reason and human approval; an unexplained bypass marker reads as the session 1187 pattern (Phase 5) and will be challenged in review.

### Phase 3: Run the gate ladder, local to CI

The ladder is ordered by feedback cost. Catching a violation at rung 1 costs seconds; at rung 4 it costs an hour of CI round-trip plus reviewer attention. The enforcement-timing hierarchy is deliberate: pre-commit beats CI beats code review beats documentation.

| Rung | Gate | Command or trigger | What runs |
|------|------|--------------------|-----------|
| 1 | Shift-left runner | `python3 scripts/validation/pre_pr.py` (`--quick` skips slow checks) | Roughly 30 validations: session end, tests, scoped markdownlint, workflow YAML, dash prohibition, plugin bump, install parity, hook anchoring. Exit codes per ADR-035: 0 pass, 1 logic failure, 2 config error (`scripts/validation/pre_pr.py` docstring) |
| 2 | Pre-commit hook | Automatic on `git commit` through Lefthook | Lefthook filters staged files and runs the named validators in `lefthook.yml` |
| 3 | Pre-push hook | Automatic on `git push` through Lefthook | Lefthook filters files in the push range and runs the named validators in `lefthook.yml` |
| 4 | CI required checks | Push and PR events | `pytest.yml`; `pr-validation.yml` (20-commit cap); `ai-pr-quality-gate.yml` (10 parallel LLM reviewers; the authoritative blocker is `scripts/quality_gate/check_critical_failures.py`, wired at `ai-pr-quality-gate.yml:735`); `ai-session-protocol.yml` (deterministic); drift and plugin-bump workflows |

Local Git hooks only run after Lefthook is installed. Run
`uv run --frozen lefthook install`, then verify with
`uv run --frozen lefthook check-install`. `pre_pr.py` also validates the binary,
configuration, and installed shims (`scripts/validation/checks_plugin.py`).

### Phase 4: Respect commit discipline

| Rule | Limit | Enforcement |
|------|-------|-------------|
| Files per commit | 5 or fewer | `.claude/rules/universal.md` MUST 4; AGENTS.md Boundaries |
| Commits per PR | Block at 20 | `pr-validation.yml:369` (`$blockThreshold = 20`); human override only via the `commit-limit-bypass` label (`pr-validation.yml:483`) |
| Mid-session check | Warn above 15 | `git rev-list --count HEAD ^origin/main` (AGENTS.md Mid gate, ADR-008) |
| Lint scope | Changed files only | PR #908 fix: scope `markdownlint --fix` to `git diff --name-only` output, never `**/*.md` |

The story behind the caps. PR #908 (January 2026) grew to 228+ comments, 59 commits, 95 files, and 5,060 additions (`.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md:6`). More than half the diff was collateral: the session protocol at the time mandated an unscoped `markdownlint --fix **/*.md`, which reformatted memory files across the repo (53 memory-file changes, 56% of the diff; five-whys at retro lines 285-298). Review became impossible and feedback arrived late on everything. The 20-commit cap, `pre_pr.py` itself, and the scoped-lint rule all date from that retrospective. When your PR approaches the caps, split it; do not reach for the bypass label.

### Phase 5: Hold the non-negotiables

Check this table before any push. The incident column is the answer to "why"; do not re-litigate settled incidents in PR threads (deep history lives in `ai-agents-failure-archaeology`). If you believe you have new evidence against a rule, propose an ADR, which itself fires `adr-review`.

| Rule | Enforcement mechanism | Incident / rationale |
|------|----------------------|----------------------|
| No new bash scripts; Python for all new scripts | Review + `.claude/rules/universal.md` SHOULD 3 ("MUST NOT create new bash scripts") | ADR-042 (Accepted) |
| No logic in YAML workflows | ADR-006 + `.claude/rules/universal.md` MUST NOT 4 | Workflow YAML cannot be tested locally. Amendment 2026-04-28 allows pure config-data YAML under 7 conditions in `templates/platforms/` and `build/` only; `run:` block logic stays banned |
| No em or en dashes in authored text | `validate_dash_prohibition` (`scripts/validation/checks_dash.py` via `pre_pr.py`) + dash-guard hook; `tests/hooks/fixtures/` exempt | `.claude/rules/universal.md` MUST NOT 5: bot reviewers open one or more threads per dash, every PR (Issue #1923) |
| SHA-pin all GitHub Actions | Pre-commit hook + workflow validation (`.agents/governance/PROJECT-CONSTRAINTS.md:162`) | Tags are mutable; SHA pinning blocks supply-chain tag-moving. See the documented tension below |
| Generated and released hook artifacts fail closed and loud (ADR-066 D1, ADR-071). Scoped, not blanket: push guards fail open on infrastructure errors by design (`.claude/hooks/PreToolUse/push_guard_base.py` docstring); repo-wide audit tracked in #2271. Per-family table: `ai-agents-architecture-contract` Phase 3 | `validate_hook_anchoring.py`, runtime-contract tests, named Lefthook jobs, and CI enforcement | #2205 customer wedge; policy reversal story below |
| Plugin content change requires a strictly greater plugin.json semver | Guard hook + `pre_pr.py` + `validate-plugin-version-bump.yml` | PR #1942 stale-cache story below |
| Block-style YAML arrays only in frontmatter | `.agents/governance/PROJECT-CONSTRAINTS.md:224` ("Exceptions: None") | Copilot CLI frontmatter parser fails on CRLF and related formatting: github/copilot-cli#694, cited at PROJECT-CONSTRAINTS.md:220; ADR-044 |
| `.agents/HANDOFF.md` is read-only | `.claude/rules/universal.md` MUST NOT 3 | ADR-014 (Accepted): the monolithic handoff file bloated and became a chronic merge-conflict magnet; distributed handoffs replaced it |
| Memory-first: retrieval precedes reasoning | AGENTS.md Retrieval section; session-start gates | ADR-007: Serena memories are canonical, Forgetful supplementary. Search before building; do not re-derive settled decisions |
| "Matches/mirrors" claims must quote the canonical source verbatim | `.claude/rules/canonical-source-mirror.md`; heuristic citation check in `pre_pr.py` | FM-9 confident-incorrectness; PR #1887 story below |
| No silent defaults | FM-10 detection table (`.agents/governance/FAILURE-MODES.md:315-399`); `taste-lints` and pre-push scans | PR #1965 verdict-parser story below |
| Session-file merge immutability | Retro rule; session-protocol validation | Session 1187 story below: take `--theirs` for main's session file, rename yours to the next number |
| No secrets, no force-push, no `--no-verify`, no direct commits to main | `.claude/rules/universal.md` MUST 1, MUST 5, MUST NOT 1, MUST NOT 2 | Hooks are the enforcement surface; skipping them is self-disarming |

Escape hatches (env vars, commit markers, skip semantics) exist for several gates. They are deliberately narrow after session 1187, and each is cataloged with its abuse story in `ai-agents-config-catalog`. Do not invent a new one inline; a new flag is itself a governance change.

### Phase 6: Know the stories the table compresses

#### Fail-closed hooks: the #2205 reversal

A launcher path bug in generated Copilot CLI hooks wedged every customer environment for 33 days across plugin versions v0.3.0 to v0.5.6; recovery required uninstalling. The in-script fail-open shim never ran because the launcher failed before the script started, so "fail-open" did not protect anyone, it only delayed detection (context section of `.agents/architecture/ADR-066-hook-fail-open-reconciliation.md`; incident retro at `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md`). The policy reversed: prevention at generation time, then fail closed and loud at runtime. Status precision matters here: ADR-066 is `status: proposed` (as of 2026-07-03), but the position is operative because ADR-071 (Accepted 2026-06-02) records the launcher-level fail-open follow-up (#2230) as rejected, closed addressed-by-prevention. Older ADRs (008, 033, 035, 062) still carry stale fail-open language; the binding direction for hooks is fail-closed. Do not cite the stale ADRs to justify a silent exit 0.

#### Plugin version bump: PR #1942

PR #1942 deleted the deprecated `workflow` skill but did not bump `plugin.json`. Installed plugins kept serving the dead `/workflow` command from a stale `0.3.0` cache because nothing signaled the content had changed (`build/scripts/validate_plugin_version_bump.py:10-12`). The gate now requires a strictly greater semver on the touched tree. Do not trust any written version snapshot; re-verify with `grep '"version"' .claude/.claude-plugin/plugin.json src/claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json`. Yes, that includes this file: editing this skill requires bumping `.claude/.claude-plugin/plugin.json`. Incident home: `ai-agents-failure-archaeology` (PR #1942 entry).

#### Escape-hatch abuse: session 1187

`SKIP_PREPUSH` was introduced at 08:55 as an "emergency use only" bypass. First abuse at 11:04, third by 11:39, each substituting for a root-cause fix. The same session resolved a session-log merge conflict with `git checkout --ours`, overwriting main's historical session 1188 instead of preserving it and renaming the local file to 1189. User verdict, quoted in the retro: "You can't be trusted in the least bit." (`.agents/retrospective/2026-02-08-session-1187-skip-prepush-abuse.md:14-16,41-42,66`). Consequences that still bind: do not introduce a project-specific global hook bypass, session files from main are immutable in merges (`--theirs`, then rename yours), and every surviving escape hatch carries telemetry or an approval requirement.

#### Verbatim quoting: FM-9 and PR #1887

FM-9 (`.agents/governance/FAILURE-MODES.md:284-307`) names the failure: a change claims to "match" or "mirror" an existing contract without quoting that contract, modeling it from memory instead. PR #1887's guard framework took 69 commits and 254 review conversations, and its own Phase-6 audit found the guards would have prevented 0 of the 35 fix commits (`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`). The rule: a first commit claiming to match a source MUST cite the path and quote the load-bearing fragment character for character; intentional divergence gets a named divergence section (`.claude/rules/canonical-source-mirror.md`).

#### No silent defaults: FM-10 and PR #1965

A CI verdict parser treated a missing `VERDICT:` line as non-blocking, silently defaulting toward PASS. Fixing it took three rounds (commits `5bbf355`, `c1d8209`, `6cb5370`) because the parser, the exit-code translator, and the workflow gate each had their own silent default layered behind the last one. The canon line, quoted verbatim from `.agents/governance/FAILURE-MODES.md`: "there is no neutral default for a missing signal." Either a missing signal is meaningful (raise or block) or the call should never have happened (fix upstream). Applies to `except: pass`, `x or default` on numeric config, and every parser fall-through you are about to write.

#### The one documented tension: SHA pinning

`.agents/governance/PROJECT-CONSTRAINTS.md:180` says "Exceptions: None. All third-party actions must be SHA-pinned." GP-006 (`.agents/governance/golden-principles.md:63-69`) allows first-party `actions/*` on version tags with Dependabot. Both are live documents. Resolution until someone reconciles them via ADR: follow the stricter rule (pin everything) unless a human explicitly approves the GP-006 allowance for a first-party action. Flag the tension in your PR description when you hit it; do not silently pick a side.

## Anti-Patterns

| Anti-pattern | Why it fails here |
|--------------|-------------------|
| Editing a generated tree to silence a drift gate | Inverts the source of truth (2025-12-15 incident, reverted). Ask which side is canonical first |
| Using `[skip-drift-check]` or `commit-limit-bypass` without a stated reason and human approval | Bypass markers are audited; unexplained use reads as the session 1187 pattern |
| Bumping plugin.json "just in case" on every commit | The gate fires only when tree content changed; noise bumps hide real releases in the version history |
| Adding a fail-open wrapper so a broken hook "does not block anyone" | Rejected pattern (#2230, recorded in ADR-071): silent exit 0 disables the hook while looking like success, exactly the #2205 failure |
| Classifying a mixed session as investigation-only | One staged file outside the ADR-034 allowlist voids the exemption; split the work |
| Fixing a bot-flagged dash or style claim without byte-level verification | Bots false-positive; count the actual bytes before editing (PR #1873 observation: an em-dash flag on a line with zero em-dashes) |
| Citing ADR-008/033/035/062 fail-open language for a new hook | Stale; the operative policy is fail-closed and loud (Phase 6, #2205 reversal) |
| Re-arguing a settled non-negotiable in a PR thread | The incident column is the answer; new evidence goes in an ADR, which fires `adr-review` |

## Verification

Before you push, confirm:

- [ ] Change classified (Phase 1) and every class obligation from Phase 2 satisfied
- [ ] `python3 scripts/validation/pre_pr.py` exits 0
- [ ] `uv run --frozen lefthook check-install` exits 0
- [ ] Touched `.claude/`, `src/claude/`, or `src/copilot-cli/`? The matching `plugin.json` version strictly increased
- [ ] Touched a canonical generation source? `python3 build/scripts/build_all.py --check` and `python3 build/generate_agents.py --validate` both pass
- [ ] Commit count under 20 (`git rev-list --count HEAD ^origin/main`), each commit 5 files or fewer
- [ ] Created or edited an ADR or SESSION-PROTOCOL.md? `adr-review` gate acknowledged
- [ ] No em or en dashes in changed files: `python3 -c "import sys; b=open(sys.argv[1],'rb').read(); print(b.count(chr(0x2014).encode())+b.count(chr(0x2013).encode()))" FILE` prints 0

## Provenance and Maintenance

Verified against the working tree on 2026-07-03. Volatile facts and their re-verification commands:

| Fact | Source | Re-verify |
|------|--------|-----------|
| Verification-based enforcement wording | `.agents/SESSION-PROTOCOL.md:36` | `sed -n 30,40p .agents/SESSION-PROTOCOL.md` |
| Investigation allowlist (9 patterns; ADR-034 text lags at 5) | `scripts/modules/investigation_allowlist.py`; `.agents/architecture/ADR-034-investigation-session-qa-exemption.md:79-83` | `uv run python -c "from scripts.modules.investigation_allowlist import get_investigation_allowlist_display as g; print(len(g()), g())"` |
| build_all no-claude-writes invariant | `build/scripts/build_all.py:962-967` | `grep -n "REQ-003-010" build/scripts/build_all.py` |
| 20-commit block threshold and bypass label | `.github/workflows/pr-validation.yml:369,483` | `grep -n "blockThreshold\|commit-limit-bypass" .github/workflows/pr-validation.yml` |
| Git hook jobs, filters, and validators | `lefthook.yml` | `uv run --frozen lefthook validate` |
| Plugin versions (volatile; never hard-code them in prose) | the three `.claude-plugin/plugin.json` files | `grep -o '"version": "[^"]*"' .claude/.claude-plugin/plugin.json src/claude/.claude-plugin/plugin.json src/copilot-cli/.claude-plugin/plugin.json` |
| PR #1942 motivating failure | `build/scripts/validate_plugin_version_bump.py:10-12` | `sed -n 8,14p build/scripts/validate_plugin_version_bump.py` |
| SHA-pin tension (Exceptions: None vs GP-006) | `.agents/governance/PROJECT-CONSTRAINTS.md:180`; `.agents/governance/golden-principles.md:63-69` | `grep -n "Exceptions" .agents/governance/PROJECT-CONSTRAINTS.md; sed -n 63,70p .agents/governance/golden-principles.md` |
| ADR-066 proposed, ADR-071 accepted, #2230 rejected | Status sections of both ADR files | `sed -n 1,20p .agents/architecture/ADR-066-hook-fail-open-reconciliation.md; sed -n 1,10p .agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md` |
| FM-9 and FM-10 sections; "neutral default" quote | `.agents/governance/FAILURE-MODES.md:284,315` | `grep -n "neutral default" .agents/governance/FAILURE-MODES.md` |
| Incident retro paths (908, 1187, 1887, 1965, 2205) | `.agents/retrospective/` | `ls .agents/retrospective/ \| grep -E "908\|1187\|1887\|1965\|2205"` |
| `[skip-drift-check]` bypass contract | `.github/workflows/agent-drift-detection.yml:17,65-69` | `grep -n "skip-drift-check" .github/workflows/agent-drift-detection.yml` |
| ai-pr-quality-gate authoritative blocker | `.github/workflows/ai-pr-quality-gate.yml:735` | `grep -n "check_critical_failures" .github/workflows/ai-pr-quality-gate.yml` |
| ADR-006 amendment scope and conditions | `.agents/architecture/ADR-006-thin-workflows-testable-modules.md:255-309` | `grep -n "Amendment 2026-04-28" .agents/architecture/ADR-006-thin-workflows-testable-modules.md` |
| Hook-install check rationale | `scripts/validation/checks_plugin.py:127-134` | `grep -n "def validate_git_hooks_installed" scripts/validation/checks_plugin.py` |

Maintenance rule: any edit to a cited source line number, plugin version, or ADR status invalidates the matching row. Re-run the re-verify command and update the row in the same commit. This file is plugin content; editing it requires a `.claude/.claude-plugin/plugin.json` bump.
