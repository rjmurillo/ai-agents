---
name: a07-remove-cause
tags: [decision, ai-agents-delta, structural]
max_turns: 3
allowed_tools: []
---

Three times this quarter a release of our Python package shipped with the wrong version string because the version is written by hand in two places, `pyproject.toml` and `src/pkg/__init__.py`, and they disagreed. A CI check that compares the two already exists, but it runs only on the release branch, so the mismatch is caught late. The package targets Python 3.14 and is always installed, never run from a source checkout.

What change do you make? Answer in at most five sentences. End your reply with one final line of the form `DECISION: <LABEL>`, where LABEL is exactly one of: DETECT (add or move checks so the mismatch is caught earlier), REMOVE_CAUSE (keep one source of truth for the version so a mismatch cannot occur).
