# Revision Grounding

Analysis and review run against a local checkout. The default branch may
advance while you work. A defect fixed upstream then reads as current, and the
issue you file duplicates work that already merged.

Bind every finding that depends on repository state to a verified live commit.

<!-- vendor-portability: declared. The helper scripts/validation/live_revision_grounding.py lives in the upstream checkout and does not ship in the plugin. Consumers without it run the manual fallback at the end of this file. Issue #5634. -->

<!-- vendor-portability-exec: the run step invokes
     scripts/validation/live_revision_grounding.py, which lives upstream in the
     rjmurillo/ai-agents repo and ships in no plugin root. A consumer checkout
     without it follows the manual fallback at the end of this file (issue #5634). -->

## When

1. At analysis start.
2. Immediately before `new_issue.py`, or before applying a fix from a finding.

## Run the helper

The helper is scripts/validation/live_revision_grounding.py. From an upstream checkout:

```bash
# Analysis start: record the live SHA.
uv run python scripts/validation/live_revision_grounding.py

# Before creating the issue: reuse the recorded SHA and revalidate each citation.
uv run python scripts/validation/live_revision_grounding.py \
  --since <live_sha from the first run> \
  --cite <file>:40-52 --cite <other-file> \
  --require-current
```

Pass every `HIGH` finding's file and line range, and every citation you mark
`CURRENT`, as a `--cite`. The helper compares the cited lines at each revision
that differs from live (`local_head`, and `--since` when it differs) against the
live revision. `--remote` must not start with `-`. `--since` must be a full
40 or 64 hex-digit SHA, lowercase.

## Read the record

| Field | Meaning |
|-------|---------|
| `live_sha`, `branch`, `retrieved_at` | The default-branch tip the remote reported just now |
| `local_head`, `status` | Your checkout against live: `equal`, `behind`, `ahead`, `diverged`, `unverified` |
| `grounded_sha` | The revision the findings were read at (`--since`, else `local_head`) |
| `live_changed` | `true` when the live SHA moved since `--since` |
| `finding_status` | `CURRENT`, `STALE`, or `UNVERIFIED` |
| `citations` | One row per citation and compared revision: `citation`, `revision`, `status`, `detail` |

Exit codes: 0 record emitted, 1 `--require-current` and not `CURRENT`, 2 usage
or configuration error, 3 remote read or fetch failed, 4 auth failure.

## Rules

- `CURRENT` means `local_head` and the grounded revision are both live, or
  every cited range is identical between each differing revision and live.
  `--since` equal to live does not vouch for a checkout that is behind: the
  findings were read from the checkout, so `local_head` is always compared.
- A cited range that starts past the end of the file at either revision is
  `UNVERIFIED`. A range that only ends past the end is clamped, and the
  `detail` says so.
- `STALE`: withdraw the finding or relabel it. Keep the original revision with
  it. A later fix does not make the old finding false history.
- `UNVERIFIED`: includes a failed remote read. Say so in the artifact. Do not
  present the finding as current.
- A `STALE` or `UNVERIFIED` finding is never the sole basis for an issue.
- Put `grounded_sha`, `live_sha`, and `finding_status` in the analysis artifact
  and in any issue body that depends on repository state.
- Run the helper again if the analysis spans a long gap. Pass the earlier
  `live_sha` as `--since` so a moved default branch shows as `live_changed`.

## Manual fallback

Without the helper, compare `git ls-remote origin HEAD` with `git rev-parse
HEAD`. If they differ, treat every finding as `UNVERIFIED` until you re-read the
cited lines at the live SHA (`git fetch origin <sha>`, then `git show
<sha>:<path>`).
