# ADR-110 claims ledger

Verified 2026-11-25 at `0b31dc034` plus the issue #7641 working tree.
Covers the Status rewrite and the section 7 amendment only.

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| TASK-040 shipped in PRs #5879, #5881, and #5885. | Quote | `gh pr view <n> --json mergeCommit,mergedAt` for each. | `59c479b1a` 2026-09-22, `764002b07` 2026-09-23, `f45e807ab` 2026-09-23 (UTC). Commit dates read 2026-09-22. |
| Milestone 3 left one owner and two canonical partials. | Count | `grep -rlE 'data, not instructions' templates/` | 6 files: the 2 partials plus the 4 approved `*.shared.md` residue copies. |
| `universal.md` owns `untrusted-content-handling`. | Path | Read `templates/rules/universal.md` lines 1-11. | `owns: [untrusted-content-handling]`, `status: active`. |
| The gate reads 50 canonical nodes and 16 edges. | Count | `uv run python scripts/validation/check_capability_graph.py --report text \| head -2` | `nodes: 50`, `edges: 16`. |
| Before the fix, a dependent that pasted the partial passed. | Behavior | Real-tree test: append `untrusted-content.mustache` to a copy of `research.SKILL.md.tmpl`, run the old gate. | `validate_capability_graph` returned `True`. |
| After the fix, the same paste fails and names the partial. | Behavior | `uv run pytest tests/validation/test_check_capability_graph_partials.py -k real_tree_rejects` | Passes: one finding naming `research.SKILL.md.tmpl` and the partial. |
| `research` also includes `no-dashes`. | Path | `grep -o '{{> [a-z-]*}}' templates/skills/research.SKILL.md.tmpl` | `bound-the-search`, `no-dashes`, `untrusted-content`. |
| Only the shared partial is attributed on the real tree. | Behavior | `_canonical_texts` on the real tree. | `untrusted-content-handling` gets `universal.md` and `untrusted-content.mustache` only. |
| `build/generate_agents.py` reads `*.shared.md` without expansion. | Behavior | `grep -n 'chevron\|render(' build/generate_agents.py`; read line 353. | No match for either; line 353 is `sorted(agents_path.glob("*.shared.md"))`. |
| The gate keeps no capability-to-path map. | Absence | `grep -n untrusted scripts/validation/check_capability_graph.py` | Two docstring examples (lines 11, 508), no lookup table; partials come from `{{> slug}}` includes via `skill_template_grammar._partial_slugs`. |
