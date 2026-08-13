# Test Report: Focused Final Validation (post internal-path fix)

## Objective

Independent, fresh-context revalidation of `feat/pr-review-toolkit-agents`
(HEAD `cf59a1e25`, plus uncommitted edits and untracked files) after the
implementer's internal-path fix to `templates/agents/code-reviewer.shared.md`.
This report does not share context with the prior QA pass
(`.agents/qa/session-14695-pr-review-toolkit-agents-test-report.md`); every
claim below was independently re-verified against the current repository
state, and two of that report's root-cause claims are corrected with evidence
(see Discussion). Scope: the 12-item validation set from todo
`revalidate-agent-changes`, executed read-only. No commits, amends, resets,
or hand-edits were made; no tools were installed; no live/API-backed eval
tokens were spent.

- **Full changed-file set** (committed + uncommitted + untracked, verified via
  `git diff --name-only origin/main...HEAD` + `git diff --name-only` +
  `git ls-files --others --exclude-standard`): 31 files across 4 agents
  (code-reviewer new, code-simplifier/pr-test-analyzer/silent-failure-hunter
  modified).

## Approach

Ran each of the 12 required checks directly against the repository, using
`uv run --python 3.14.5` (the `.python-version` pin, 3.14.6, is not
installable in this sandbox; 3.14.5 is the closest locally available
interpreter, matching the prior pass's environment note). Where a claim in
the prior QA report was surprising or load-bearing (the "false positive"
framing of two `pre_pr.py` failures), reproduced the exact production
mechanism from source rather than accepting the prior report's conclusion.

## Results

### Summary

| # | Gate | Status |
|---|------|--------|
| 1 | `generate_agents.py --validate` | [PASS] |
| 2 | Agent catalog validator | [PASS] |
| 3a | Content parity (`.claude/agents` vs `src/claude`) | [PASS] |
| 3b | Install parity, default (base-diff scoped) | [FAIL] (scoping artifact, not diff-caused) |
| 3c | Install parity, explicit `--files` (31-file set) | [PASS] |
| 4a | Copilot frontmatter validator | [PASS] |
| 4b | Argument-hint validator, default scan | [PASS] |
| 4c | Argument-hint validator, explicit untracked/new files | [PASS] |
| 5 | Grep for internal-path/vendor strings across 5 shipped roots | [PASS] (0 matches; Finding 1 confirmed fixed) |
| 6 | Strict drift detector (`--all --fail-on-install-drift`) | [PASS] (0 drift / 63 compared, 1 pre-existing no-counterpart) |
| 7 | Scenario JSON parse/schema (4 files, via real `load_scenarios()`) | [PASS] (8/8 scenarios) |
| 8 | Eval dry-runs (4 files) | [PASS] |
| 9 | Scoped markdownlint (26 changed .md files) | [PASS] (21 linted after repo-config exclusions, 0 issues) |
| 10 | Skill Markdown Portability (exact `pre_pr.py` function) | [PASS] (242 grandfathered refs, 0 new drift) |
| 11 | Session log validator | [FAIL, protocol-only] (schema valid; 13 incomplete MUST checklist items) |
| 12 | `pre_pr.py` full suite | [FAIL] (47/51 passed, 4 failed; 0 of the 4 are diff-caused; 1 separate advisory-mode violation IS diff-caused, see Finding 3) |

### Test Results by Category

| Test | Category | Status | Notes |
|------|----------|--------|-------|
| `generate_agents.py --validate` | Generator drift | [PASS] | "VALIDATION PASSED" |
| `validate_agent_catalog.py` | Catalog drift | [PASS] | matches templates/agents/ |
| `check_agent_content_parity.py` | Content parity | [PASS] | 33/33 byte-identical |
| `validate_install_parity.py --base origin/main` | Install parity | [FAIL] | 4x SHARED_AGENT "missing sibling" (working-tree files invisible to git diff) |
| `validate_install_parity.py --files <31>` | Install parity | [PASS] | "install-parity: OK" |
| `validate_copilot_agent_frontmatter.py` | Frontmatter | [PASS] | 31/31 valid |
| `validate_argument_hint.py` (default + 12 explicit) | Argument-hint | [PASS] | 593 + 12 files scanned |
| Grep 5 shipped roots for forbidden strings | Vendor/internal-path | [PASS] | 0 hits for `templates/agents/security.shared.md`, `Sentry`, `Statsig`, `errorIds.ts`; `CLAUDE.md` mentions are either pre-existing untouched files or code-reviewer's explicit "do not assume CLAUDE.md exists" (opposite of "required") |
| `detect_agent_drift.py --all --fail-on-install-drift` | Drift (strict) | [PASS] | 62 OK (2 baselined) + 1 no-counterpart (pre-existing `claude-instructions.template`, unrelated to this diff) |
| `load_scenarios()` (real function, not a mirror) on 4 files | Eval scenarios | [PASS] | 8/8 valid |
| `eval-prompt-change.py --dry-run` x4 | ADR-057 dry-run | [PASS] | 3 via `--base-ref origin/main`; code-reviewer via explicit `--before <empty file>` (new agent, no base counterpart) |
| `markdownlint-cli2` (26 files passed, 21 actually linted) | Markdown lint | [PASS] | 0 issues; 5 excluded by `.markdownlint-cli2.yaml` (`.github/agents/**/*.agent.md`, `.agents/**`), confirmed unrelated to this diff |
| `checks_spec.validate_skill_md_portability()` (exact function `pre_pr.py` calls) | Skill MD portability | [PASS] | 242 grandfathered refs, baseline 242, 0 new drift. Scans `.claude/skills`, `src/copilot-cli/skills`, `.claude/commands`, `templates/agents` only (does NOT scan `.claude/agents`, `.github/agents`, `src/claude`, `src/copilot-cli/agents`, `src/vs-code-agents`, by the script's own docstring). Item 5's direct grep across those 5 install roots is therefore not redundant; it is the only check in this suite that verifies the shipped install copies, not just the template source. |
| `validate_session_json.py` (default/full) | Session protocol | [FAIL] | 13 incomplete MUST + empty QA evidence path |
| `validate_session_json.py --creation-mode` | Session protocol (schema only) | [PASS] | Confirms the FAIL above is 100% protocol-completion state, not a schema/shape defect |
| `pre_pr.py` full suite | All gates | [FAIL] | 47/51 passed in 243.01s |

## Discussion

### Finding 1 (resolved): internal-path citation removed and verified clean

`templates/agents/code-reviewer.shared.md` no longer cites
`templates/agents/security.shared.md`; the sentence was reworded to state the
untrusted-data rule inline. Confirmed by three independent methods: (a) direct
grep across all 5 shipped roots (0 hits), (b) direct invocation of the exact
`checks_spec.validate_skill_md_portability()` function `pre_pr.py` calls (0
new drift), (c) full `pre_pr.py` run (Skill Markdown Portability gate: PASS,
vs. FAIL in the prior report). The fix is verified, not merely re-asserted.

### Finding 2 (correction to the prior QA report): the `pre_pr.py` Count
Ratchets failure is real but mis-attributed in the prior report, and is not
diff-caused

The prior report's Finding 2 claimed the `merge-tree-ratchet` ruff-count
regression (42 > baseline 27) was a Windows `PermissionError`
scratch-cleanup false positive, and supported this with "`git merge-base
--is-ancestor origin/main HEAD` confirms `origin/main` is an ancestor of
`HEAD`". Independently re-run just now:

```text
git merge-base --is-ancestor origin/main HEAD; echo $LASTEXITCODE
# => 1  (NOT an ancestor)
git log --oneline HEAD..origin/main
# => 90be321b3 chore(memory): consolidate duplicate Serena memories (#4943)
#    d83211000 chore(deps): update dependency @anthropic-ai/claude-code to v2.1.223 (#4947)
```

`origin/main` has advanced past this branch's fork point since the prior
session ran; that specific claim no longer holds (and origin/main is a moving
target across sessions, so this is a timing artifact of re-running later, not
necessarily an error the prior agent made at the time). Two separate,
independently-verified conclusions follow:

1. **`memory-index-count-ratchet` (BASELINE ABOVE BASE, 387 vs 378)**: real
   and correctly attributed. `scripts/ci/memory_index_count_baseline.txt` is
   `387` at this branch's fork point (`7514eb219`) and unchanged since; PR
   #4943 landed on `origin/main` after the fork point and lowered it to
   `378`. This branch has not rebased to pick up the lower value. **Not
   diff-caused** (this diff never touches that file or the memory index); it
   is ordinary branch staleness, resolved by a rebase/merge.

2. **`merge-tree-ratchet`'s ruff-count sub-check (42 vs baseline 27)**:
   real and reproducible, but the prior report's specific mechanism
   (Windows `PermissionError` during scratch-pack cleanup) does not explain
   it, and it is **not** a stale-branch signal either. Reproduced the exact
   production code path directly (`materialize_tree` + `init_scratch_repo` +
   `ruff_count_ratchet.current_count()`, not a `git archive` approximation):

   - The real merge-tree of `origin/main` + `HEAD` measures 42.
   - `origin/main`'s tree **by itself**, materialized through the identical
     mechanism with no merge involved, **also measures 42** (not 27).
   - The 15-violation delta is 15 `I001` (import-sort) findings, all in
     `tests/test_memory_*.py` files.
   - Those files are byte-identical (confirmed via `git diff` and raw
     `SHA256`/byte comparison) between the real working tree (which measures
     27, clean) and the scratch materialization (which measures 42, dirty).
     `pyproject.toml` and `conftest.py` are also byte-identical between the
     two locations.

   Conclusion: this is a pre-existing, content-independent, environment-level
   defect in the `checkout-index` + `git init` scratch-materialization
   mechanism itself (`scripts/ci/merge_tree_materialization.py`), which
   causes `ruff` to report spurious import-sort violations on a subset of
   files when scanned from a freshly materialized scratch tree versus the
   real working directory, regardless of which commit or branch is
   materialized. It reproduces for `origin/main` alone, so it cannot be
   caused by anything in this PR's diff (which touches zero `.py` files).
   The correct classification is "environment-caused false positive in the
   ratchet's own materialization step," not "Windows cleanup permission
   error" and not "stale branch." Root-causing the exact `ruff`/isort
   behavior further is out of QA's read-only scope; flagging precisely
   matters because the prior report's framing would lead a reader to dismiss
   this as a one-off cleanup glitch, when it is a reproducible, systemic gap
   in the ratchet mechanism that will resurface on every branch run on this
   OS/environment.

### Finding 3 (new; missed by the prior QA report): new `model: opus` pin
lacks required `model-rationale` field

`pre_pr.py`'s "Model Pin Governance (warn)" gate reports:

```text
[model-pins] VIOLATION: .claude/agents/code-reviewer.md: [new pin] bare alias 'opus' lacks a model-rationale field
[model-pins] 1 hard violation(s)
[model-pins] warn mode: reporting only, exit 0
```

Confirmed by running the same checker in enforce mode directly:

```text
uv run --python 3.14.5 python scripts/validation/check_model_pins.py --mode enforce
# => exit 1, same violation line
```

`.claude/agents/code-reviewer.md` sets `model: opus` with no
`model-rationale` field. Per ADR-080, existing bare-alias pins are
grandfathered (38 backlog items reported, none blocking); this pin is
explicitly tagged `[new pin]` because `code-reviewer` is a brand-new agent
introduced by this diff, so it does not inherit the grandfather exemption.
`pre_pr.py` currently runs this gate in advisory/warn mode (exit 0 today,
non-blocking), so it does not currently fail the suite, but it is a real,
diff-caused compliance gap that will hard-fail if/when this gate is switched
to `--mode enforce`, and should be fixed (add a `model-rationale` field)
before merge rather than deferred. The prior QA report did not run or mention
this gate at all.

### Finding 4 (repeat, independently reconfirmed): `pre_pr.py` install-parity
and session-end gates are scoping artifacts, not diff-caused

- Install Parity (default `git diff --name-only <base>..HEAD` scoping) is
  blind to this branch's uncommitted edits and untracked new files;
  confirmed clean (`install-parity: OK`) when scoped with an explicit
  `--files` list covering all 31 changed files.
- `pre_pr.py`'s own "Session End Validation" gate reports
  `[PASS] (no session logs on branch)`, which is a false clean: it is scoped
  through git-tracked/diffed paths and cannot see the untracked
  `.agents/sessions/2026-08-13-session-14695-...json` file sitting in the
  working tree. Running the canonical validator directly against that file
  (item 11) shows real, non-trivial FAIL state.

### Finding 5 (repeat, independently reconfirmed): `Markdown Linting` and
`Lefthook Installed` gate failures are local-environment artifacts

- `Markdown Linting`: `shutil.which("npx")` finds `npx.cmd`, but
  `subprocess.run(["npx", ...], shell=False)` raises `FileNotFoundError` on
  Windows (CPython's `CreateProcess` does not resolve `.cmd` shims without a
  shell). Independently verified clean: direct `npx markdownlint-cli2`
  invocation against the 26 changed markdown files reports 0 issues (21
  actually linted after the repo's own `.markdownlint-cli2.yaml`
  exclusions for `.github/agents/**/*.agent.md` and `.agents/**`, both
  pre-existing and unrelated to this diff).
- `Lefthook Installed`: the binary is present and functional; the gate fails
  because `lefthook install --reset-hooks-path` was never run in this
  checkout. Not run here: it mutates `.git/config` (`core.hooksPath`) and
  `.git/hooks`, a persistent local environment change outside the read-only
  validation mandate for this pass.

### Session log validator: protocol vs. schema (item 11, separated as required)

```text
uv run --python 3.14.5 python scripts/validate_session_json.py <log>
# => FAIL: 13 incomplete MUST items (7 sessionStart, 6 sessionEnd) + empty QA evidence path

uv run --python 3.14.5 python scripts/validate_session_json.py --creation-mode <log>
# => PASS

uv run --python 3.14.5 python scripts/validate_session_json.py --existing-log <log>
# => PASS
```

The schema/shape of the log is valid (both non-protocol modes pass cleanly).
The FAIL in default/full mode is entirely session end-state incompleteness
(the session-start and session-end checklists were never marked complete,
and no QA evidence path is recorded in the log itself), not a defect in the
four reviewed agent prompts. This QA report, once saved, is available to be
cited as the `qaValidation` evidence, but the session log itself still needs
its checklist fields updated by whoever closes the session.

### Coverage Gaps

| Gap | Reason | Priority |
|-----|--------|----------|
| ADR-057 live before/after eval | No `ANTHROPIC_API_KEY`; not attempted (explicit instruction: do not spend GitHub Models tokens; `--provider github-models` would be the only path with `gh` auth present, and was correctly not exercised) | P1 - required before merge per ADR-057 for behavioral prompt changes |
| `model-rationale` field for `code-reviewer`'s `opus` pin | New pin, no grandfather exemption, advisory-only today | P1 - fix before this gate flips to enforce |
| Session log protocol checklist | 13 MUST items incomplete | P1 - blocks clean session close, not a content defect |

## Recommendations

1. Add a `model-rationale` field to `.claude/agents/code-reviewer.md`'s
   frontmatter (and mirror to every install copy) before merge; this is the
   one new, real, diff-caused compliance gap this pass found that the prior
   QA pass missed entirely.
2. Rebase/merge this branch onto current `origin/main` before the next
   validation pass; it is now 2 commits behind, which is the direct cause
   of the `memory-index-count-ratchet` failure.
3. File the merge-tree-ratchet ruff-count materialization defect
   (Finding 2) as its own issue: it is reproducible independent of any
   branch content and will falsely flag every branch validated on this
   environment until `scripts/ci/merge_tree_materialization.py` or the
   `ruff` invocation inside it is fixed.
4. Run the ADR-057 live eval (`eval-prompt-change.py`, no `--dry-run`) once
   credentials are available; this pass only validated dry-run structure.
5. Complete the session-start/session-end protocol checklist on the active
   session log, or split it, before that session closes.

## Verdict

```text
Promised: Run the 12-item validation set against the current branch state
  (committed + uncommitted + untracked) after the internal-path fix, without
  committing, amending, resetting, or hand-editing generated files; report
  commands, exit codes, whether any diff-caused failure remains, whether
  fully done, and blockers/questions. Update the todos SQL row if a database
  is present.
Delivered: All 12 items executed with documented commands and exit codes.
  Items 1, 2, 4, 6, 7, 8, 9, 10 pass cleanly. Item 3 passes when correctly
  scoped (default scoping is a documented, pre-existing tool limitation).
  Item 5's grep confirms Finding 1 (the internal-path citation) is fixed.
  Item 11 is schema-valid but protocol-incomplete (session end-state gap,
  not a prompt defect). Item 12 (pre_pr.py) shows 47/51 passing; all 4
  failures are environment/scoping artifacts, independently re-verified with
  corrected root causes for two of them versus the prior QA report. One
  new, real, diff-caused gap was found and was NOT in the prior report: the
  new code-reviewer agent's `model: opus` pin lacks a required
  `model-rationale` field (ADR-080), currently advisory-only but would hard
  fail under `--mode enforce`.
  No SQL database was found in this repository backing a `todos` table
  (searched for `.db` files and a `sqlite3` binary; found neither), so the
  requested `UPDATE todos SET status = ...` could not be executed.
Gap: model-rationale field missing (Finding 3, new). Branch is 2 commits
  behind origin/main (memory-index ratchet). ADR-057 live eval not run (no
  credentials, and instructed not to spend tokens). Session protocol
  checklist incomplete (pre-existing, not this diff's content).
Result: FAIL (one real, diff-caused, fixable gap remains: the missing
  model-rationale field; everything else is either already fixed, a
  pre-existing environment/tooling artifact independently reproduced and
  root-caused here, or explicitly out of scope for this pass)
```

**Status**: FAIL
**Confidence**: High
**Rationale**: The internal-path fix (prior Finding 1) is verified fixed
across three independent methods. However, this fresh pass found one new,
real, diff-caused compliance gap the prior QA report missed (missing
`model-rationale` on the new agent's `opus` pin), and corrected two
root-cause claims in the prior report's environment-failure analysis with
direct reproduction of the exact production code paths. No diff-caused
content defect remains in the four reviewed agent prompts themselves beyond
the model-pin metadata gap; the four `pre_pr.py` failures and the session-log
protocol failure are environment/scoping artifacts unrelated to the reviewed
prompts' content.
