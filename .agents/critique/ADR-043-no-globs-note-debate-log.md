# ADR-043 Amendment: No-Globs Note Debate Log

**ADR**: `.agents/architecture/ADR-043-scoped-tool-execution.md`
**Amendment**: Correct the --no-globs note at the "Tool Invocation" section
**Issue**: #4401
**Date**: 2026-08-04
**Branch**: fix/tooling-accuracy-cluster

---

## Scope

ADR-043 line 60 stated:

> Note: `--no-globs` ensures only explicitly specified files are processed.

This claim is incorrect. The `--no-globs` flag disables glob expansion in the
shell layer. It does not prevent a tool from reading files it discovers through
other means (imports, transitive analysis, config-file traversal). The
correction changes one sentence to accurately describe what the flag does.

## Review

### analyst: APPROVE

The change is a factual correction with a narrow scope. The original text
overstated the guarantee. The replacement text accurately describes the flag as
a shell-expansion control, not an isolation boundary.

No design decision is involved. No behavior changes. The correction reduces
the risk of callers relying on a guarantee that the flag does not provide.

Evidence: running `ruff check --no-globs file.py` does not prevent ruff from
following imports or reading pyproject.toml. The flag affects only how the
file list is assembled from the command line, not what the tool reads once
started.

### critic: APPROVE

One-line doc fix. The original claim was unverifiable and stronger than what
the flag delivers. Narrowing the claim to shell-expansion scope is correct.

No regression risk. The ADR continues to recommend `--no-globs` for scoping;
only the description of its guarantee changes.

## Decision

APPROVED. The ADR-043 note is corrected to describe `--no-globs` as
controlling shell glob expansion only, not providing full file isolation.

References ADR-043.
