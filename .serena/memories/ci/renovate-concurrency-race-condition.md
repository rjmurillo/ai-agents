# Renovate PR Concurrency Race Condition

## Problem

Renovate dependency PRs frequently fail required CI checks "Validate PR" and "Validate PR title" even though the PR titles are valid conventional commits. This blocks auto-merge.

## Root Cause

The `cancel-in-progress: true` setting in two workflows creates a race condition:

1. Renovate opens a PR, firing the `opened` event. Both workflows start.
2. Renovate immediately edits the PR title/body, firing the `edited` event.
3. The concurrency group (`pr-validation-{number}` and `semantic-pr-check-{number}`) cancels the first in-progress run.
4. The second run completes successfully.
5. GitHub branch protection sees TWO check runs: one CANCELLED, one SUCCESS. It requires ALL to pass. The CANCELLED run blocks merge.

## Affected Workflows

- `.github/workflows/pr-validation.yml` (job name: "Validate PR")
- `.github/workflows/semantic-pr-title-check.yml` (job name: "Validate PR title")

## Diagnosis Steps

When a Renovate PR fails these checks:

1. Do NOT assume the title format is wrong. Check the title first, but the cause is usually this race.
2. Get check details: `python3 .claude/skills/github/scripts/pr/get_pr_checks.py --owner rjmurillo --repo ai-agents --pull-request {NUMBER} --output-format json`
3. Look for CANCELLED runs alongside SUCCESS runs for the same check name.

## Immediate Fix

Re-run the cancelled workflow run: `gh run rerun {RUN_ID} --repo rjmurillo/ai-agents`

## Durable Fix

PR #1602 adds `renovate[bot]` to the bot skip list in both workflows, preventing the race entirely. Once merged, Renovate PRs skip validation (Renovate config controls title format).

## Discovery Date

2026-04-10. Found while triaging 16 open PRs. PRs #1587, #1585, #1561 all exhibited this pattern.
