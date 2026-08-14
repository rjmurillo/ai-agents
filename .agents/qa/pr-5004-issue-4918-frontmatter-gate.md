---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-14-session-14708.json
qaCommit: 8972531ef003950827b30aeb5c8a1a34ef1a798e
---

# PR 5004 Issue 4918 Frontmatter Repair and Gate QA

## Scope

Validate the repair of `.serena/memories/implementation/implementation-008-spec-schema-validation.md`,
the frontmatter gate in `scripts/validation/memory_index.py`, its tests in
`tests/test_validation_memory_index.py`, and the memory plus index mirrors added
under `.serena/memories/`.

This branch replaces `fix/4918-implementation-008-frontmatter` (PR 4985). See
"Branch Replacement" below; the content is identical, re-verified here.

## Acceptance Criteria

Quoted verbatim from issue 4918:

1. "`description` value is valid YAML (quoted or restructured) without changing meaning"
2. "`memory_enhancement verify-all` runs against `.serena/memories` with zero
   `malformed YAML frontmatter` warnings"
3. "Memory index validator and targeted memory integration tests pass"

## Verdict

**PASS.** All three criteria verified at commit `8972531ef003950827b30aeb5c8a1a34ef1a798e`.

## Evidence

| # | Criterion | Command | Result |
|---|-----------|---------|--------|
| 1 | Valid YAML, meaning preserved | `frontmatter.loads` on the repaired file, compare `description` to the original text | Parsed value equals `Constraints for writing spec artifacts (REQ/DESIGN/TASK): read spec-schemas.md first; validate enums before committing` (`True`) |
| 2 | Zero malformed warnings | `uv run --frozen python -m memory_enhancement verify-all` piped to `grep -ci "malformed YAML frontmatter"` | `0` |
| 3 | Index validator | `uv run --frozen python scripts/validation/memory_index.py --path .serena/memories --ci --orphan-policy ratchet` | `Result: PASSED`, exit 0, 567 indexed files, 0 missing, 0 keyword issues |
| 3 | Targeted tests | `uv run --frozen python -m pytest tests/test_validation_memory_index.py -q` | `185 passed` |

## Negative Control

A gate that never fires also reports zero warnings. Replaying the pre-fix file
content through the canonical loader still reproduces the original symptom:

```text
Warning: malformed YAML frontmatter, treating as plain markdown
```

The gate flags that same content with an actionable message, so the zero in
criterion 2 is a repair and not a silenced check.

## Differential Parity Probe

The gate must fire exactly where `frontmatter.loads` raises `yaml.YAMLError`,
which is the site of the warning in
`scripts/memory_enhancement/serena_integration.py`. A probe compared both over 16
frontmatter shapes and found three false negatives in the original gate: 4-dash
boundaries, 5-dash boundaries, and leading blank lines. python-frontmatter's
canonical constant is

```python
FM_BOUNDARY = re.compile(r"^-{3,}\s*$", re.MULTILINE)
```

while the gate keyed on `line == "---"`, and `frontmatter.parse` normalizes with
`text = u(text, encoding).strip()` before detecting, which the gate did not do.
Both are now mirrored.

| Probe outcome | Before | After |
|---------------|--------|-------|
| False negatives (loader warns, gate silent) | 3 | 0 |
| False positives on the real memory tree | 0 | 0 |

Four shapes are flagged by the gate although the loader stays quiet: unclosed
delimiter, list block, scalar block, and BOM. These are deliberate
stricter-than-canonical cases documented in the `_parse_leading_frontmatter`
docstring; each one silently discards metadata under the loader.

## Quality Gates

| Gate | Command | Result |
|------|---------|--------|
| Unit tests | `pytest tests/test_validation_memory_index.py -q` | 185 passed |
| Lint | `ruff check scripts/validation/memory_index.py tests/test_validation_memory_index.py` | All checks passed |
| Types | `mypy scripts/validation/memory_index.py` | Success, no issues |
| Token counts | `scripts/update_memory_index_tokens.py --check` | current |
| Taste ratchet | `scripts/ci/taste_count_ratchet.py` | 582 <= baseline 583 |
| Pre-PR | `scripts/validation/pre_pr.py` (pre-push `pre-pr-validation` job) | passed |
| Full test suite | pre-push `python-tests` job | passed in 348 seconds |

## Taste Ratchet Regression Closed

Adding the frontmatter section pushed `format_markdown` to cyclomatic complexity
12 against a ceiling of 10. The formatter was decomposed into `_bullet_section`
and `_domain_section` rather than raising `scripts/ci/taste_count_baseline.txt`.
The formatter had two tests and none covered the optional sections, so four were
added: missing files, orphans, malformed frontmatter, and an empty case proving
absent sections stay absent.

## Branch Replacement

PR 4985 on `fix/4918-implementation-008-frontmatter` carries the same fix and
cannot accept further compliant pushes: nine commits on it were authored and
committed as `Test <test@test.com>` by a concurrent `pr-autofix` session, and the
pre-push `placeholder-identity` guard evaluates the whole branch delta
(`merge-base(origin/main, HEAD)..HEAD`), so every push from a hook-enabled
environment is rejected. Clearing it needs a history rewrite plus a force push,
which `AGENTS.md` prohibits. This branch replays the same content from
`origin/main` under a compliant identity with the logical commit boundaries
preserved, and the `strip()` parity contribution from that session is carried in
its own commit with attribution.

## Residual Risk

`scripts/validation/memory_index.py` is 1,726 lines and `main()` has complexity
14. Both are pre-existing taste errors present on `origin/main`, outside this
issue's scope, and recorded in the session log's next steps.
