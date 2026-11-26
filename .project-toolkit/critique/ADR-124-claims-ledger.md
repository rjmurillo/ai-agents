# ADR-124 claims ledger

The draft proposes a design. This ledger records claims about the current tree and receipts.

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| The next free ADR number is 124. | count | `uv run --frozen python scripts/validation/check_adr_uniqueness.py --print-next` after the main merge | Returned 124. Main holds `ADR-123-skill-artifact-flow-declarations.md`. |
| The first integrated scan at `8f889d682` exited 10 with 801 highs. | count | Round 1 ledger row for the parent receipt | 801 high, zero critical, exit 10. |
| Round 1 blocked with six votes. | behavior | Read the round 1 table in the debate log | Six Block votes. |
| The `6a8c7e8c8` replay exited 10 with 1,137 highs. | count | Read `.project-toolkit/scratch/readiness-6a8c7e8c8-corpus.log` | `Findings: 1137 total`, `high: 1137`, exit status 10. |
| All 1,137 findings are `unresolved_symbol`. | count | Rerun `run_compilability_check` on the saved assessment and claims | Category counter shows 1,137 `unresolved_symbol`. |
| The split is 817 C#, 287 TypeScript, and 33 Python. | count | Join replay findings to claims by `claim_id` and count `language` | csharp 817, typescript 287, python 33. |
| The findings span 111 files. | count | Count distinct `file` values in replay findings | 111. Mirror copies of skill references account for part of the total. |
| `System` accounts for 153 findings. | count | Count quoted symbols in replay finding descriptions | `System` 153, `IReadOnlyDictionary` 19, `ReadOnlySpan` 17. |
| TypeScript `map` still appears as a finding. | count | Same symbol count | `map` 5. |
| The probe's invented names pass at HEAD. | behavior | Run the regular CLI on `.project-toolkit/scratch/readiness-export-probe` at `f56b96104` | Exit 10 with one finding, `System`. No invented name is reported. |
| The replay took 12 minutes 56 seconds and 328,940 KiB peak RSS. | count | GNU time output in the corpus log | `12:56.16` elapsed and `328940` maximum RSS. |
| Removing shortcuts added 223 raw findings in round 1. | count | Round 1 P0 2 in the debate log | 87 C-family plus 136 Python stdlib. |
| Commit `f915118ec` added scope and literal handling. | behavior | `git log -1 --format='%h %s' f915118ec` | `fix(doc-accuracy): resolve verified example bindings`. Ancestor of HEAD. |
| Commit `3c2a56c1b` added the vendored SDK marker. | behavior | `git log -1 --format='%h %s' 3c2a56c1b` | `fix(doc-accuracy): add an external-sdk marker for vendored SDK docs (#7423)`. |
| Exit 10 means findings met the threshold; exit 1 means inconclusive. | behavior | `doc_accuracy.py --help` exit code table | 10 and 1 as stated. |
| Hermes has a 399-file pack budget. | count | `grep -n packMaxFiles templates/platforms/hermes*.yaml` | `packMaxFiles: 399`. |
| The scanner has six tracked copies. | count | Round 1 ledger row for `git ls-files '*doc-accuracy/scripts/doc_accuracy.py'` | Claude, Codex, Copilot CLI, Cursor, Hermes delivery, and Muse. |
| The probe versions are .NET SDK 10.0.404, reference pack 10.0.15, TypeScript 5.9.3, Node 26.13.1, and mypy 2.4.1. | behavior | Round 1 ledger probe rows | Versions match the Linux probe host. |
| The related ADR links resolve. | path | `ls` each linked ADR file | ADR-115, ADR-121, and ADR-122 exist. |
