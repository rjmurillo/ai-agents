# Confidence Scoring Guide

How the `memory_enhancement` confidence score is calculated, what it does and
does not mean, and how to act on it.

Source of truth: `scripts/memory_enhancement/confidence.py`. If this guide and
that module disagree, the module is right and this guide is a bug.

## Table of Contents

1. [Formula](#formula)
2. [Interpretation](#interpretation)
3. [Reading a Score Honestly](#reading-a-score-honestly)
4. [When to Recalculate](#when-to-recalculate)
5. [Persistence](#persistence)
6. [Best Practices](#best-practices)

## Formula

Confidence is a weighted blend of four factors, clamped to `0.0-1.0`:

```text
confidence = 0.50 * validity
           + 0.25 * recency
           + 0.15 * links
           + 0.10 * freshness
```

| Factor | Weight | Definition |
|--------|--------|------------|
| `validity` | 0.50 | valid citations / total citations. **Returns 1.0 when the memory has no citations.** |
| `recency` | 0.25 | `1 - (days since updated_at / 90)`, floored at 0 |
| `links` | 0.15 | `outgoing links / 10`, capped at 1.0 |
| `freshness` | 0.10 | `1 - (days since created_at / 365)`, floored at 0 |

Constants live in `confidence.py`: `_WEIGHT_VALIDITY`, `_WEIGHT_RECENCY`,
`_WEIGHT_LINKS`, `_WEIGHT_FRESHNESS`, `_MAX_RECENCY_DAYS` (90),
`_MAX_AGE_DAYS` (365), `_MAX_LINKS` (10).

### Worked Examples

```text
# Written today, 3 citations all valid, 5 links
0.50*1.00 + 0.25*1.00 + 0.15*0.50 + 0.10*1.00 = 0.925

# Written today, 3 citations with 1 broken, 5 links
0.50*0.67 + 0.25*1.00 + 0.15*0.50 + 0.10*1.00 = 0.760

# Written today, no citations, no links
0.50*1.00 + 0.25*1.00 + 0.15*0.00 + 0.10*1.00 = 0.850

# 200 days old, never updated, no citations, no links
0.50*1.00 + 0.25*0.00 + 0.15*0.00 + 0.10*0.45 = 0.545
```

The third example is the one that matters. **A memory with zero citations
scores 0.85**, higher than a well-cited memory with one broken reference. The
score rewards recency and link density, and a memory that cites nothing has
nothing that can be found broken.

## Interpretation

| Score Range | Meaning | Action |
|-------------|---------|--------|
| 0.85 - 1.00 | Recent, well linked, nothing known broken | Usable, but check whether it has citations at all |
| 0.70 - 0.85 | Recent, or well cited, rarely both | Read the citations before relying on it |
| 0.50 - 0.70 | Aging, or a broken citation is dragging validity down | Re-verify before use |
| 0.00 - 0.50 | Old and uncited, or most citations broken | Update or retire |

These bands are guidance for a reader, not thresholds enforced anywhere in the
code. The only threshold in the package is `_SKILL_CONFIDENCE_THRESHOLD = 0.8`
in `scripts/memory_enhancement/reflection.py`, used to nominate skill
candidates.

## Reading a Score Honestly

A confidence score answers "how fresh and connected is this memory, and is
anything it points at known to be broken?" It does not answer "is this memory
true."

Three failure modes to keep in mind:

1. **A high score can mean no data.** Zero citations gives `validity = 1.0`.
   Check the citation count before treating a high score as verification.
2. **Recency dominates early.** A memory written today with no citations and
   no links starts at about 0.85 (measured 0.848: validity 1.0, recency and
   freshness near 1.0, links 0.0). Age alone pulls it down with no content
   change.
3. **Link count is gameable.** Ten links maxes the link factor regardless of
   whether the targets exist. Graph traversal (`graph --start ID`) checks
   reachability; the confidence score does not.

To find out whether a memory is actually verified, run `verify` and read the
citation results, not the confidence number.

## When to Recalculate

Scores are computed on demand. There is no stored value to go stale, so
"recalculating" means running the command again:

```bash
python -m memory_enhancement confidence
```

Output is one `<memory-id>: <score>` line per memory, for every memory. There
is no single-memory filter.

Run it after:

1. Major refactoring, which can invalidate file and function citations
2. File moves or renames
3. Code deletion
4. Periodic review

Pair it with verification to see which citations moved:

```bash
python -m memory_enhancement verify-all --json
python -m memory_enhancement health --markdown
```

### CI Integration

```yaml
# .github/workflows/memory-validation.yml
- name: Verify memory citations
  run: python -m memory_enhancement verify-all --json
  continue-on-error: true

- name: Report memory health
  if: failure()
  run: python -m memory_enhancement health --markdown > memory-health.md
```

`verify-all` exits 1 when any citation is invalid. `health` exits 1 when any
citation is broken or a memory is stale.

## Persistence

**The `confidence` subcommand does not write anything.** It loads memories,
computes scores, prints them, and exits 0. Running it leaves the working tree
unchanged.

A `confidence:` value in YAML frontmatter *is* read back by
`_parse_confidence` in `serena_integration.py` and clamped to `0.0-1.0`, so a
hand-written value is honoured as the memory's stored confidence. Nothing on
the CLI path updates it.

The library function `reinforce_memories()` in
`scripts/memory_enhancement/reflection.py` does persist scores through
`save_memory`. Its only non-test caller is
`scripts/memory_enhancement/hooks/session_end_memory.py`, which is not
registered under any hook event in `.claude/settings.json`. Treat persisted
confidence as an unwired capability, not a running one.

Practical consequence: do not expect a `confidence:` field to reflect a recent
run. Read the command output instead.

## Best Practices

### 1. Cite in the Body, Not the Frontmatter

Only the inline form is parsed:

```markdown
[cite:file](src/api/validate.py) - input validation entry point
```

Valid `source_type` values are `file`, `function`, `issue`, `pr`, `adr`,
`memory`, `url`. An unrecognized type prints a warning to stderr and the
citation is skipped. A `citations:` list in YAML frontmatter is never read.

### 2. Verify Regularly

```bash
python -m memory_enhancement verify-all
```

Exit code 1 means at least one citation no longer resolves.

### 3. Prioritize by Health, Not by Score

```bash
python -m memory_enhancement health --json
```

The report carries counts (total, valid, stale, broken, unverified), the ids of
stale memories, and recommendations. It does not name individual citations. To
see which citation failed and why, run `verify --memory-id ID` or `verify-all
--json`, which report per-citation status and reason.

### 4. Link Deliberately

Links feed 15% of the score and drive graph traversal. Use the inline form at
the end of a line:

```markdown
[link:supersedes](security/old-auth-pattern) - replaced in the v2 migration
```

Valid `link_type` values are `depends_on`, `related_to`, `supersedes`,
`contradicts`, `refines`.

### 5. Balance Citation Quantity

More citations is not better. Each one is a maintenance obligation, and each
broken one costs 1/N of the validity factor.

**Prefer:**

- Two or three citations to stable, load-bearing code
- File-level citations for broad concepts
- Function citations only where the function name is the contract

**Avoid:**

- Twenty citations to consecutive lines of one file
- Citations into volatile test fixtures
- Redundant citations to the same area

### 6. Do Not Chase 1.0

The maximum is unreachable for an aging memory. After 90 days without an
update the recency factor is 0, which caps the score at about 0.73 even with
every citation valid and ten links. Past a year the freshness factor also
reaches 0 and the ceiling settles at 0.65 (measured: a 210-day memory with ten
links and a valid citation scores 0.6923). A stable, correct memory is
supposed to decay on this scale. Decay is a prompt to re-verify, not evidence
of a defect.

## Summary

1. Confidence is a weighted blend of validity, recency, links, and freshness,
   not a citation ratio.
2. Zero citations scores **high** (1.0 validity), so a high score can mean
   "unverified" rather than "verified".
3. The `confidence` subcommand prints and never writes.
4. `verify` and `health` tell you what is actually broken; use them to act.
5. Citations and links must be inline in the body to be parsed at all.

<!-- vendor-portability: declared. This guide cites scripts/memory_enhancement/confidence.py, reflection.py, serena_integration.py, and hooks/session_end_memory.py as the source of truth for the weights and the persistence path. Those paths live outside the plugin root and are absent from a vendored install. They are read-only citations that let a maintainer in this repository re-derive every number here; the guide is complete without them. Issue #2050. -->
