---
name: orphan-ref-validator
version: 1.0.0
model: claude-sonnet-4-6
description: Detect references to skills, scripts, and counts in structured artifacts (specs, ADRs, eval fixtures, plugin manifests, skill descriptions) that do not match working-tree state. Run as a /build Mandatory Exit Gate to block orphan refs pre-commit instead of paying iteration rounds in /pr-quality:all post-PR.
license: MIT
---

# orphan-ref-validator

## Purpose

Scans structured artifacts (specs, ADRs, eval fixtures, plugin manifests, skill descriptions) for references to entities that do not exist in the working tree:

- Skill names that no longer have a `.claude/skills/<name>/` directory.
- Script paths under `build/scripts/`, `scripts/validation/`, or `scripts/` that are not present on disk.
- Count claims in plugin or marketplace manifests that diverge from actual catalog enumeration.

Emits findings per the ADR-056 envelope and a final `VERDICT: PASS|WARN|CRITICAL_FAIL` line. Exit code follows ADR-035: `0` for PASS or WARN, `1` for CRITICAL_FAIL, `2` for configuration error.

The skill ships with vendored installs. When a target path is not present (for example, `.agents/` is absent), the skill logs INFO and continues; it does not raise.

## Triggers

| Trigger | Effect |
|---|---|
| `scan for orphan refs` | Run with default targets |
| `validate orphan references` | Run on a specific path |
| `check skill catalog drift` | Run with default targets |
| `validate manifest counts` | Run on plugin manifests |
| `build mandatory exit gate` | Invoked by the build lifecycle command |

## Inputs

```text
python3 .claude/skills/orphan-ref-validator/scripts/scan.py \
    [--targets PATH ...] \
    [--repo-root PATH] \
    [--output {json,human}] \
    [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

| Flag | Purpose | Default |
|---|---|---|
| `--targets` | Files or directories to scan | `.agents/specs/`, `tests/evals/`, `.claude/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json` |
| `--include-adrs` | Add `.agents/architecture/` and `docs/` to defaults (opt-in) | off |
| `--include-skill-descriptions` | Add `.claude/skills/*/SKILL.md` to defaults (opt-in until preexisting drift is cleaned) | off |
| `--repo-root` | Repository root. Walks up from CWD for the nearest `.git` directory; falls back to CWD. Validates that user-supplied paths exist and are directories (returns ADR-035 exit `2` otherwise). | walked from CWD |
| `--output` | `json` (ADR-056 envelope) or `human` (compact summary) | `json` |
| `--log-level` | Python logging level | `WARNING` |

## Outputs

`json` mode (default):

```json
{
  "Success": true,
  "Data": {
    "findings": [
      {
        "kind": "skill_name",
        "severity": "critical",
        "target_file": "docs/old.md",
        "line": 12,
        "referenced_entity": "doc-sync",
        "recommendation": "Skill `doc-sync` not present at .claude/skills/. Update reference, restore the skill, or remove the mention."
      }
    ],
    "verdict": "CRITICAL_FAIL",
    "counts": {"files_scanned": 142, "refs_checked": 318, "findings_total": 1}
  },
  "Error": null,
  "Metadata": {"Script": "scan.py", "Version": "1.0.0", "Timestamp": "..."}
}
VERDICT: CRITICAL_FAIL
```

`human` mode:

```text
orphan-ref-validator 1.0.0
  files_scanned: 142
  refs_checked:  318
  findings:      1
  [critical] docs/old.md:12 skill_name `doc-sync` -- Skill `doc-sync` not present at .claude/skills/. ...
VERDICT: CRITICAL_FAIL
```

## Process

### Phase 1: Resolve Targets

- Read `--targets` if supplied, else use `DEFAULT_TARGETS`.
- Append `OPT_IN_ADR_TARGETS` if `--include-adrs` is set.
- Append `OPT_IN_SKILL_TARGETS` if `--include-skill-descriptions` is set.
- Expand glob patterns containing `*` or `?` against the repository root.
- Skip any target that resolves outside the repository root.

### Phase 2: Walk Files

- For directory targets, recurse and yield files whose suffix matches `.md`, `.json`, `.yaml`, `.yml`.
- Exclude paths whose any segment is in `EXCLUDE_DIR_NAMES` (`__pycache__`, `.git`, `node_modules`, `references`, `templates`).
- Exclude files matching the secret denylist and files larger than 5 MB.

### Phase 3: Detect References

- Read the first 50 lines for `<!-- orphan-ref-ignore-file -->`. If present, skip the file.
- Apply `SKILL_REF_RE`, `SCRIPT_REF_RE`, and `COUNT_CLAIM_RE` line by line.
- Skip any line carrying `<!-- orphan-ref-ignore -->`.
- Filter known-kebab tokens (model IDs, frontmatter fields, Action names, bot ids, git hooks, vocabulary terms).

### Phase 4: Resolve and Verdict

- For each surviving reference, check the source of truth (skill set, file presence, count enumeration).
- Build the ADR-056 envelope with findings, counts, and verdict.
- Verdict is `CRITICAL_FAIL` if any finding has severity `critical`, else `WARN` if findings exist, else `PASS`.
- Print envelope and `VERDICT:` line. Exit 1 on CRITICAL_FAIL, 2 on configuration error, 0 otherwise.

## Verification

Success criteria for the skill:

- [ ] `uv run pytest .claude/skills/orphan-ref-validator/tests/ -q` reports 34 passed.
- [ ] `python3 .claude/skills/orphan-ref-validator/scripts/scan.py --help` exits 0 with the documented argparse output.
- [ ] `python3 .claude/skills/orphan-ref-validator/scripts/scan.py --targets /tmp/empty.md` exits 0 with `VERDICT: PASS`.
- [ ] `python3 .claude/skills/orphan-ref-validator/scripts/scan.py` from the repo root exits 0 with `VERDICT: PASS` on default targets.
- [ ] `.claude/commands/build.md` Mandatory Exit Gates lists orphan-ref-validator as gate 4.

## Scripts

| Script | Purpose |
|---|---|
| `scripts/scan.py` | Main entrypoint. Argparse CLI, target resolution, walking, detection, envelope rendering, exit codes. |
| `scripts/__init__.py` | Marks `scripts/` as a Python package so tests can import `from scripts.scan import ...`. |

Invoke directly with `python3 .claude/skills/orphan-ref-validator/scripts/scan.py [flags]`. Do not import the script from other modules; treat it as a CLI tool.

## Anti-Patterns

- Adding a new skill name to the denylist when the real fix is to register the skill or remove the reference.
- Using `<!-- orphan-ref-ignore-file -->` on an active spec to mask a real orphan; reserve the directive for historical specs and proposed-entity catalogs.
- Suppressing real script_path findings by editing the regex; instead, fix the AC text or restore the script.
- Running with `--include-skill-descriptions` at the `/build` gate before preexisting skill-description drift is cleaned; the gate becomes noisy and reviewers ignore it.

## Extension Points

- Add new entity kinds (for example, agent names) by extending `Kind`, adding a regex, and wiring `scan_file` to call a new enumerator.
- Tighten the regex for a kind by editing the corresponding `*_REF_RE` constant in `scan.py`.
- Add per-kind exit-code escalation by branching on `result.verdict` in `main` before returning.
- Replace the markdown ignore directive with a structured config file by parsing `.orphan-ref-ignore` at the repository root.

## Behavior

### Reference detection

| Kind | Pattern | Source of truth |
|---|---|---|
| `skill_name` | `` `<kebab>` `` where `<kebab>` matches `[a-z][a-z0-9-]+` | `.claude/skills/<name>/SKILL.md` directories |
| `script_path` | `` `(build/scripts\|scripts/validation\|scripts)/<path>.py` `` | file existence on disk |
| `count_claim` | `\b<digits>\s+(skills\|agents\|commands\|hooks)\b` (manifest files only) | working-tree enumeration |

Common kebab-case English phrases (`well-known`, `open-source`, `step-by-step`, etc.) are filtered to reduce false positives. The filter list lives in `scan.py:_is_known_kebab_word`.

### Verdict logic

| Findings | Verdict |
|---|---|
| Any finding has `severity=critical` | `CRITICAL_FAIL` |
| Findings exist, all `severity=warn` | `WARN` |
| No findings | `PASS` |

### Vendored install behavior

Each missing target path logs `INFO skipping <path>: not present` and is skipped. The skill never raises on absent paths; it returns `PASS` if the entire target list is absent.

### Path safety

Target paths are resolved with `pathlib.Path.resolve()` and must lie under the repository root. Paths outside the repo are skipped with a `WARNING` log. Files in the secret denylist (`.env*`, `secrets.*`, `*.key`, `*.pem`) are excluded. Files larger than 5 MB are skipped with a `WARNING`.

## Failure modes

| Mode | Behavior |
|---|---|
| Missing target path (vendored install) | `INFO` log + skip; not an error |
| Target file unreadable (permissions) | `WARNING` log + skip; no finding |
| Manifest with malformed JSON | scanned as text; count claims still extracted |
| Cannot enumerate count for kind (target dir absent) | `WARN`-severity finding |
| Symlink loops or oversized files | bounded by Python's `Path.rglob` and the 5 MB cap |
| Unknown count kind | ignored |

## Examples

```bash
# Default scan from repo root
python3 .claude/skills/orphan-ref-validator/scripts/scan.py

# Scan only one file
python3 .claude/skills/orphan-ref-validator/scripts/scan.py \
    --targets docs/skill-reference.md

# Human summary
python3 .claude/skills/orphan-ref-validator/scripts/scan.py --output human
```

## Tests

```bash
pytest .claude/skills/orphan-ref-validator/tests/ -q
```

Coverage target is 80 percent line coverage on `scan.py`. Cases cover positive and negative detection for each kind, the ADR-056 envelope shape, vendored-install scenarios, and edge cases (empty file, mixed living-and-dead refs, large files, secret files).

## Wiring

### `/build` Mandatory Exit Gate

`.claude/commands/build.md` invokes the skill. Exit `1` blocks the build phase.

### Pre-push hook (optional)

Repos that want a tighter feedback loop can add a pre-push hook that runs the skill against the staged diff. The skill is read-only and exits `1` on critical findings, which the hook can use to block the push.

## References

- REQ-008, DESIGN-008, TASK-008
- ADR-035 (exit codes)
- ADR-042 (Python first)
- ADR-056 (skill output envelope)
- Issue #1939, Epic #1933, retro #1940
- Companion validators: `build/scripts/validate_marketplace_counts.py`, `build/scripts/validate_plugin_manifests.py`
