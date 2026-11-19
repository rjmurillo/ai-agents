# Citation freshness replay

Measured 2026-11-19: caught 9 of 9 in-scope positives, 0 FP on 12 negatives, 2 manual with reasons.

The checker revision is 5303955a3506.
Every in-scope positive matched the pinned file, class, and line.
The twelve negatives produced no findings.

## Method

Run from the repository root:

```text
uv run python scripts/eval/docs_review_citation_freshness_replay.py
```

The runner fetches each PR head into a unique temporary ref.
It creates detached worktrees under the external repository worktree directory.
Each case uses its pinned commit, including intermediate PR commits.
GitHub supplies the PR base commit through `baseRefOid`.
The comparison base is its merge base with the pinned commit.
Both pre-PR citation functions inspect that historical committed tree.
The validator implementation comes from the working checkout.
Results record the implementation revision and source hashes.
Case findings are stored one file per case.
Cleanup removes each temporary worktree and ref, including after check failures.

A catch requires the same citing file and defect class.
The reported line must fall within three lines of the recorded location.
Every finding on a negative case counts as a false positive.
Operational errors fail the replay instead of becoming clean negatives.

C1-02 catches a retained citation after its surrounding prose changes.
Unique boundary lines reveal that its cited range shifted and grew.
C1-06 catches a stale citation introduced on an added line.

## Cases

| Case | SHA | Expected | Got | Result | Reason |
|---|---|---|---|---|---|
| C1-01 | 8e7e59b2634b | `build_all.py:1005-1033` moved | suggested `build_all.py:1235-1240` | caught | The cited block moved at HEAD. |
| C1-02 | 2580325a93bd | `checks_coverage.py:70-135` drifted | suggested `checks_coverage.py:72-144` | caught | The range moved and grew at HEAD. |
| C1-03 | d4dc86aadf55 | `ai-spec-review.yml:168` is the wrong step | anchors miss line 168 | caught | The added citation does not match that line. |
| C1-04 | 727e9bf5f0ad | `lefthook.yml:328-350` is the wrong group | rare names sit outside 328-350 | caught | The job names sit outside the cited range. |
| C1-05 | b13283f2c305 | `.markdownlint-cli2.yaml:131` should be 138 | anchors miss line 131 | caught | A citation beside an edit fails at HEAD. |
| C1-06 | 2bcb83d278e0 | The new audit citation names stale lines | anchors miss line 58 | caught | The added line cites lines the anchors miss. |
| C1-07 | 81b88dd3df19 | ADR-036 heading moved from line 45 to 58 | anchors miss line 45 | caught | The ADR alias resolves and line 45 fails. |
| C1-08 | 94a46b801ace | `generate_adr_index.py:202` is stale | anchors miss line 202 | caught | The bare name resolves to the changed file. |
| C1-09 | 3d6180a6bf04 | `detect_agent_drift.py:57-76` and line 668 are stale | both ranges fail | caught | Each bare range binds to that one filename. |
| C1-10 | 4f85dfb9864c | Portability lines 660-666 moved | not checked | manual | Serena memories remain exempt under HISTORICAL_ROOTS. |
| C1-11 | 66c5478efaec | Prose lines 265-271 moved | not checked | manual | Prose line ranges lack a path:N citation and occur in a historical root. |
| N01 | 6b9340fac073 | No stale citation | no findings | clean | Negative pull request 7452. |
| N02 | e30fb2297694 | No stale citation | no findings | clean | Negative pull request 7431. |
| N03 | 17e0aa089892 | No stale citation | no findings | clean | Negative pull request 7377. |
| N04 | f9493d63c4e4 | No stale citation | no findings | clean | Negative pull request 7412. |
| N05 | 8fc3c74779bc | No stale citation | no findings | clean | Negative pull request 7146. |
| N06 | c99aca0eb179 | No stale citation | no findings | clean | Negative pull request 7415. |
| N07 | 2bccad6a6a7e | No stale citation | no findings | clean | Negative pull request 7174. |
| N08 | 773f93276e32 | No stale citation | no findings | clean | Negative pull request 7313. |
| N09 | 4d0d39000608 | No stale citation | no findings | clean | Negative pull request 7324. |
| N10 | 3adae314d514 | No stale citation | no findings | clean | Negative pull request 7446. |
| N11 | 2d7585ba6c4e | No stale citation | no findings | clean | Negative pull request 7294. |
| N12 | dd30394857a8 | No stale citation | no findings | clean | Negative pull request 7253. |

## What stays manual and why

C1-10 stays manual.
Serena memories remain exempt under HISTORICAL_ROOTS.
C1-11 stays manual.
Prose line ranges lack a path:N citation and occur in a historical root.

## Limits

The reverse pass blocks new drift and preserves pre-existing citation debt.
A shared token inside a range does not save two rare names outside it.
A name found both inside and outside a range does not vote.
Repeated or edited boundary text can prevent safe relocation suggestions.
A bare basename counts only when one tracked file has that name.
A bare `:N` binds to the previous unique filename.
Prose line ranges with no path stay manual.
Serena memory citation checks require a separate scope decision.
Generated skill copies remain exempt; template sources receive checks directly.
