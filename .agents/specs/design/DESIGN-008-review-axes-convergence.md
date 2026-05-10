---
type: design
id: DESIGN-008
title: review-axes-convergence
related:
  - REQ-008
  - REQ-008-01
  - REQ-008-02
  - REQ-008-03
  - REQ-008-04
  - REQ-008-05
  - REQ-008-06
  - REQ-008-07
  - REQ-008-08
adr:
  - ADR-006 (thin workflows)
  - ADR-035 (exit codes)
  - ADR-042 (Python-first)
  - ADR-054 (security scan scope)
author: Richard Murillo
date: 2026-05-09
---

# DESIGN-008: review-axes-convergence

## Requirements Addressed

REQ-008-01 through REQ-008-08. Resolves drift between `/review` local evaluation and CI `ai-pr-quality-gate.yml` discovered via retrospective `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`.

## Design Overview

A single canonical source directory (`.claude/review-axes/`) holds one markdown file per review role. A generator (`build/scripts/generate_pr_quality_prompts.py`) derives CI prompt files from it atomically. Drift is enforced at two gates: pre-push hook (bypassable) and CI drift-check job (not bypassable). `/review` loads canonical files at runtime and chains 3 skill invocations, merging all 9 verdicts via `ai_review_common.py`. No new abstraction layer is introduced; the 6/3 family split is explicit in `/review` prose.

## File Layout

```
.claude/
  review-axes/              # SoR - canonical axis definitions
    analyst.md
    architect.md
    devops.md
    qa.md
    roadmap.md
    security.md
  lib/
    ai_review_common.py     # verdict merge module (SoR for merge logic)
  commands/
    review.md               # rewritten /review command
    pr-quality/
      all.md                # updated citation (ai_review_common.py)

.github/
  prompts/                  # derived - never hand-edited
    pr-quality-gate-analyst.md
    pr-quality-gate-architect.md
    pr-quality-gate-devops.md
    pr-quality-gate-qa.md
    pr-quality-gate-roadmap.md
    pr-quality-gate-security.md
  workflows/
    ai-pr-quality-gate.yml  # drift-check job added

build/
  scripts/
    generate_pr_quality_prompts.py   # new generator

.githooks/
  pre-push                  # drift-detection step added

tests/
  lib/
    test_ai_review.py
  build_scripts/
    test_generate_pr_quality_prompts.py
  hooks/
    test_drift_check.py
  integration/
    test_vendored_install.py
```

## Component Architecture

### Canonical Axis File (`.claude/review-axes/{role}.md`)

**Purpose:** Single source of truth for review role definition.

**Responsibilities:**
- Define role identity (`name`, `role`, `version`, `description` in YAML frontmatter).
- Define evaluation scope (`Analysis Focus Areas`).
- Define behavioral constraints (`Grounding Rules`).
- Define output contract (`Output Schema` with `severity`, `category`, `location`, `recommendation`, `verdict`).

**Interface:** File system read. No execution. Consumed by generator and by `/review` at runtime.

**Invariants:**
- Frontmatter keys `name`, `role`, `version`, `description` are required.
- Body headings `Grounding Rules`, `Analysis Focus Areas`, `Output Schema` are required.
- Verdict tokens documented in `Output Schema`: `PASS`, `WARN`, `CRITICAL_FAIL`, `UNKNOWN`.
- Filename regex: `^[a-z][a-z0-9_-]*\.md$`.

**Initial content:** Seeded verbatim from `.github/prompts/pr-quality-gate-{role}.md` at migration time. The migration task is TASK-008-01.

### Verdict Merge Module (`.claude/lib/ai_review_common/`)

**Purpose:** Single authoritative implementation of verdict merge rules and emoji mapping.

**Responsibilities:**
- `merge_verdicts(verdicts: Sequence[str]) -> str`: collapse N verdict tokens to one.
- `get_verdict_emoji(verdict: str) -> str`: map token to display emoji.

**Interface:**

```python
# ai_review_common.py
# Canonical source: .claude/review-axes/{role}.md Output Schema section
# Verdict tokens: PASS, WARN, CRITICAL_FAIL, REJECTED, FAIL, UNKNOWN

from typing import Sequence

VERDICT_TOKENS = {"PASS", "WARN", "CRITICAL_FAIL", "REJECTED", "FAIL", "UNKNOWN"}
CRITICAL_TOKENS = {"CRITICAL_FAIL", "REJECTED", "FAIL"}

def merge_verdicts(verdicts: Sequence[str]) -> str:
    """
    Merge rule (in priority order):
    1. Any CRITICAL_FAIL / REJECTED / FAIL -> CRITICAL_FAIL
    2. Any WARN -> WARN
    3. All PASS -> PASS
    4. Empty or all UNKNOWN -> UNKNOWN
    Unknown tokens are treated as UNKNOWN and logged as WARN.
    """
    ...

def get_verdict_emoji(verdict: str) -> str:
    """Return display emoji for a verdict token. Unknown tokens return a fallback."""
    ...
```

**Emoji mapping (reference, not normative):**

| Token | Emoji |
|-------|-------|
| PASS | `[+]` or green checkmark |
| WARN | `[!]` or yellow warning |
| CRITICAL_FAIL | `[X]` or red cross |
| UNKNOWN | `[?]` or grey circle |

Exact emoji characters are an implementation detail resolved in TASK-008-02. Chosen for terminal compatibility (avoid Unicode that renders as boxes in some CI log viewers).

**Constraints:**
- No `eval`, `exec`, subprocess calls.
- No file I/O.
- Pure function (no side effects beyond logging unknown token names).
- 100% line and branch coverage required.

### Generator (`build/scripts/generate_pr_quality_prompts.py`)

**Purpose:** Derive `.github/prompts/pr-quality-gate-{role}.md` from `.claude/review-axes/{role}.md`.

**Responsibilities:**
- Scan `.claude/review-axes/` for files matching `^[a-z][a-z0-9_-]*\.md$`.
- Validate required frontmatter keys.
- Transform content (apply CI-specific header/footer if needed; otherwise copy verbatim with a `# GENERATED - do not edit` banner).
- Write atomically: open `.tmp` file, write, `fsync`, `os.rename`.
- Emit `key=value` lines to stdout per role.
- Exit 0/1/2 per ADR-035.

**Interface (CLI):**

```
python3 build/scripts/generate_pr_quality_prompts.py [--dry-run] [--no-regen]

Options:
  --dry-run     Compute diff but do not write files. Exit 1 if diff non-empty.
  --no-regen    Skip files with NO-REGEN sentinel comment in canonical.

Exit codes:
  0  All files generated successfully (or no changes needed in dry-run).
  1  Content/logic error (malformed frontmatter, unknown token in schema, etc.).
  2  Config error (canonical directory missing, canonical file unreadable).

Stdout (key=value per role):
  role=analyst status=ok output=.github/prompts/pr-quality-gate-analyst.md
  role=architect status=ok output=.github/prompts/pr-quality-gate-architect.md
  ...
  summary=generated:6 skipped:0 errors:0
```

**Atomic write sequence:**

```
tmp_path = output_path + ".tmp"
open(tmp_path, "w") as f:
    f.write(content)
    f.flush()
    os.fsync(f.fileno())
os.rename(tmp_path, output_path)
```

**Constraints:**
- No `eval`, `exec`, `shell=True`, subprocess.
- Follows `generate_commands.py` precedent (ADR-035 exit codes, NO-REGEN sentinel, regen_guard pattern).
- Pure Python string operations for content transformation.

**OQ2 resolution (Orchestrator update mechanism):** The generator does NOT auto-update `.claude/commands/pr-quality/all.md`. That file's citation update is a one-time manual task (TASK-008-07). DEF1 defers generator-driven orchestrator prose to a future trigger.

### Drift Check (pre-push hook step + CI job)

**Purpose:** Enforce that generated files match canonical at push and merge time.

**Pre-push hook step (`.githooks/pre-push`):**

Bash (ADR-005 grandfathered). Added step after existing checks:

```bash
# Drift check: canonical vs generated
if command -v python3 >/dev/null 2>&1; then
  python3 build/scripts/generate_pr_quality_prompts.py --dry-run
  if [ $? -ne 0 ]; then
    echo "ERROR: review-axes drift detected. Run: python3 build/scripts/generate_pr_quality_prompts.py" >&2
    exit 1
  fi
fi
```

Bypassable via `--no-verify`. CI job is the backstop.

**CI drift-check job (`ai-pr-quality-gate.yml`):**

```yaml
drift-check:
  name: Drift Check (canonical vs generated)
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@<SHA>
    - uses: actions/setup-python@<SHA>
      with:
        python-version: "3.14"
    - name: Check drift
      run: |
        python3 build/scripts/generate_pr_quality_prompts.py --dry-run
      # On non-zero exit, actions/github-script emits error annotation
    - name: Annotate on failure
      if: failure()
      uses: actions/github-script@<SHA>
      with:
        script: |
          core.error('review-axes drift: run python3 build/scripts/generate_pr_quality_prompts.py and commit changes')
```

**Security:** Drift check reads file bytes and runs Python string ops only. No prompt content is executed.

### `/review` Command (`.claude/commands/review.md`)

**Purpose:** Converged local review command that matches CI evaluation surface.

**Responsibilities:**
- Load 6 canonical axis files from `.claude/review-axes/`.
- Evaluate PR diff against each axis using the axis file's `Analysis Focus Areas` and `Grounding Rules`.
- Collect verdict token from `Output Schema` fields for each axis.
- Chain 3 skill invocations: `Skill(skill="code-qualities-assessment")`, `Skill(skill="golden-principles")`, `Skill(skill="taste-lints")`.
- Collect verdict token from each skill (default `UNKNOWN` if skill crashes or returns no verdict).
- Merge all 9 verdicts via `merge_verdicts` from `.claude/lib/ai_review_common/`.
- Output findings table and merged verdict with emoji.

**Findings table format:**

```
| Axis                  | Verdict      | Key Findings                        |
|-----------------------|--------------|-------------------------------------|
| analyst               | [+] PASS     | No maintainability issues.          |
| architect             | [!] WARN     | Boundary leak in hooks layer.       |
| qa                    | [+] PASS     | Test coverage adequate.             |
| security              | [X] CRITICAL | CWE-78 pattern in run_cmd().        |
| devops                | [+] PASS     | CI config correct.                  |
| roadmap               | [+] PASS     | Aligned with epic #1933.            |
| code-qualities        | [+] PASS     | Cohesion score 8/10.                |
| golden-principles     | [!] WARN     | GP-003 violation in helpers.py.     |
| taste-lints           | [+] PASS     | No taste violations.                |

Final verdict: [X] CRITICAL_FAIL
```

**Error handling per axis:**
- If a skill invocation raises or returns no verdict: log `UNKNOWN` for that axis, continue.
- `UNKNOWN` propagates into `merge_verdicts` per REQ-008-05 rules (does not force CRITICAL_FAIL).

**OQ1 resolution (Plugin manifest):** `/review` reads `.claude/review-axes/` via relative path from the command's working directory. No plugin manifest enumeration is needed; the directory convention is sufficient. If `validate_plugin_manifests.py` requires explicit enumeration, the 6 role names are a static list that can be hardcoded in the validator. Implementer must read `scripts/validate_plugin_manifests.py` to confirm (TASK-008-06).

**OQ3 resolution (Schema MUSTs vs SHOULDs):** The three body sections (`Grounding Rules`, `Analysis Focus Areas`, `Output Schema`) are MUST in the axis file schema. Individual sub-fields within `Output Schema` findings are MUST for `severity`, `verdict`; SHOULD for `category`, `location`, `recommendation`.

## Technology Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Canonical SoR location | `.claude/review-axes/` | Ships with `.claude/` convention; vendored installs get it automatically |
| Generator language | Python 3.14 | ADR-042 Python-first; no new bash scripts |
| Atomic write | tmp + fsync + rename | Prevents corrupt output on crash; POSIX rename is atomic |
| Verdict merge location | `.claude/lib/ai_review_common/` | Replaces deleted `AIReviewCommon.psm1`; Python per ADR-042 |
| Drift enforcement | pre-push (bypassable) + CI job (not bypassable) | Defense in depth; pre-push = fast feedback; CI = backstop |
| `/review` axis loading | Runtime file read from `.claude/review-axes/` | No build step required at review time; works in vendored install |
| 3 extra skill axes | Chained via `Skill()` after canonical axes | Independent lifecycle; not duplicated in CI (CI-counterpart: no) |
| Orchestrator update | Manual one-time task, not generator-driven | DEF1 deferred; complexity not justified until recurrence observed |

## Data Flow

```
[Maintainer edits .claude/review-axes/analyst.md]
         |
         v
[git push]
  -> .githooks/pre-push drift-check step
     -> generate_pr_quality_prompts.py --dry-run
     -> exit 1 on divergence (show diff)
         |
         v (on push success)
[PR open -> ai-pr-quality-gate.yml]
  -> drift-check job (backstop)
  -> 6 axis prompt jobs (each reads .github/prompts/pr-quality-gate-{role}.md)
         |
[Maintainer runs /review locally]
  -> loads .claude/review-axes/*.md (6 files)
  -> evaluates PR diff against each
  -> chains Skill(code-qualities-assessment)
  -> chains Skill(golden-principles)
  -> chains Skill(taste-lints)
  -> merge_verdicts([v1..v9]) -> final_verdict
  -> output findings table + emoji verdict
```

## Security Considerations

- Canonical axis files are mode 0644. No execution permission.
- Drift check compares file bytes; does not execute prompt content. No prompt injection surface.
- Generator uses pure Python string ops; no `eval`, `exec`, `shell=True`, subprocess.
- Filename validation regex `^[a-z][a-z0-9_-]*\.md$` prevents path traversal in generator's directory scan.
- `.claude/review-axes/` changes trigger `security-detection` skill per `.claude/rules/security.md`.
- No secrets stored in canonical files or generated prompts.

## Testing Strategy

| Test file | What it covers |
|-----------|----------------|
| `tests/lib/test_ai_review.py` | All `merge_verdicts` combinations, all `get_verdict_emoji` tokens, 100% coverage |
| `tests/build_scripts/test_generate_pr_quality_prompts.py` | Idempotency, partial-write recovery, schema validation (filename regex, missing frontmatter), NO-REGEN sentinel, exit codes |
| `tests/hooks/test_drift_check.py` | Pre-push drift step positive (no diff, exit 0) and negative (diff present, unified diff emitted, exit 1) |
| `tests/integration/test_vendored_install.py` | Fresh-checkout with only `.claude/` subtree; `/review` completes successfully |

All tests: pytest 8+, Python 3.14. No `Skip` or `pytest.mark.skip` without linked issue.

## Open Questions

| OQ | Status | Resolution |
|----|--------|------------|
| OQ1: Plugin manifest enumeration | Resolved in design | Runtime relative path read; implementer confirms by reading `validate_plugin_manifests.py` in TASK-008-06 |
| OQ2: Orchestrator update mechanism | Resolved in design | Manual one-time task; DEF1 defers generator-driven approach |
| OQ3: Axis schema MUSTs vs SHOULDs | Resolved in design | Sections MUST; sub-fields: severity+verdict MUST, others SHOULD |
| OQ4: Issue body update timing | Deferred to implementer | TASK-008-08; run after module exists to cite correctly |
