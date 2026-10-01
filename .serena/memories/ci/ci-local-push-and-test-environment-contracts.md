# Local test and push runs need three environment settings

Three contracts that fail late or silently when missing. Sources: PR #6063
report, PR #6040, the D17 agent report, PR #6062, and the code cited below.

## CLAUDE_PLUGIN_ROOT points at `.claude`

Set `CLAUDE_PLUGIN_ROOT=.claude`, not the repository root. With the root, the
memory scripts fail at import. The skill command paths already fall back to
`.claude` (`${CLAUDE_PLUGIN_ROOT:-.claude}`), so an explicit value must match.

## Set PYTHONDONTWRITEBYTECODE=1 for ad hoc runs

A leftover `__pycache__` under `.claude` or `src` fails the generated-staleness
push gate. Set `PYTHONDONTWRITEBYTECODE=1` for the run that created it.

Do not confuse this with `decision-warm-pycache-before-push-never-purge.md`.
That memory covers the parallel pre-push group racing on a cold cache under
`scripts`, where the fix is to warm the cache, never to purge it. This one covers
stray bytecode written by manual runs into trees the staleness gate scans.

## The pre-push python-tests job only collects

By default pre-push runs a collection smoke, not the suite
(`TEST_COLLECTION_TIMEOUT_SECONDS` in `scripts/validation/git_hook_policy.py`;
full execution is opt-in through `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY`, per
ADR-104). Real execution happens in CI or by hand. To match CI locally:

```bash
CLAUDE_PLUGIN_ROOT=.claude GITHUB_EVENT_NAME=merge_group PYTHONDONTWRITEBYTECODE=1 \
  uv run --frozen pytest
```

A green pre-push is not a green suite.

## A merge of main can demand a D9 review marker

After merging main into a branch, the push carries main's new commits. If they
touched CRITICAL paths such as workflows, the `infrastructure-advisory` job in
`lefthook.yml` (issue #5636, D9) refuses the push unless HEAD is a `/review`
marker commit binding the security axis to its parent. The merge commit is not a
marker, so the push is refused although your own diff is clean. Run `/review`
on the merged head, then push.
