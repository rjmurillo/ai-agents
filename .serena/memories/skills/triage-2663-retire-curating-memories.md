# Skill triage: retire curating-memories (folded into memory-enhancement)

Issue #2663. Live pairwise overlap eval #1949 (2026-06-17, run-id m4-overlap-1949-2026-06-17,
model claude-sonnet-4-6) returned SUBSUMED: memory-enhancement covers curating-memories'
prompts without reciprocity (curating-memories own-delta -0.25, cross-delta -0.25).

## Decision

RETIRE curating-memories. Fold its unique Forgetful curation guidance into
memory-enhancement/SKILL.md (new "Forgetful Curation" section). The two skills had
different backends (curating-memories = Forgetful update_memory/mark_memory_obsolete/
link_memories; memory-enhancement = Serena citations/confidence) but the eval scored them
overlapping enough to merge. memory-enhancement now owns both Serena citation health and
Forgetful curation.

## What changed

- memory-enhancement/SKILL.md: version 1.0.0 -> 1.1.0, description + triggers expanded,
  added Forgetful Curation section (update/obsolete/link/dedup workflow + anti-patterns +
  verification). 434 lines, under the 500 cap.
- Deleted .claude/skills/curating-memories/ + src/copilot-cli/skills/curating-memories/.
  No scripts existed (SKILL.md only), nothing to preserve.
- Routing repointed to memory-enhancement in: exploring-knowledge-graph, using-forgetful-memory,
  memory-search, memory, reflect SKILL.md; docs/skill-reference.md; tests/test_skill_registry.py.
- Bumped .claude and src/copilot-cli plugin.json 0.5.208 -> 0.5.209 (#2118). src/claude
  manifest (0.3.21) untouched: skills are not generated into src/claude.

## Validator notes for future skill retirements

- Skills are NOT agents: detect_agent_drift.py is unaffected by a skill deletion (baseline
  drift count stayed 11). Do not chase "drift" when removing a skill.
- orphan-ref-validator default targets exclude skill descriptions (opt-in via
  --include-skill-descriptions); the real PR gate is the changed-files scan. Scan each
  changed SKILL.md / doc individually (multi-target .md passing reported files_scanned:0).
- marketplace.json descriptions carry no numeric skill-count token, so deleting a skill dir
  does not trip validate_plugin_manifests count checks. Counts validated OK.
- copilot mirror regenerates via build/scripts/build_all.py (generate_skills copies the
  artifacts.skills set); it dropped curating-memories and picked up the new memory-enhancement
  content automatically.
