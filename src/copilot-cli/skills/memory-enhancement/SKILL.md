---
name: memory-enhancement
version: 1.0.0
description: >
  Manage memory citations, verify code references, and track confidence scores. Use when adding citations to memories, checking memory health, or verifying code references are still valid.
  Use when you say "add a citation", "verify this memory's code refs", "check memory health".
  Do NOT use for searching or creating memories (use memory) or for documentary reports (use memory-documentary).
license: MIT
metadata:
  domains: [memory, citations, verification]
  type: utility
  adr: ADR-007, ADR-038
---

# Memory Enhancement

Manage citations, verify code references, and track confidence scores for Serena memories. Ensures memories stay accurate by linking them to specific code locations and detecting when those locations change.

## Triggers

- `add citation to memory` - Link memory to specific code location
- `verify memory citations` - Check if code references are still valid
- `check memory health` - Generate staleness report across all memories
- `update memory confidence` - Recalculate trust score based on verification

## Quick Reference

| Input | Output | Duration |
|-------|--------|----------|
| Memory ID + code reference | Citation added with validation | < 5 seconds |
| Memory directory | Health report with stale memories | < 30 seconds |
| Verification results | Updated confidence scores | < 10 seconds |

## Decision Tree

```text
Need memory enhancement?
│
├─ Add citation to memory → edit the memory file (no CLI command)
├─ Verify citations → verify or verify-all command
├─ Check memory health → health command
├─ Traverse memory graph → graph command
└─ Show confidence scores → confidence command
```

## Command Surface

Global options come **before** the subcommand. Placing `--repo-root` or
`--memories-dir` after the subcommand exits 2.

```text
python -m memory_enhancement [--repo-root PATH] [--memories-dir PATH] <command>
```

| Command | Options | Exit codes |
|---------|---------|------------|
| `verify` | `--memory-id ID` | 1 if any citation is invalid, or the id is unknown |
| `verify-all` | `--json` | 1 if any citation is invalid |
| `health` | `--json`, `--text`, `--markdown` (default) | 1 if any citation is broken or stale, or any memory is stale |
| `graph` | `--start ID` (required), `--depth N` | 1 if the start id is unknown |
| `confidence` | none | 0 |
| `search` | `QUERY` (positional), `--top N`, `--json` | 0 |

`--memories-dir` must resolve inside `--repo-root`; otherwise the CLI exits 1.
A memory id is its path under the memories directory without the `.md`
suffix, so `.serena/memories/testing/foo.md` has the id `testing/foo`.

## Process

### Phase 1: Identify Target Memory

Locate the memory file by id:

1. **Derive the id** - The id is the path under the memories directory without
   the `.md` suffix (`.serena/memories/testing/foo.md` has id `testing/foo`).
2. **Point at a different tree** - Pass `--memories-dir PATH` before the
   subcommand. It must resolve inside `--repo-root`.
3. **Validate existence** - `verify --memory-id <id>` prints
   `Memory not found: <id>` and exits 1 when the id is unknown.

**Verification:** Memory file exists and is readable

### Phase 2: Add/Verify Citations

#### Add Citation

There is no `add-citation` command. Citations are markdown, so add one by
editing the memory file and appending a citation line to its body:

```text
[cite:file](src/api.py) - the error handler lives here
```

**Syntax:** `[cite:<source-type>](<target>) - <context>`

- `source-type` - one of `file`, `function`, `issue`, `pr`, `adr`, `memory`, `url`
- `target` - repository-relative path or identifier; must be non-empty
- `context` - optional prose after ` - `, kept as the citation context

An unrecognized `source-type` warns on stderr and the citation is dropped, so
the memory can still exit 0 with the citation missing. Verify after editing.
A `citations:` block in YAML frontmatter is **not** read by this tool.

**Verification:** `verify --memory-id <id>` lists the new citation

#### Verify Citations

```bash
# Single memory
python -m memory_enhancement verify --memory-id <memory-id>

# All memories, human-readable
python -m memory_enhancement verify-all

# All memories, JSON for CI
python -m memory_enhancement verify-all --json
```

**Output Indicators:**

- `[PASS] <target> - <reason>` - citation resolves
- `[FAIL] <target> - <reason>` - citation is broken or stale
- Exit code 1 when any citation is invalid

**Verification:** Citations validated against current codebase state

### Phase 3: Show Confidence

Recalculate scores from current verification results:

```bash
python -m memory_enhancement confidence
```

Prints `<memory-id>: <score>` for every memory. The command computes scores on
each run and **does not write them back** to the memory files, and it has no
single-memory filter.

**Confidence Calculation:**

A weighted blend of four factors, clamped to `0.0-1.0`:

| Factor | Weight | Definition |
|--------|--------|------------|
| Citation validity | 0.50 | valid citations / total citations; **1.0 when there are none** |
| Update recency | 0.25 | decays linearly to 0 over 90 days since `updated_at` |
| Link count | 0.15 | outgoing links / 10, capped at 1.0 |
| Memory freshness | 0.10 | decays linearly to 0 over 365 days since `created_at` |

A memory with no citations therefore does not score low; it scores high on
validity and is limited only by age and link count. Read a high score as
"nothing is known to be broken", not "this was checked against code".

**Interpretation:**

| Score Range | Meaning | Action |
|-------------|---------|--------|
| 0.9 - 1.0 | High confidence | Trust memory, use in decisions |
| 0.7 - 0.9 | Medium confidence | Review stale citations |
| 0.5 - 0.7 | Low confidence | Update memory or mark obsolete |
| 0.0 - 0.5 | Very low confidence | Memory likely outdated |

**Verification:** `confidence` prints a score for every memory

### Phase 4: Report Results

Display summary with actionable recommendations:

#### List Citations

There is no `list-citations` command. Verifying a memory prints its citations
alongside their status:

```bash
python -m memory_enhancement verify --memory-id <memory-id>
```

Human-readable output:

```text
testing/demo:
  [PASS] src/api.py - File exists
  [FAIL] src/missing.py - File not found: src/missing.py
```

For machine-readable output across every memory, use `verify-all --json`. It
emits a flat array, one object per citation:

```json
[
  {
    "memory_id": "testing/demo",
    "target": "src/api.py",
    "source_type": "file",
    "valid": true,
    "reason": "File exists"
  }
]
```

#### Health Report

```bash
python -m memory_enhancement health --json
```

Reports the following, and nothing else:

- `total_memories`, `total_citations`
- `valid_citations`, `stale_citations`, `broken_citations`, `unverified_citations`
- `health_score` (`(valid + 0.5 * stale) / total`; 1.0 for an empty corpus, 0.0 when memories exist but carry no citations)
- `stale_memories` (ids only, unordered)
- `recommendations` (prose strings)

There is no orphan detection and no staleness ranking.

**Verification:** Report generated successfully

## Script Reference

| Operation | CLI Command | Key Parameters |
|-----------|-------------|----------------|
| Add citation | none; edit the memory body | `[cite:<type>](<target>) - <context>` |
| Verify memory | `python -m memory_enhancement verify` | `--memory-id` |
| Verify all | `python -m memory_enhancement verify-all` | `--json` |
| Health report | `python -m memory_enhancement health` | `--json`, `--text`, `--markdown` |
| Show confidence | `python -m memory_enhancement confidence` | none |
| List citations | `python -m memory_enhancement verify` | `--memory-id` |
| Graph traversal | `python -m memory_enhancement graph` | `--start`, `--depth` |
| Search memories | `python -m memory_enhancement search` | `QUERY`, `--top`, `--json` |

Prefix any of these with `--repo-root PATH` or `--memories-dir PATH` to point
at a different tree. Both are global options and must precede the subcommand.

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Placing `--repo-root` after the subcommand | argparse rejects it and exits 2 | Put global options first |
| Adding a citation without checking the target | Nothing validates on write; it is a text edit | Run `verify --memory-id <id>` right after editing |
| Putting citations in YAML frontmatter | The parser only reads `[cite:...]` in the body | Add the citation line to the memory body |
| Reading a high confidence score as verified | Memories with no citations score high on validity | Check `total_citations` before trusting a score |
| Using absolute paths | Breaks on different machines | Use repo-relative paths |
| Forgetting to verify after refactoring | Citations go stale silently | Run `verify-all` regularly or in CI |

## Integration with Existing Skills

- **reflect** - Auto-capture citations from learnings that reference code
- **memory** - Verify citations during memory search
- **curating-memories** - Update citations when memories change
- **qa** - Run verification as part of test strategy

### Phase 5: Health Reporting

Run batch health checks:

```bash
# Full report (human-readable markdown, the default)
python -m memory_enhancement --repo-root . --memories-dir .serena/memories health

# JSON output (for CI parsing)
python -m memory_enhancement health --json

# Markdown output (for PR comments)
python -m memory_enhancement health --markdown

# Plain text output
python -m memory_enhancement health --text
```

The three format flags are mutually exclusive. There is no exemption
mechanism: `exempt: true` in frontmatter has no effect, and every memory in
the directory is scanned.

**Exit Codes:**

- 0: No broken citations, no stale citations, no stale memories
- 1: One or more memories are broken or stale
- 2: argparse rejected the command line

## CI Integration

### Memory Health Workflow

The `.github/workflows/memory-health.yml` workflow runs health checks on all PRs:

- Detects changes to `.serena/memories/**` and memory enhancement code
- Generates JSON and Markdown health reports
- Posts/updates a PR comment with results
- Non-blocking (warning only, not a required check)
- Uses `<!-- MEMORY-HEALTH -->` marker for idempotent comment updates

### Citation Verification Workflow

The `.github/workflows/citation-verify.yml` workflow verifies citations:

- Runs on every pull request to `main`, plus `workflow_dispatch`
- Filters on `.serena/memories/**` and `.claude/skills/memory-enhancement/**`
- Runs `python3 -m memory_enhancement --repo-root . --memories-dir .serena/memories verify-all`
- Blocking: a stale or broken citation exits 1 and fails the check
- Posts no PR comment
- Pairs with a `skip-verification` job so the required check still reports on
  pull requests that touch neither path

## Verification

After using this skill:

- [ ] Citations validated against the current codebase
- [ ] Confidence scores read from `confidence` output, not from frontmatter
- [ ] Stale memories identified and reported
- [ ] Health report generated (if requested)
- [ ] Any memory edits written to the memory body, not to frontmatter

## References

- [examples.md](references/examples.md) - Usage examples and workflows
- [confidence-scoring.md](references/confidence-scoring.md) - How confidence is calculated
- ADR-007 `.agents/architecture/ADR-007-memory-first-architecture.md` - Memory-first architecture
- ADR-038 `.agents/architecture/ADR-038-reflexion-memory-schema.md` - Reflexion memory schema

<!-- vendor-portability: declared. This skill links .agents/architecture/ADR-007 and ADR-038 as the memory-first and reflexion-schema ADRs, and names .github/workflows/memory-health.yml and .github/workflows/citation-verify.yml as the CI that runs these commands. All four sit outside the plugin root and are absent from a vendored install. Every one is a documentation citation; the enhancement logic reads none of them, the CLI behaves identically without them, and a vendored install loses only the links and the description of this repository's CI wiring. Issue #2050. -->
