---
type: design
id: DESIGN-008
title: Orphan-Ref Validator Skill Design
status: draft
priority: P2
related: [REQ-008]
created: 2026-05-10
updated: 2026-05-10
author: richard
---

# DESIGN-008: Orphan-Ref Validator Skill

## Overview

Single-process Python scanner that walks configured target paths, applies a small set of reference-pattern regexes, and reconciles each match against the working tree. Emits ADR-056 envelope on stdout. Exit code per ADR-035.

## Architecture

```text
+----------------------+
| CLI entry: scan.py   |
| --targets PATH...    |
| --output json|human  |
+----------+-----------+
           |
           v
+----------+-----------+
| Target enumeration   |
| (skip missing paths) |
+----------+-----------+
           |
           v
+----------+-----------+
| Reference extraction |
| per target file:     |
|  - skill_name regex  |
|  - script_path regex |
|  - count_claim regex |
+----------+-----------+
           |
           v
+----------+-----------+
| Working-tree probes  |
|  - .claude/skills/   |
|    enumeration       |
|  - file existence    |
|  - count enumerator  |
+----------+-----------+
           |
           v
+----------+-----------+
| Findings aggregator  |
| Verdict computation  |
+----------+-----------+
           |
           v
+----------+-----------+
| Output formatter     |
| ADR-056 envelope     |
| + VERDICT line       |
+----------------------+
```

## Components

### `scan.py` (CLI entry, ~250-350 LOC)

Public functions:

- `def scan(targets: list[Path], repo_root: Path) -> ScanResult`
- `def main(argv: list[str] | None = None) -> int`

Internal pure functions:

- `enumerate_skills(repo_root: Path) -> set[str]` -- reads `.claude/skills/*/SKILL.md` directories.
- `enumerate_skill_scripts(repo_root: Path) -> set[Path]` -- reads `build/scripts/*.py`, `scripts/**/*.py`.
- `extract_skill_refs(target_text: str) -> Iterable[Match]` -- yields `(line, kebab_name)`.
- `extract_script_refs(target_text: str) -> Iterable[Match]` -- yields `(line, path)`.
- `extract_count_claims(target_text: str, target_path: Path) -> Iterable[Match]` -- only fires on plugin/marketplace manifests.
- `enumerate_count_for_kind(repo_root: Path, kind: str) -> int` -- delegates to existing strategies in `validate_marketplace_counts.py`.
- `compute_verdict(findings: list[Finding]) -> str` -- PASS / WARN / CRITICAL_FAIL.

### `SKILL.md`

Frontmatter:

```yaml
---
name: orphan-ref-validator
description: Detect references to skills, scripts, and counts in structured artifacts that do not match working tree state. Catches orphan refs pre-commit before /pr-quality:all surfaces them.
license: MIT
metadata:
  version: 1.0.0
---
```

Body sections:

- Triggers (`scan for orphan refs`, `validate references`, /build exit gate, /test gate 5)
- Inputs (CLI args)
- Outputs (envelope + verdict)
- Behavior (per acceptance criteria)
- Failure modes (vendored install, parse errors)
- Examples
- References (REQ-008, ADR-035, ADR-056, ADR-042)

### `tests/test_scan.py` (pytest)

Test cases:

| Case | Setup | Expected |
|---|---|---|
| AC2 positive | tmp file mentions `doc-sync`; `.claude/skills/doc-sync/` absent | Finding(kind=skill_name, severity=critical) | <!-- orphan-ref-ignore -->
| AC2 negative | tmp file mentions only living skill names | 0 findings |
| AC3 positive | tmp file references `build/scripts/nonexistent.py` | Finding(kind=script_path, severity=critical) | <!-- orphan-ref-ignore -->
| AC3 negative | tmp file references existing scripts | 0 findings |
| AC4 positive | manifest claims `100 skills` with 67 actual | Finding(kind=count_claim, severity=critical) |
| AC4 negative | manifest count matches actual | 0 findings |
| AC5 envelope | any scan | stdout matches ADR-056 schema; last line starts `VERDICT:` |
| AC6 vendored | scan with target path that does not exist | exit 0, INFO log line, no exception |
| AC9 edge: empty file | empty target | 0 findings, PASS |
| AC9 edge: mixed | file with both living and dead refs | findings only for dead |

Coverage target: ≥80% line on `scan.py`.

## Data Model

```python
@dataclass(frozen=True)
class Finding:
    kind: Literal["skill_name", "script_path", "count_claim"]
    severity: Literal["critical", "warn"]
    target_file: Path  # relative to repo_root
    line: int
    referenced_entity: str
    recommendation: str
    expected: str | None = None  # for count_claim
    actual: str | None = None    # for count_claim

@dataclass(frozen=True)
class ScanResult:
    findings: list[Finding]
    verdict: Literal["PASS", "WARN", "CRITICAL_FAIL"]
    files_scanned: int
    refs_checked: int
```

## Output Envelope (ADR-056)

```json
{
  "Success": true,
  "Data": {
    "findings": [
      {"kind": "skill_name", "severity": "critical", "target_file": "...", "line": 7, "referenced_entity": "doc-sync", "recommendation": "Update reference or restore skill"}
    ],
    "verdict": "CRITICAL_FAIL",
    "counts": {"files_scanned": 142, "refs_checked": 318, "findings_total": 1}
  },
  "Error": null,
  "Metadata": {"Script": "scan.py", "Version": "1.0.0", "Timestamp": "..."}
}
VERDICT: CRITICAL_FAIL
```

Exit code (ADR-035):

| Verdict | Exit |
|---|---|
| PASS | 0 |
| WARN | 0 (warn does not block) |
| CRITICAL_FAIL | 1 |
| Config error (bad CLI args, missing repo root) | 2 |

## Default Scan Targets

When invoked without `--targets`, the skill scans:

- `.agents/specs/` (recursive)
- `tests/evals/` (recursive)
- `.claude/skills/` (recursive; SKILL.md description fields and any siblings)
- `.claude/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `.github/plugin/marketplace.json`

Each absent path -> INFO log + skip.

### Opt-in targets (`--include-adrs`)

`.agents/architecture/` and `docs/` are excluded from the default scan. Both
contain a high density of references that look like skill names but are not
skill references in the working tree: model identifiers, third-party Action
names, CodeQL configuration tokens, frontmatter field labels, bot identifiers,
proposed-but-unimplemented memory entities, and historical references to skills
deleted by superseding ADRs. Including them by default produces a critical-fail
verdict whose findings are dominated by historical artifacts, defeating the
build-gate purpose. The `--include-adrs` flag opts back in for periodic audits.

### Wedge-PR scope decision (PR1)

PR1 of TASK-008 implements detection for skill-name and count-claim refs only.
Script-path detection (REQ-008-AC3) is deferred to PR2 alongside `/test` Gate 5
wiring (REQ-008-AC8). Self-test on the source repository surfaced two real
orphans within the default scope:

1. `.claude-plugin/marketplace.json` claimed `23 agents`; actual count is `25`.
2. ADR-052 references `build/scripts/generate_platform_agents.py`, which is <!-- orphan-ref-ignore -->
   absent on disk. AC3 is not yet active in PR1, so this orphan is filed for
   PR2 follow-up.

Real orphans inside `.agents/architecture/` (deleted skills referenced in
ADR-007, ADR-017, ADR-040) are out of scope for the wedge PR and tracked as a
follow-up issue.

## Wiring into Lifecycle Gates

### `/build` Mandatory Exit Gates

`.claude/commands/build.md` already lists code-qualities-assessment, taste-lints, doc-accuracy. Add:

```markdown
- [ ] orphan-ref-validator: `python3 .claude/skills/orphan-ref-validator/scripts/scan.py`. CRITICAL_FAIL blocks build phase.
```

### `/test` Gate 5 (DX)

`.claude/commands/test.md` Gate 5 lists cross-cutting checks. Add:

```markdown
- [ ] orphan-ref-validator: `python3 .claude/skills/orphan-ref-validator/scripts/scan.py`. CRITICAL_FAIL surfaces in test summary.
```

## Performance Characteristics

- File walk bounded by target enumeration (default <500 files).
- Regex application is line-oriented; per-file O(N).
- Working-tree probes cached per scan (skill set, script set enumerated once).
- Expected runtime: <2s on default targets (full repo scan).
- Memory: bounded by findings list; expected <1MB.

## Failure Recovery

| Failure | Recovery |
|---|---|
| Target path missing | INFO log + skip |
| Target file unreadable (permissions) | WARN log + skip; Finding(kind=parse_error) |
| Malformed JSON in manifest | Finding(kind=count_claim, severity=warn, msg="parse failed"); continue |
| Regex catastrophic backtrack | Bounded by Python `re` (no `re2` dependency); pattern designed without nested quantifiers |
| Out of memory on large file | File-size guard: skip files >5MB with WARN |

## Security

- Read-only file system access.
- Path normalization via `pathlib.Path.resolve()`.
- Reject scan targets outside repo root (CWE-22 mitigation).
- No shell, no subprocess, no network, no eval.
- No secret reading: explicit denylist for `.env*`, `secrets.*`, `*.key`, `*.pem`.

## Open Design Decisions

None. All resolved in REQ-008 + this design.
