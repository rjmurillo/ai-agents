---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-18-session-5154-b6c2a2eed-retire-three-tool-use-hooks-vendored.json
qaCommit: b2e1e248be185d8c9e39bd274e9b53cf7ff0c53e
---

# QA report: issue #5154 tool-use hook retirement

**Branch**: `claude/remove-tool-use-hooks-ii1fob`
**Base**: `21a986b` (origin/main, merged into this branch)
**Scope**: retirement of three tool-use hooks from the vendored plugin surface,
the guard-maturity classifier stack, the ADR-068/071/082/085 amendments, and the
citation sweep that follows from them.

## What was verified

| Check | Command | Result |
|---|---|---|
| Hook and dispatcher tests | `uv run --frozen python -m pytest tests/hooks/ tests/build_scripts/ -q` | 2467 passed, 2 skipped |
| ADR-prose gates | `uv run --frozen python -m pytest tests/build_scripts/test_hook_contract_knowledge.py tests/hooks/test_adr_hook_claims.py -q` | 402 passed |
| Skills and PR-description validation | `uv run --frozen python -m pytest tests/skills/ tests/test_validation_pr_description.py -q` | 3041 passed |
| Validation suite | `uv run --frozen python -m pytest tests/validation/ -q` | exit 0 |
| Pre-PR gate suite | `uv run --frozen python scripts/validation/pre_pr.py` | exit 0, `RESULT: All validations passed`, zero BLOCKING findings |
| Generator drift | `uv run --frozen python build/scripts/build_all.py --check` | exit 0 |
| Plugin lib sync | `uv run --frozen python scripts/sync_plugin_lib.py --check` | "All plugin lib copies are in sync." |
| Skill size budgets | `uv run --frozen python scripts/validation/skill_size.py --ci` | "All skill files within size limits." |
| Markdown portability ratchet | `uv run --frozen python scripts/validation/check_skill_md_portability.py` | "No Markdown vendor-portability drift. 240 grandfathered refs across 95 files (baseline 240)." |
| Orphan references | `.claude/skills/orphan-ref-validator/scripts/scan.py` | 6 findings, 0 attributable to this change (see below) |

## Second scope: ADR-084 rule 6 and the tool-use hook bar

Added after the owner lifted the 20-commit ceiling. Rule 3 of ADR-084 is
restored to its original text; the new bar is rule 6, so no existing citation to
rule 3 changes meaning.

| Check | Command | Result |
|---|---|---|
| Full pre-PR gate, merged tree | `uv run --frozen python scripts/validation/pre_pr.py` | exit 0, `RESULT: All validations passed` |
| Rule activation coverage | `scripts/validation/check_rule_activation_coverage.py` | OK, within baseline |
| Always-on corpus claims | `pytest tests/validation/test_always_on_corpus_claims.py` | 37 passed |
| Generator drift | `build/scripts/generate_rules.py` then `build_all.py --check` | exit 0 |
| ADR-prose and hook suites, post-flip | `pytest tests/build_scripts tests/validation tests/hooks -q` | 5792 passed, 9 skipped |
| ADR-prose gates, post round-2 fixes | `pytest tests/build_scripts/test_hook_contract_knowledge.py tests/hooks/test_adr_hook_claims.py -q` | 402 passed |

adr-review round 1 returned 3 Block, 2 Disagree-and-Commit, 1 conditional
Accept. Every blocking finding is resolved and recorded in
`.agents/critique/ADR-084-rule-6-tool-use-bar-debate-log.md`. Four were defects
in the first draft that I verified against source before fixing:

- The amendment moved ADR-084's security carve-out from line 145 to 169 and
  orphaned 11 live citations to it. All 11 now cite the section anchor.
- The claim that the two tool-use events are the only per-call ones is false.
  `.claude/settings.json` registers `PostToolUseFailure` with no matcher, and
  `generate_dispatcher.py:517` omits it from `_MATCHER_EVENTS`, so it cannot be
  narrowed. The bar now covers every per-call event.
- The one-command-per-event union was attributed to Copilot. It is ours (#2342).
- The 498 ms figure is not a spawn cost: 4.9x the bare-`Bash` figure for a
  strictly narrower matcher, so it measures the guard's own work.

Known-not-fixed: no mechanical gate ships with the bar. ADR-084 rule 5's own
planned CI check is unbuilt 29 days on, measured as zero occurrences of
`Customer value:` in `scripts/`, `build/`, or `.github/workflows/`. Recorded as
an open item in the debate log rather than silently deferred.

## Behavior changes worth a reviewer's attention

**The shipped PreToolUse dispatcher no longer denies on malformed stdin.** With
the two command-scoped matchers retired, the only remaining shim matches on tool
name, and it cannot show that an unparseable payload is an Agent spawn, so it
skips. That is the documented issue #4672 fail-open policy applied to a gate
whose own docstring says it bounds model spend and is not a security boundary.
Measured directly against the shipped artifact:

- deeply nested JSON: exit 0, stderr `matcher-shim [^(Agent|Task)$]: stdin JSON nesting too deep; refusing`
- conflicting input aliases: exit 0, stderr names the conflict
- duplicate `toolCalls` keys: exit 0, stderr names the duplicate key
- oversized matched payload: exit 2, stderr names the matcher, the source field, and the 2097152-byte limit

The fail-closed path for a command-scoped matcher is still pinned by the
synthetic tests in `tests/build_scripts/test_generate_hooks_schema_security.py`.

**The generator prunes an emptied event directory.** Removing the last
PostToolUse group deletes `src/copilot-cli/hooks/PostToolUse/` outright rather
than emitting a manifest with no shims. Verified by running the generator and
inspecting the tree.

**Consumer coverage.** `invoke_markdownlint_guard.py` self-neutered in consumer
repos (`run_guard` called `skip_if_consumer_repo` before reading stdin), so its
consumer coverage was already zero. `invoke_markdown_auto_lint.py` had no such
gate, so consumer-side markdown auto-fix drops to zero with this change. Both
are recorded in ADR-085 Decisions 9 and 10.

## Known-not-fixed, with attribution

- Orphan-ref scan reports `VERDICT: CRITICAL_FAIL` with 6 findings. All six are
  `scripts/memory/update_memory_index_tokens.py` and `tests/test_new_pr.py`
  referenced from two rules and their four generated mirrors. Both targets are
  absent on `origin/main`, so the findings pre-date this branch. The three
  findings this change would have added were annotated at their source in
  `.agents/specs/tasks/TASK-015-pr-iteration-cost.md`, following the
  retired-dependency convention already in that file.
- `build/scripts/generate_hooks_events.py` carries a `taste-lint: ignore
  file-size` suppression with its rationale. The file was 1377 lines at
  `599b9ee` and is 1365 here; the gate blocks any commit touching it, so the
  improvement could not land without the suppression.
- `docs/getting-started.md:63` and `docs/installation.md:74,86` advertise hook
  counts (29 Claude, 28 Copilot) that were already wrong before this change: the
  tree held 22 and 8 Python hook files. No gate checks them. Not corrected here
  because the intended counting method is unclear.
- The vendor-provenance workflow and validator pin three paths that do not exist
  in the tree: `.claude/hooks/PreToolUse/_markdownlint_verifier.py`,
  `.claude/hooks/PreToolUse/_vendor/**`, and
  `.claude/hooks/PreToolUse/markdownlint-cli2.yaml`. Pre-existing and unrelated
  to this change; `markdownlint-safe-config.yaml`, which that pipeline does pin
  and which does exist, was deliberately kept for exactly that reason.

## Full-suite status

`uv run --frozen python -m pytest tests/ -q` completed with exit 0 on the same
tree contents before the commits were restructured. Re-runs since then hit the
local 15-minute command cap rather than a test failure. The pre-push
`python-tests` job runs the same suite under a 30-minute budget and is the
authoritative gate.
