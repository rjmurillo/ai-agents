# ADR-113 claims ledger

Each row is one factual claim in ADR-113, the command run, and the result observed in this session on branch docs/5636-promotion-gate-adr cut from origin/main at 1e6f770fb.

| # | Claim | Kind | Command | Result |
|---|---|---|---|---|
| 1 | The epic lists the five quoted requirements | quote | `gh issue view 5636 --json body` | VERIFIED. All five lines appear verbatim in the body |
| 2 | The only release workflow is publish.yml | absence | `ls .github/workflows` filtered for release, promot, publish | VERIFIED. One match, publish.yml |
| 3 | publish.yml is tag-triggered (v*) and has a validate job for metadata, tag-version match, pack size | behavior | read `.github/workflows/publish.yml` lines 1-80 | VERIFIED |
| 4 | Nothing in publish.yml reads test, analysis, or validation results | absence | grep for needs, aggregate, required, check-runs, status in publish.yml | VERIFIED. Only `needs: validate` matches, which is the in-file job |
| 5 | A repository search for "promotion gate" finds only skillbook logic | absence | `grep -rniE "promotion gate\|promotion-gate"` over py, yml, md, json, minus session and QA notes | VERIFIED. scripts/skillbook.py and .project-toolkit/skillbook/README.md, plus .serena and .project-toolkit/qa notes excluded as records |
| 6 | evidence.py defines five states, a revision field, worst-wins aggregation, PolicyException | path | read `scripts/validation/evidence.py` lines 136-146, 235-250, 543, 562-576 | VERIFIED |
| 7 | PolicyException has validator, states, reasons, justification, reference and no owner, approval, expiry, remediation field | absence | read lines 560-576, grep owner, expir, approv in evidence.py | VERIFIED. The three grep hits are unrelated prose |
| 8 | aggregate treats an empty child set as UNKNOWN | behavior | read lines 908-940 | VERIFIED. REASON_NO_OUTCOMES and a docstring naming UNKNOWN |
| 9 | ADR-101 states the plane-above rule verbatim | quote | `grep -c` of the full sentence in ADR-101 | VERIFIED. Count 1 |
| 10 | The drift allowlist has path and reason per entry, a strict loader, and CODEOWNERS protection | behavior | read `build/drift_allowlist.py` and `.github/CODEOWNERS` lines 66-70 | VERIFIED |
| 11 | The repository lists one code owner | count | grep of owners in CODEOWNERS | VERIFIED. One distinct owner, @rjmurillo |
| 12 | Decision D17 allowlist uses owner and expiry fields | behavior | D17 owner message in this session | NOT CHECKED IN THE TREE. The allowlist lands in a separate pull request under #5636 and is not merged when this ledger was written |
| 13 | publish.yml also publishes on workflow_dispatch with dry-run false | behavior | read `.github/workflows/publish.yml` lines 11-26 | VERIFIED. `workflow_dispatch` with a `dry-run` choice input, default true |
| 14 | CheckOutcome has no digest field and aggregate compares no revisions | absence | grep digest, sha256, artifact in `scripts/validation/evidence.py`; read `aggregate` | VERIFIED by the architect seat in debate round 1; no digest or artifact field found |
| 15 | A tag push runs the workflow file at the tagged commit | behavior | GitHub Actions documented behavior for `push` events | NOT CHECKED IN THE TREE. External behavior, stated as the reason decision 5 exists |
