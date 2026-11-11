# Maintainer operations: CI and release controls

## Goal

By the end, you will have run each control you operate and read its verdict
yourself. You will know:

- Which workflows wait for your approval, and why they never hold a merge.
- Which workflows are required and which only report.
- What the promotion gate and the tarball digest check do before an npm publish.
- How the two ruleset drift checks fire.
- How to cut a release.
- Which dependency bumps Renovate and Dependabot will not merge for you.

One check proves it worked: every command below exits as the page says. Each
part ends with its own check.

This page links to the reference text. It does not copy it. When a link and this
page disagree, the link wins.

## Before you start

- A clone of `rjmurillo/ai-agents` on `main`, set up with the one-command
  [Setup Steps](../../CONTRIBUTING.md#setup-steps).
- `gh` signed in with read access to the repository. The drift checks read the
  live ruleset through the GitHub API.
- Admin rights on the repository, if you want to approve a run or change a
  setting. A read-only clone is enough for every command on this page.
- Work from the repository root.

Do not skip hooks with `--no-verify` and do not force-push. The
[runbook conventions](../runbooks/README.md#conventions) apply to every step.

## Part 1: Agent workflows wait for you and never block a merge

**Outcome:** you can name the workflows that need your click, and you can show
that a failed run of one of them does not stop a merge.

### What the policy says

[ADR-114](../../.project-toolkit/architecture/ADR-114-agent-workflows-approval-and-non-blocking.md)
sets two rules for every workflow that calls a model:

1. The job runs in a provider environment with a required reviewer. The run waits
   for a click before it spends anything. The environments are `agent-claude`,
   `agent-copilot`, `agent-codex`, and `agent-droid`.
2. The check it posts is advisory. A failed, skipped, cancelled, or waiting
   result never holds a merge.

The plugin CLI smoke used to be the one exception. The owner made it advisory on
2026-11-05, so it is no longer an exception. Read the ADR-114 amendment of that
date. Older issue text (#6131, #6215, #6197) predates it.

[docs/COST-GOVERNANCE.md](../COST-GOVERNANCE.md#agent-workflows-approval-gated-advisory)
lists the gated workflows and the secret each environment holds.

### Approve a run

1. Open the run in the Actions tab. A gated run shows "Waiting".
2. Read the event that started it. The approval screen shows the job, not the
   comment or PR text that drives the agent.
3. Choose **Review deployments**, tick the environments, and approve or reject.

One review can approve both `agent-claude` and `agent-copilot` for the smoke.
Each new push cancels the older run, including legs still waiting.

You are the only reviewer, and self-review is allowed. Any process that holds
your token can approve its own run. Claude Code denies this call for that reason:

```bash
grep -n pending_deployments templates/hooks/settings.tmpl
```

```text
70:            "Bash(gh api *pending_deployments*)"
```

The deny rule slows an agent down. It does not stop `curl` or the GraphQL
mutation (ADR-112, gap G11). Approve from the browser and never hand an agent
your token.

### See which checks are advisory

The list lives in `.claude/skills/pr-review/pr-review-config.yaml`. The
readiness check reads it from `origin/main`, so a PR cannot add its own check.

```bash
sed -n '/^advisory_agent_workflows:/,/^transport_preflight:/p' \
  .claude/skills/pr-review/pr-review-config.yaml | grep 'path:'
```

```text
  - path: ".github/workflows/ai-spec-validation.yml"
  - path: ".github/workflows/ai-spec-review.yml"
  - path: ".github/workflows/slash-command-quality.yml"
  - path: ".github/workflows/post-pr-retrospective.yml"
  - path: ".github/workflows/software-engineering-library-activation.yml"
  - path: ".github/workflows/claude.yml"
  - path: ".github/workflows/plugin-cli-smoke.yml"
```

Only workflows that run on `pull_request` are listed. The scheduled and dispatch
agent workflows post no check on a PR. A check that the branch ruleset requires
stays blocking even if its workflow is listed (ADR-114 decision 7).

### Prove the exemption

```bash
uv run --frozen pytest -n0 -q tests/test_pr_merge_ready_advisory_agent_checks.py
```

```text
============================== 83 passed in 9.95s ==============================
```

To read the live verdict on any open PR, run the readiness check. Add
`--include-non-required` so waiting checks count too:

```bash
python3 .claude/skills/github/scripts/pr/test_pr_merge_ready.py \
  --pull-request <number> --include-non-required
```

Look at `UndisposedNonRequiredFailures` and `PendingNonRequiredChecks` in the
JSON. A listed agent check never appears there.

### Check your result

The pytest line ends in `passed` with no failures.

### If it fails

- **A gated run never asks for approval.** The environment may be missing or
  unprotected. GitHub creates a missing environment with no reviewers on first
  use, and then the run starts unapproved (ADR-114 decision 12). Open
  Settings > Environments and confirm each `agent-*` environment lists a required
  reviewer. Only an admin can see this.
- **You deleted an environment and it came back.** A waiting run recreated it
  with no protection (ADR-114 decision 11 item 6). Check every waiting run before
  you delete an environment.
- **A new agent workflow blocks merges.** It is missing from
  `advisory_agent_workflows`. Add it in a PR. The list is read from `main`, so
  the change takes effect after it merges.
- **A Claude leg fails with "Credit balance is too low".** This is accepted
  (ADR-114 decision 11 item 9). The check is advisory, so the PR can merge.

## Part 2: Required versus report-only workflows

**Outcome:** you can say, for any PR workflow, whether it is required or only
reports, and you can see the test that fails when someone forgets to choose.

Issue #7024 made the choice explicit. Every workflow that triggers on
`pull_request`, `pull_request_target`, or `merge_group` is in one of two sets in
`scripts/ci/ruleset_required_contexts.py`:

- `REQUIRED_WORKFLOWS`: workflows that produce a context the branch ruleset pins.
- `REPORT_ONLY_WORKFLOWS`: every other one, each with a written reason.

Count them:

```bash
PYTHONPATH=. uv run --frozen python -c "
from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS, REQUIRED_WORKFLOWS, REPORT_ONLY_WORKFLOWS
print(len(REQUIRED_CONTEXTS), len(REQUIRED_WORKFLOWS), len(REPORT_ONLY_WORKFLOWS))
print(REPORT_ONLY_WORKFLOWS['plugin-cli-smoke.yml'])
"
```

```text
9 7 37
model-driven: spends provider quota or waits on an agent-<cli> environment approval, so it must never gate a merge
```

The first line reads: 9 pinned contexts, 7 required workflows, 37 report-only
workflows. These counts describe `main` at `b959011e3` (2026-11-10).

Run the classification test:

```bash
uv run --frozen pytest -n0 -q tests/ci/test_pr_workflow_classification.py
```

```text
============================== 50 passed in 2.80s ==============================
```

The test fails when a PR workflow is in neither set. It also fails when a
required workflow reads a model credential. Add a new PR workflow and you must
pick a set.

Promoting a report-only workflow to required is a ruleset change. Only an admin
can make it, and the drift checks in Part 3 then need a matching record.

### Check your result

Both commands exit 0 and the test prints `50 passed`.

### If it fails

- **The test names a workflow in neither set.** Add it to `REQUIRED_WORKFLOWS`
  or to `REPORT_ONLY_WORKFLOWS` with a reason.
- **The test says a required workflow reads a model credential.** Move the model
  call to a report-only workflow. A model outage must never hold a merge.
- **The "Verify dispatch closure against base" job is red on a PR that edits
  gate scripts.** That is the check working as designed. It is report-only and
  lists the closure files the PR itself edited (issue #7024).

## Part 3: Ruleset drift detection

**Outcome:** both drift checks exit 0 against the live ruleset, and you know what
to do when one opens an alert issue.

Two scheduled workflows compare the live ruleset with the state the repository
records. Each opens an issue when they disagree. The full response procedure is
in the [Ruleset drift alert runbook](../runbooks/ruleset-drift-alert.md). Read it
now, because you will need it at a bad time.

| Workflow | Program | Alert issue title |
|---|---|---|
| `check-ruleset-drift.yml` | `scripts/validation/check_ruleset_params_drift.py --alert` | Ruleset Parameter Drift Detected |
| `ruleset-context-drift.yml` | `scripts/ci/ruleset_context_drift.py --alert` | Ruleset Required Context Drift Detected |

The parameter check compares both ways (issue #5757). A live parameter with no
record is drift. It also compares `enforcement` and `bypass_actors`, so a new
bypass actor shows up. Issue #7057 added `--alert`.

Run both checks. Without `--alert` they print and file nothing:

```bash
uv run --frozen python scripts/validation/check_ruleset_params_drift.py
echo "exit=$?"
```

```text
OK: all recorded ruleset parameters match live values.
exit=0
```

```bash
PYTHONPATH=. uv run --frozen python scripts/ci/ruleset_context_drift.py
echo "exit=$?"
```

```text
Compared 9 live contexts with 9 pinned contexts.
No required-context drift detected.
exit=0
```

### Check your result

Both exits are 0. The exit codes follow ADR-035: 0 clean, 1 drift, 2 local
configuration error, 3 GitHub API failure, 4 authentication failure.

### If it fails

- **Exit 1.** The ruleset and the record differ. Decide whether someone changed
  the ruleset on purpose. Only you or another admin makes that call. Do not edit
  `scripts/validation/ruleset_params_baseline.json` or `REQUIRED_CONTEXTS` until
  the owner confirms. The runbook has both branches.
- **Exit 3 or 4.** This is a tooling or token problem, not drift. Read the log
  and fix `gh` auth before you touch the ruleset.
- **A hidden `bypass_actors`.** The Actions token cannot read it, so the
  scheduled check logs that it skipped the comparison. Run the check with an
  admin token to compare it.
- **GitHub adds a ruleset field.** The check goes red until the baseline records
  it. This is deliberate (issue #5757).

Treat an unexplained new bypass actor or a weakened rule as a security event.
Tell the owner the same day.

## Part 4: The promotion gate and the tarball digest

**Outcome:** you run the gate locally in advisory mode, read a `WOULD BLOCK`
verdict, and verify a digest match and a mismatch.

An npm publish passes through the promotion gate (ADR-113, issues #6109 and
#6135). The gate reads evidence files, binds each one to the candidate commit and
the tarball digest, and sorts every finding into one of four classes:
remediated, accepted, expired, or unresolved. Evidence that names another commit
or digest counts as missing.

`publish.yml` builds the tarball once, hashes it, and calls the gate with that
digest. The publish job checks the digest again right before `npm publish`, and
it never rebuilds. A real publish runs the gate in enforcing mode. A dry run
runs it in advisory mode.

### Run the gate by hand

An empty evidence directory stands in for a candidate with no evidence:

```bash
EVIDENCE=$(mktemp -d)
uv run --frozen python scripts/validation/promotion_gate.py \
  --evidence-dir "$EVIDENCE" \
  --candidate-sha "$(git rev-parse HEAD)" \
  --output "$EVIDENCE/manifest.json" \
  --mode advisory
echo "exit=$?"
```

```text
promotion gate: WOULD BLOCK (advisory) state=UNKNOWN accepted=0 expired=0 remediated=0 unresolved=9
exit=0
```

Advisory mode prints `WOULD BLOCK` and exits 0. Read the manifest, not the exit
code. Enforcing mode (`--mode enforcing`) exits 1 on a block. It also refuses to
run without `--ancestor-of` and exits 2.

Nine unresolved findings appear because a local run has no evidence from CI. The
manifest shows `"enforced": false` and `"verdict": "block"`.

The repository has one code owner, so the gate accepts no exception record
(ADR-113 decision 7). Do not add an entry to
`.agents/governance/promotion-exceptions.json` to get past a block.

### Check a tarball digest

```bash
DEMO="$EVIDENCE/demo.tgz"
printf 'hello' > "$DEMO"
python3 scripts/validation/tarball_digest.py compute --file "$DEMO"
```

```text
tarball digest: 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
```

```bash
python3 scripts/validation/tarball_digest.py verify \
  --expected 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824 \
  --file "$DEMO"
echo "exit=$?"
```

```text
[PASS] tarball digest: 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824 matches the bound digest
exit=0
```

Change the file and verify again:

```bash
printf 'x' >> "$DEMO"
python3 scripts/validation/tarball_digest.py verify \
  --expected 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824 \
  --file "$DEMO"
echo "exit=$?"
```

```text
[FAIL] tarball digest: 1a6bba431fb9347e697f27558c7f712a13897c95fcda1e50b853a9785d732d37 does not match the bound digest
exit=1
```

The first `verify` passes. The second fails and prints on stderr. That is the
check the publish job runs on the real tarball.

### Check your result

You saw `WOULD BLOCK` with exit 0, then `[PASS]` with exit 0, then `[FAIL]` with
exit 1.

### If it fails

The [npm publish or promotion gate failure runbook](../runbooks/publish-failure.md)
covers every failed job. Two points to remember:

- A red "Resolve Publish Route" run after a tag push is expected. The `v*` tag
  route is dormant until the owner creates the tag ruleset (issue #5636). Run the
  workflow by dispatch from the default branch.
- If "Attach manifest to release" fails, the publish already succeeded. Check npm
  and do not publish again.

## Part 5: Cut a release

**Outcome:** a dry run of `npm Publish` is green, and you have a release-notes
draft that follows the style guide.

Read [RELEASING.md](../../RELEASING.md) first. It owns the one-time setup (npm
scope link, 2FA, the `npm` environment, OIDC) and the standard publish steps.

### Publish the package

1. Update the version in `packages/ai-agents-cli/package.json` and merge it to
   the default branch.
2. Optional: create the release `vX.Y.Z` on that commit, so the gate can attach
   its manifest.
3. Open Actions > npm Publish > Run workflow on the default branch. Leave
   `dry-run` at `true` and run it first.
4. Read the "Promotion Gate" job and its `promotion-manifest` artifact. A
   `WOULD BLOCK` line means the real run will fail.
5. When the dry run is clean, run it again with `dry-run: false`.

Then check what the registry holds:

```bash
npm view @rjmurillo/ai-agents versions
echo "exit=$?"
```

```text
npm error code E404
npm error 404 Not Found - GET https://registry.npmjs.org/@rjmurillo%2fai-agents - Not found
...
exit=1
```

The package had not been published when this page was written (2026-11-10).
After the first publish this command lists the versions. Use
`npm view @rjmurillo/ai-agents@X.Y.Z version` to check one exact version.

### Write the release notes

Follow [docs/release-notes-styleguide.md](../release-notes-styleguide.md). The
steps are in RELEASING.md under "Writing release notes". Start from the generated
draft, then write the narrative by hand.

The opening paragraph needs a commit count. Get it from two tags:

```bash
git rev-list --count v0.5.0..v0.6.0
```

```text
376
```

Replace the tags with the previous release and the new one. The style guide
asks for the title pattern `AI Agents vX.Y.Z: Tagline Emoji Emoji`.

### Check your result

The dry-run workflow is green, `npm view` answers as you expect, and the draft
release has a title, an opening paragraph with both counts, and an "All Changes"
section.

### If it fails

Use the table in the
[publish failure runbook](../runbooks/publish-failure.md). If a bad version
already reached npm, follow
[Bad plugin or package release](../runbooks/bad-release-rollback.md).

## Part 6: Renovate automerge limits for workflow bumps

**Outcome:** you can explain which dependency bumps wait for your review, and you
have run the tests that pin the rule.

Issue #7129 closed a gap. A bump to a workflow that holds secrets used to merge
with no human approval. Now neither Renovate nor Dependabot merges a PR that
touches `.github/workflows/**` or `.github/cli-smoke/**`:

- **Renovate:** a `packageRules` entry in `renovate.json` sets `automerge: false`
  for those paths. It sits after every rule that turns automerge on, because
  Renovate applies rules in order. A second entry keeps the weekly lock-file
  refresh of `.github/cli-smoke/**` on its own branch, so the repository-root
  refresh can still automerge.
- **Dependabot:** `dependabot-approve-and-auto-merge.yml` reads the PR file list
  and skips the merge for both directories. A failed read fails the step.

The CLI smoke installs each CLI with `npm ci` from a committed lockfile under
`.github/cli-smoke/<cli>/`. Renovate maintains each pair.

Run the tests that pin it:

```bash
uv run --frozen pytest -n0 -q tests/test_renovate_config.py \
  tests/test_renovate_workflow_exemption.py tests/test_dependabot_workflow_guard.py
```

```text
============================== 30 passed in 0.56s ==============================
```

When one of these PRs opens, review the diff and merge it yourself. The tool will
not.

### Check your result

The tests print `30 passed`.

### If it fails

- **A workflow bump merged on its own.** Check the rule order in `renovate.json`.
  An automerge rule placed after the exemption would re-enable it.
- **A new directory needs the same limit.** Add it to the Renovate globs and to
  the Dependabot step. A drift test ties the two lists together.

## Next

- [Runbooks index](../runbooks/README.md): every incident procedure in one place.
- [docs/COST-GOVERNANCE.md](../COST-GOVERNANCE.md): what the gated workflows cost.
- [ADR-114](../../.project-toolkit/architecture/ADR-114-agent-workflows-approval-and-non-blocking.md),
  [ADR-113](../../.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md),
  and [ADR-101](../../.project-toolkit/architecture/ADR-101-enforcement-planes.md):
  the decisions behind these controls.
