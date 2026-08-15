---
qaCommit: f507b79f87150e27df3bdc7d986b589090f889e4
qaSessionLog: .agents/sessions/2026-08-14-session-14711-fix-4948-doc-accuracy-false-positives.json
qaVerdict: PASS
---

# QA Report: Issue #4948 - Doc Accuracy False Positives

## Objective

Verify the fix for `doc-accuracy` false positives on text fences, Mermaid fences, PowerShell examples, unmapped code claims, and code examples in languages that have no `SYMBOL_EXTRACTORS` entry (Go, Rust, Java, and any future addition).

## Tests

- `uv run pytest tests/skills/doc-accuracy/test_doc_accuracy.py -q`
- `uv run ruff check .claude/skills/doc-accuracy/scripts/doc_accuracy.py tests/skills/doc-accuracy/test_doc_accuracy.py`
- `uv run python build/scripts/build_all.py`
- `diff .claude/skills/doc-accuracy/scripts/doc_accuracy.py src/copilot-cli/skills/doc-accuracy/scripts/doc_accuracy.py`
- `uv run python build/scripts/build_all.py --check` (run after committing; run before a commit always reports the just-regenerated file as uncommitted drift, which is expected, not a defect)
- Temp fixture reproduction with `doc_accuracy.py --target <tmp> --format summary --severity-threshold high`

## Results

| Check | Result |
|-------|--------|
| Targeted pytest | PASS, 96 tests (was 88 before this round; +8 for the Go/Rust/Java skip and every-supported-language coverage) |
| Ruff (canonical script + tests) | PASS, "All checks passed!" |
| `build_all.py` regeneration | PASS, mirror rewritten from canonical, `diff` reports no differences |
| `build_all.py --check` (post-commit, clean tree) | PASS, exit 0, no staleness reported |
| Reproduction before the original fix | FAIL, exit 10 with 2 claims and 8 high findings |
| Reproduction after the original fix | PASS, exit 0 with 0 claims and 0 findings |

## Notes

- Text fences, Mermaid fences, and PowerShell code examples are unaffected: none of those languages ever had a `SYMBOL_EXTRACTORS` entry, so the switch from the `NON_COMPILABLE_LANGUAGES` denylist to a `SYMBOL_EXTRACTORS`-based allowlist keeps skipping them.
- `run_claim_extraction` (Phase 2) and `run_compilability_check` (Phase 3) both skip a `code_example` claim when its normalized language is not a key in `SYMBOL_EXTRACTORS` (`csharp`, `python`, `javascript`, `typescript` as of this commit). This closes the gap where Go, Rust, and Java fences were absent from both the old `NON_COMPILABLE_LANGUAGES` set and the old Phase 3 tuple, so their generic identifiers were checked against the Python/C#/JS/TS symbol index and could produce a false `unresolved_symbol` finding.
- `method_signature` claims (which always carry `language=""`) are never skipped by this check; only `code_example` claims are gated on the fence language.
- New tests: `test_skips_go_fences`, `test_skips_rust_fences`, `test_skips_java_fences` (Phase 2); `test_skips_go_code_examples`, `test_skips_rust_code_examples`, `test_skips_java_code_examples` (Phase 3); and one `test_resolves_symbol_extractor_languages` test per phase that loops over the live `mod.SYMBOL_EXTRACTORS` keys and asserts `csharp`, `python`, `javascript`, and `typescript` still resolve (Phase 2 still extracts the claim; Phase 3 still reaches the unresolved-symbol check instead of skipping).
- Code example claims no longer inherit a fallback source file when no symbol matches (unchanged from the original fix).

