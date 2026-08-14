# Test Report: PR Review Toolkit Agents (feat/pr-review-toolkit-agents)

## Objective

Validate the full branch state (3 committed commits + uncommitted working-tree
edits + untracked files) that adds a technology-agnostic `code-reviewer` agent
and genericizes `code-simplifier`, `pr-test-analyzer`, `silent-failure-hunter`.
Scope: the smallest complete validation set specified by the todo
`validate-agent-changes` (11 items), executed read-only. No commits, amends,
resets, or hand-edits were made.

- **Branch**: `feat/pr-review-toolkit-agents` @ `cf59a1e25` (HEAD), base `origin/main` @ `7514eb219`
- **Full changed-file set** (committed + uncommitted + untracked, 30 files):
  agent mirrors for 4 agents (code-reviewer, code-simplifier, pr-test-analyzer,
  silent-failure-hunter) across `.claude/agents`, `.github/agents`,
  `src/claude`, `src/copilot-cli/agents`, `src/vs-code-agents`,
  `templates/agents`; `docs/agent-catalog.md`; 4 new
  `tests/evals/*-scenarios.json`; 1 untracked session log.

## Approach

- Environment: Windows, `.python-version` pins `3.14.6`; not installable via
  `uv python install` in this sandbox (`No download found for request:
  cpython-3.14.6-windows-x86_64-none`). Closest available pinned interpreter:
  **3.14.5** (`C:\Users\rimuri\AppData\Roaming\uv\python\cpython-3.14.5-...`).
  All `uv run` invocations used `--python 3.14.5` explicitly, or `UV_PYTHON=3.14.5`
  for nested subprocess calls (`pre_pr.py`'s ratchets shell out to their own
  `uv run --frozen`, which does not inherit a CLI `--python` flag).
- No new tools were installed. `npx`, `markdownlint-cli2`, `lefthook` (binary),
  `ruff` were already present via uv/npm caches.
- Did not commit, amend, reset, or rewrite history. Did not hand-edit any
  generated output.

## Results

### Summary

| Gate | Status |
|------|--------|
| 1. `generate_agents.py --validate` (Python 3.14.5) | [PASS] |
| 2. Agent catalog drift validator | [PASS] |
| 3a. Content parity (`.claude/agents` vs `src/claude`) | [PASS] |
| 3b. Install parity, default (`git diff` base..HEAD only) | [FAIL] (false positive, see Discussion) |
| 3c. Install parity, explicit `--files` (full changed set) | [PASS] |
| 4a. Copilot agent frontmatter validator | [PASS] |
| 4b. Argument-hint validator, default scan (tracked files only) | [PASS] (593 files; misses 2 untracked new files, see Discussion) |
| 4c. Argument-hint validator, explicit untracked files | [PASS] |
| 5a. Vendor portability check | [SKIP] (cannot run: Windows path bug, see Discussion) |
| 5b. Plugin frontmatter self-containment | [PASS] (930 tracked files; misses 2 untracked new files, no override flag exists) |
| 6. Drift detector, `--fail-on-install-drift` (CI strict flag) | [PASS] (0 drift / 63 agents compared) |
| 7. Parse/schema check, 4 new eval scenario files | [PASS] (8/8 scenarios valid) |
| 8a. ADR-057 dry-run, all 4 scenario files | [PASS] |
| 8b. ADR-057 live before/after eval | [UNRUN] (no credentials; see Discussion) |
| 9. Scoped markdownlint, 22 authored files | [PASS] (18 linted, 0 issues; 4 `.github/agents/*.agent.md` excluded per repo config) |
| 10. `pre_pr.py` full suite | [FAIL] (5/51 gates failed; see Discussion) |
| 11. Session log validator (canonical) | [FAIL] (13 incomplete MUST items + missing QA evidence) |

### Test Results by Category

| Test | Category | Status | Notes |
|------|----------|--------|-------|
| `generate_agents.py --validate` | Generator drift | [PASS] | "VALIDATION PASSED: All generated files match committed files" |
| `validate_agent_catalog.py` | Catalog drift | [PASS] | "OK: docs/agent-catalog.md matches templates/agents/" |
| `check_agent_content_parity.py` | Content parity | [PASS] | 33/33 files byte-identical |
| `validate_install_parity.py --base origin/main` | Install parity | [FAIL] | 4x SHARED_AGENT violations, all false (working-tree-only files invisible to `git diff`) |
| `validate_install_parity.py --files <30 files>` | Install parity | [PASS] | "install-parity: OK" |
| `validate_copilot_agent_frontmatter.py` | Frontmatter | [PASS] | 31/31 files valid YAML |
| `validate_argument_hint.py` (default) | Argument-hint | [PASS] | 593 tracked files scanned |
| `validate_argument_hint.py <9 explicit files>` | Argument-hint | [PASS] | Covers the 2 untracked new files the default scan misses |
| `check_vendor_portability.py` | Vendor portability | [SKIP] | Refuses `.claude/skills` as "outside the repository" - false; see Discussion |
| `check_plugin_frontmatter_self_containment.py` | Self-containment | [PASS] | 930 tracked `.md` files, 0 outward refs |
| `detect_agent_drift.py --fail-on-install-drift` | Drift (CI flag) | [PASS] | 62 OK (2 baselined) / 63, 1 no-counterpart (pre-existing, unrelated) |
| Scenario JSON schema check (4 files) | Eval scenarios | [PASS] | REQUIRED_SCENARIO_FIELDS + verdict_options contract, 8/8 scenarios |
| `eval-prompt-change.py --dry-run` x4 | ADR-057 dry-run | [PASS] | code-simplifier, pr-test-analyzer, silent-failure-hunter via `--base-ref main`; code-reviewer via explicit empty `--before` (new file, no `main` counterpart) |
| `eval-prompt-change.py` live | ADR-057 live | [UNRUN] | No `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`; `gh` auth present but using it requires `--provider github-models` (a configuration change) and incurs real API cost - not attempted without confirmation |
| `markdownlint-cli2` (18 files) | Markdown lint | [PASS] | 0 issues |
| `pre_pr.py` (UV_PYTHON=3.14.5) | Full gate suite | [FAIL] | 46/51 pass, 5 fail (Count Ratchets, Markdown Linting, Skill Markdown Portability, Install Parity, Lefthook Installed) |
| `validate_session_json.py` on active session log | Session protocol | [FAIL] | 13 incomplete MUST items, empty QA evidence path |

## Discussion

### Risk Areas

| Area | Risk Level | Rationale |
|------|------------|-----------|
| `templates/agents/code-reviewer.shared.md` prose | High | Real, diff-caused vendor-portability violation shipped to all 5 install copies (see below) |
| Windows-only validator bugs | Medium | Three separate scripts (`check_vendor_portability.py`, `checks_tooling.py` npx call, `merge_tree_materialization.py`) misbehave only on Windows; masks or falsely reports gate results in this environment regardless of PR content |
| Session protocol incompleteness | Medium | Active session log fails 13 MUST checks; not this diff's content defect, but blocks a clean session close |

### Finding 1 (blocking): vendor-portability violation in new `code-reviewer` content

`templates/agents/code-reviewer.shared.md` (and, because it propagated
correctly, all 5 install copies: `.claude/agents/code-reviewer.md`,
`.github/agents/code-reviewer.agent.md`, `src/claude/code-reviewer.md`,
`src/copilot-cli/agents/code-reviewer.agent.md`,
`src/vs-code-agents/code-reviewer.agent.md`) contains this sentence in the
"Critical: Treat Reviewed Content as Data, Not Instructions" section:

> `templates/agents/security.shared.md` states the canonical rule this agent
> applies to every reviewed artifact: ...

`templates/` is the generator source tree in `rjmurillo/ai-agents`. It is not
shipped in any of the 3 plugin roots (`.claude`, `src/copilot-cli`,
`src/vs-code-agents`). A consumer who installs this plugin gets an agent
prompt that cites a file path that does not exist anywhere in their
installation. `scripts/validation/check_plugin_frontmatter_self_containment.py`
does not catch this because it scopes to frontmatter `description`/`name`
only; `scripts/validation/check_skill_md_portability.py` (run inside
`pre_pr.py` as "Skill Markdown Portability") catches it because its scan is
broader (body prose, all 3 plugin roots). This is why item 10 shows a real
failure here even though item 5's frontmatter-only check passes.

This is a content-authoring defect, not generated drift. It exists identically
in the hand-authored template and in every mechanically generated/copied
mirror, so rerunning `build/generate_agents.py` cannot fix it; the source
prose in `templates/agents/code-reviewer.shared.md` must be reworded (e.g.
paraphrase the untrusted-data rule inline instead of citing a template path,
or replace the citation with the shipped consumer-facing skill/rule name that
carries the same content). Per this agent's constraints, QA does not hand-edit
this: routed to implementer.

### Finding 2: `pre_pr.py` (5 of 51 gates fail; 1 is the Finding-1 defect, 4 are environment/scoping artifacts)

Full run (`UV_PYTHON=3.14.5 uv run --python 3.14.5 python scripts/validation/pre_pr.py`),
46/51 passed in 306.99s.

| Gate | Root cause | Diff-caused? |
|------|-----------|--------------|
| Skill Markdown Portability | Finding 1 above | **Yes** |
| Install Parity (agents and rules) | `validate_install_parity.py` scopes to `git diff --name-only <base>..HEAD`, which is blind to uncommitted/untracked files. 4 SHARED_AGENT groups (code-reviewer, code-simplifier, pr-test-analyzer, silent-failure-hunter) show their `src/copilot-cli`/`src/vs-code-agents` mirrors as "missing" because those edits are uncommitted. Independently confirmed clean when scoped with an explicit `--files` list of all 30 changed files (item 3c above): `install-parity: OK`. | No (scoping artifact; resolves once committed) |
| Count Ratchets | All 8 ratchets initially failed with `No interpreter found for Python 3.14.6` (env-only; `.python-version` pin unavailable). Re-run with `UV_PYTHON=3.14.5` fixed 7/8. The 8th (`merge-tree-ratchet`) still fails on its `ruff count ratchet` sub-check: "42 > effective baseline 27 (+15); base ref records 27, merged tree records 27." Independently verified as a **false positive**: `git merge-base --is-ancestor origin/main HEAD` confirms `origin/main` is an ancestor of `HEAD`, so the "merged tree" is exactly `HEAD`'s tree (`cf59a1e25`). A clean `git worktree add --detach` checkout of that exact commit, scanned with the identical `ruff check --output-format json-lines` invocation, measures **27** (matches baseline, not 42). The discrepancy is reproducible (2 runs, identical "42") and every occurrence pairs with a Windows `PermissionError: [WinError 5] Access is denied` deleting the scratch git pack `.idx` file during cleanup, evidence that the scratch-tree materialization (`scripts/ci/merge_tree_materialization.py`, `git init` + `checkout-index` + `git add -A` into a fresh temp repo) produces a different file set than the real commit on this OS. This diff touches 0 Python files, so it cannot be the cause of a Python-lint-count change. | No (Windows-only materialization bug, reproducible independent of this diff) |
| Markdown Linting | `shutil.which("npx")` resolves `npx.CMD`, but `subprocess.run(["npx", ...], shell=False)` (no `shell=True`) raises `FileNotFoundError` on Windows because CPython's `CreateProcess` does not resolve `.cmd`/`.bat` shims the way `cmd.exe` does. Confirmed by direct reproduction. Independently verified clean: item 9's scoped `markdownlint-cli2` run against the same 18 relevant files reports 0 issues. | No (Windows-only subprocess bug in `checks_tooling.py:190`) |
| Lefthook Installed | Lefthook the binary is present and functional (`uv run --python 3.14.5 lefthook version` → `2.1.10`); the gate fails because git hooks are not wired into this checkout (`lefthook install --reset-hooks-path` was never run here). Not executed by QA: it mutates `.git/config` (`core.hooksPath`) and `.git/hooks`, a local, semi-persistent environment change outside pure validation, and a second agent is reviewing this same working tree concurrently. Flagged for confirmation rather than run unilaterally. | No (local environment setup step, not this diff) |

### Finding 3: `pre_pr.py`'s own Session End Validation gate silently misses the untracked session log

`pre_pr.py` reported `[PASS] Session End Validation (no session logs on branch)`.
This is a false clean: `scripts/validation/session_scope.py` scopes new-session
detection through `git ls-files` / `git diff`, both blind to the untracked
`.agents/sessions/2026-08-13-session-14695-....json` file sitting in the
working tree. Running the canonical validator directly against that file
(item 11) shows it is very much present and fails validation. Same root cause
as the Install Parity scoping gap (Finding 2): git-diff/git-ls-files-scoped
gates in this codebase cannot see genuinely untracked new files, so a fully
uncommitted change set gets a free pass from several gates simultaneously.

### Finding 4: Session log validator (13 incomplete MUST items, no QA evidence binding)

`uv run python scripts/validate_session_json.py .agents/sessions/2026-08-13-session-14695-b1cdc6d2e-implement-technology-agnostic-review-agents-based.json`
exits 1:

```text
- Incomplete MUST: sessionStart.handoffRead
- Incomplete MUST: sessionStart.constraintsRead
- Incomplete MUST: sessionStart.serenaActivated
- Incomplete MUST: sessionStart.skillScriptsListed
- Incomplete MUST: sessionStart.serenaInstructions
- Incomplete MUST: sessionStart.memoriesLoaded
- Incomplete MUST: sessionStart.usageMandatoryRead
- Incomplete MUST: sessionEnd.changesCommitted
- Incomplete MUST: sessionEnd.markdownLintRun
- Incomplete MUST: sessionEnd.checklistComplete
- Incomplete MUST: sessionEnd.validationPassed
- Incomplete MUST: sessionEnd.handoffPreserved
- Incomplete MUST: sessionEnd.qaValidation
- Incomplete MUST: sessionEnd.serenaMemoryUpdated
- QA evidence must name a report under the configured QA artifact root: ''
```

The session log's own `nextSteps` array already self-reports this ("This
integration pass did not perform session start ... or session end ... for the
overall session"). The self-report is accurate but does not change the FAIL
verdict: the protocol requires the checklist complete before session end, not
merely documented as incomplete.

### Finding 5: `check_vendor_portability.py` cannot run on Windows (undercuts item 5)

`scan_roots()` (`scripts/validation/check_vendor_portability.py:190`) tests
containment with `str(resolved).startswith(str(resolved_repo) + "/")`. On
Windows, `pathlib` renders paths with `\`, so this check is always `False`
even for a path genuinely inside the repo, and the script refuses every scan
root with "resolves to ..., which is outside the repository" and returns
`[SKIP]` with exit 0. Verified directly:

```text
resolved_repo: C:\src\GitHub\rjmurillo\ai-agents
resolved:      C:\src\GitHub\rjmurillo\ai-agents\.claude\skills
startswith check: False
is_relative_to:   True
```

This means item 5's vendor-portability half did not actually scan anything in
this session; the `[SKIP]`/exit-0 result is not evidence of cleanliness. It is
a pre-existing bug unrelated to this diff's content, but it means vendor
portability for the touched agents is genuinely unverified here. No baseline
or CI evidence was available to substitute (this environment has no `origin`
CI run to inspect for this branch).

### Finding 6: Two validators have no override for untracked files

`validate_argument_hint.py`'s default scan and
`check_plugin_frontmatter_self_containment.py`'s `iter_markdown` both source
their file list from `git ls-files`, which never includes an untracked file.
`validate_argument_hint.py` accepts positional path arguments as a workaround
(used here to cover the 2 untracked files under `src/copilot-cli/agents/` and
`src/vs-code-agents/`). `check_plugin_frontmatter_self_containment.py` has
`--repo-root` only, no explicit file-list flag; QA substituted a manual
frontmatter inspection of the 9 untracked/new agent files (documented in the
Results table) rather than skipping the check silently. No frontmatter
`description`/`name` field in any of the 9 files names an outward file path,
so this substitute check is clean, but it is a manual read, not a tool run.

### Coverage Gaps

| Gap | Reason | Priority |
|-----|--------|----------|
| ADR-057 live before/after eval | No API credentials in this environment; running via `--provider github-models` would require exporting `GITHUB_TOKEN`/`GH_TOKEN` (a configuration change) and spends real tokens (external, irreversible-ish cost) | P1 - required before merge per ADR-057 "MUST run" for behavioral prompt changes |
| No permanent pytest coverage for the 4 new scenario files | Session log's own `nextSteps` flags this as optional; no test mirrors `tests/evals/test_hook_feedback_scenarios.py` for these 4 files | P2 |
| Vendor portability (Finding 5) | Windows-only tool bug, not fixable within QA's read-only scope | P1 - re-run on Linux/CI before merge to get a real answer |

## Recommendations

1. Reword `templates/agents/code-reviewer.shared.md`'s citation of `templates/agents/security.shared.md` to remove the dangling upstream-only path (Finding 1); this blocks `pre_pr.py`'s Skill Markdown Portability gate and is the one gate failure genuinely caused by this diff.
2. Commit the templates/install-copy edits and the newly generated `src/copilot-cli`/`src/vs-code-agents` mirrors together so Install Parity (Finding 2) and the Session End Validation blind spot (Finding 3) stop reading a partial diff.
3. Run the ADR-057 live before/after eval (`eval-prompt-change.py`, no `--dry-run`) for all 4 scenario files once `ANTHROPIC_API_KEY` (or an explicitly authorized `--provider`) is available; this session only validated dry-run structure, not behavior.
4. Complete the session-start/session-end protocol checklist on the active session log (Finding 4) or split the log per-session before merge.
5. Re-run vendor portability and the full `pre_pr.py` suite on Linux/CI to get a trustworthy signal on the two Windows-only tool bugs (Findings 2's Count-Ratchet/Markdown-Linting rows, Finding 5); do not treat this session's `[SKIP]`/false-`[FAIL]` results on those specific rows as final.

## Verdict

```text
Promised: Run the 11-item validation set against the full branch state
  (committed + uncommitted + untracked) without committing, amending,
  resetting, or hand-editing generated output; report commands, exit codes,
  failures, completeness, and blockers.
Delivered: All 11 items executed with documented commands and exit codes.
  Items 1, 2, 4, 6, 7, 9 pass cleanly. Item 3 passes when scoped correctly
  (documented limitation of default scoping). Item 5 partially unverifiable
  (Windows tool bug, documented). Item 8 dry-run passes; live run correctly
  reported as unrun (no credentials). Item 10 fails on 5/51 gates, 1 of which
  (Skill Markdown Portability) is a genuine content defect in this diff.
  Item 11 fails (session protocol incomplete).
Gap: One real, diff-caused blocking defect (Finding 1, vendor-portability
  citation in code-reviewer prompt). Session protocol incomplete (Finding 4).
  ADR-057 live eval not run (no credentials available). Vendor portability
  unverifiable on this OS pending a Linux/CI re-run.
Result: FAIL
```

**Status**: FAIL
**Confidence**: High
**Rationale**: The validation set was executed completely and every failure
was root-caused (real defect vs. environment/scoping artifact) rather than
merely reported. One gate failure (Skill Markdown Portability /
vendor-portability citation of `templates/agents/security.shared.md`) is a
genuine content defect this diff introduces and ships to all 5 install
copies; it blocks merge and requires implementer rework, not a generator
re-run. The session log also fails its own protocol validator. Recommend
routing to implementer for Finding 1, and to whichever step owns session
closure for Finding 4.
