## Entry points

- `sessions/handoffs/<date>-<issue>-handoff.md`: read latest, update at end. Sibling `handoffs/`: separate per-branch tier (ADR-014 Tier 2).
- `AGENT-INSTRUCTIONS.md`: BLOCKING scaffold; `implementer.md`/`orchestrator.md` gate on it.
- `architecture/ADR-NNN-*.md`: YAML `status` is truth; `README.md` generated (`generate_adr_index.py`), drift-gated (`OWNED_PREFIXES`), hand-edits lost. Frontmatter ratcheted pre-PR vs committed baseline (`check_adr_lifecycle.py`, ADR-073).
- `memory/episodes/*.json`: never hand-edit; auto-staged by `extract-session-episodes` pre-commit, exempt from the 5-file atomic limit. `recovery-hints.yaml`: hand-edited `error_classification.py` data.
