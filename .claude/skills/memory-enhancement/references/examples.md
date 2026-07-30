# Memory Enhancement Examples

Worked examples for the `memory_enhancement` CLI. Every command and every
output block below was captured from a real run against a two-memory fixture.

The fixture: `security/input-validation` cites `src/validate.py` (exists) and
`src/missing.py` (does not), and links to `security/output-encoding`, which
cites `src/validate.py`.

## Table of Contents

1. [Adding Citations](#adding-citations)
2. [Verifying Citations](#verifying-citations)
3. [Confidence](#confidence)
4. [Health Monitoring](#health-monitoring)
5. [Graph and Search](#graph-and-search)
6. [Integration Workflows](#integration-workflows)

## Adding Citations

There is no `add-citation` command. Citations are markdown you write into the
memory body. The parser reads only this inline form:

```text
[cite:<source_type>](<target>) - <context>
```

`source_type` must be one of `file`, `function`, `issue`, `pr`, `adr`,
`memory`, `url`. Any other value prints `Warning: unrecognized citation source
type '<value>'` to stderr and the citation is dropped. `target` must not be
empty.

### Example 1: Cite a File

Append to the memory body:

```markdown
## Citations

[cite:file](src/validate.py) - the validation entry point
```

### Example 2: Cite Several Kinds of Source

```markdown
## Citations

[cite:file](src/api/validate.py) - request validation
[cite:adr](ADR-035) - the exit-code standard this follows
[cite:pr](3986) - where the contract was fixed
```

### Example 3: What Does Not Work

A `citations:` list in YAML frontmatter is never parsed. This memory verifies
as having **zero** citations:

```markdown
---
title: Validate at the boundary
citations:
  - path: src/validate.py
    line: 42
---
```

There is no dry-run mode, and no command validates a citation at the moment
you write it. Write the line, then run `verify`.

## Verifying Citations

The memory id is the path under the memories directory with `.md` removed. A
memory at `.serena/memories/security/input-validation.md` has the id
`security/input-validation`. The `id:` field in frontmatter is ignored.

### Example 1: Verify a Memory Whose Citations All Resolve

```bash
python -m memory_enhancement verify --memory-id security/output-encoding
```

**Output (exit code 0):**

```text
security/output-encoding:
  [PASS] src/validate.py - File exists
```

### Example 2: Verify a Memory With a Broken Citation

```bash
python -m memory_enhancement verify --memory-id security/input-validation
```

**Output (exit code 1):**

```text
security/input-validation:
  [PASS] src/validate.py - File exists
  [FAIL] src/missing.py - File not found: src/missing.py
```

### Example 3: Unknown Memory Id

```bash
python -m memory_enhancement verify --memory-id input-validation
```

**Output (exit code 1):**

```text
Memory not found: input-validation
```

The id above fails because it omits the `security/` directory. Exit code 1
covers both "not found" and "has a broken citation"; read the message to tell
them apart.

### Example 4: Verify Every Memory

```bash
python -m memory_enhancement verify-all
```

**Output (exit code 1, because one citation is broken):**

```text
security/input-validation:
  [PASS] src/validate.py - File exists
  [FAIL] src/missing.py - File not found: src/missing.py

security/output-encoding:
  [PASS] src/validate.py - File exists
```

### Example 5: Machine-Readable Verification

```bash
python -m memory_enhancement verify-all --json
```

**Output (exit code 1):**

```json
[
  {
    "memory_id": "security/input-validation",
    "target": "src/validate.py",
    "source_type": "file",
    "valid": true,
    "reason": "File exists"
  },
  {
    "memory_id": "security/input-validation",
    "target": "src/missing.py",
    "source_type": "file",
    "valid": false,
    "reason": "File not found: src/missing.py"
  },
  {
    "memory_id": "security/output-encoding",
    "target": "src/validate.py",
    "source_type": "file",
    "valid": true,
    "reason": "File exists"
  }
]
```

One object per citation, not per memory. `verify` has no `--json` flag; use
`verify-all --json` and filter on `memory_id`.

## Confidence

There is no `update-confidence` command and no per-memory filter. The
`confidence` subcommand scores every memory and prints the result.

```bash
python -m memory_enhancement confidence
```

**Output (exit code 0):**

```text
security/input-validation: 0.525
security/output-encoding: 0.760
```

Nothing is written. See
[confidence-scoring.md](confidence-scoring.md) for the formula and for why a
memory with no citations scores higher than one with a broken citation.

## Health Monitoring

`health` accepts exactly one of `--markdown` (default), `--json`, or `--text`.
There is no `--format`, no `--summary`, and no `--include-graph`. It exits 1
when any citation is broken or any memory is stale.

### Example 1: Markdown Report

```bash
python -m memory_enhancement health
```

**Output (exit code 1):**

```markdown
# Memory Health Report

**Health Score**: 66.7%

## Citation Summary

| Metric | Count |
|--------|-------|
| Total memories | 2 |
| Total citations | 3 |
| Valid | 2 |
| Stale | 0 |
| Broken | 1 |
| Unverified | 0 |

## Stale Memories

- security/input-validation

## Recommendations

- Fix 1 broken citation(s) to restore reference integrity.
- Review 1 stale memory/memories for relevance.
```

### Example 2: JSON Report

```bash
python -m memory_enhancement health --json
```

**Output (exit code 1):**

```json
{
  "total_memories": 2,
  "total_citations": 3,
  "valid_citations": 2,
  "stale_citations": 0,
  "broken_citations": 1,
  "unverified_citations": 0,
  "health_score": 0.6666666666666666,
  "stale_memories": [
    "security/input-validation"
  ],
  "recommendations": [
    "Fix 1 broken citation(s) to restore reference integrity.",
    "Review 1 stale memory/memories for relevance."
  ]
}
```

### Example 3: Plain Text Report

```bash
python -m memory_enhancement health --text
```

**Output (exit code 1):**

```text
Memory Health Report
====================

Health Score: 66.7%

Citation Summary:
  Total memories:   2
  Total citations:  3
  Valid:            2
  Stale:            0
  Broken:           1
  Unverified:       0

Stale Memories:
  - security/input-validation

Recommendations:
  - Fix 1 broken citation(s) to restore reference integrity.
  - Review 1 stale memory/memories for relevance.
```

### Reading `health_score` Correctly

`health_score` is `(valid_citations + 0.5 * stale_citations) / total_citations`.
Stale counts half; broken and unverified count zero.

Two different things are called stale:

- `stale_citations` counts citations whose file still exists but whose content
  moved: a line number past the end of the file, or a function no longer
  defined in it. A citation whose target is missing entirely counts as
  `broken`.
- `stale_memories` lists memories, not citations. A memory is listed when its
  `updated_at` is more than 30 days old **or** any of its citations failed.

A repository whose memories carry no citations reports `total_citations: 0`
and `health_score: 1.0`. That is "nothing to check", not "everything checks
out". Read `total_citations` before you trust the score.

## Graph and Search

### Example 1: Traverse Memory Links

`--start` is required. Links come from `[link:<type>](<target-id>)` at the end
of a line in the memory body. Valid types: `depends_on`, `related_to`,
`supersedes`, `contradicts`, `refines`.

```bash
python -m memory_enhancement graph --start security/input-validation
```

**Output (exit code 0):**

```text
  security/output-encoding (related_to, depth=1)
```

The start memory is not echoed; only what it reaches. Use `--depth N` to bound
traversal.

### Example 2: Search

```bash
python -m memory_enhancement search validation --top 3
```

**Output (exit code 0):**

```text
input-validation (52%, broken) - Validate at the boundary
```

**Known defect:** `search` prints the file stem, while `verify` and `graph`
expect the path-derived id. For a memory in a subdirectory the two do not
match, so a `search` result cannot be pasted into `--memory-id` as-is. Prepend
the subdirectory yourself, or locate the file first:

```bash
python -m memory_enhancement search validation --json
```

## Integration Workflows

### After a Refactor

```bash
python -m memory_enhancement verify-all
python -m memory_enhancement health --markdown
```

The first command names every citation that stopped resolving. The second
ranks the damage and lists stale memories.

### In CI

```yaml
- name: Verify memory citations
  run: python -m memory_enhancement verify-all --json
  continue-on-error: true

- name: Report memory health
  if: failure()
  run: python -m memory_enhancement health --markdown > memory-health.md
```

Start with `continue-on-error: true`. Make it blocking once citations exist in
enough memories that the signal is real.

### Global Options Come First

`--repo-root` and `--memories-dir` are global:

```bash
python -m memory_enhancement --repo-root . --memories-dir .serena/memories verify-all
```

Placing either one after the subcommand exits 2 with
`unrecognized arguments: --repo-root .`.

`--memories-dir` must resolve inside `--repo-root`. Otherwise the command
exits 1 with `Error: memories-dir must be within repo-root`.
