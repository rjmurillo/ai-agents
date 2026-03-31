# Engineering Review: ai-agents CLI Platform

**Skill:** plan-eng-review (Garry Tan gstack methodology)  
**Plan:** `.agents/plans/PRD-ai-agents-platform.md`  
**Date:** 2025-03-31  
**Branch:** claude/slack-session-VWZ5m  
**Status:** CLEARED

---

## Executive Summary

Engineering review of the ai-agents CLI platform PRD. 7 issues identified, 7 decisions made. All critical paths have mitigation strategies. Ready for implementation.

---

## Step 0: Scope Challenge

### Reuse Assessment

| Sub-Problem | Existing Code | Reuse? |
|-------------|---------------|--------|
| Agent definitions | `src/claude/*.md` (25 agents) | YES |
| Session protocol | `.agents/SESSION-PROTOCOL.md` | YES |
| Governance | `.agents/governance/*.md` | YES |
| Validation | `build/scripts/*.py` (27 scripts) | YES |
| Squad parsing | None | NO |
| JSON export/import | None | NO |

**Verdict:** ~40% reuse potential. Templates high, commands split.

### Complexity Check

- Files touched: 8 command files + templates → YELLOW
- New services: 4 → YELLOW
- External deps: commander.js only → GREEN
- Cross-cutting: None → GREEN

**Verdict:** Moderate complexity. Acceptable for 4-week timeline.

### Lake vs Ocean

- 8 CLI commands: **Lake** (boilable in 4 weeks)
- Spec v1.0: **Lake** (1 week)
- Marketplace: **Ocean** (defer)
- IDE extensions: **Ocean** (defer)

---

## Section 1: Architecture Review

### System Boundaries

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          ai-agents CLI                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      Command Layer                               │   │
│  │  init | status | doctor | export | import | nap | upgrade        │   │
│  └──────────────────────────┬──────────────────────────────────────┘   │
│                             │                                          │
│  ┌──────────────────────────┴──────────────────────────────────────┐   │
│  │                      Service Layer                               │   │
│  │  ScaffoldService | ValidateService | MigrateService | Serialize  │   │
│  └──────────────────────────┬──────────────────────────────────────┘   │
│                             │                                          │
│  ┌──────────────────────────┴──────────────────────────────────────┐   │
│  │                      I/O Layer                                   │   │
│  │  fs (read/write) | path (resolution) | glob (discovery)          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Architecture Decisions

| Issue | Decision | Rationale |
|-------|----------|-----------|
| ARCH-1: Partial scaffold on disk full | Transaction pattern (temp → rename) | Atomic operations, easy rollback |
| ARCH-2: Large repo export | Streaming + progress bar | Handles 100K+ files |
| ARCH-3: Upgrade conflicts | Conflict detection with hash | Preserves user modifications |

### Production Failure Scenarios

| Command | Failure | Mitigation |
|---------|---------|------------|
| init | Disk full | Transaction rollback |
| --from squad | Malformed YAML | Parse error with line number |
| export | Memory exhaustion | Streaming JSON |
| upgrade | User modifications | Conflict detection |

---

## Section 2: Code Quality

### Module Structure

```
packages/ai-agents-cli/
├── src/
│   ├── index.ts           # CLI entry (commander)
│   ├── commands/          # 8 command files
│   ├── services/          # 4 services
│   ├── importers/         # squad.ts, json.ts
│   ├── templates/         # minimal/, standard/, full/
│   └── utils/             # Shared helpers
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── package.json
```

### Code Quality Decisions

| Issue | Decision | Rationale |
|-------|----------|-----------|
| CODE-1: Error handling | Typed error hierarchy | Clear exit codes, user-friendly messages |

### DRY Extraction Targets

| Pattern | Extract To |
|---------|------------|
| Path validation | `utils/safe-path.ts` |
| "Not initialized" check | `utils/guards.ts` |
| Progress bar | `utils/progress.ts` |
| YAML safe parsing | `utils/yaml.ts` |

---

## Section 3: Test Coverage

### Codepath Coverage Diagram

```
init Command:
  ├── .agents/ exists + no --force    [★★★]
  ├── .agents/ exists + --force       [★★]
  ├── --from squad + no .squad/       [★★★]
  ├── --from squad + .squad/ exists   [★★]
  ├── template=minimal/standard/full  [★★]
  ├── disk full mid-write             [GAP → ARCH-1 fixes]
  └── success                         [★]

status Command:
  ├── no .agents/                     [★★★]
  ├── .agents/ exists                 [★★]
  ├── corrupted .agents/              [GAP → add handling]
  └── success                         [★]

--from squad Migration:
  ├── .squad/team.md missing          [★★★]
  ├── .squad/team.md malformed        [★★]
  ├── unknown Squad version           [GAP → add detection]
  └── success                         [★]
```

### Test Decisions

| Issue | Decision | Rationale |
|-------|----------|-----------|
| TEST-1: Ctrl+C during scaffold | Add SIGINT cleanup handler | Clean up orphaned temp dirs |
| TEST-2: Symlinks in .squad/ | Resolve + validate containment | Security-conscious, prevent escapes |

### Required Test Fixtures

- `.squad/` samples: v0.1, v1.0, malformed, empty
- Large repo: 10K+ files
- Edge cases: symlinks, permissions, unicode filenames

---

## Section 4: Performance

### Critical Paths

| Operation | Complexity | Mitigation |
|-----------|------------|------------|
| init | O(n) files | OK (max 200) |
| export | O(n) files | Streaming JSON |
| import | O(n) files | Streaming JSON |

### Performance Decisions

| Issue | Decision | Rationale |
|-------|----------|-----------|
| PERF-1: Large export memory | Streaming JSON (JSONStream) | Handles any size repo |

---

## Parallelization Strategy

| Lane | Work | Dependencies |
|------|------|--------------|
| Lane 1+4 | init + --from squad | None |
| Lane 2+3 | status/doctor + export/import | Shares services |
| Lane 5 | nap + upgrade | After init |

**Recommended:** Run Lanes 1+4 and 2+3 in parallel worktrees.

---

## Decision Log

| ID | Issue | Decision |
|----|-------|----------|
| ARCH-1 | Partial scaffold | Transaction pattern |
| ARCH-2 | Large export | Streaming + progress |
| ARCH-3 | Upgrade conflicts | Conflict detection |
| CODE-1 | Error handling | Typed error hierarchy |
| TEST-1 | Ctrl+C cleanup | SIGINT handler |
| TEST-2 | Symlinks | Resolve + validate |
| PERF-1 | Export memory | Streaming JSON |

---

## Review Readiness

| Review | Status | Required? |
|--------|--------|-----------|
| CEO Review | CLEARED | No |
| **Eng Review** | **CLEARED** | **YES** |
| Design Review | N/A | No (no UI) |

---

## Verdict

**CLEARED**

All 7 issues have decisions. Implementation can proceed with:

1. Transaction pattern for init
2. Streaming JSON for export/import
3. Conflict detection for upgrade
4. Typed error hierarchy
5. SIGINT cleanup handler
6. Symlink resolution with containment
7. Progress bars for long operations

---

*Engineering Review completed: 2025-03-31*  
*Methodology: Garry Tan gstack plan-eng-review*
