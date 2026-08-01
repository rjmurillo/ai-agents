# Backticking a broken path is concealment, not repair

**Date**: 2026-07-31
**Primary failure mode**: #4 False completion markers
**Secondary failure mode**: #9 Confident-incorrectness recurrence
**Severity**: Medium
**Evidence**: PR #4136, commits `baf01459d8` (defect) and `a556a269df` (repair)

## What happened

PR #4136 converted twenty root-escaping Markdown links inside plugin roots into
backticked paths, following `plugin-self-containment` SHOULD 2. The description
reported all twenty as handled.

Three of those citations pointed at a file that does not exist:

```
cited:  .serena/memories/memory-size-001-decomposition-thresholds.md
actual: .serena/memories/memory/memory-size-001-decomposition-thresholds.md
```

Wrapping the citation in backticks removed it from the link scanner's view.
The scanner count dropped, the gates went green, and the description claimed a
fix. The path was still wrong. The same unverified path was then copied into a
newly written `vendor-portability` declaration, so the rule artifact itself
named a file that does not exist.

A second finding in the same review: `session/SKILL.md` cites an ADR by exact
filename while its declaration named only the containing directory. The PR
description called this "one judgment call left open ... a question about the
rule's wording." The rule's wording is not ambiguous. MUST 1 requires the
declaration to name that path.

## Root cause

Two distinct causes, one shared shape.

**Adopting the tool's definition of done.** The scanner defines "fixed" as "no
longer counted." A reader defines it as "the path resolves." SHOULD 2's
transform is correct for a path that exists but does not ship to a consumer. It
is not correct for a path that does not exist at all. The transform was applied
mechanically to a list of scanner hits without checking that precondition on
any entry, so a broken path was laundered into a compliant-looking citation.

**Asserting ambiguity instead of reading the text.** Framing the ADR
declaration as a wording question produced a comfortable non-answer. Reading
MUST 1 took under a minute and produced an unambiguous violation.

## Detection gap

No gate catches this. Measured on this branch by adding the matched path
`.agents/this-path-does-not-exist.md` to both shipped copies of a declared
skill:

| Gate | Exit code with a nonexistent declared path |
|---|---|
| `check_vendor_portability` | 0 |
| `check_skill_portability` | 0 |
| `check_skill_md_portability` | 0 |
| `check_skill_md_exec_portability` | 0 |
| `check_plugin_frontmatter_self_containment` | 0 |

All five returned 0. Only `check_skill_md_portability` matched the body citation,
then suppressed the declared file. The other four do not inspect body-prose
citations. None validates that the paths a declaration names *exist*. A
declaration is therefore a claim the toolchain accepts without checking, which
is the same category of trust failure the declarations were introduced to
close.

Both defects were caught by adversarial review on a different model family,
which is a human-scale control, not an automated one.

## Impact

| Area | Severity | Detail |
|---|---|---|
| Consumer-facing docs | Medium | A vendored install would follow a citation to a file that does not exist in any repository. |
| Rule artifacts | Medium | A `vendor-portability` declaration named a nonexistent path, so the artifact asserting portability was itself wrong. |
| Trust in gate output | Medium | Five green gates coexisted with the defect, which makes green a weaker signal than it appeared. |
| Review load | Low | Two adversarial rounds were needed on one PR. |

## Remediation

1. **Done in PR #4136**: corrected all three occurrences in both trees,
   corrected the declaration to name the real path, extended the `session`
   declaration to name the exact ADR path, and corrected the PR description,
   which had published the concealment as a fix.
2. **Done in PR #4136**: tightened `skill_md_portability_baseline.json` for the
   `security-detection` entries from 2 to 0 so the improvement cannot silently
   regress.
3. **Follow-up, unowned**: add existence validation for every path named inside
   a `vendor-portability` declaration. The check is cheap: parse the declaration,
   resolve each path against the repository root, fail on a miss. Scope it to
   repository-relative paths and exempt consumer-workspace paths, which by
   definition do not exist here.
4. **Practice change**: applying SHOULD 2 to a scanner hit requires confirming
   the path resolves before the transform. A path that does not resolve is a
   broken reference to repair, not a non-shipping reference to annotate.

## Learning

A gate that checks for the presence of an assertion, rather than the truth of
it, converts the assertion into a formality. When adding a declaration-style
escape hatch, validate the declaration's content in the same change that
introduces the hatch, or the hatch becomes a way to pass without complying.

The narrower version, worth carrying: making a warning disappear is not the
same as fixing what the warning pointed at. Confirm the underlying condition
changed, not just the report of it.
