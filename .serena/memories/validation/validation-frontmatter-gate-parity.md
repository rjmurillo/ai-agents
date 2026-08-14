---
name: validation-frontmatter-gate-parity
description: "Guard parity rule (issue #4918): copy the canonical parser's own delimiter pattern, never an approximation of it"
type: feedback
---

# Validation: A Frontmatter Gate Must Copy the Parser, Not Approximate It

**Statement**: When a validator exists to stop what another tool only warns
about, it must reuse that tool's own detection pattern verbatim. An
approximation that looks equivalent produces false negatives, and a gate with
false negatives is decorative.

**Context**: Writing a CI or hook gate that mirrors a runtime loader, parser,
or validator.

## Evidence (issue #4918, PR #5004)

Two distinct defects, one incident:

1. `.serena/memories/implementation/implementation-008-spec-schema-validation.md`
   carried an unquoted `description` whose value contained a colon-space:
   `... (REQ/DESIGN/TASK): read spec-schemas.md first`. YAML reads
   `(REQ/DESIGN/TASK): read ...` as a nested mapping, `frontmatter.loads`
   raised `yaml.YAMLError`, and `serena_integration._extract_metadata` caught
   it, printed `Warning: malformed YAML frontmatter, treating as plain
   markdown` to stderr, and dropped the file's `name` and `type`. A warning on
   stderr fails nothing, so the corruption merged and sat on main.

2. The first gate written to stop recurrence keyed on `line == "---"`. The
   parser it mirrors, python-frontmatter's `YAMLHandler`, uses
   `FM_BOUNDARY = re.compile(r"^-{3,}\s*$", re.MULTILINE)`, and
   `frontmatter.parse` normalizes with `text = u(text, encoding).strip()`
   before matching. A file opening with `----`, or with a blank first line,
   therefore had real, broken frontmatter to the loader (which warned) and no
   frontmatter at all to the gate (which passed). A differential probe over 16
   shapes found three false negatives; asserting the gate flags every shape the
   real parser raises on now guards it.

## Mirror Both Directions

Copying the pattern closes only the false negatives you thought to probe. Two
more came from review:

- **Pin the constant, not just the behavior.** Fixed-input tests stay green
  when upstream changes a pattern that still matches those inputs. Assert
  `local.pattern == canonical.pattern` so the drift itself fails.
- **A valid block behind a BOM is lost too.** `FM_BOUNDARY.match` fails on
  `\ufeff---`, so the loader reads the file as plain Markdown and drops
  metadata with no warning at all. A gate that only flags BOM-plus-malformed
  leaves the silent case open. Ask what the mirrored tool does with the
  *valid* input, not only the broken one.
- **Split lines the way the pattern anchors.** `str.splitlines()` breaks on
  `\v`, `\f`, `\x85`, `\u2028` and more; `re.MULTILINE` anchors only around
  `\n`. Splitting more widely invents delimiters the parser cannot see.

## Pattern

- Quote any YAML scalar containing `: `. Unquoted colon-space is the single
  most common frontmatter corruption.
- Before mirroring a tool, open its source and copy the constant. Quote it in a
  comment beside your copy so the next reader can diff the two.
- Test the mirror against the real dependency, not a restatement of it. Driving
  `frontmatter.loads` in the test means an upstream pattern change fails the
  test instead of silently reopening the gap.
- A warning that no gate reads is not a control. Decide whether the condition
  fails the build, then make it fail.

## Related

- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-tooling-patterns](validation-tooling-patterns.md)
