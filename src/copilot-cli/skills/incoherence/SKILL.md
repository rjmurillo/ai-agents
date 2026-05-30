---
name: incoherence
description: >-
  DEPRECATED: use doc-accuracy instead. doc-accuracy absorbed incoherence
  detection and is the canonical doc-vs-code audit entrypoint. Retained only
  for the legacy scripts/incoherence.py reconciliation workflow.
model: claude-sonnet-4-6
license: MIT
metadata:
  version: 1.0.0
---

# Incoherence Detector Skill

> [!WARNING]
> **DEPRECATED 2026-05-29. Use `doc-accuracy` instead.**
> The `doc-accuracy` skill absorbed incoherence detection (see its frontmatter: "absorbs incoherence detection"). It is the single canonical entrypoint for doc-vs-code contradiction auditing. Route all "audit docs vs code", "find contradictions in the docs", and "check for stale documentation" requests to `doc-accuracy`. This skill is retained only for the legacy 22-step `scripts/incoherence.py` reconciliation workflow and will be removed after callers migrate.

**Migration:** invoke `doc-accuracy` with `audit docs vs code` (Phases 1-4) or `check doc consistency` (Phases 1-2, 5).

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `find contradictions in the docs` | Detection phase (steps 1-13) |
| `audit docs vs code consistency` | Detection phase with Dimension A focus |
| `check for stale documentation` | Detection phase with Dimension D focus |
| `run incoherence detector` | Full detection phase |
| `reconcile incoherence report` | Reconciliation phase (steps 14-22) |

---

## Verification

After detection:

- [ ] Report file created at user-specified path
- [ ] Each issue has Type, Severity, Source A/B, Suggestions, and Resolution section
- [ ] Dimension coverage matches selection from step 2

After reconciliation:

- [ ] Resolved issues show status marker in report
- [ ] Code changes match user-provided resolutions
- [ ] No unresolved critical or high severity issues remain

---

## Prerequisites

**Before starting**: User must specify the report filename (e.g., "output to incoherence-report.md").

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/incoherence.py` | 22-step detection and reconciliation workflow for doc-code contradictions |

## Invocation

```bash
# Detection phase (steps 1-13)
python3 scripts/incoherence.py --step-number 1 --total-steps 22 --thoughts "<context>"

# Reconciliation phase (steps 14-22, after user edits report)
python3 scripts/incoherence.py --step-number 14 --total-steps 22 --thoughts "Reconciling..."
```
