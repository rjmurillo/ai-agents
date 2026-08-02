# Citation Schema

Formal specification of the memory enhancement citation system. Citations are
structured code references embedded in Serena memory files. They enable
automated staleness detection and confidence scoring at retrieval time.

Source of truth: `scripts/memory_enhancement/`. Where this document and that
package disagree, the package is right and this document is a bug.

## Storage Format

Citations and links live in the **markdown body**, not in YAML frontmatter.
A `citations:` key in frontmatter is never parsed.

### Citation Syntax

```text
[cite:<source_type>](<target>) - <context>
```

The context suffix is optional; the leading `- ` separator is required when
context is present. The parser is `_CITATION_PATTERN` in
`scripts/memory_enhancement/serena_integration.py`, which scans the whole body.
Convention is to collect citations under a `## Citations` heading, which
`save_memory` emits and `_strip_citation_link_blocks` recognizes.

### Link Syntax

```text
[link:<link_type>](<target_memory_id>) - <context>
```

A link must sit at the end of a line: `_LINK_PATTERN` is anchored with `$`
under `re.MULTILINE`. Convention is a `## Links` heading.

### Example Memory

```markdown
---
title: Validate at the boundary
tags: [security]
created_at: 2026-07-01T00:00:00+00:00
updated_at: 2026-07-01T00:00:00+00:00
---

Validate untrusted input where it enters the system.

## Citations

[cite:file](src/validate.py) - the validation entry point
[cite:adr](ADR-035-exit-code-standard) - the exit codes this follows

## Links

[link:related_to](security/output-encoding) - the matching output rule
```

## Frontmatter Fields

Only these keys are read, by `_extract_metadata` in `serena_integration.py`:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `title` | string | memory id | Human-readable title |
| `tags` | list[string] or string | `[]` | Classification tags; a bare string is wrapped in a list |
| `created_at` | datetime or date | now (UTC) | Feeds the freshness factor |
| `updated_at` | datetime or date | now (UTC) | Feeds the recency factor and 30-day staleness |
| `confidence` | float | `0.0` | Clamped to `0.0-1.0`; booleans and unparseable values become `0.0` |

Naive datetimes are treated as UTC. If exactly one of `created_at` or
`updated_at` is present, the other takes its value.

There is **no** `id` field. The memory id is the path under the memories
directory with `.md` removed, assigned by `load_memories`. A memory at
`.serena/memories/security/input-validation.md` has the id
`security/input-validation`. An `id:` key in frontmatter is ignored.

A memory with no frontmatter falls back to a `# Title (YYYY-MM-DD)` first
line, which supplies the title and both timestamps.

## Source Types

`SourceType` in `models.py`. An unrecognized type prints
`Warning: unrecognized citation source type '<value>'` to stderr and the
citation is dropped, so it never appears in any count.

| Type | Target format | Check performed | Sample pass reason |
|------|---------------|-----------------|--------------------|
| `file` | `path` or `path:LINE` | File exists inside repo root; if `:LINE` given, the file has at least that many lines | `File exists with line 3` |
| `function` | `path::name` | File exists, and a `def name` or `async def name` appears in it | `Function 'validate_input' found` |
| `issue` | `123` or `#123` | Format only. No GitHub API call | `Valid issue/PR reference format` |
| `pr` | `123` or `#123` | Format only. No GitHub API call | `Valid issue/PR reference format` |
| `memory` | id, `.md` optional | Resolves under `.serena/memories/` | `Memory file exists` |
| `adr` | id, `.md` optional | Resolves under `.agents/architecture/` | `ADR file exists` |
| `url` | `http://` or `https://` prefix | Prefix only. No HTTP request | `Valid URL format` |

There is **no snippet field**. Line content is never compared. A `:LINE`
suffix asserts only that the file is long enough.

The `function` verifier is a text search, not a parser. It passes when the file
contains `def name` or `async def name` anywhere, including inside a comment or
a string, and it never inspects the file extension. In practice it recognises
Python callables only: a TypeScript, C#, or PowerShell function is reported
stale, and so is a Python class, because none of them is preceded by `def`.

## Verification

`verify_citation` in `verification.py` dispatches on source type. Each
verifier returns a `VerificationResult` with `is_valid` and a `reason` string.

### Path Containment

Every path-resolving verifier calls `_validate_path_containment`, which
resolves the target and requires the result to stay under the base directory.
Escapes fail with `Path traversal blocked: <target>` (CWE-22 guard).

Base directories differ by type: repo root for `file` and `function`,
`.serena/memories/` for `memory`, `.agents/architecture/` for `adr`.

### Failure Reasons

| Reason | Cause | Fix |
|--------|-------|-----|
| `Path traversal blocked: X` | Target resolves outside its base directory | Use a relative path with no `../` escape |
| `File not found: X` | Referenced file deleted or moved | Update the target or drop the citation |
| `Line N exceeds file length (M lines)` | File shortened | Update or drop the `:LINE` suffix |
| `Line number must be >= 1, got N` | Non-positive line number | Use 1-based line numbers |
| `Function 'f' not found in file` | Function renamed or removed | Update the target |
| `Invalid file target format: X` | Target contains more than one `:` | Use `path` or `path:LINE` |
| `Invalid function target format: X` | Target is missing the `::` separator, or the name contains a character outside `[A-Za-z0-9_]` | Use `path::name`; cite the file instead for a hyphenated name |
| `Invalid issue/PR format: X` | Target is not `123` or `#123` | Use a bare number |
| `Invalid URL format: X` | Scheme is not `http`/`https` | Use an absolute http(s) URL |
| `Cannot read file: E` | Permissions or I/O error | Fix file access |

### Stale Versus Broken

`_classify_result` in `health.py` splits failures using
`STALE_REASON_MARKERS = ("exceeds", "not found in file")`:

- **stale**: the file is present but the target is not where the citation says
  it is. The file is now shorter than the cited line, or no `def name` text is
  found.
- **broken**: the target itself is missing or malformed.

The distinction matters because stale citations count half in the health
score and broken citations count zero.

## Confidence

Confidence is **not** a citation ratio. It is a weighted blend, clamped to
`0.0-1.0`, defined in `confidence.py`:

```text
confidence = 0.50 * validity     # valid/total, and 1.0 when there are none
           + 0.25 * recency      # 1 - (days since updated_at / 90), floor 0
           + 0.15 * links        # outgoing links / 10, capped at 1.0
           + 0.10 * freshness    # 1 - (days since created_at / 365), floor 0
```

A memory with zero citations scores **1.0 on validity**, so an uncited memory
scores higher than a well-cited one with a single broken reference. Read a
high confidence as "nothing is known to be broken", not "this was verified".

The `confidence` subcommand prints scores and writes nothing. See
`.claude/skills/memory-enhancement/references/confidence-scoring.md`.

## Health Score

`_calculate_health_score` in `health.py`:

```text
health_score = (valid + 0.5 * stale) / total_citations
```

It returns `1.0` when there are no memories or no citations. A repository with
no citations therefore reports a perfect score. Read `total_citations` first.

`stale_memories` is a separate, memory-level list: a memory appears when its
`updated_at` is more than 30 days old, or any of its citations failed.

## CLI Reference

Global options must precede the subcommand.

```text
python -m memory_enhancement [--repo-root PATH] [--memories-dir PATH] <command>
```

`--memories-dir` must resolve inside `--repo-root`, otherwise the command
exits 1 with `Error: memories-dir must be within repo-root`.

| Command | Options | Behaviour |
|---------|---------|-----------|
| `verify` | `--memory-id ID` | Verify one memory. With no id, verifies all |
| `verify-all` | `--json` | Verify every memory |
| `health` | `--json`, `--text`, `--markdown` | Health report; `--markdown` is the default. The three are mutually exclusive |
| `graph` | `--start ID` (required), `--depth N` | Traverse links from a memory |
| `confidence` | none | Print `<memory-id>: <score>` for every memory |
| `search` | `QUERY`, `--top N`, `--json` | Rank memories matching a query |

There is no `--dir`, no `--format`, no `--summary`, and no `--include-graph`.
There are no `add-citation`, `update-confidence`, `list-citations`,
`auto-cite`, `add`, `get`, `list`, `archive`, or `doctor` commands. Citations
are written by editing the memory body.

### Verify a Single Memory

`security/input-validation` below is a hypothetical. The corpus currently
carries zero citations, so this shows the output shape, not a live run.

```bash
python -m memory_enhancement verify --memory-id security/input-validation
```

Output, one line per citation:

```text
security/input-validation:
  [PASS] src/validate.py - File exists
  [FAIL] src/missing.py - File not found: src/missing.py
```

`verify` has no `--json` flag. Use `verify-all --json` and filter on
`memory_id`.

### Verify All Memories

```bash
python -m memory_enhancement verify-all --json
```

Emits a flat array with **one object per citation**, not per memory:

```json
[
  {
    "memory_id": "security/input-validation",
    "target": "src/missing.py",
    "source_type": "file",
    "valid": false,
    "reason": "File not found: src/missing.py"
  }
]
```

## Link Types

`LinkType` in `models.py`. Unknown types print a warning and are skipped.

| Link Type | Semantics |
|-----------|-----------|
| `depends_on` | This memory requires the target to hold |
| `related_to` | General association |
| `supersedes` | This memory replaces the target; the target is obsolete |
| `contradicts` | This memory conflicts with the target |
| `refines` | This memory adds detail to the target |

Links drive `graph` traversal and feed 15% of the confidence score. The score
does not check that a link target exists; `graph` does.

## Integration

### CI Workflow

`.github/workflows/citation-verify.yml` runs on pull requests targeting
`main`. It uses `dorny/paths-filter` to detect changes in:

- `.serena/memories/**`
- `.claude/skills/memory-enhancement/**`

When changes are detected it sets up the code environment via
`./.github/actions/setup-code-env` and runs:

```bash
python3 -m memory_enhancement --repo-root . --memories-dir .serena/memories verify-all
```

The job fails when any citation is invalid.

### Pre-commit Hook

```bash
python -m memory_enhancement --repo-root "$(git rev-parse --show-toplevel)" verify-all
```

Add as a Lefthook pre-commit job. Note the global option comes first; placing
`--repo-root` after `verify-all` exits 2.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Verification passed, or the report found nothing wrong |
| `1` | A citation failed, a memory id was not found, or `--memories-dir` fell outside `--repo-root` |
| `2` | argparse rejected the command line (unknown subcommand, unknown flag, missing required argument) |

Exit code 1 is overloaded. Read the message to tell "not found" from "has a
broken citation".
