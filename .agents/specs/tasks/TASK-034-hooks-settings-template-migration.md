---
type: task
id: TASK-034
title: Hooks and settings move to templates/hooks/, .github/hooks/*.json binplaced for the first time (B4)
status: todo
priority: P1
complexity: L
source: ADR-109
related:
  - REQ-026
  - DESIGN-025
  - TASK-031
  - TASK-032
  - TASK-033
created: 2026-09-11
updated: 2026-09-11
author: spec
---

# TASK-034: Hooks and settings move to templates/hooks/, .github/hooks/*.json binplaced for the first time (B4)

## Objective

Create `templates/hooks/` scoped to the hooks CLASS, not every file under `.claude/hooks/`: 16 files (measured with `git ls-files .claude/hooks | wc -l` returning 23 total, tracked, not a directory walk which also picks up untracked `__pycache__` byproducts) are the class: 13 executable scripts (`git ls-files .claude/hooks | grep -cE '\.(py|sh)$'`), `hooks.json`, `dispatch_groups.json`, and `PreToolUse/markdownlint-safe-config.yaml` (a hook's own configuration file), plus a separate settings template for `.claude/settings.json` (outside `.claude/hooks/` entirely). The remaining 7 files under `.claude/hooks/` are documentation (`AGENTS.md`, five `CLAUDE.md` files, one `README.md`) and stay hand-maintained, outside this task's class, until a later task's owner-approved scope widening names them. Build a new `build/scripts/hook_templates.py` compile module (byte copy for scripts, a render for `.claude/settings.json` and `hooks.json`) that renders the hooks class into `src/claude/hooks/` and `src/claude/hooks.json` for the first time, closing the plugin-tree gap ADR-109 section 2 names and B1 does not fill; wire `generate_hooks.py` and `generate_dispatcher.py` to compile first; bin-place that plugin tree into `.claude/hooks/` and, for the first time, into `.github/hooks/*.json`, since that path does not exist in this tree today (`ls .github/hooks` fails).

## In/Out of Scope

In scope: `templates/hooks/` as canonical source for the 16-file class (13 executables, `hooks.json`, `dispatch_groups.json`, `markdownlint-safe-config.yaml`); a separate settings template for `.claude/settings.json`; the hooks compile module, rendering into `src/claude/hooks/<event>/<script>` and `src/claude/hooks.json` (the plugin tree ADR-109 section 2 names, not yet delivered by any earlier task); `.claude/hooks/` (class members only) binplaced from `src/claude/hooks/`, and `.claude/settings.json` rendered straight from `templates/hooks/settings.tmpl` with no plugin-tree hop; `.github/hooks/*.json` as a new binplace output; widening `OWNED_PREFIXES` to include `.claude/hooks/` and `.github/hooks/`; the runtime-contract test that Copilot CLI's interactive CLI and cloud agent both load the binplaced file; the owner's ruleset decision on code-owner review for this task, recorded in the PR.

Explicitly out of scope within `.claude/hooks/`: the 7 doc files; they are not part of the hooks class this task defines and are not moved, templated, or binplaced by this task.

Out of scope: ADR-097's decision that both plugin `hooks.json` files register nothing; this task does not reopen what a plugin registers, only where the repo-local file lands. Agents, rules, skills, lib, marketplace switch.

## Acceptance Criteria

- [ ] `find templates/hooks -type f | wc -l` matches the class scope: 13 executables, `hooks.json`, `dispatch_groups.json`, and `markdownlint-safe-config.yaml` (16), plus one settings template (17 total under `templates/hooks/`); `git ls-files .claude/hooks | wc -l` (23) minus the templated 16 leaves the 7 doc files hand-maintained and unchanged by this task.
- [ ] `find src/claude/hooks -type f | wc -l` returns 15 (13 executables, `dispatch_groups.json`, `markdownlint-safe-config.yaml`); `test -f src/claude/hooks.json` exits 0; both render for the first time in this tree.
- [ ] `git diff --exit-code -- .claude/hooks .claude/settings.json` exits 0 after `uv run python build/scripts/build_all.py` runs on a clean checkout, confirming the binplace copy from `src/claude/hooks/` reproduces `.claude/hooks/`'s class members exactly.
- [ ] `grep -n "OWNED_PREFIXES" -A 8 build/scripts/build_all.py` lists `.claude/hooks/` and `.github/hooks/` in the tuple; symlinking either and running `uv run python build/scripts/build_all.py --check` exits 2.
- [ ] `ls .github/hooks/*.json` lists at least one file where it previously failed with "No such file or directory".
- [ ] A new runtime-contract test (extending `tests/build_scripts/test_generate_hooks_runtime_contract.py`'s pattern) generates `.github/hooks/*.json`, runs the emitted command under the Copilot cloud-agent contract (cwd set to the working directory, `bash` as the only honored interpreter, per `.claude/skills/agent-harness-reference/references/official-hook-contracts.md`), and asserts the vendored script is found, with a negative control proving a bare relative command fails the same harness.
- [ ] `uv run python build/scripts/build_all.py --check` exits 2 after a hand edit to any file under `.claude/hooks/`, `.claude/settings.json`, or `.github/hooks/`, and the hand edit is still present afterward.
- [ ] `templates/platforms/binplace.yaml` gains the `hooks` row (scoped to `src/claude/hooks/` directory), the `hooks-json` row (scoped to `src/claude/hooks.json` root file), and the `settings` row (with `plugin_tree: null`, since `.claude/settings.json` ships in no plugin per ADR-109 section 3). A manifest test asserts that the root `hooks.json` file is mapped to `.claude/hooks/hooks.json`.
- [ ] `_Gate("Hook Template Drift", ...)` appears in `scripts/validation/pre_pr_sequence.py`'s registry and in `tests/validation/test_pre_pr_sequence_registry.py`'s `EXPECTED_ORDER`.
- [ ] The PR body records the owner's ruleset decision on whether `require_code_owner_review` becomes `true` on the default-branch ruleset before this task's writes land, per ADR-109's Negative consequences.
- [ ] `.github/CODEOWNERS` gains an entry for `/templates/hooks/`.
- [ ] No em dash or en dash in any changed file; `uv run python scripts/validation/pre_pr.py` reports no BLOCKING finding.

## Files Affected

| File | Action | Description |
|---|---|---|
| `templates/hooks/<event>/<script>` (13 executables), `templates/hooks/hooks.json`, `templates/hooks/dispatch_groups.json`, `templates/hooks/PreToolUse/markdownlint-safe-config.yaml`, plus one settings template (17 files total) | Create | Canonical source, current content of each unchanged; the 7 doc files under `.claude/hooks/` are not created here |
| `build/scripts/hook_templates.py` | Create | `discover`, `owned_targets`, `compile_all`: byte copy for scripts into `src/claude/hooks/`, JSON render for `src/claude/hooks.json` and `.claude/settings.json` |
| `build/scripts/generate_hooks.py`, `generate_dispatcher.py` | Modify | Compile step before existing mirror-generation logic |
| `templates/platforms/binplace.yaml` | Modify | Add the `hooks` row (`plugin_tree: src/claude/hooks`, `install_tree: .claude/hooks`, plus the `.github/hooks/*.json` install target) and the `settings` row (`plugin_tree: null`, straight to `.claude/settings.json`) |
| `build/scripts/build_all.py` (`OWNED_PREFIXES`) | Modify | Widen to include `.claude/hooks/` and `.github/hooks/` |
| `tests/build_scripts/test_hook_templates.py` | Create | Positive, negative, edge cases for byte-copy and JSON-render paths |
| `tests/build_scripts/test_generate_hooks_runtime_contract.py` | Modify | Extend with the `.github/hooks/*.json` cloud-agent contract case and its negative control |
| `scripts/validation/checks_portability.py`, `pre_pr_sequence.py`, `pre_pr.py` | Modify | `Hook Template Drift` gate wrapper, `_Gate` row, facade re-export |
| `tests/validation/test_pre_pr_sequence_registry.py` | Modify | `EXPECTED_ORDER` entry |
| `.github/CODEOWNERS` | Modify | `/templates/hooks/` entry |
| `.agents/governance/GENERATOR-FILES.md` | Modify | New generated-trees row for hooks and settings |

## Implementation Notes

- No mustache grammar for this class: hooks are Python and JSON, per ADR-109 section 6 ("the compile is a byte copy for scripts and a render for `settings.json` and `hooks.json`, the drift gate is byte comparison, and ADR-108's mustache grammar applies to the markdown classes only"). Do not import `skill_template_grammar` into `hook_templates.py`.
- This is the first task to render `src/claude/hooks/` and `src/claude/hooks.json`; neither exists before this task, since B1 (TASK-031) delivers only `src/claude/agents/`. The binplace step's copy of `src/claude/hooks/` into `.claude/hooks/` is the same two-hop shape agents and (after TASK-033) skills already use.
- `.claude/settings.json` ships in no plugin (repo-local Claude Code configuration); its manifest row carries `plugin_tree: null` and copies straight from its template to `.claude/settings.json`.
- This is the first task in the migration order that writes executable configuration Copilot CLI's cloud agent reads; size the review accordingly. Name the blast radius in the PR description per `.claude/rules/generated-artifacts.md`'s "size the blast radius before you ship" guidance.
- Atomic commits, five or fewer authored files each: templates in two batches (hook scripts, then the settings and hooks.json templates); compile module plus generator wiring (3 files); manifest rows (1 file); runtime-contract test extension (1 file); pre_pr wiring plus registry test (4 files); CODEOWNERS and governance (2 files).

## Testing Requirements

Positive: every hook script byte-identical to its template, rendered first into `src/claude/hooks/` then binplaced into `.claude/hooks/`; rendered `settings.json` and `src/claude/hooks.json` match a fixture. Negative: a malformed JSON template (invalid after render) exits 2. Edge: a hook script with no corresponding template during migration is untouched. Contract: the extended runtime-contract test proves `.github/hooks/*.json` resolves under the Copilot cloud-agent's real environment contract, not merely that the generator emits the expected literal command.

## Dependencies

TASK-031, TASK-032, TASK-033 merged. ADR-109 section 7 places hooks and settings after the remaining skills batch, before lib.
