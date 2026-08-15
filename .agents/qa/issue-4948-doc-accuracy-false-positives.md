---
qaCommit: aed5d0c14ded588ff6e46b9b43d91e6f2941fa2e
qaSessionLog: .agents/sessions/2026-08-14-session-14711-fix-4948-doc-accuracy-false-positives.json
qaVerdict: PASS
---

# QA Report: Issue #4948 - Doc Accuracy False Positives

## Objective

Verify the fix for `doc-accuracy` false positives on text fences, Mermaid fences, PowerShell examples, unmapped code claims, and code examples in languages that have no `SYMBOL_EXTRACTORS` entry (Go, Rust, Java, and any future addition). Also verify the follow-up fix for a regression where the fence-detection regex truncated `c#` to `c`, causing the new `SYMBOL_EXTRACTORS` allowlist to incorrectly skip common C# fences written as ` ```c#`.

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
| Targeted pytest | PASS, 99 tests (was 96 after the Go/Rust/Java skip fix; +3 for the c# fence regression: one `_detect_language("c#")` alias pin, one extraction-phase regression test, one end-to-end extraction+compilability-check regression test) |
| Ruff (canonical script + tests) | PASS, "All checks passed!" |
| `build_all.py` regeneration | PASS, mirror rewritten from canonical, `diff` reports no differences |
| `build_all.py --check` (post-commit, clean tree) | PASS, exit 0, no staleness reported |
| Reproduction before the original fix | FAIL, exit 10 with 2 claims and 8 high findings |
| Reproduction after the original fix | PASS, exit 0 with 0 claims and 0 findings |
| Reproduction of the c# regression before the follow-up fix | FAIL, `run_claim_extraction` on a ` ```c#` fence returned `claims: []` (claim silently dropped) |
| Reproduction of the c# regression after the follow-up fix | PASS, `run_claim_extraction` returns one `code_example` claim with `language == "csharp"` |

## Notes

- Text fences, Mermaid fences, and PowerShell code examples are unaffected: none of those languages ever had a `SYMBOL_EXTRACTORS` entry, so the switch from the `NON_COMPILABLE_LANGUAGES` denylist to a `SYMBOL_EXTRACTORS`-based allowlist keeps skipping them.
- `run_claim_extraction` (Phase 2) and `run_compilability_check` (Phase 3) both skip a `code_example` claim when its normalized language is not a key in `SYMBOL_EXTRACTORS` (`csharp`, `python`, `javascript`, `typescript` as of this commit). This closes the gap where Go, Rust, and Java fences were absent from both the old `NON_COMPILABLE_LANGUAGES` set and the old Phase 3 tuple, so their generic identifiers were checked against the Python/C#/JS/TS symbol index and could produce a false `unresolved_symbol` finding.
- `method_signature` claims (which always carry `language=""`) are never skipped by this check; only `code_example` claims are gated on the fence language.
- New tests from the Go/Rust/Java skip fix: `test_skips_go_fences`, `test_skips_rust_fences`, `test_skips_java_fences` (Phase 2); `test_skips_go_code_examples`, `test_skips_rust_code_examples`, `test_skips_java_code_examples` (Phase 3); and one `test_resolves_symbol_extractor_languages` test per phase that loops over the live `mod.SYMBOL_EXTRACTORS` keys and asserts `csharp`, `python`, `javascript`, and `typescript` still resolve (Phase 2 still extracts the claim; Phase 3 still reaches the unresolved-symbol check instead of skipping).
- Code example claims no longer inherit a fallback source file when no symbol matches (unchanged from the original fix).
- **c# regression (follow-up fix)**: the fence-detection regex in `run_claim_extraction` captured the info string with `\w*`, which stops at the first non-word character. A ` ```c#` fence therefore passed only `"c"` to `_detect_language`, which has no alias for bare `"c"` (only `"cs"`/`"csharp"`/`"c#"` map to `"csharp"`), so `"c"` was returned unchanged and, having no `SYMBOL_EXTRACTORS` entry, every c# code example was silently skipped by the new allowlist. Fixed by broadening the capture group to `\S*`, which captures the full non-whitespace info-string token (`_detect_language` already tokenizes on whitespace via `.split()[0]`, so this is a no-op for any fence whose info string was already all word characters). `_count_code_blocks` has the same underlying character-class limitation (`^```\w*\s*$`) but is a Phase 1 statistics-only counter, not part of the compilability-gating logic that was the subject of the reported regression; left unchanged per "fix narrowly."
- New tests from the c# regression fix: `TestDetectLanguage.test_c_sharp_hash_alias` (pins the pre-existing `"c#"` -> `"csharp"` `lang_map` entry so it cannot be silently removed), `TestRunClaimExtraction.test_extracts_csharp_from_hash_alias_fence` (proves a ` ```c#` fence still produces a `code_example` claim with `language == "csharp"`, i.e., extraction is not skipped), and `TestRunCompilabilityCheck.test_checks_csharp_hash_alias_end_to_end` (runs the real `run_claim_extraction` output for a ` ```c#` fence through `run_compilability_check` and asserts an `unresolved_symbol` finding is produced, i.e., compilability resolution is not skipped either).

