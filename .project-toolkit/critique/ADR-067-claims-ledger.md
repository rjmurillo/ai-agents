# ADR-067 Claims Ledger: stale failure-message quotes

Checked against the working tree on base `67899d52d` (2026-11-25).

| Claim | Kind | Command | Result |
|---|---|---|---|
| ADR-067 line 154 marks the old "use a bullet/bold" advice superseded | quote | `sed -n 154p` on the ADR | VERIFIED |
| ADR-067 line 195 marks item 5 superseded and keeps the original text | quote | `sed -n 195p` on the ADR | VERIFIED |
| Line 154 keeps the original quote verbatim | quote | `git show HEAD:<ADR> \| sed -n 154p` | VERIFIED |
| The live message scopes claims only when a change heading exists | behavior | `sed -n 1280,1284p scripts/validation/pr_description.py` | VERIFIED, "When the body has a ... heading" |
| The live Check 1 message includes "Remove the path, move it out of that heading, or wrap it in a code fence." | quote | `sed -n 1266,1305p scripts/validation/pr_description.py` | VERIFIED, lines 1285 and 1286; the bypass-label sentences follow it |
| The live message says paths outside a change heading are informational | quote | same range | VERIFIED, line 1284 |
| Line 195 quotes "only paths under it are change claims; paths elsewhere are informational." verbatim | quote | `sed -n 1283,1284p scripts/validation/pr_description.py` | VERIFIED |
| Check 1 lives in `validate_pr_description` | behavior | `awk` for the enclosing `def` of line 1269 | VERIFIED, `def` at line 1253 |
| With a change heading, every pattern is scoped to it | behavior | `sed -n 134,143p` and `_scoped_pattern_indexes` at line 585 | VERIFIED |
| PR #6414 merged as `294ce6aec` | path | `gh pr view 6414 --json state,mergeCommit` | VERIFIED, MERGED 2026-10-13 UTC |
| The 2026-11-25 amendment section exists in ADR-067 | quote | `grep -n "^## Amendment" ` on the ADR | VERIFIED, line 224 |
| The ADR keeps 234 lines, so line citations hold | count | `wc -l` before and after | VERIFIED, 234 both |
