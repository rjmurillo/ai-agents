---
type: design
id: DESIGN-008
title: Orphan-Ref Validator Skill Design
status: draft
priority: P2
related: [REQ-008, TASK-008]
created: 2026-05-10
updated: 2026-05-10
author: richard
---

# DESIGN-008: Orphan-Ref Validator Skill

## Requirements Addressed

This design implements REQ-008 acceptance criteria AC1, AC2, AC3, AC5, AC6, AC7, and AC9 (subset). AC4 (count_claim emission) is delegated to `build/scripts/validate_marketplace_counts.py` per `.claude/rules/canonical-source-mirror.md`; the regex and label map mirror the canonical pattern, but emission is gated behind an opt-in flag reserved for PR2. AC8 (/test Gate 5 wiring) is deferred to PR2. Cross-references: REQ-008-AC1 through REQ-008-AC9, ADR-035 (exit codes), ADR-056 (output envelope), `.claude/rules/canonical-source-mirror.md` (citation policy).

## Design Overview

Single-process Python scanner that walks configured target paths, applies a small set of reference-pattern regexes, and reconciles each match against the working tree. Emits ADR-056 envelope on stdout. Exit code per ADR-035.

The skill is fail-closed: any unrecognized configuration error returns exit `2`, any critical finding returns exit `1`. PASS and WARN return `0`. The envelope's `Success` field reflects scan execution (`true` for any completed scan, including CRITICAL_FAIL); `Success: false` is reserved for configuration or runtime failures with a populated `Error` block, per ADR-056.

## Component Details

| Component | Location | Responsibility |
|---|---|---|
| CLI entry | `scan.py:main`, `parse_args` | Parse argv, validate `--repo-root`, dispatch to `scan`, format envelope, return ADR-035 exit code |
| Target expansion | `scan.py:_expand_target` | Resolve literal files, directories, and glob patterns against repo root |
| File walk | `walking.py:walk_targets`, `_iter_dir_pruned`, `is_safe_subdirectory` | Recursive iterdir with directory-name pruning for `EXCLUDE_DIR_NAMES`; secret denylist; 5 MB cap; symlink-directory containment at recursion entry |
| Reference detection | `patterns.py:extract_skill_refs`, `extract_script_refs`, `extract_count_claims` | Line-oriented regex extraction with file-scope and line-scope ignore directive support; consumed by `scan.py` via re-export |
| Filters | `filters.py:is_known_kebab_word` | Curated denylist of kebab tokens that match `SKILL_REF_RE` but are not skill references (model IDs, frontmatter fields, third-party Action names, bot identifiers, eval verdict literals) |
| Source-of-truth enumeration | `counts.py:enumerate_skills`, `enumerate_count`, `_count_md_agents`, `_count_md_recursive`, `_count_py_recursive` | Mirror canonical strategies from `build/scripts/validate_marketplace_counts.py` for working-tree counts |
| Output rendering | `envelope.py:Finding`, `ScanResult`, `render_envelope`, `render_error_envelope` | ADR-056 envelope shape and verdict line; `render_error_envelope` covers the exit-2 path |
| Containment | `scan.py:scan` | Repo-root containment recheck on every walked file (post symlink resolution); `skill_catalog_present` flag thread for warn-vs-critical disambiguation |

## Technology Decisions

- **Language**: Python (repo declares `>=3.10` in `pyproject.toml`); stdlib only, no third-party imports. Rationale: ADR-042 Python-first, plus the skill must run in vendored installs where `pip install` may not have run.
- **Walk strategy**: `Path.iterdir` with directory-name pruning, not `Path.rglob('*')`. Rationale: gemini-code-assist [bot] flagged `rglob('*')` as O(N) over excluded subtrees (`node_modules`, `.git`, `references`, `templates`, `__pycache__`); pruning at directory level avoids entering them.
- **Output envelope**: ADR-056 four-field shape (`Success`, `Data`, `Error`, `Metadata`) with `VERDICT:` line appended for grep-friendly downstream parsing.
- **Exit codes**: ADR-035 (`0` PASS/WARN, `1` CRITICAL_FAIL, `2` configuration error).
- **Canonical-source-mirror**: COUNT_CLAIM_RE and COUNT_LABEL_MAP mirror `validate_marketplace_counts.py:COUNT_PATTERN` and `LABEL_MAP` byte-for-byte. enumerate_count mirrors the project-toolkit `md_agents`, `commands`, `hooks`, `skill_dirs` strategies; the canonical's per-plugin override loader (`templates/marketplace-counters.yaml`) is not duplicated.

## Security Considerations

- **Path traversal (CWE-22 / CWE-59)**: every target and every walked file resolves through `Path.resolve()` and is rechecked against `repo_root` via `relative_to`. Symlink directories that resolve outside the repo are skipped at recursion entry (in `walking.is_safe_subdirectory`); symlink files outside the repo are skipped after resolution. The walker never enters a foreign tree.
- **Command injection (CWE-78)**: not applicable; no `subprocess`, no shell, no string concatenation into commands.
- **Secrets in scanned content**: secret-denylist regex skips files whose names match `.env*`, `secrets.*`, `*.key`, `*.pem`, `*.pfx`, `*.p12`, `id_rsa(.pub)?`, `id_ed25519(.pub)?`, `id_ecdsa(.pub)?`, `id_dsa(.pub)?`, `.netrc`, `.npmrc`, `.pypirc`, `credentials`. Files larger than 5 MB are skipped to avoid memory exhaustion.
- **Trusted input only**: scan targets are repository paths controlled by the developer running `/build`. No untrusted external input crosses the regex boundary.
- **No network**: skill is fully read-only and offline.
- **Ignore-directive bypass is intentional**: `<!-- orphan-ref-ignore-file -->` and `<!-- orphan-ref-ignore -->` are documented escape hatches. A committer can mute the gate by adding the directive in the same change. The compensating control is human code review of any commit that adds an ignore directive (the directives are rare in the working tree and easy to grep). This is a deliberate trade between false-positive friction and security-of-the-gate; treat it as policy, not a bug.

## Testing Strategy

- **Unit tests**: `tests/test_scan.py` covers each AC positively and negatively, ADR-056 envelope shape (including the `Success: false` exit-2 envelope), ADR-035 exit codes, vendored-install scenarios (skill catalog absent, empty, or pointing at a regular file), ignore directives at both scopes, glob target expansion, walk-prune behavior, symlink containment for both file and directory targets, in-repo symlink-cycle guard, max-findings cap, and edge cases (empty file, secret denylist, oversized files, mixed living-and-dead refs, CWD-not-in-git fallback).
- **Self-test (TASK-008-07)**: scan the source repo with default scope; iterate filters and ignore directives until VERDICT: PASS; document remaining preexisting orphans surfaced by `--include-adrs` and `--include-skill-descriptions` as out-of-scope follow-up work.
- **Coverage gate**: `pytest --cov=scripts.scan --cov-fail-under=80`. Achieved coverage on `scan.py` exceeds the 80% floor.
- **Integration with canonical**: `tests/test_validate_marketplace_counts.py` continues to enforce manifest counts; orphan-ref-validator does not duplicate that path. The two test suites do not overlap.

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
- `.claude/.claude-plugin/plugin.json`
- `.claude-plugin/marketplace.json`
- `.github/plugin/marketplace.json`

Each absent path -> INFO log + skip. Skill descriptions (`.claude/skills/*/SKILL.md`) are opt-in via `--include-skill-descriptions`; ADRs and `docs/` are opt-in via `--include-adrs`.

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

PR1 of TASK-008 implements detection for skill_name, script_path, and
count_claim refs. count_claim emission is delegated to the canonical
`build/scripts/validate_marketplace_counts.py` (PR1 ships the regex and label
map but no Findings). `/test` Gate 5 wiring (REQ-008-AC8) is deferred to PR2.

Real orphans inside `.agents/architecture/` (deleted skills referenced in
ADR-007, ADR-017, ADR-040) are out of scope for the wedge PR and tracked as a
follow-up issue.

## Wiring into Lifecycle Gates

### `/build` Mandatory Exit Gates

`.claude/commands/build.md` already lists code-qualities-assessment, taste-lints, doc-accuracy. Add:

```markdown
- [ ] orphan-ref-validator: `python3 .claude/skills/orphan-ref-validator/scripts/scan.py`. CRITICAL_FAIL blocks build phase.
```

### `/test` Gate 5 (DX) -- deferred to PR2

PR1 does not wire `/test` Gate 5; this is REQ-008-AC8, deferred per the Deferred section in REQ-008 and the milestones in TASK-008. PR2 will add:

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
| Target path missing | INFO log + skip; no finding |
| Target file unreadable (permissions) | WARN log + skip; no finding emitted (the file is treated like an absent target) |
| Malformed JSON in manifest | Manifest is read as text; `COUNT_CLAIM_RE` still matches the description string. Count enforcement is delegated to the canonical validator, so PR1 emits no finding here. Canonical-side errors are reported by `validate_marketplace_counts.py`. |
| Regex catastrophic backtrack | Bounded by Python `re` (no `re2` dependency); patterns designed without nested quantifiers |
| Out of memory on large file | File-size guard: skip files >5MB with WARN |
| Findings list grows unbounded | `MAX_FINDINGS=500` cap; on hit, scan halts and emits `Finding(kind=scan_truncated, severity=warn)` so the operator knows the result is partial. |
| Symlink target outside repo (file or directory) | Skipped at recursion entry / yield; logged as WARN (CWE-22 / CWE-59) |
| In-repo symlink cycle | Visited-set guard; skipped on revisit; logged as WARN |

## Security

- Read-only file system access.
- Path normalization via `pathlib.Path.resolve()`.
- Reject scan targets outside repo root (CWE-22 mitigation).
- No shell, no subprocess, no network, no eval.
- No secret reading: explicit denylist for `.env*`, `secrets.*`, `*.key`, `*.pem`.

## Open Design Decisions

None. All resolved in REQ-008 + this design.
