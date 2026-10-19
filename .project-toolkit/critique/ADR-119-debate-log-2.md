# ADR Debate Log: ADR-119 Codex Skill Links Under .agents/skills

## Summary

- **Rounds**: 2 of 10
- **Prior debate log**: `.project-toolkit/critique/ADR-119-debate-log.md` (closed by consensus)
- **Outcome**: Consensus
- **Final Status**: proposed
- **Records covered**: ADR-119 only. The delta added decision 7 (`.agents/skills/<name>` links to `src/codex/skills/<name>`), so former decisions 8 and 9 are now 9 and 10. The first log's references to "decisions 8 and 9" are left as written.
- **Panel**: full six seats (architect, critic, independent-thinker, security, analyst, high-level-advisor), because the delta widens the binplace install-root validator.

## Round 1 Summary

### Key Issues Addressed

- critic, analyst, independent-thinker (Block, P0): `scripts/validation/check_agents_write_targets.py` treated `.agents/skills` as the path issue #5421 retired, so the commit and CI gates went red (4 violations). Fix: a narrow carve-out in `scripts/validation/agents_install_roots.py`, read by the checker (moved there so the checker stays under the 500-line taste cap). Only `build/scripts/binplace_manifest.py`, `templates/platforms/binplace.yaml`, and `templates/platforms/surface-parity.yaml` may name the exact root; rule (b) write checks are unchanged; `skills` is not a KEEP subtree. Result: 0 violations in 7049 files.
- critic, analyst (P1): duplicate loading with the marketplace plugin unmeasured. Fix: a Codex 0.163.0 probe in this repository with `project-toolkit@ai-agents` enabled lists `chestertons-fence` and `project-toolkit:chestertons-fence`, distinct names, recorded as a Negative consequence.
- architect (P1): `GENERATOR-FILES.md` omitted the new output. Fix: the binplace row now names `.agents/skills/<name>`.
- P2 items fixed: decision 7 says repo-local skills stay Claude-only; Rationale covers decision 7; Consequences name edits through generated links, the missing snapshot guard, and the 104 link entries; Impact names the checker; Related Decisions flags ADR-012's earlier use of `.agents/skills`; Reversibility step 3 lists every piece; tests reject `.agents/skillsx` and `.agents/skills/sub`.
- The `.agents/AGENTS.md` parenthetical removal is a byte trim: the `.agents` path-local effective-context ceiling was 32 bytes over after the new sentence.

### Major Changes Made

- Checker carve-out with positive and negative tests; ADR-119 decision 7 text, consequences, impact, related decisions, reversibility.

### Agent Positions

| Agent | Round 1 | Round 2 |
|-------|---------|---------|
| architect | Accept | Accept |
| critic | Block | Accept |
| independent-thinker | Block | Accept |
| security | Accept | Accept |
| analyst | Block | Accept |
| high-level-advisor | Accept | Accept |

## Round 2 Summary

### Key Issues Addressed

All P0 and P1 items verified resolved by each seat with commands (`check_agents_write_targets.py`: 0 violations in 7049 files; targeted tests passed). Remaining P2 items, fixed after the vote:

- critic, independent-thinker: whether Copilot CLI or VS Code scans `.agents/skills` is now stated as unverified in the duplicate-listing consequence.
- critic: a test case now pins that an owner file naming `.agents/skills/foo` is still flagged.
- architect: this log records the renumbering of decisions 8 and 9 to 9 and 10.

### Major Changes Made

- The P2 fixes above. No P0 or P1 change followed the vote.

### Next Steps

None blocking. Status stays `proposed` until the owner accepts.
