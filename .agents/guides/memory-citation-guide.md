# Memory Citation Guide

How to attach citations to a Serena memory, verify them, and fix them when they
break.

This guide covers the workflow and the judgment calls. It deliberately does not
restate the schema. The schema of record is
[CITATION-SCHEMA.md](../architecture/CITATION-SCHEMA.md): field types, source
types, verification semantics, and both scoring formulas live there, and that is
the file to change when the code changes.

## Why Cite

A citation ties a claim in a memory to a location in the repository. The payoff
is mechanical staleness detection: when the cited code moves or disappears,
`verify` fails and the memory is flagged instead of quietly rotting.

An uncited memory is not flagged as suspect. It scores a validity factor of 1.0,
the same as a memory whose citations all pass. Citations buy you detection, not
credit.

## When To Cite

Cite a claim when a reader would otherwise have to search the repository to
check it:

- A described implementation pattern, so the reader can see it in place.
- A configuration value, path, or contract the memory asserts.
- A decision recorded elsewhere, via an `adr`, `issue`, or `pr` citation.

Do not cite:

- General knowledge, language features, or industry practice. There is nothing
  in the repository to point at, and a citation to an incidental file will go
  stale for no benefit.
- Planned work that does not exist yet. The citation is broken on arrival.
- Every file a memory happens to mention. Each citation is a maintenance
  obligation; a memory with twenty citations fails often and gets ignored.

Aim to cite the few locations that would falsify the memory if they changed.

## Writing a Citation

Citations go in the body, conventionally under a `## Citations` heading:

```markdown
## Citations

[cite:file](src/validate.py) - the validation entry point
[cite:file](src/validate.py:42) - the boundary check
[cite:function](src/validate.py::validate_input) - the check itself
[cite:adr](ADR-035-exit-code-standard) - the exit codes this follows
```

Relationships between memories use links, conventionally under `## Links`:

```markdown
## Links

[link:related_to](security/output-encoding) - the matching output rule
```

Three things routinely cost people a debugging session:

1. **A link must end its line.** A citation may sit inline in a sentence; a link
   may not. `[link:related_to](x) and more words` parses as zero links, with no
   warning.
2. **The memory id is the path, not the frontmatter.** A memory at
   `.serena/memories/security/input-validation.md` has the id
   `security/input-validation`. An `id:` field in frontmatter is ignored.
3. **A misspelled source type deletes the citation.** It warns on stderr and
   then the citation is absent from every count, so the memory can pass with
   nothing checked. Read the stderr of the run, not just its exit code.

There is no command that adds a citation for you and no dry-run mode. Write the
line, then verify.

## Verifying

Global options must come before the subcommand.

```bash
# One memory
uv run python -m scripts.memory_enhancement verify --memory-id security/input-validation

# Every memory
uv run python -m scripts.memory_enhancement verify-all

# Aggregate report
uv run python -m scripts.memory_enhancement health --json
```

`verify` and `verify-all` exit 1 when any citation fails, which is what makes
them usable in CI.

## Reading a Failure

Failures come in two kinds, and they call for different fixes.

**Stale** means the file is still there but the content moved. The reason
mentions `exceeds` or `not found in file`:

```text
[FAIL] src/a.py:99 - Line 99 exceeds file length (2 lines)
[FAIL] src/a.py::zzz - Function 'zzz' not found in file
```

Fix by re-pointing the citation. The knowledge is probably still true.

**Broken** means the target is gone:

```text
[FAIL] src/gone.py - File not found: src/gone.py
```

Fix by finding the replacement, or by asking whether the memory still describes
the system. A file deleted outright often means the memory is obsolete, not
mis-pointed.

Stale and broken are weighted differently in the health score, which is why the
distinction is worth keeping straight. See
[CITATION-SCHEMA.md](../architecture/CITATION-SCHEMA.md) for the formula.

## Fixing a Stale Citation

1. Run `verify --memory-id <id>` and read every `[FAIL]` line.
2. For each one, open the cited file and find where the content went.
3. Re-point the citation. Prefer `[cite:function](path::name)` over
   `[cite:file](path:LINE)`; a line number goes stale on the next edit above it,
   a function name does not.
4. Re-run `verify --memory-id <id>` and confirm it exits 0.
5. If the content is gone rather than moved, fix the memory text too. A memory
   that cites the right file while describing behavior that no longer exists is
   worse than one with a broken citation, because nothing detects it.

## CI

`.github/workflows/memory-validation.yml` runs verification on pull requests
that touch `.serena/memories/**` or `scripts/memory_enhancement/**`.

Read the aggregate numbers before trusting a green result. A repository with
many memories and no citations reports a perfect health score, because the score
is computed over citations rather than over memories. A high score with a low
citation count means nothing was checked.

## References

- [CITATION-SCHEMA.md](../architecture/CITATION-SCHEMA.md) - schema of record
- [ADR-038: Reflexion Memory Schema](../architecture/ADR-038-reflexion-memory-schema.md)
- [memory-validation.yml](../../.github/workflows/memory-validation.yml)
