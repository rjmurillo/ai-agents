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

- **Skill names** that no longer have a `.claude/skills/<name>/` directory. Emitted as `Finding(kind="skill_name", severity="critical")`.
- **Script paths** under `build/scripts/`, `scripts/validation/`, or `scripts/` that are not present on disk. Emitted as `Finding(kind="script_path", severity="critical")`.
- **Count claims** in plugin or marketplace manifests. The regex extracts the canonical claim shape (`COUNT_CLAIM_RE` mirrors `build/scripts/validate_marketplace_counts.py:COUNT_PATTERN`), but emission is delegated to that canonical validator. PR1 ships detection only; an opt-in `--enforce-counts` is reserved for PR2 single-plugin enforcement. Per `.claude/rules/canonical-source-mirror.md`, the canonical's YAML-driven per-plugin source-dir resolution and `--fix` path are not duplicated here.

Emits findings per the ADR-056 envelope and a final verdict line. Exit code follows ADR-035: `VERDICT: PASS` or `VERDICT: WARN` exits `0`; `VERDICT: CRITICAL_FAIL` exits `1`; configuration or runtime failures emit `VERDICT: ERROR` with `Success: false` and a populated `Error` block (`Code: 2`, `Type: InvalidParams`) and exit `2`.

The skill ships with vendored installs. When a target path is not present (for example, `.agents/` is absent), the skill logs INFO and continues; it does not raise.

## Triggers

| Trigger | Effect |
|---|---|
| `scan for orphan refs` | Run with default targets |
| `validate orphan references` | Run on a specific path |
| `check skill catalog drift` | Run with default targets |
| `validate manifest counts` | Run on plugin manifests |
| `build mandatory exit gate` | Invoked by the build lifecycle command |

## Path conventions

Absolute paths in this document (e.g. `python3 .claude/skills/orphan-ref-validator/scripts/scan.py`) assume the canonical Claude install layout under `.claude/`. The Copilot CLI mirror at `src/copilot-cli/skills/orphan-ref-validator/scripts/scan.py` is byte-identical Python; on Copilot CLI, replace `.claude/` with the install root the platform uses. The `Skill(skill="orphan-ref-validator")` invocation form is platform-agnostic and is what the `/build` gate uses.

## Inputs

```text
python3 .claude/skills/orphan-ref-validator/scripts/scan.py \
    [--targets PATH ...] \
    [--include-adrs] \
    [--include-skill-descriptions] \
    [--baseline FILE] \
    [--repo-root PATH] \
    [--output {json,human}] \
    [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

| Flag | Purpose | Default |
|---|---|---|
| `--targets` | Files or directories to scan | `.agents/specs/`, `tests/evals/`, `.claude/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json` |
| `--include-adrs` | Add `.agents/architecture/` and `docs/` to defaults (opt-in) | off |
| `--include-skill-descriptions` | Add `.claude/skills/*/SKILL.md` to defaults (opt-in until preexisting drift is cleaned) | off |
| `--baseline` | Path to a file of known pre-existing finding keys (`target_file:line:kind:referenced_entity`). Matching findings are marked `suppressed` and do not fail the scan; new findings still exit `1`. Accepts a JSON list of keys, a saved scan envelope (`Data.findings`), or one key per line (`#` comments allowed). | none |
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
    "counts": {"files_scanned": 142, "refs_checked": 318, "findings_total": 1, "findings_suppressed": 0}
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
  suppressed:    0
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
- Exclude paths whose any segment is in `EXCLUDE_DIR_NAMES` (`__pycache__`, `.git`, `node_modules`, `worktrees`, `cache`, `references`, `templates`). The first five mirror canonical `validate_marketplace_counts.py:_EXCLUDED_DIRS`; the last two are added because skill `references/` and `templates/` directories are progressive-disclosure docs that legitimately cite external entities.
- Exclude files matching the secret denylist and files larger than 5 MB.

### Phase 3: Detect References

- Apply `SKILL_REF_RE`, `SCRIPT_REF_RE`, and `COUNT_CLAIM_RE` line by line.
- Filter known-kebab tokens (model IDs, frontmatter fields, Action names, bot ids, git hooks, vocabulary terms).
- Honor the ignore directives described below.

### Ignore directives

| Directive | Scope | Where it must appear | Effect |
|---|---|---|---|
| `<!-- orphan-ref-ignore-file -->` | Whole file | Anywhere in the **first 50 lines** of the file | Skip the file entirely; emit no findings. |
| `<!-- orphan-ref-ignore -->` | Single line | Anywhere on the same line as a backticked reference | Skip every reference on that line. |

Place file-scope directives below the YAML frontmatter (if any) and well within the first 50-line window. Adding a directive at line 51 or later silently fails because the scanner only reads `text.splitlines()[:50]`.

Use file-scope on M1-deletion specs and proposed-entity catalogs whose every reference is intentional history. Use line-scope for one-off references that document an absence (for example, "the script `scripts/validation/manifest_counts.py` was not created").

### Phase 4: Resolve and Verdict

- For each surviving reference, check the source of truth (skill set, file presence, count enumeration).
- Build the ADR-056 envelope with findings, counts, and verdict.
- Verdict is `CRITICAL_FAIL` if any finding has severity `critical`, else `WARN` if findings exist, else `PASS`.
- Print envelope and `VERDICT:` line. Exit 1 on CRITICAL_FAIL, 2 on configuration error, 0 otherwise.

## Verification

Success criteria for the skill:

- [ ] `uv run pytest .claude/skills/orphan-ref-validator/tests/ -q` reports all tests passed.
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
- Tighten the regex for a kind by editing the corresponding `*_REF_RE` constant in `patterns.py`.
- Add per-kind exit-code escalation by branching on `result.verdict` in `main` before returning.
- Replace the markdown ignore directive with a structured config file by parsing `.orphan-ref-ignore` at the repository root.

## Behavior

### Reference detection

| Kind | Pattern | Source of truth |
|---|---|---|
| `skill_name` | `` `<kebab>` `` where `<kebab>` matches `[a-z][a-z0-9]*(?:-[a-z0-9]+)+` (at least one hyphen, no trailing hyphen) | `.claude/skills/<name>/SKILL.md` directories |
| `script_path` | `` `(build/scripts\|scripts/validation\|scripts)/<path>.py` `` | file existence on disk |
| `count_claim` | canonical `COUNT_PATTERN` from `validate_marketplace_counts.py` matching `<digits>\s+(specialized\s+agent\s+definition\|agent\s+definition\|agent\|slash\s+command\|lifecycle\s+hook\|reusable\s+skill)s?` (manifest files only) | working-tree enumeration via canonical strategies; **emission delegated to canonical validator in PR1** |

Common kebab-case English phrases (`well-known`, `open-source`, `step-by-step`, etc.) are filtered to reduce false positives. The filter list lives in `filters.py:is_known_kebab_word`.

### Verdict logic

The verdict considers only active (non-suppressed) findings. A finding whose
key is in the `--baseline` is marked `suppressed` and is excluded from the
verdict calculation.

| Active findings | Verdict |
|---|---|
| Any active finding has `severity=critical` | `CRITICAL_FAIL` |
| Active findings exist, all `severity=warn` | `WARN` |
| No active findings (none, or all suppressed by baseline) | `PASS` |

### Vendored install behavior

Each missing target path logs `INFO skipping <path>: not present` and is skipped. The skill never raises on absent paths; it returns `PASS` if the entire target list is absent.

### Path safety

Target paths are resolved with `pathlib.Path.resolve()` and must lie under the repository root. Paths outside the repo are skipped with a `WARNING` log. Symlink directories that resolve outside the repo are skipped at recursion entry (CWE-22 / CWE-59 hardening). Files in the secret denylist (`.env*`, `secrets.*`, `*.key`, `*.pem`, `*.pfx`, `*.p12`, `id_rsa(.pub)?`, `id_ed25519(.pub)?`, `id_ecdsa(.pub)?`, `id_dsa(.pub)?`, `.netrc`, `.npmrc`, `.pypirc`, `credentials`) are excluded. Files larger than 5 MB are skipped with a `WARNING`.

## Failure modes

| Mode | Behavior |
|---|---|
| Missing target path (vendored install) | `INFO` log + skip; not an error |
| Target file unreadable (permissions) | `WARNING` log + skip; no finding |
| Manifest with malformed JSON | scanned as text; count claims still extracted |
| Cannot enumerate count for kind (target dir absent) | No finding emitted; PR1 delegates count enforcement to canonical `validate_marketplace_counts.py`. The opt-in `--enforce-counts` flag (PR2) will surface a `WARN`-severity finding here. |
| Symlink directory pointing outside repo | Skipped at recursion entry; logged as `WARNING` (CWE-22 / CWE-59) |
| Symlink file pointing outside repo | Skipped post-resolution; logged as `WARNING` |
| Oversized files (>5 MB) | Skipped; logged as `WARNING` |
| Unknown count kind | ignored |

## When the /build gate fails

If `/build` exits with `VERDICT: CRITICAL_FAIL` from this skill, the recovery is:

1. Re-run with the human formatter to get a grep-able list of `path:line` findings:

   ```bash
   python3 .claude/skills/orphan-ref-validator/scripts/scan.py --output human
   ```

2. For each finding, choose one of three resolutions named in the recommendation string:

   | Finding kind | Three options |
   |---|---|
   | `skill_name` | restore the skill, update the reference, or remove the mention |
   | `script_path` | restore the script, update the reference, or remove the mention |

3. If the reference is intentional historical or proposed-entity documentation, add a line-scope `<!-- orphan-ref-ignore -->` (single line) or a file-scope `<!-- orphan-ref-ignore-file -->` (whole file). See "Ignore directives" above for placement rules.

4. Re-run the skill and confirm `VERDICT: PASS`.

## Investigation workflow

To find latent drift in surfaces that are opt-in by default:

```bash
python3 .claude/skills/orphan-ref-validator/scripts/scan.py \
    --include-adrs \
    --include-skill-descriptions \
    --output human
```

This adds `.agents/architecture/`, `docs/`, and every `.claude/skills/*/SKILL.md` to the scan. The output is intentionally noisy on first run because preexisting drift surfaces; treat it as a triage list, not a `/build` gate.

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
uv run pytest .claude/skills/orphan-ref-validator/tests/ -q
```

Coverage target is 80 percent line coverage on `scan.py`. Cases cover positive and negative detection for each kind, the ADR-056 envelope shape, vendored-install scenarios, and edge cases (empty file, mixed living-and-dead refs, large files, secret files).

## Wiring

### `/build` Mandatory Exit Gate

`.claude/commands/build.md` invokes the skill. Exit `1` blocks the build phase.

### PR exit gate: scope to changed files

A default repo-wide scan (no `--targets`) fails on pre-existing orphan refs that
predate the gate, so it is not a usable PR gate on a repo that already carries
debt. Two patterns avoid that:

1. **Scope to the changed files** so the gate judges only what the PR touches:

   ```bash
   python3 .claude/skills/orphan-ref-validator/scripts/scan.py \
       --targets $(git diff --name-only origin/main...HEAD)
   ```

   A PR that introduces no new orphan ref exits `0`; a PR that adds one exits `1`.
   This is the recommended PR exit-gate form.

2. **Baseline the known debt** so a repo-wide scan suppresses pre-existing
   findings and fails only on new ones. See "Generating a baseline" below.

### Generating a baseline

Capture the current repo-wide findings once, commit the baseline, and the gate
then fails only on findings introduced after that snapshot:

```bash
# Save the current full scan as the baseline (JSON envelope form).
python3 .claude/skills/orphan-ref-validator/scripts/scan.py \
    --include-adrs --include-skill-descriptions \
    --output json > orphan-ref-baseline.json

# Later runs suppress the baselined findings; new ones still fail.
python3 .claude/skills/orphan-ref-validator/scripts/scan.py \
    --include-adrs --include-skill-descriptions \
    --baseline orphan-ref-baseline.json
```

The baseline file accepts three shapes: a saved JSON envelope (`Data.findings`,
as produced above), a JSON list of key strings, or a plain-text file with one
`target_file:line:kind:referenced_entity` key per line (`#` comments allowed).
Keys are positional: editing a file shifts line numbers, so regenerate the
baseline after touching a baselined file, or prefer the changed-files form for
PR gating. Treat the baseline as debt to pay down, not a permanent allowlist.

### Pre-push hook (optional)

Repos that want a tighter feedback loop can add a pre-push hook that runs the skill against the push changeset (the commits being pushed, not the index state). Use `git diff --name-only @{push}..HEAD` (or the equivalent post-receive computation) to scope `--targets` to changed files. The skill is read-only and exits `1` on critical findings, which the hook can use to block the push.

## References

- REQ-009, DESIGN-009, TASK-009 (specs in `.agents/specs/`)
- ADR-035 (exit codes)
- ADR-042 (Python first)
- ADR-056 (skill output envelope)
- `.claude/rules/canonical-source-mirror.md` (citation policy)
- Companion validators: `build/scripts/validate_marketplace_counts.py`, `build/scripts/validate_plugin_manifests.py`
