# Memory Validation workflow: cost analysis

**Question**: does `.github/workflows/memory-validation.yml` earn its cost, or should a
deterministic script replace it?

**Verdict**: it is already a deterministic script. The problem is not the
implementation. Every step it runs is duplicated by another gate, its citation half
has had zero possible signal for the life of the corpus, and it posts a 56 KiB
always-green comment on PRs that is on a measured path to exceeding GitHub's comment
size limit. Recommend deleting the workflow.

## Measurements

All commands run on `origin/main` at `f2dd625`, 2026-09-06.

### The citation gate has no input

```
$ uv run --frozen python -m memory_enhancement verify-all --json | wc -c
3                      # the file is exactly "[]"

$ uv run --frozen python -m memory_enhancement verify-all | wc -l
1036
$ uv run --frozen python -m memory_enhancement verify-all | grep -c "no citations"
1036                   # every line, no exceptions

$ find .serena/memories -name '*.md' | wc -l
1037                   # 1036 scanned; README.md and CLAUDE.md are skipped

$ grep -rn "\[cite:" .serena/memories/ | wc -l
0
$ git log -S"[cite:" -- .serena/memories/
                       # no output, searched against full unshallowed history
```

The workflow was added on 2025-12-24 (`0dadc6994`, "ci: add memory validation workflow for
ADR-017 enforcement", PR #342). It has run for 256 days without a citation existing for it
to check.

The `[cite:type](target)` syntax is documented in `.claude/skills/memory-enhancement/SKILL.md:91`
and `.claude/skills/reflect/references/phase3-4-propose-persist.md:139`. No memory writer
has ever emitted it. The consumer shipped; the producer did not.

### The verifier itself is correct

The zero result is an adoption gap, not a broken parser. Positive and negative control,
run against the same binary:

```
$ printf '# Good\n\nBody.\n\n## Citations\n\n[cite:file](README.md) - exists\n' > .tmp/good.md
$ printf '# Bad\n\nBody.\n\n## Citations\n\n[cite:file](does/not/exist.py) - missing\n' > .tmp/bad.md
$ uv run --frozen python -m memory_enhancement --repo-root . --memories-dir .tmp verify-all
bad:
  [FAIL] does/not/exist.py - File not found: does/not/exist.py

good:
  [PASS] README.md - File exists
$ echo $?
1
```

`memory_enhancement/verification.py` works. Keep it. It is the workflow wrapped around it
that has nothing to do.

### The reported numbers contradict the report body

`scripts/ci/parse_memory_validation_results.py` counts entries in the flat citation array,
not memories. With an empty array:

```
$ python3 scripts/ci/parse_memory_validation_results.py --input results.json --output out.txt
$ cat out.txt
total=0
valid=0
stale=0
has_stale=false
```

`has_stale=false` selects the `✅ Pass` banner at `memory-validation.yml:165`, and the
details block renders `Total memories checked: 0` directly beneath a body that lists 1036
memories by name. A reader who trusts the summary learns nothing; a reader who trusts the
body is reading 1036 lines of "no citations".

### The PR comment is 56 KiB and approaching a hard limit

The workflow posts `memory-health-report.md`, which is the full `verify-all` listing:

| Quantity | Value |
|---|---|
| Report body | 57,152 characters |
| Comment wrapper (`memory-validation.yml:166-179`) | 295 characters |
| Posted comment | 57,447 characters |
| GitHub issue comment limit | 65,536 characters |
| Headroom | 8,089 characters |
| Characters per memory file | 55.2 |
| Memory files until the limit | 146 |

At 146 more memory files, the `Post PR comment` step returns 422 and the job goes red for
a reason unrelated to any PR that trips it. Corpus growth, counted from `git ls-tree` at monthly
points on `origin/main`:

| Date | Memory files |
|---|---|
| 2026-03-06 | 835 |
| 2026-05-06 | 861 |
| 2026-06-06 | 877 |
| 2026-07-06 | 829 |
| 2026-08-06 | 981 |
| 2026-09-06 | 1037 |

The last month ran at 1.81 files per day, the last six months at 1.10 per day (the July dip
is a consolidation pass, not a deletion trend). That puts the 146 file headroom between 81
and 133 days out. The file count is the hard number; the date is a projection.

Every agent that reads a PR thread (pr-comment-responder, the review skills, the CI
feedback sub-loop) pulls those 57,447 characters into context, roughly 14k tokens, to learn
that a feature nobody uses has no findings.

### The comment has never rendered as written

The template literal at `memory-validation.yml:166-179` carries 12 literal spaces on every
line after the opening backtick:

```
            const message = `<!-- MEMORY-VALIDATION -->
            ## ${status}: Memory Validation
            ...
            <details>
            <summary>Validation Details</summary>
```

JavaScript template literals preserve that whitespace, so it reaches GitHub inside the
comment body. CommonMark treats a line indented four or more spaces as an indented code
block, so the status heading, the `---` rule, and the `<details>` collapsible are all
past that threshold. The `${report}` interpolation inherits the indent on its first line
only; the remaining 1035 lines arrive at column zero.

NOT VERIFIED by rendering: this is read from the source and the CommonMark indented-code
rule, not from a posted comment. The indentation itself is directly observable in the file.

### Every step is already run somewhere else

| Step in `memory-validation.yml` | Also runs in | Blocking there? |
|---|---|---|
| `validate_memory_tier.py` (line 89) | `lefthook.yml:354` `memory-tier`, pre-commit | Yes, local |
| `scripts/validation/memory_index.py` (line 96) | `lefthook.yml:344` `memory-index`, pre-commit | Yes, local |
| `scripts/ci/memory_index_count_ratchet.py` (line 102) | `pr-validation.yml:331`, job `Validate PR` | Yes, required check |
| `verify-all` (line 113) | `citation-verify.yml:67` | Yes, exits 1 on stale |
| `verify-all` report (line 133) | `memory-health.yml:108` posts the `health` report | Non-blocking |

`memory-health.yml:12` already labels this workflow "legacy" in its own header comment.

### Not a required check

`scripts/ci/ruleset_required_contexts.py:11-23` pins the nine required contexts:

```
Analyze (actions), Analyze (python), Run Python Tests, Validate Generated Files,
Validate Path Normalization, Validate PR, Validate PR title,
Validate Plugin Version Bump, Validate Spec Coverage
```

"Memory Validation" is not among them, nor are "Citation Verification" or "Memory Health".
The comment at `memory-validation.yml:4-6` says the path-filter structure exists "to satisfy
required checks". It is defending a requirement that the pinned baseline does not record.

NOT VERIFIED against the live ruleset: `gh api` returns 403 in this session. The claim rests
on the repository's own pinned baseline, which `check-ruleset-drift.yml` is supposed to keep
honest.

### Run volume

```
13,391 total runs
40/40 sampled runs: success (all pull_request events)
40 runs over 41.2 hours = 23.3 runs per day
run duration: 71 s and 113 s on two sampled runs
billable UBUNTU time: 0 ms (public repository)
```

The CI cost is not money. It is 2 jobs and 1 to 2 minutes on the PR critical path, a status
line that is always green, and the comment above.

## Recommendation

**Delete `.github/workflows/memory-validation.yml`.** Nothing is lost:

1. Tier and index checks stay enforced at pre-commit by `lefthook.yml:344` and `:354`.
2. The count ratchet stays enforced by the required `Validate PR` check.
3. Citation verification stays enforced, and blocking, by `citation-verify.yml`.
4. The 56 KiB PR comment and its future 422 go away with it.

Confirm `check-ruleset-drift.yml` reports no drift on the required-context set before
deleting, so the removal cannot orphan a live required check that the pinned baseline
missed.

### Two findings this analysis surfaced but did not fix

- `citation-verify.yml` and `memory-health.yml` both scan a corpus with zero citations, so
  both are also structurally silent today. They are cheap (no PR comment from
  citation-verify, a short one from memory-health) and they become useful the moment a
  memory carries a citation. The decision worth making is whether the citation feature gets
  a producer or gets retired; that is a separate call from deleting the redundant workflow.
- `scripts/ci/parse_memory_validation_results.py` labels a citation count as
  "Total memories checked". If any consumer of that script survives the deletion, the label
  is wrong and should say citations.
