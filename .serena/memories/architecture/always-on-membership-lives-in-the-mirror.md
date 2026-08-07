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
the number. The two destination trees agree today, measured on this branch after the universal rule gained the same-checker item:

| Tree | Consumer | Always-on |
|---|---|---|
| `.github/instructions` | Copilot in this repository | 8 rules, 71,484 bytes |
| `src/copilot-cli/instructions` | the shipped plugin, installed elsewhere | 8 rules, 71,484 bytes |

Membership is identical: `builder-ethos`, `claude-model-patches`, `code-quality`,
`knowledge-persistence`, `lsp-first`, `search-before-building`, `universal`,
`voice`.

Those bytes are whole generated files, frontmatter included. The same eight
rules measure 71,619 bytes at `.claude/rules/`, 135 more, because the generator
drops `priority:` and turns `paths:` or `alwaysApply:` into `applyTo:`. Name the
tree whenever you quote a figure; a gap of about that size is a basis mismatch,
not staleness.

That agreement is recent. Until issue #4317 closed, the generator universalized
a rule whose scope was entirely internal, which made `governance`,
`secret-redaction`, and `session-logs` always-on in the plugin and cost a vendor
install 7,532 bytes a turn on three rules pointing at `.agents/` paths the
installing repository does not have. PR #4426 replaced that fallback with an
explicit skip, so those rules are absent from the plugin tree rather than
universalized in it. The plugin ships 23 instruction files against 27 in
`.github/instructions`, and that gap is the fix, not drift.

`tests/validation/test_always_on_corpus_claims.py` pins the two trees together
and pins the figures on this page against a live measurement, so the convergence
is a guarded invariant rather than a coincidence, and these numbers cannot go
stale without turning a test red.

## Why the source cannot answer it

`build/scripts/generate_rules.py` reaches `applyTo: "**"` four ways. Only the
first leaves a line in the source file that a grep can find.

1. The source declares `paths: ["**"]` or `applyTo: '**'`. Renamed verbatim
   (`build/scripts/generate_rules.py:24`).
2. The source declares `alwaysApply: true` and no path scope. Line 25 drops
   `alwaysApply:`, which leaves no scope, so case 3 fires.
3. The source declares no scope at all. Lines 338-341 synthesize `**`:

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

Cases 2 and 3 are one branch, not two. `_has_path_scope` (line 209) reads only
the path-scope keys, so `alwaysApply` never sets `had_scope`.

## The footgun

Case 4 inverts intent. Narrowing a rule to `.claude/**` reads like a reduction in
scope and silently widens it to every turn in the shipped plugin. The generator
prints `WARNING: dropped internal-only glob from applyTo` to stderr, and nobody
reads stderr during a build.

Cases 3 and 4 are why a source-tree measurement is not merely conservative. It
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

# Pass the tree you actually mean. They do not agree.
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

## Related

- `.claude/rules/canonical-source-mirror.md`, section "The one place the mirror
  outranks the source: always-on membership".
- `.claude/skills/context-optimizer/references/model-context-doctrine.md`, which
  carries the measured corpus figures.
- `.agents/architecture/ADR-088-progressive-disclosure-book-rules.md`. Its
  always-on list is stale as of #4424 and needs a human decision to correct.
