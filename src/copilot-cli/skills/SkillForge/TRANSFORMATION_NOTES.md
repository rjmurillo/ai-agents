# SkillForge Transformation Notes

**Purpose**: Document local modifications for reapplication after upstream updates

**Initial sync**: 2026-01-03 (Session 372) — v4.x content extraction + policy deletions
**Latest sync**: 2026-04-13 — upstream v5.1.0 @ `f07042f`
**Upstream**: https://github.com/tripleyak/SkillForge

## Sync Log

| Date | Upstream ver | Commit | Notes |
|------|--------------|--------|-------|
| 2026-01-03 | v4.1.0 (pre-slim) | unknown | Initial vendoring + local content extraction to references/ |
| 2026-04-13 | v5.1.0 | `f07042f` | Added 3 new scripts, 1 new test, 9 new references; kept local extras and script enhancements |

**Reason (original)**: Token efficiency, skill-creator compliance

---

## Files Deleted

1. **README.md** - Violates skill-creator "no auxiliary files" rule
2. **LICENSE** - Violates skill-creator "no auxiliary files" rule
3. **SESSION_HANDOFF.md** - Violates skill-creator "no auxiliary files" rule

**Rationale**: Skill-creator spec prohibits auxiliary documentation files. Only SKILL.md, references/, scripts/, and assets/ are allowed.

---

## Content Moved to references/

### Extracted from SKILL.md `<details>` sections

All deep dive content moved from main SKILL.md to references/ for progressive disclosure:

| Original Location | New File | Content | Lines Extracted |
|-------------------|----------|---------|-----------------|
| Lines 357-498 | `references/phase1-analysis-deep-dive.md` | 1A: Input Expansion, 1B: Multi-Lens Analysis, 1C: Regression Questioning, 1D: Automation Analysis | 142 |
| Lines 500-568 | `references/phase2-specification-deep-dive.md` | Specification Structure, Specification Validation | 69 |
| Lines 570-629 | `references/phase3-generation-deep-dive.md` | Generation Order, Quality Checks During Generation | 60 |
| Lines 631-715 | `references/phase4-synthesis-deep-dive.md` | Panel Composition, Script Agent, Agent Evaluation, Consensus Protocol | 85 |
| Lines 717-754 | `references/evolution-timelessness.md` | Temporal Projection, Timelessness Scoring, Anti-Obsolescence Patterns | 38 |
| Lines 756-785 | `references/architecture-patterns.md` | Architecture Pattern Selection, Selection Decision Tree | 30 |
| Lines 787-817 | `references/configuration.md` | SkillForge configuration YAML | 31 |

**Total lines extracted**: ~455 lines

---

## SKILL.md Modifications

### Line Count Reduction

- **Before**: 851 lines (exceeds 500 soft limit)
- **After**: ~396 lines (within limits)
- **Reduction**: 455 lines moved to references/

### Replaced Content

**Original** (lines 357-817):
```markdown
<details>
<summary><strong>Deep Dive: Phase 1 - Analysis</strong></summary>
[... 455 lines of deep dive content ...]
</details>
```

**Replacement** (lines 357-367):
```markdown
## Deep Dives

For detailed implementation guides, see:

- [Phase 1: Analysis](references/phase1-analysis-deep-dive.md) - Input expansion, multi-lens analysis, regression questioning, automation analysis
- [Phase 2: Specification](references/phase2-specification-deep-dive.md) - Specification structure and validation
- [Phase 3: Generation](references/phase3-generation-deep-dive.md) - Generation order and quality checks
- [Phase 4: Multi-Agent Synthesis](references/phase4-synthesis-deep-dive.md) - Panel composition, evaluation, consensus protocol
- [Evolution/Timelessness](references/evolution-timelessness.md) - Temporal projection, timelessness scoring, anti-obsolescence patterns
- [Architecture Patterns](references/architecture-patterns.md) - Pattern selection decision tree
- [Configuration](references/configuration.md) - SkillForge configuration settings
```

---

## Reapplication Instructions

When updating from upstream:

1. **Delete prohibited files** (if they return):
   ```bash
   rm README.md LICENSE SESSION_HANDOFF.md
   ```

2. **Check line count**:
   ```bash
   wc -l SKILL.md
   ```
   If >500 lines, proceed with extraction.

3. **Extract details sections** (if present):
   - Identify all `<details>` sections with `grep -n "<details>" SKILL.md`
   - Extract each to corresponding `references/*.md` file using sed
   - Pattern: `sed -n 'START,ENDp' SKILL.md > references/filename.md`

4. **Replace with reference links**:
   - Remove all `<details>` content from SKILL.md
   - Add "Deep Dives" section with links to references/

5. **Verify compliance**:
   ```bash
   wc -l SKILL.md  # Should be <500
   ls -la          # Should only have SKILL.md, references/, scripts/, assets/
   ```

---

## Progressive Disclosure Pattern Applied

**Before**: Single monolithic SKILL.md with everything inline
**After**: Token-efficient structure:

```
SKILL.md (concise, lazy-loaded)
├── Quick Start
├── Workflow Overview
├── Verification Checklist
└── Deep Dives (links to references/)

references/ (deep documentation)
├── phase1-analysis-deep-dive.md
├── phase2-specification-deep-dive.md
├── phase3-generation-deep-dive.md
├── phase4-synthesis-deep-dive.md
├── evolution-timelessness.md
├── architecture-patterns.md
├── configuration.md
├── multi-lens-framework.md
├── regression-questions.md
├── script-integration-framework.md
└── ... (existing references)
```

---

## Governance Standard Applied

Per `.agents/governance/skill-description-trigger-standard.md` v2.0:

- **Description**: Excellent (includes trigger keywords)
- **Body**: Concise with decision trees, anti-patterns, verification checklists, trigger tables
- **Progressive disclosure**: Deep content in references/ (✓)
- **Token efficiency**: SKILL.md reduced from 851 to ~396 lines (✓)
- **No prohibited files**: README, LICENSE, SESSION_HANDOFF removed (✓)
- **No changelog in body**: Already removed in earlier session (✓)

---

## Verification

```bash
# File count
ls -la | grep -E "(SKILL.md|references|scripts|assets)"

# Line count
wc -l SKILL.md

# No prohibited files
! ls README.md LICENSE SESSION_HANDOFF.md 2>/dev/null

# References exist
ls -la references/*.md
```

Expected results:
- SKILL.md: ~396 lines
- references/: 14 files (7 new + 7 existing)
- No README.md, LICENSE, or SESSION_HANDOFF.md

---

## Notes

- **Upstream sync frequency**: Unknown
- **Conflict risk**: High if upstream adds back README/LICENSE
- **Reapplication time**: ~15 minutes (automated with scripts if frequent)
- **Alternative**: Propose upstream accepts progressive disclosure pattern

---

## 2026-04-13 Sync: Upstream v5.1.0 (commit f07042f)

### Upstream changes applied

**Scripts added (3 new files from upstream):**
- `scripts/check_docs_safety.py` (83 lines) — docs safety checker for unsafe command interpolation patterns (v5.1 addition)
- `scripts/discover_skills.py` (468 lines) — skill discovery utility (v5.0/v5.1)
- `scripts/init_skill.py` (393 lines) — skill scaffolder (v5.0/v5.1)

**Tests added:**
- `scripts/tests/test_package_skill_ignore.py` (upstream v5.1 — tests `.skillignore` enforcement in packaging)

**References added (9 new files from upstream v5.x architecture):**
- `degrees-of-freedom.md`
- `evolution-scoring.md`
- `iteration-guide.md`
- `multi-lens-framework.md`
- `regression-questions.md`
- `script-integration-framework.md`
- `script-patterns-catalog.md`
- `specification-template.md`
- `synthesis-protocol.md`

### Local preservation (NOT touched by sync)

**SKILL.md**: NO CHANGE. The only diff vs upstream is the intentional local model override (`claude-opus-4-6` instead of upstream's `claude-opus-4-5-20251101`). Upstream has not updated past 4-5 dated snapshots. Our 4-6 bump tracks the current Claude model family (per PR #1613 + #1634).

**Scripts NOT updated (local versions are larger, may have local improvements):**
- `scripts/_constants.py` (vendored +46 bytes)
- `scripts/package_skill.py` (vendored +712 bytes)
- `scripts/quick_validate.py` (vendored +382 bytes)
- `scripts/triage_skill_request.py` (vendored +110 bytes)
- `scripts/validate-skill.py` (vendored +1317 bytes)
- **Flagged for follow-up review.** Upstream simplified these in v5.0/v5.1; we need to confirm whether our enhancements are worth keeping, whether upstream replaced them with equivalent functionality elsewhere, or whether the upstream versions are now preferred.

**Local-only scripts preserved:**
- `scripts/frontmatter.py` — local utility
- `scripts/skill_modularity_audit.py` — local utility

**Local-only references preserved (v4.x content extractions, may now be orphaned by v5.x architecture):**
- `references/architecture-patterns.md`
- `references/configuration.md`
- `references/evolution-timelessness.md`
- `references/modularity-guidelines.md`
- `references/phase1-analysis-deep-dive.md`
- `references/phase2-specification-deep-dive.md`
- `references/phase3-generation-deep-dive.md`
- `references/phase4-synthesis-deep-dive.md`
- **Flagged for follow-up review.** These were extracted from the pre-v5 SKILL.md as our own progressive-disclosure transformation (Session 372, 2026-01-03). Upstream v5.0 did its own slim with different file names. Both sets now coexist. Consolidation needs a separate session.

**Local tests preserved:**
- `tests/test_skill_modularity_audit.py` — local test for local audit script

**Local deletions preserved:**
- `README.md` — still deleted per skill-creator "no auxiliary files" rule
- `LICENSE` — still deleted per same rule
- `SESSION_HANDOFF.md` — still deleted

### Verification (post-sync)

```bash
# Assets identical with upstream
diff -rq /tmp/upstream/assets .claude/skills/SkillForge/assets  # empty = identical

# SKILL.md differs only in model field
diff .claude/skills/SkillForge/SKILL.md /tmp/upstream/SKILL.md  # 6 lines changed, all model/subagent_model

# Total vendored files: 49 (up from 35 pre-sync)
find .claude/skills/SkillForge -type f | wc -l
```

### Known TODO for next sync

1. **Script diff triage** — run a 3-way merge on the 5 shared scripts where vendored is larger. Decide per-script: keep local, adopt upstream, or cherry-pick specific improvements.
2. **References consolidation** — decide fate of 8 v4.x legacy reference files. Either rename to `references/_v4-legacy/` to mark deprecated, delete if fully superseded by upstream's 9 new files, or merge content.
3. **Consider rebasing on upstream** — if local enhancements matter, propose them upstream. If not, do a clean overwrite on the next sync and only preserve intentional policy deletions (README/LICENSE).
4. **Upstream still on 4-5 models** — our 4-6 override will stay as a local fork until upstream bumps.
