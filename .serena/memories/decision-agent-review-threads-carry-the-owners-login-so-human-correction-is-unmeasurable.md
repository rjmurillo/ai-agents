# EUREKA: every review intervention here carries the PR author's login, so human correction cannot be counted

## Question

Can the review-intervention miner count how often a human corrected an agent's PR?

## Conventional answer

Count review threads opened by someone other than the PR author, or by a human account, and call them human interventions. Intervention clusters then read as repeated human corrections.

## First-principles position

On this repository the owner's login posts both human and agent review text. The author field cannot separate them.

Measured on `origin/main` at `981de77c1` per issue 7304, and re-read from the committed file on 2026-11-11:

| Field in `.project-toolkit/metrics/reviewer-intervention-clusters/report.json` (`examined`) | Value |
|---|---|
| `interventions` | 755 |
| `interventions_by_pr_author` | 755 |
| `agent_pull_requests` | 1037 |
| `trailer_pull_requests` | 1024 |

All 755 threads sit under the PR author's login. Agent PRs are found by a Claude Code trailer in the body, because the author login is the owner's.

The README in that directory records a sample read: 30 of 106 interventions on PRs from the six days to 2026-11-11 were long, structured findings with file and line references and exact diff quotes. That fits agent-written review. The API does not say who typed them, so this is INFERRED, not proven.

Consequence: the premises of issues 7153 and 7154, which treat these threads as human corrections, hold only with the caveat. A human-versus-agent split needs a distinct agent account or a comment marker.

## Decision

Issue 7304 proposed a signal to separate the two. The owner closed it as not planned on 2026-11-11 and chose to keep the caveat. The README states that clusters are repeated findings under the owner's login, not proven human corrections. Reopen only if a consumer needs human-only counts.

## Relations

- **related_to**: [decision-neither-session-store-carries-usable-authorship](decision-neither-session-store-carries-usable-authorship.md)
