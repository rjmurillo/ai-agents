---
date: 2026-08-03
issue: 4401
scope: .agents/architecture, tests
---

## Retrospective: ADR-043 --no-globs scope correction

### What changed

ADR-043 claimed `--no-globs` "ensures only specified files are processed."
The flag only disables the config's `globs` key. The `ignores` key still
drops explicitly passed files. This repo has no `globs` key, so the flag
is inert here. Correction note appended to ADR-043; regression test added.

### What went wrong initially

The issue text accepted the doc claim without measuring the flag. The doc
was wrong. The code (markdownlint-cli2 source) was right.

### Measurement method

Ran markdownlint-cli2 with `--no-globs` and without on a file covered by
`ignores`. Result: file was excluded in both cases. Flag had no effect.
Checked the markdownlint-cli2 source: `no-globs` sets `noGlobs` which
only applies to the `globs` config key, not `ignores`.

### Learnings captured

Diff the prose against the code. Prose about a flag is wrong more often
than the flag itself. Run the tool, read the output, then write the doc.

### Issues closed

Closes #4401 via PR attached to this branch.
