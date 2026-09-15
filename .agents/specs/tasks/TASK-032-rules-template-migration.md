---
type: task
id: TASK-032
title: Rules move to templates/rules/, new compile module, binplace manifest row (B2)
status: todo
priority: P1
complexity: M
source: ADR-109
related:
  - REQ-026
  - DESIGN-025
  - TASK-031
created: 2026-09-11
updated: 2026-09-11
author: spec
---

# TASK-032: Rules move to templates/rules/, new compile module, binplace manifest row (B2)

## Objective

Create `templates/rules/<name>.md` for all 30 rule files, a new `build/scripts/rule_templates.py` compile module reusing `skill_template_grammar.py`'s render and grammar functions, and wire `generate_rules.py` to compile before its existing mirror generation. Add the `rules` row to the binplace manifest.

## In/Out of Scope

In scope: `templates/rules/` as canonical source for all 30 rules; the rules compile module; `generate_rules.py`'s new compile step; the manifest's `rules` row (`.claude/rules/` as the install-tree target); the drift gate; symlink and containment checks for `.claude/rules/<name>.md`.

Out of scope: agents (TASK-031, done), skills beyond the existing 18 (TASK-033), hooks and settings (TASK-034), lib (TASK-035), marketplace switch (TASK-036). No rule's content changes; every template is the current file's text, unchanged.

## Acceptance Criteria

- [ ] `ls templates/rules/*.md | wc -l` equals `ls .claude/rules/*.md | wc -l` (30).
- [ ] `git diff --exit-code -- .claude/rules` exits 0 after `uv run python build/scripts/build_all.py` runs on a clean checkout.
- [ ] `uv run python build/scripts/build_all.py --check` exits 2 after a hand edit to any file under `.claude/rules/`, and the hand edit is still present afterward (nothing was overwritten by the failing check).
- [ ] `git diff --exit-code -- .github/instructions src/copilot-cli/instructions` exits 0 (the existing Copilot mirror, generated from `.claude/rules/` unchanged, still matches after the compile step is inserted upstream of it).
- [ ] `uv run pytest tests/build_scripts/test_rule_templates.py -v` passes: a rendered-fixture positive case, a disallowed-tag negative case, an untemplated-rule edge case (not expected once all 30 land, but the discovery function is tested against it), and a symlinked `.claude/rules/<name>.md` negative case.
- [ ] `templates/platforms/binplace.yaml` gains the `rules` row; `tests/build_scripts/test_binplace_manifest.py` still passes with three active rows (`agents`, `skills`, `rules`; TASK-031 ships the manifest with `agents` and `skills` active, not `agents` alone).
- [ ] `grep -n "OWNED_PREFIXES" -A 8 build/scripts/build_all.py` lists `.claude/rules/` in the tuple; symlinking `.claude/rules/` and running `uv run python build/scripts/build_all.py --check` exits 2 (issue #4632's unreachable-owned-path check, widened per class per REQ-026 criterion 14).
- [ ] `_Gate("Rule Template Drift", ...)` appears in `scripts/validation/pre_pr_sequence.py`'s registry and in `tests/validation/test_pre_pr_sequence_registry.py`'s `EXPECTED_ORDER`.
- [ ] `.github/CODEOWNERS` gains an entry for `/templates/rules/`.
- [ ] `.agents/governance/GENERATOR-FILES.md` gains a row for the rules compile step; the "no `templates/rules/` tree exists" state ADR-109 records in its Context section no longer holds.
- [ ] No em dash or en dash in any changed file; `uv run python scripts/validation/pre_pr.py` reports no BLOCKING finding.

## Files Affected

| File | Action | Description |
|---|---|---|
| `templates/rules/<name>.md` (30 files) | Create | Canonical source, current `.claude/rules/<name>.md` content unchanged |
| `build/scripts/rule_templates.py` | Create | `discover`, `owned_targets`, `compile_all`, reusing `skill_template_grammar.check_grammar` and `render` |
| `build/scripts/generate_rules.py` | Modify | Compile step before existing mirror-generation logic; module docstring cites ADR-109 |
| `templates/platforms/binplace.yaml` | Modify | Add the `rules` row (manifest already carries `agents` and `skills` from TASK-031; this brings the active count to three) |
| `build/scripts/build_all.py` (`OWNED_PREFIXES`) | Modify | Widen to include `.claude/rules/` |
| `tests/build_scripts/test_rule_templates.py` | Create | Positive, negative, edge, symlink cases |
| `scripts/validation/checks_portability.py`, `pre_pr_sequence.py`, `pre_pr.py` | Modify | `Rule Template Drift` gate wrapper, `_Gate` row, facade re-export |
| `tests/validation/test_pre_pr_sequence_registry.py` | Modify | `EXPECTED_ORDER` entry |
| `.agents/governance/GENERATOR-FILES.md` | Modify | New generated-trees row for rules |
| `.github/CODEOWNERS` | Modify | `/templates/rules/` entry |

## Implementation Notes

- No rule's paths frontmatter, content, or ordering changes; this task moves the edit location, not the text. Diff the rendered output against the pre-migration file to confirm byte-identity before committing the template.
- Because `.claude/rules/*.md` is itself the source `generate_rules.py` already reads for the Copilot instruction mirrors, this task inserts the compile step upstream of that existing read, so the mirror generation logic itself needs no change; only its input's provenance changes from hand-maintained to compiled.
- Atomic commits, five or fewer authored files each: templates in two or three batches of ten to fifteen files (well under any per-PR cap since template content is copy-only); compile module plus `generate_rules.py` (2 files); manifest row (1 file); pre_pr wiring plus registry test (4 files); governance and CODEOWNERS (2 files).

## Testing Requirements

Positive: rendered `.claude/rules/<name>.md` byte-identical to a fixture render for every one of the 30 rules. Negative: a disallowed tag or missing partial exits 2, target untouched. Edge: `discover()` on a `templates/rules/` directory missing one file still compiles the other 29 without error. Contract: the Copilot mirror (`.github/instructions/`, `src/copilot-cli/instructions/`) is unaffected, since its generator still reads `.claude/rules/` unchanged, now compiled rather than hand-maintained.

## Dependencies

TASK-031 (B1) merged: the binplace manifest and `assert_no_claude_writes`'s generalized allowlist must exist before this task adds a second row to either.
