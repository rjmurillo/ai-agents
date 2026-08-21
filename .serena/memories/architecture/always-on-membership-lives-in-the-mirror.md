# To Learn Which Rules Are Always-On, Parse the Mirror, Not the Source

## The contradiction

This repository's dominant convention is that the canonical source wins and a
generated mirror is never authoritative. `.claude/rules/canonical-source-mirror.md`
is a whole rule file devoted to it, and `.claude/rules/generated-artifacts.md`
forbids hand-editing a mirror at all.

For exactly one question that convention is backwards.

The question is which rules load on every agent turn. A rule is always-on when
its **generated** `applyTo` resolves to `**`, so the answer lives in the
generated tree. Parsing `.claude/rules/*.md` gives a wrong answer, wrong in both
directions.

There is also no single answer per tree by default, so always name the tree with
the number. The two destination trees agree today, measured on this branch after `session-logs` dropped its optional-session-log mention from `knowledge-persistence`:

| Tree | Consumer | Always-on |
|---|---|---|
| `.github/instructions` | Copilot in this repository | 7 rules, 70,269 bytes |
| `src/copilot-cli/instructions` | the shipped plugin, installed elsewhere | 7 rules, 70,269 bytes |

Membership is identical: `builder-ethos`, `claude-model-patches`, `code-quality`,
`knowledge-persistence`, `search-before-building`, `universal`, `voice`.

Those bytes are whole generated files, frontmatter included. The same seven
rules measure 70,385 bytes at `.claude/rules/`, 116 more, because the generator
drops `priority:` and turns `paths:` or `alwaysApply:` into `applyTo:`. Name the
tree whenever you quote a figure; a gap of about that size is a basis mismatch,
not staleness.

That agreement is recent. Until issue #4317 closed, the generator universalized
a rule whose scope was entirely internal, which made `governance`,
`secret-redaction`, and `session-logs` always-on in the plugin and cost a vendor
install 7,532 bytes a turn on three rules pointing at `.agents/` paths the
installing repository does not have. PR #4426 replaced that fallback with an
explicit skip, so those rules are absent from the plugin tree rather than
universalized in it. The plugin ships 23 instruction files against 28 in
`.github/instructions`, and that gap is the fix, not drift.

`tests/validation/test_always_on_corpus_claims.py` pins the two trees together
and pins the figures on this page against a live measurement, so the convergence
is a guarded invariant rather than a coincidence, and these numbers cannot go
stale without turning a test red.

The pin is narrower than it reads.
`test_doctrine_plugin_tree_figures_match_the_shipped_tree` compares the two
trees on rule count and byte total only, so a swap that preserved both would
pass. Nothing pins the names, and nothing pins which rules are in the set.

## Why the source cannot answer it

`build/scripts/generate_rules.py` reaches `applyTo: "**"` three ways. Only the
first leaves a line in the source file that a grep can find.

1. The source declares `paths: ["**"]` or `applyTo: '**'`. Renamed verbatim
   (`build/scripts/generate_rules.py:24`).
2. The source declares `alwaysApply: true` and no path scope. Line 25 drops
   `alwaysApply:`, which leaves no scope, so case 3 fires.
3. The source declares no scope at all. Lines 345-348 synthesize `**`:

   ```python
   if not had_scope and "applyTo" not in result:
       result = {"applyTo": _UNIVERSAL_SCOPE, **result}
   ```

4. The source declares a scope whose globs are **all** filtered as internal-only.
   Lines 342-344 skip the rule rather than shipping it with a widened scope:

   ```python
   applyto_value = result.get("applyTo")
   if had_scope and isinstance(applyto_value, str) and not applyto_value.strip():
       return _SCOPE_SKIPPED
   ```

   This case is **destination-dependent**.
   `templates/platforms/copilot-cli.yaml:39-40` lists `.github/instructions`
   under `keepInternalGlobsFor`, disabling the filter there, so case 4 cannot
   fire for that tree. It fires only for `src/copilot-cli/instructions`, which
   is why the plugin ships fewer instruction files. Before PR #4426 this branch
   assigned `_UNIVERSAL_SCOPE` instead of returning, which is what made narrowly
   scoped rules always-on for plugin consumers.

Four rules take that skip today: `governance`, `push-lock`,
`secret-redaction`, and `session-logs` are present in `.github/instructions`
and absent from `src/copilot-cli/instructions` altogether, which is the whole
of the 27-against-23 file gap. So the two trees hold different *rule sets*
while agreeing on the always-on subset. Membership can still diverge, by a
rule the filter does not touch gaining or losing a universal scope in one tree
only.

Cases 2 and 3 are one branch, not two. `_has_path_scope` (line 209) reads only
the path-scope keys, so `alwaysApply` never sets `had_scope`.

## The footgun

The pruning is silent in the direction that matters now. The generator prints
`WARNING: dropped internal-only glob from applyTo` to stderr, and nobody reads
stderr during a build, so a rule can leave the plugin entirely without anyone
noticing. That is the safe failure direction, but it is still invisible.

Cases 3 and the retired case 4 are why a source-tree measurement is not merely
conservative. It
misses synthesized members, and it can count a rule whose globs were filtered
out from under it.

## Second trap: do not regex the frontmatter

A scope key may be an inline string or a YAML block list.
`.claude/rules/knowledge-persistence.md` uses the block form:

```yaml
paths:
  - "**"
```

`^applyTo:\s*(.+)$` returns nothing for that file and reports it as unscoped,
which is the exact opposite of the truth. Use `yaml.safe_load` on the
frontmatter block. This produced a wrong always-on count during the audit that
wrote this memory, and the wrong count looked plausible enough to act on.

## How to measure it

```python
import yaml
from pathlib import Path

# Pass the tree you actually mean. They can diverge even when they agree today.
TREE = ".github/instructions"  # or "src/copilot-cli/instructions"

always_on = []
for p in sorted(Path(TREE).glob("*.instructions.md")):
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---"):
        continue
    fm = yaml.safe_load(text.split("---", 2)[1]) or {}
    scope = fm.get("applyTo")
    globs = [scope] if isinstance(scope, str) else list(scope or [])
    if "**" in globs:
        always_on.append(p.stem.removesuffix(".instructions"))
```

## Where this is enforced

`tests/validation/test_always_on_corpus_claims.py` measures the corpus this way
and fails when a shipped document drifts from it. Added because PR #4424
narrowed `pragmatic-programmer` out of the always-on set and left two documents
quoting the old composition.

**Bytes you add to an always-on rule break this file.** The corpus size is
hand-written into
`.claude/skills/context-optimizer/references/model-context-doctrine.md` in six
places, and the guard reads all six. Adding 868 bytes to
`knowledge-persistence.md` on 2026-08-05 failed five at once:

```
test_doctrine_always_on_figures_match_the_measured_mirror
test_doctrine_python_figures_match_the_measured_mirror
test_doctrine_source_basis_figure_and_delta_are_consistent
test_doctrine_plugin_tree_figures_match_the_shipped_tree
test_doctrine_8kb_multipliers_match_the_measured_source_sizes
```

Four of those trip on any nonzero delta. The fifth needs enough to move a
rounded multiplier, so a small edit fails four and reads as a different problem.

The trap is *when* you find out. That file runs inside the pre-push
`python-tests` hook, which took 891 seconds in that run and is not fast in any
run. Check it in half a second instead:

```bash
uv run --frozen pytest tests/validation/test_always_on_corpus_claims.py -q
```

Each assertion message states both figures (`doctrine states X; measured Y`), so
the fix is mechanical. Three things the messages do not tell you. The
multipliers are measured at **source** basis while the corpus figures are
measured at **mirror** basis, so they move by different amounts. The doctrine is
mirrored into `src/copilot-cli/skills/context-optimizer/references/`, which is
generated: fix `.claude/`, then run `build/scripts/generate_skills.py`; editing
the mirror by hand trips the drift gate instead. And the guard's six regexes
(`tests/validation/test_always_on_corpus_claims.py:194-208`) do not cover every
number in the document. The book-rule percentage and the per-rule byte table go
stale silently. Recompute those by hand in the same edit.

## Related

- `.claude/rules/canonical-source-mirror.md`, section "The one place the mirror
  outranks the source: always-on membership".
- `.claude/skills/context-optimizer/references/model-context-doctrine.md`, which
  carries the measured corpus figures.
- `.agents/architecture/ADR-088-progressive-disclosure-book-rules.md`. Its
  always-on list is stale as of #4424 and needs a human decision to correct.
