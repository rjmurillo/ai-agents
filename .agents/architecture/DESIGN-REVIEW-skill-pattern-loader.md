# Design Review: Skill Pattern Loading Refactor

**Branch**: feat/update-skill-learning-patterns
**Reviewer**: Architect
**Date**: 2026-02-08
**Verdict**: PASS with MINOR observations

---

## Summary

Replaces hardcoded skill pattern dictionaries with runtime SKILL.md scanning plus stat-based caching. Module separation is clean. Graceful degradation design is sound. Cache invalidation strategy is correct. Cross-harness support is comprehensive.

---

## Architecture Assessment

### 1. Pattern: Replace Hardcoded Dicts with Runtime Scanning

**Design**: [PASS]

Eliminates hardcoded `SKILL_PATTERNS` and `COMMAND_TO_SKILL` dictionaries (54 lines deleted). Replaced with runtime loader that scans SKILL.md trigger tables.

**Benefits**:
- Single source of truth: SKILL.md files define triggers
- Zero maintenance cost when skills added/modified
- Automatic sync between skill catalog and detection patterns
- Covers both harness ecosystems (Claude Code + Copilot)

**Implementation Quality**:
- Clean separation: `skill_pattern_loader.py` is independent module
- Consumer (`invoke_skill_learning.py`) uses lazy loading via `_ensure_patterns_loaded()`
- Regex parsing is focused: backtick-wrapped phrases from trigger table cells
- Frontmatter name extraction with fallback to directory name
- Case-insensitive SKILL.md discovery (both `SKILL.md` and `skill.md`)

**Code Evidence** (skill_pattern_loader.py:29):
```python
# Regex to extract backtick-wrapped phrases from markdown table cells.
# Matches: | `phrase here` | ... |
_TRIGGER_CELL_RE = re.compile(r"\|\s*`([^`]+)`\s*\|")
```

### 2. Module Separation: Separate Use from Creation

**Design**: [PASS]

`skill_pattern_loader.py` creates patterns. `invoke_skill_learning.py` uses patterns. No mixing of concerns.

**Separation Verification**:
- Loader has no dependency on consumer
- Consumer imports loader only when needed (`_ensure_patterns_loaded`)
- Global state mutation is confined to consumer (`SKILL_PATTERNS`, `COMMAND_TO_SKILL`)
- Loader returns data, consumer decides what to do with it

**Code Evidence** (invoke_skill_learning.py:154):
```python
from skill_pattern_loader import load_skill_patterns
loaded_patterns, loaded_commands = load_skill_patterns(project_dir)
if loaded_patterns:
    SKILL_PATTERNS = loaded_patterns
if loaded_commands:
    COMMAND_TO_SKILL = loaded_commands
```

**Principle Adherence**: "A makes B OR uses B, never both"
- `skill_pattern_loader.py` makes patterns (scans, parses, builds maps)
- `invoke_skill_learning.py` uses patterns (detection, validation)

### 3. Graceful Degradation Design

**Design**: [PASS]

All failure modes return empty dicts. Consumer continues with regex-based detection (skill paths, slash commands).

**Degradation Layers**:
1. Missing skill directories → skip that source, try next
2. Parse failure on single SKILL.md → empty triggers for that skill
3. Load failure (any exception) → return `({}, {})`
4. Consumer catches import/load failure → empty dicts, set `_patterns_loaded = True`

**Code Evidence** (skill_pattern_loader.py:316):
```python
except Exception:
    return {}, {}
```

**Code Evidence** (invoke_skill_learning.py:160):
```python
except Exception:
    pass  # Graceful degradation: regex detection still works
```

**Robustness**: No crash paths. Hook continues operating even with zero patterns loaded.

### 4. Cache Invalidation Strategy

**Design**: [PASS]

Stat-based invalidation using mtime (modification time) checks. Cache is busted when any source SKILL.md changes (added, modified, deleted).

**Invalidation Conditions**:
- New SKILL.md file added (set of paths differs)
- Existing SKILL.md modified (mtime differs)
- SKILL.md deleted (set of paths differs)

**Code Evidence** (skill_pattern_loader.py:241-248):
```python
# Check that the sets of files match and all mtimes agree
if set(stored_mtimes.keys()) != set(current_mtimes.keys()):
    return False

for path_str, mtime in current_mtimes.items():
    if stored_mtimes.get(path_str) != mtime:
        return False
```

**Performance Budget** (documented in module docstring):
- Cold start: ~40ms (42 files × ~2KB each)
- Warm cache: ~2ms (one JSON read + stat checks)

**Cache Location**: `.claude/hooks/Stop/.skill_pattern_cache.json`
**Ignored in git**: Yes (.gitignore updated)

**Cache Versioning**: `CACHE_VERSION = 1` allows future schema changes.

### 5. Cross-Harness Support

**Design**: [PASS]

Scans four skill source paths with priority-based deduplication:

1. `{project}/.claude/skills/*/SKILL.md` (Claude Code repo)
2. `{project}/.github/skills/*/SKILL.md` (Copilot/GitHub repo)
3. `~/.claude/skills/*/SKILL.md` (Claude Code user)
4. `~/.copilot/skills/*/SKILL.md` (Copilot CLI user)

**Priority Rule**: Lower index wins for same skill name. Repo-level overrides user-level.

**Code Evidence** (skill_pattern_loader.py:47-52):
```python
search_roots = [
    project_dir / ".claude" / "skills",
    project_dir / ".github" / "skills",
    home / ".claude" / "skills",
    home / ".copilot" / "skills",
]
```

**Deduplication** (skill_pattern_loader.py:64-68):
```python
skill_name = skill_md.parent.name.lower()
if skill_name in seen_names:
    continue
seen_names.add(skill_name)
```

**Compatibility**: Supports both Claude Code and GitHub Copilot skill ecosystems.

---

## Architectural Principles Assessment

### SOLID Compliance

| Principle | Status | Evidence |
|-----------|--------|----------|
| **Single Responsibility** | PASS | Loader only loads patterns. Consumer only detects skills. |
| **Open-Closed** | PASS | Adding new SKILL.md extends behavior without modifying loader. |
| **Liskov Substitution** | N/A | No inheritance hierarchy. |
| **Interface Segregation** | PASS | Single function `load_skill_patterns()` returns tuple. |
| **Dependency Inversion** | PASS | Consumer depends on loader's public API, not implementation. |

### Encapsulation

**Strong Encapsulation** [PASS]:
- Cache format is private (underscore-prefixed helpers: `_read_cache`, `_write_cache`)
- Regex patterns are module-scoped constants (not exposed)
- Public API is single entry point: `load_skill_patterns(project_dir)`

**Code Evidence** (skill_pattern_loader.py:197-199):
```python
def _get_cache_path(project_dir: Path) -> Path:
    """Return the cache file path within the hooks directory."""
    return project_dir / ".claude" / "hooks" / "Stop" / CACHE_FILENAME
```

Private cache path construction is hidden from consumer.

### Cohesion

**High Cohesion** [PASS]:
- All functions relate to single purpose: skill pattern extraction
- Helper functions have narrow, focused roles:
  - `scan_skill_directories()` → find SKILL.md files
  - `parse_skill_triggers()` → extract triggers from one file
  - `build_detection_maps()` → combine parsed data into maps
  - `_check_cache_freshness()` → validate cache
  - `_read_cache()` / `_write_cache()` → cache I/O

No unrelated functionality mixed in.

### Coupling

**Loose Coupling** [PASS]:
- Loader has zero dependencies on consumer
- Consumer imports loader dynamically (not at module level)
- Communication is data-only (dicts, no callbacks)
- No shared mutable state between modules

**Code Evidence** (invoke_skill_learning.py:154):
```python
from skill_pattern_loader import load_skill_patterns
```

Import is inside function, not module-level. Minimizes coupling.

---

## Test Coverage Assessment

### New Module Tests (test_skill_pattern_loader.py)

**Coverage**: 513 lines of tests for 317 lines of code (~1.6:1 ratio)

**Test Classes**:
1. `TestParseSkillTriggers` → SKILL.md parsing edge cases
2. `TestScanSkillDirectories` → multi-source scanning, deduplication
3. `TestBuildDetectionMaps` → pattern/command map construction
4. `TestCacheFreshness` → invalidation on add/modify/delete
5. `TestCacheRoundtrip` → write/read correctness, format validation
6. `TestLoadSkillPatterns` → integration tests (full flow)

**Key Coverage**:
- Missing directories handled gracefully
- Case-insensitive file discovery (SKILL.md vs skill.md)
- Multiple trigger sections (## Triggers + ### HIGH Priority Triggers)
- Slash command extraction (`/session-init` → `session-init`)
- Identity mappings (`reflect` → `reflect`)
- Cache invalidation triggers (new file, modified file, deleted file)
- Graceful degradation (empty project returns `({}, {})`)

### Consumer Tests Updated (test_invoke_skill_learning.py)

**Changes**: 298 insertions, patterns loaded from real SKILL.md files at test start.

**Code Evidence** (test_invoke_skill_learning.py:40-41):
```python
_PROJECT_ROOT = Path(__file__).parent.parent
_ensure_patterns_loaded(_PROJECT_ROOT)
```

Tests now operate on real skill catalog, not hardcoded fixtures. This validates actual SKILL.md files are parseable.

**LLM Fallback Disabled** (test_invoke_skill_learning.py:48):
```python
invoke_skill_learning.USE_LLM_FALLBACK = False
```

Ensures deterministic pattern-based testing (no LLM reclassification).

**Test Updates**:
- GitHub skill patterns changed to match actual SKILL.md triggers ("create a PR" not "gh pr list")
- Documentation skill renamed to doc-sync (matches actual skill)
- Pattern sync tests verify loaded patterns work with detection functions

---

## Design Quality: Strengths

### 1. Single Source of Truth

SKILL.md trigger tables are now the only source for pattern definitions. No more drift between skill documentation and detection logic.

### 2. Zero Maintenance Cost

Adding a new skill requires:
1. Create `.claude/skills/new-skill/SKILL.md`
2. Add trigger table with backtick-wrapped phrases

No code changes needed. Pattern extraction is automatic.

### 3. Performance-Conscious Caching

Stat-based caching is correct and efficient. Warm cache hits are ~2ms (acceptable for hook runtime). Cold start ~40ms is tolerable (happens once per session or when skills change).

### 4. Fail-Safe Design

Every failure path returns empty dicts. No crashes. Regex-based detection (skill paths, slash commands) still works as fallback.

### 5. Cross-Platform Compatibility

- Case-insensitive file discovery (Linux ext4 vs macOS APFS)
- Path.home() usage for user-level skills
- No OS-specific assumptions

---

## Design Quality: Observations (MINOR)

### Observation 1: No Cache TTL

Cache has no expiration policy. If SKILL.md changes externally (editor doesn't update mtime), cache persists.

**Likelihood**: Low (mtime updates on save)
**Impact**: Medium (stale patterns used until manual cache delete)
**Mitigation**: Current stat-based invalidation is sufficient for normal workflow
**Recommendation**: Document cache location for manual invalidation if needed

### Observation 2: No Logging

Loader has no logging. Silent failures make debugging difficult if patterns aren't loaded.

**Likelihood**: Medium (temporary file permission issues)
**Impact**: Low (graceful degradation to empty dicts)
**Mitigation**: Tests cover failure modes extensively
**Recommendation**: Consider adding optional logging to stderr for diagnostic purposes

### Observation 3: Regex Assumes Well-Formed Tables

`_TRIGGER_CELL_RE` assumes backtick-wrapped phrases in table cells. Malformed tables (missing backticks, broken pipes) are silently skipped.

**Likelihood**: Medium (human error in SKILL.md editing)
**Impact**: Low (skill not detected, but no crash)
**Mitigation**: SkillForge validator checks trigger table format
**Recommendation**: Current behavior (skip malformed) is acceptable

---

## Comparison: Before vs After

| Aspect | Before | After |
|--------|--------|-------|
| **Pattern Source** | Hardcoded dicts (54 lines) | SKILL.md trigger tables |
| **Maintenance** | Manual updates per skill | Zero (automatic extraction) |
| **Sync Risk** | High (drift between docs and code) | None (single source of truth) |
| **Cross-Harness** | Claude Code only | Claude Code + Copilot |
| **Performance** | O(1) dict lookup | O(1) dict lookup (cached) |
| **Cold Start** | ~0ms (in-memory) | ~40ms (file scan + parse) |
| **Test Coverage** | Pattern fixtures only | Real SKILL.md validation |

---

## Alignment with ADRs

### ADR-042: Python-First for New Scripts

**Status**: Aligned

New module is Python (`.py` not `.ps1`). Fits ML/AI ecosystem alignment principle.

### ADR-007: Memory-First Pattern

**Status**: N/A (no memory operations)

Loader is stateless. No cross-session memory needed.

---

## Security Assessment

### Path Injection Risk

**Status**: MITIGATED

- `project_dir` is validated by consumer before passing to loader
- Loader uses `Path.home()` for user directories (safe)
- No user-controlled path concatenation

**Code Evidence** (invoke_skill_learning.py:951):
```python
_ensure_patterns_loaded(safe_project_path)
```

`safe_project_path` is sanitized via `_get_safe_root_from_env()` before passing to loader.

### SKILL.md Content Injection

**Status**: SAFE

Loader only reads SKILL.md files, never executes them. Regex extraction is read-only. No eval, exec, or import of SKILL.md content.

### Cache Poisoning

**Status**: MITIGATED

Cache is written to `.claude/hooks/Stop/` (project-local). Attacker would need filesystem write access to project root.

Cache validation checks version and required fields before trusting data.

---

## Recommendations

### Required Actions: NONE

Design is sound. Implementation is correct. Test coverage is comprehensive.

### Optional Enhancements

1. **Add stderr logging** (if hook failures reported):
   ```python
   import sys
   print(f"Failed to load patterns: {e}", file=sys.stderr)
   ```

2. **Document cache invalidation** (in SKILL.md):
   ```markdown
   ## Troubleshooting
   If pattern changes aren't detected, delete cache:
   rm .claude/hooks/Stop/.skill_pattern_cache.json
   ```

3. **Add cache stats** (for performance monitoring):
   ```python
   # Return (patterns, commands, cache_hit: bool)
   return (skill_patterns, command_to_skill, cache_hit)
   ```

None of these are blocking. Current design is production-ready.

---

## Verdict: PASS

**Summary**: Clean separation of concerns. Graceful degradation. Correct cache invalidation. Comprehensive test coverage. No critical issues.

**Architecture Quality**: High cohesion, low coupling, strong encapsulation, single source of truth.

**Observations**: Three minor points (no cache TTL, no logging, regex assumes well-formed tables). None are critical. Current behavior is acceptable.

**Recommendation**: Merge without changes. Optional enhancements can be considered in future iterations if operational issues arise.

---

## Key Findings

| Aspect | Assessment |
|--------|------------|
| **Separate Use from Creation** | PASS |
| **Encapsulation** | PASS (private helpers, public API) |
| **Cohesion** | PASS (single purpose: pattern extraction) |
| **Coupling** | PASS (data-only interface, no shared state) |
| **Graceful Degradation** | PASS (empty dicts on failure) |
| **Cache Invalidation** | PASS (stat-based, correct triggers) |
| **Cross-Harness Support** | PASS (4 sources, priority dedup) |
| **Test Coverage** | PASS (1.6:1 ratio, edge cases covered) |
| **Security** | PASS (no injection risks, read-only ops) |

**Overall**: Production-ready. No blocking issues.

---

**Architect Sign-Off**: APPROVED
**Date**: 2026-02-08
