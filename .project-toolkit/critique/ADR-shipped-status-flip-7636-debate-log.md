# Debate Log: accept 17 shipped ADRs (issue #7636)

- **Records**: ADR-038, ADR-049, ADR-067, ADR-070, ADR-075, ADR-077, ADR-078,
  ADR-088, ADR-089, ADR-098, ADR-104, ADR-107, ADR-112, ADR-114, ADR-115,
  ADR-119, ADR-126. ADR-055 gets one dated sentence.
- **Panel**: reduced (architect, critic). No Decision changes in substance.
- **Outcome**: Consensus
- **Final Status**: accepted, all 17 records

## Owner direction

On 2026-11-25 the repository owner accepted all 17 records in one decision
brief for issue #7636. ADR-073 forbids a self-asserted `accepted`. The owner's
answer is the approval, and this log records it.

- D1: accept ADR-038, 067, 070, 088, 104, 107, 112, 114, 119, and 126.
- D2: accept ADR-075, 078, 089, and 098. ADR-055 recorded these as held on
  purpose until the owner signed. This is that signature.
- D3: the owner asked for the ADR-077 trial to be investigated first. The
  review found no recorded use and no recorded harm, so it produced no data.
  The rule is already carried by five live artifacts. The failure class it
  targets recurred in the 2026-09-01 PR #5343 retrospective. Outcome: accepted
  as permanent, with `review-by` cleared.
- D4: accept ADR-049 now. Issue #7588 had no PR in flight on 2026-11-25, and
  it will amend the accepted record through adr-review. Accept ADR-115 with
  `implemented: false`.

## Implementation verification

Each `implemented: false` record was checked against the tree at `ffc759356`
(2026-11-25) before the flip.

| ADR | Result | Evidence |
|---|---|---|
| ADR-088 | Shipped | `software-engineering-library` skill holds every moved book reference |
| ADR-104 | Shipped | Merged as PR #5319; container clamp and testmon path in `git_hook_policy.py` |
| ADR-107 | Shipped | Issues #5686 to #5691 closed as completed; M5 via PR #5743 |
| ADR-114 | Shipped | 11 of 11 gated workflows declare `agent-*`; the environments have required reviewers |
| ADR-115 | Not shipped | Decision 4 commits to `src/devin/`, which does not exist |
| ADR-126 | Shipped | PR #7546 merged 2026-11-24 |

## What changed

1. Frontmatter `status` moved to `accepted` on all 17. `implemented` moved to
   true on ADR-088, 104, 107, 114, and 126.
2. Each `## Status` section that opened with "Proposed" now records the
   acceptance, so `prose-frontmatter-agree` holds.
3. Accepting a record turns on `cited-paths-exist` for it. Dead paths were
   either corrected to the live file or written as plain text, and marked
   removed, host-relative, external, or illustrative.
4. `implemented-implies-decided` and `review-by-past-due` in
   `scripts/validation/adr_lifecycle_baseline.json` are now empty.

## Review

| Reviewer | Verdict | Findings |
|---|---|---|
| architect | Disagree-and-Commit | 3 P1, 4 P2 |
| critic | Accept | 4 P2 |

All findings were fixed in this change:

- architect P1: this log is committed with the change.
- architect P1 and critic P2: the ADR-107 Status now cites PR #5743 for M5. The
  "enforces nothing until M1" line now reads in the past tense.
- architect P1: ADR-077 notes in the body that the trial ended.
- critic P2: the ADR-077 claim names the search it relied on. It no longer says
  the retrospective proves the rule worked.
- critic P2: ADR-104 cites PR #5319 and `107205cf7`.
- architect P2: ADR-089 cites the live `reflexion_memory.py` path as a code span.
- architect P2: ADR-115 marks the manifest paths as host-relative.
- architect and critic P2: ADR-055 notes that ADR-093 was already accepted.

**Verdict**: Consensus to accept, with no BLOCK.
