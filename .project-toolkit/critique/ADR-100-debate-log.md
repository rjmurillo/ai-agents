# ADR-100 Debate Log

## Summary

The reduced panel reached consensus after four rounds with 0 open P0 and 0 open P1 findings.
The ADR retains its accepted status.
Earlier reviews include the [joint debate](ADR-100-101-enforcement-planes-debate-log.md) and the [September amendment](ADR-100-amendment-2026-09-22-debate-log.md).

D19a authorized citation repairs.
D21A added minimal historical CI framing for ADR-102.
The patch contains no policy, enforcement, or gate-read rule changes.
Architect and critic reviewed it under the reduced-panel rule.
The parent supplied the positions and review receipt IDs below.

## Reviewed Patch

The Round 2 patch replaces 15 lines across three ADRs.
Rounds 3 and 4 are later citation-only repairs after merges from main.
The base commit is `49ebeee9ecc173475670fb42d3fb454b272ca3a4`.
The full-index ADR patch has SHA-256 `431f1f3b7b42f10292112ce6a8d213a8ffff2bbae011e81c24f3c38e8a1fe996`.

| Version | Git blob |
| --- | --- |
| Base | `fd9817f468fc1c7ad13a97ab49d3d5bbf34ac764` |
| Round 1 | `da74d6c746589934380c8042230d8e99c322992c` |
| Round 2 | `da74d6c746589934380c8042230d8e99c322992c` |
| Round 3 | `e1e3aeb35d09aa3edfb975403cf3b49b7812291b` |
| Round 4 | `c1e79358afdbc5a48091e5c734e5377aae1e2851` |

## Round 1

The panel reviewed three historical citation repairs under D19a. The critic recorded the range qualification below.

| Reviewer | Verdict | Review receipt ID |
| --- | --- | --- |
| Architect | Accept | `f4b12e0f-9990-4014-b075-4c3ec9b9f183` |
| Critic | Disagree-and-Commit | `81b4d669-f1de-435a-b78e-3d802a6dc02c` |

## Round 2

Both reviewers accepted the citation repair with two P2 reservations about existing wording.

- Line 436 states range equivalence without qualification. The pre-push code first tries the trunk merge base. On an existing branch, it falls back to the remote SHA if needed. [Range selection](https://github.com/rjmurillo/ai-agents/blob/7d87d633331573e5a42aec75396237dd54216848/scripts/validation/git_hook_policy.py#L5610-L5636)
- Line 256 uses "now" for the dated advisory snapshot. Commit `23ad6e429` later removed that implementation. [Advisory snapshot](https://github.com/rjmurillo/ai-agents/blob/76e2b319b4fd32e172ce800f8922f3b2ba9365a1/scripts/validation/git_hook_policy.py#L6727-L6769) and [removal](https://github.com/rjmurillo/ai-agents/commit/23ad6e4290d9bce259824d26e74b2fc43a2edb50).

The panel kept both reservations outside the approved citation repair.
Existing advisory references on ADR lines 31, 37, and 250 remain outside scope.

| Reviewer | Verdict | Review receipt ID |
| --- | --- | --- |
| Architect | Disagree-and-Commit | `c71a5fc7-4d61-4ea6-9650-c8c9c6654ecd` |
| Critic | Disagree-and-Commit | `c5b49daf-681f-44c9-837b-73faefd1d63c` |

## Round 3

Merges from main moved the code that line 37 cites.
The reverse citation gate blocked pre-push on the stale `:6389`.
The repair changes `git_hook_policy.py:6373` to `:6854` and `:6389` to `:6870`.
Both lines hold the quoted code. No decision text changed.

| Reviewer | Verdict | Review receipt ID |
| --- | --- | --- |
| Architect | Accept | not issued |
| Critic | Accept | not issued |

The architect noted that line-number citations will drift again after later merges.
The critic noted that line 37 still cites `pr_commit_count.py`, which #5893 deleted.
Both reservations predate this repair and stay outside its scope.

Editing line 37 made the gate re-check its `:6727` citation.
That line cited `_check_commit_limit`, which #5893 deleted with the size ceilings.
A `citation-freshness: ignore` comment above line 37 marks it as history, as ADR-101 line 188 does.

## Round 4

The merge of #7537 added two lines near the top of `git_hook_policy.py`.
Line 37 cited code that now sits two lines lower.
The repair changes `:6854` to `:6856` and `:6870` to `:6872`.
It changes both the prose and the existing ignore comment.
Both lines hold the quoted code. No decision text changed.

| Reviewer | Verdict | Review receipt ID |
| --- | --- | --- |
| Architect | Accept | not issued |
| Critic | Accept | not issued |

The critic first blocked an unrepaired `:2787` citation in ADR-102.
That repair is in the ADR-102 debate log, and the critic then accepted.
Citations that were already stale before the merge stay outside this repair.
