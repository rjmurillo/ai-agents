# Plugin descriptions carry no component counts

## Question

Should CI gate the descriptions this repository publishes for its plugins, and
if so, what exactly should it assert?

## Conventional answer

Two obvious framings, both wrong here.

The first is "recompute the count and check it." That is what
`validate_marketplace_counts.py` did. It asserted a hard-coded component count
matched what was on disk, so every PR that added or removed an agent broke an
unrelated check and forced a fix commit (#2148). PR #2187 retired it.

The second is "make the marketplace entry and the plugin manifest agree." That
one is intuitive, and it is what the first draft of this gate did. It is not
supported.

## First-principles position

The real defect is not disagreement between two copies. It is that a description
embeds a number nothing recomputes. The number is stale the moment a component
is added or removed, and no reader can tell whether it was ever true.

So the gate asserts the narrow, verifiable thing: **no published description
embeds a component count.** It counts nothing and derives nothing, so it stays
silent on every PR that adds or removes a component. That is precisely the
property the retired validator lacked.

## Evidence

**The decision is real and cited.** PR #2187, commit `2043c39863`
(2026-06-01), is titled "strip drifting component counts and retire the count
validator." `git show 2043c39863` shows it rewrote descriptions in exactly two
files, `.claude-plugin/marketplace.json` and `.github/plugin/marketplace.json`.
It never touched `src/claude/.claude-plugin/plugin.json`, which kept publishing
`25 specialized agent definitions with templates and governance for Claude Code`.

The number was already wrong before the sweep ran. Commit `cb7a9f9b01`
(2026-05-31) converted the spec-generator agent into a skill and deleted
`.claude/agents/spec-generator.md`, taking the catalog from 25 to 24. #2187
landed the next day and corrected both marketplace files. The manifest was
missed and has carried the wrong number on main for **57 days** and counting;
issue #3651 is open and this is the change that closes it.

The lesson is about the direction of the drift. The count did not go stale
because someone added a component. It went stale because someone removed one,
which is the case nobody thinks to check.

**The equality invariant was tested and failed.** Two claims were offered for it
and both collapsed under adversarial review:

1. *"The pairs are the same sentence, so equality was intended."* At
   `2043c39863` the `claude-agents` pair read "Specialized agent definitions with
   templates and governance for Claude Code" against "25 specialized agent
   definitions ...". Textual similarity shows the count should be deleted. It
   does not show that all future descriptions must stay byte-identical.
2. *"PR #3559 independently converged on the same string."* False.
   `git show e99659d1cc^:src/copilot-cli/.claude-plugin/plugin.json` proves that
   branch already carried the string before #3559 did any work. Main had
   regressed; the merge restored pre-existing text. Nobody derived anything.

**Upstream permits the two to differ.** The marketplace docs
(code.claude.com/docs/en/plugin-marketplaces) state a plugin entry "can include
any field from the plugin manifest schema," meaning entries carry catalog
metadata in their own right. Under `strict: false` the entry is the entire
definition and the plugin may legitimately ship no `plugin.json` at all, so a
gate that resolves every entry to a manifest reports a config error on a valid
marketplace.

**Equality and countlessness are in direct tension, and the repo picked
countlessness.** Walking every mainline commit that touched
`src/claude/.claude-plugin/plugin.json` (38 commits) finds exactly four where the
entry and manifest descriptions agree: `645f868915` and `2e85005e0f` (both
publishing `23 specialized agent definitions ...` on both sides) and `178a898a9a`
and `60c363c5e1` (both publishing `25 specialized ...`).

The pairs agreed only while both copies carried a count. #2187 then deleted the
count from the marketplace copies and left the manifests alone, which is what
broke the agreement. Equality was not lost by accident; it was traded away to get
rid of the counts. A gate that restores equality would therefore reverse the
decision it claims to enforce.

Reproduce with `git log --format=%H origin/main -- src/claude/.claude-plugin/plugin.json`
and compare the `claude-agents` entry against the manifest at each commit.

## Decision

`build/scripts/check_plugin_manifest_parity.py` gates two things:

1. `check_version_parity`: the two project-toolkit manifests carry the same
   version (pre-existing, #2222).
2. `check_description_counts`: no description in `_DESCRIBED_FILES` embeds a
   component count. Covers both marketplace files, including their top-level
   description and every entry, plus all three plugin manifests.

Entry-to-manifest equality is **not** gated, and the docstring says so and why.

## Operational facts

- The pattern is a count token, digits or spelled out, then at most **three**
  intervening words, then a component noun that may be **singular or plural**.
  Both bounds are pinned by tests: three words must match (`12 production-ready
  specialized review agents`), four must not. Singular is accepted because the
  count is what goes stale, not the grammar (`1 agent`, `25-agent toolkit`).
  `one` is in the token set; only the partitive `one of the skills` is excluded,
  by a `(?!of\b)` guard on the intervening words rather than by dropping the
  token. The separator between all of these is `[-\s]+`, so a hyphen reads as a
  word break and `twenty-odd agents` is a count.
- Dropping source resolution deleted the whole path-traversal, `pluginRoot`, and
  containment surface. There is no longer any path built from marketplace input.
- `_read_manifest` catches `(OSError, UnicodeDecodeError, ValueError,
  RecursionError)`. `json.JSONDecodeError` subclasses `ValueError`, and CPython's
  integer digit cap raises a bare `ValueError` on syntactically valid JSON.
- Exit codes follow ADR-035: 1 is staleness, 2 is a malformed or missing file.
- `tests/test_check_plugin_manifest_parity.py` parameterizes over
  `_DESCRIBED_FILES` by index, so dropping any configured file fails a test
  instead of passing silently. Twelve mutations were run against the gate and
  all twelve were killed.

## Refs

Issues #3651, #3645, #2148, #2222. PRs #2187, #3507, #3559.
Concept: "Release Scripts Need Staged Closure."
