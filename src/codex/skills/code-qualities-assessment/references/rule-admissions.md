# Rule admissions

Two rule admissions keep a raw drop in the report but stop it from failing
the gate (rjmurillo/ai-agents issue #7525). Raw scores and regression rows
stay in the JSON and on stderr either way.

## Non-redundancy

A non-redundancy drop is admitted when no line gained a copy: each line's
repeat count at head is at most its count at base. A file that only loses
unique lines passes, whatever the size of the drop. This admission is on for
every consumer and language, and has no config switch.

## Coupling (Python, opt-in)

A Python coupling drop is admitted when the change added no third-party import
root, as when local logic moves into a shared first-party module. It is off
unless the config sets `"firstPartyCouplingAdmission": {"importRoots": [...]}`.

A root is first-party only when the HEAD commit holds `<root>.py` or
`<root>/__init__.py` in one of these folders:

- the importing file's folder, or a parent folder inside the workspace
- a folder named in `importRoots`

A root the scanner's interpreter can import from its site-packages is always
third-party, so a same-named folder cannot hide an installed dependency. A
bare folder, or a module the HEAD commit does not hold, is not first-party.

In a `test_*.py` or `conftest.py` file under a `tests` folder, `pytest` does
not count as a third-party root. The test runner is not a dependency of the
code under test, so adding `import pytest` for `mark.parametrize` couples
nothing new. Any other new root in a test file still fails.

## Still failing

A new third-party root, a line that gained a copy, or any other regressed
quality still exits 10. A declined candidate prints
`NOT ADMITTED: <file>: <quality>: <reason>` on stderr.

## Fields

Each admitted quality maps to a record under `rule_admissions`:

| Quality | Rule | Fields |
| --- | --- | --- |
| `coupling` | `no_new_third_party_import` | `baseThirdParty`, `headThirdParty`: sorted import roots |
| `non_redundancy` | `no_new_duplicate_lines` | `baseDuplicateLines`, `headDuplicateLines`: counts |

Every record also carries `issue: 7525`. The review adapter reports admitted
rows as WARN. It checks the totals; the assessor enforces the per-line rule.

These rules differ from the `changeAdmissions` records in `.qualityrc.json`
(ADR-122 item 10, issue #7493). Each of those records names one file, quality,
score transition, and blob pair. The scanner writes the matched records to
`change_admissions`, a separate field.
