# Run the CI and release controls you own

## Goal

You will run each control a maintainer operates and read its verdict yourself. This page is for maintainers. By the end you can:

- Name the workflows that wait for your approval, and show that they never hold a merge.
- Say whether a PR workflow is required or only reports.
- Run both ruleset drift checks and read their exit codes.
- Run the promotion gate and the tarball digest check, and read a pass and a fail.
- Cut a release and write its notes.
- Name the dependency bumps Renovate and Dependabot will not merge for you.

You know it worked when every command below exits as the page says. The last section lists each check.

## Before you start

- A clone of `rjmurillo/ai-agents` on `main`, set up with the one-command [Setup Steps](../../CONTRIBUTING.md#setup-steps).
- `gh` signed in with read access. The drift checks read the live ruleset through the GitHub API.
- Admin rights, only if you want to approve a run or change a setting. A read-only clone runs every command here.
- A shell in the repository root.

Do not skip hooks with `--no-verify` and do not force-push. The [runbook conventions](../runbooks/README.md#conventions) apply to every step.

## Steps

### Part 1: Agent workflows wait for you and never block a merge

[ADR-114](../../.project-toolkit/architecture/ADR-114-agent-workflows-approval-and-non-blocking.md) sets two rules for every workflow that calls a model:

1. The job runs in a provider environment with a required reviewer: `agent-claude`, `agent-copilot`, `agent-codex`, or `agent-droid`. The run waits for your click before it spends anything.
2. The check it posts is advisory. A failed, skipped, cancelled, or waiting result never holds a merge.

The plugin CLI smoke used to be the one exception. The owner made it advisory on 2026-11-05, so there is no exception now. Older issue text (#6131, #6215, #6197) predates that change. [docs/COST-GOVERNANCE.md](../COST-GOVERNANCE.md#agent-workflows-approval-gated-advisory) lists the gated workflows and the secret each environment holds.

1. Approve a run. Open it in the Actions tab, where a gated run shows "Waiting". Read the event that started it, because the approval screen shows the job and not the comment or PR text that drives the agent. Choose **Review deployments**, tick the environments, and approve or reject. One review can approve both `agent-claude` and `agent-copilot`. Each new push cancels the older run, including legs still waiting.

2. Confirm that agents cannot approve for you. You are the only reviewer, and self-review is allowed, so any process that holds your token could approve its own run. Claude Code denies the call:

   ```bash
   grep -n pending_deployments templates/hooks/settings.tmpl
   ```

   ```text
   70:            "Bash(gh api *pending_deployments*)"
   ```

   The rule slows an agent down. It does not stop `curl` or the GraphQL mutation (ADR-112, gap G11). Approve from the browser and never hand an agent your token.

3. List the advisory checks. The readiness check reads this list from `origin/main`, so a PR cannot add its own entry:

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

   Only workflows that run on `pull_request` are listed. Scheduled and dispatch agent workflows post no check on a PR. A check the branch ruleset requires stays blocking even if its workflow is listed (ADR-114 decision 7).

4. Prove the exemption:

   ```bash
   uv run pytest -n0 -q tests/test_pr_merge_ready_advisory_agent_checks.py
   ```

   ```text
   ============================== 83 passed in 9.95s ==============================
   ```

5. Read a live verdict on any open PR. Add `--include-non-required` so waiting checks count too:

   ```bash
   uv run python .claude/skills/github/scripts/pr/test_pr_merge_ready.py \
     --pull-request <number> --include-non-required
   ```

   Look at `UndisposedNonRequiredFailures` and `PendingNonRequiredChecks` in the JSON. A listed agent check never appears there.

Watch for these four failures:

- **A gated run never asks for approval.** The environment may be missing or unprotected. GitHub creates a missing environment with no reviewers on first use, and the run then starts unapproved (ADR-114 decision 12). Open Settings > Environments and confirm each `agent-*` environment lists a required reviewer. Only an admin can see this.
- **You deleted an environment and it came back.** A waiting run recreated it with no protection (ADR-114 decision 11 item 6). Check every waiting run before you delete an environment.
- **A new agent workflow blocks merges.** It is missing from `advisory_agent_workflows`. Add it in a PR. The list is read from `main`, so the change takes effect after the merge.
- **A Claude leg fails with "Credit balance is too low".** This is accepted (ADR-114 decision 11 item 9). The check is advisory, so the PR can merge.

### Part 2: Required versus report-only workflows

Issue #7024 made the choice explicit. Every workflow that triggers on `pull_request`, `pull_request_target`, or `merge_group` sits in one of two sets in `scripts/ci/ruleset_required_contexts.py`:

- `REQUIRED_WORKFLOWS` holds the workflows that produce a context the branch ruleset pins.
- `REPORT_ONLY_WORKFLOWS` holds every other one, each with a written reason.

1. Count them:

   ```bash
   PYTHONPATH=. uv run python -c "
   from scripts.ci.ruleset_required_contexts import REQUIRED_CONTEXTS, REQUIRED_WORKFLOWS, REPORT_ONLY_WORKFLOWS
   print(len(REQUIRED_CONTEXTS), len(REQUIRED_WORKFLOWS), len(REPORT_ONLY_WORKFLOWS))
   print(REPORT_ONLY_WORKFLOWS['plugin-cli-smoke.yml'])
   "
   ```

   ```text
   9 7 37
   model-driven: spends provider quota or waits on an agent-<cli> environment approval, so it must never gate a merge
   ```

   The first line reads: 9 pinned contexts, 7 required workflows, 37 report-only workflows. These counts describe `main` at `b959011e3` (2026-11-10).

2. Run the classification test:

   ```bash
   uv run pytest -n0 -q tests/ci/test_pr_workflow_classification.py
   ```

   ```text
   ============================== 50 passed in 2.80s ==============================
   ```

The test fails when a PR workflow is in neither set. It also fails when a required workflow reads a model credential. Add a PR workflow and you must pick a set. Promoting a report-only workflow to required is a ruleset change. Only an admin can make it, and the drift checks in Part 3 then need a matching record.

If the "Verify dispatch closure against base" job is red on a PR that edits gate scripts, the check is working as designed. It is report-only and lists the closure files that PR edited (issue #7024).

### Part 3: Ruleset drift detection

Two scheduled workflows compare the live ruleset with the state the repository records. Each opens an issue when they disagree. The [Ruleset drift alert runbook](../runbooks/ruleset-drift-alert.md) owns the response procedure. Read it now, because you will need it at a bad time.

| Workflow | Program | Alert issue title |
|---|---|---|
| `check-ruleset-drift.yml` | `scripts/validation/check_ruleset_params_drift.py --alert` | Ruleset Parameter Drift Detected |
| `ruleset-context-drift.yml` | `scripts/ci/ruleset_context_drift.py --alert` | Ruleset Required Context Drift Detected |

The parameter check compares both ways (issue #5757). A live parameter with no record is drift. It also compares `enforcement` and `bypass_actors`, so a new bypass actor shows up. Issue #7057 added `--alert`.

1. Run the parameter check. Without `--alert` it files nothing:

   ```bash
   uv run python scripts/validation/check_ruleset_params_drift.py
   echo "exit=$?"
   ```

   ```text
   OK: all recorded ruleset parameters match live values.
   exit=0
   ```

2. Run the required-context check:

   ```bash
   PYTHONPATH=. uv run python scripts/ci/ruleset_context_drift.py
   echo "exit=$?"
   ```

   ```text
   Compared 9 live contexts with 9 pinned contexts.
   No required-context drift detected.
   exit=0
   ```

Exit codes follow ADR-035: 0 clean, 1 drift, 2 local configuration error, 3 GitHub API failure, 4 authentication failure.

Watch for these failures:

- **Exit 1.** The ruleset and the record differ. Decide whether someone changed the ruleset on purpose. Only you or another admin makes that call. Do not edit `scripts/validation/ruleset_params_baseline.json` or `REQUIRED_CONTEXTS` until the owner confirms. The runbook has both branches.
- **Exit 3 or 4.** This is a tooling or token problem, not drift. Read the log and fix `gh` auth before you touch the ruleset.
- **A hidden `bypass_actors`.** The Actions token cannot read it, so the scheduled check logs that it skipped the comparison. Run the check with an admin token to compare it.
- **GitHub adds a ruleset field.** The check goes red until the baseline records it. This is deliberate (issue #5757).

Treat an unexplained new bypass actor or a weakened rule as a security event. Tell the owner the same day.

### Part 4: The promotion gate and the tarball digest

An npm publish passes through the promotion gate (ADR-113, issues #6109 and #6135). The gate reads evidence files, binds each one to the candidate commit and the tarball digest, and sorts every finding into one of four classes: remediated, accepted, expired, or unresolved. Evidence that names another commit or digest counts as missing.

`publish.yml` builds the tarball once, hashes it, and calls the gate with that digest. The publish job checks the digest again right before `npm publish`, and it never rebuilds. A real publish runs the gate in enforcing mode. A dry run runs it in advisory mode.

1. Run the gate by hand. An empty evidence directory stands in for a candidate with no evidence:

   ```bash
   EVIDENCE=$(mktemp -d)
   uv run python scripts/validation/promotion_gate.py \
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

   Advisory mode prints `WOULD BLOCK` and exits 0, so read the manifest and not the exit code. It shows `"enforced": false` and `"verdict": "block"`. Nine findings stay unresolved because a local run has no CI evidence. Enforcing mode (`--mode enforcing`) exits 1 on a block. It also refuses to run without `--ancestor-of` and exits 2.

2. Compute a digest:

   ```bash
   DEMO="$EVIDENCE/demo.tgz"
   printf 'hello' > "$DEMO"
   uv run python scripts/validation/tarball_digest.py compute --file "$DEMO"
   ```

   ```text
   tarball digest: 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824
   ```

3. Verify it:

   ```bash
   uv run python scripts/validation/tarball_digest.py verify \
     --expected 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824 \
     --file "$DEMO"
   echo "exit=$?"
   ```

   ```text
   [PASS] tarball digest: 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824 matches the bound digest
   exit=0
   ```

4. Change the file and verify again:

   ```bash
   printf 'x' >> "$DEMO"
   uv run python scripts/validation/tarball_digest.py verify \
     --expected 2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824 \
     --file "$DEMO"
   echo "exit=$?"
   ```

   ```text
   [FAIL] tarball digest: 1a6bba431fb9347e697f27558c7f712a13897c95fcda1e50b853a9785d732d37 does not match the bound digest
   exit=1
   ```

   The fail line prints on stderr. This is the check the publish job runs on the real tarball.

The repository has one code owner, so the gate accepts no exception record (ADR-113 decision 7). Do not add an entry to `.agents/governance/promotion-exceptions.json` to get past a block.

The [publish failure runbook](../runbooks/publish-failure.md) covers every failed job. Two points matter most:

- A red "Resolve Publish Route" run after a tag push is expected. The `v*` tag route is dormant until the owner creates the tag ruleset (issue #5636). Run the workflow by dispatch from the default branch.
- If "Attach manifest to release" fails, the publish already succeeded. Check npm and do not publish again.

### Part 5: Cut a release

Read [RELEASING.md](../../RELEASING.md) first. It owns the one-time setup (npm scope link, 2FA, the `npm` environment, OIDC) and the standard publish steps.

1. Update the version in `packages/ai-agents-cli/package.json` and merge it to the default branch.
2. Optional: create the release `vX.Y.Z` on that commit, so the gate can attach its manifest.
3. Open Actions > npm Publish > Run workflow on the default branch. Leave `dry-run` at `true` and run it first.
4. Read the "Promotion Gate" job and its `promotion-manifest` artifact. A `WOULD BLOCK` line means the real run will fail.
5. When the dry run is clean, run it again with `dry-run: false`.
6. Check what the registry holds:

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

   The package had not been published on 2026-11-10, so this is the answer today. After the first publish the command lists the versions. Use `npm view @rjmurillo/ai-agents@X.Y.Z version` to check one exact version.

7. Write the release notes. Follow [docs/release-notes-styleguide.md](../release-notes-styleguide.md) and the "Writing release notes" steps in RELEASING.md. Start from the generated draft, then write the narrative by hand. The title pattern is `AI Agents vX.Y.Z: Tagline Emoji Emoji`.

8. Get the commit count for the opening paragraph from two tags:

   ```bash
   git rev-list --count v0.5.0..v0.6.0
   ```

   ```text
   376
   ```

   Swap in the previous release and the new one.

If a bad version already reached npm, follow [Bad plugin or package release](../runbooks/bad-release-rollback.md).

### Part 6: Renovate automerge limits for workflow bumps

Issue #7129 closed a gap. A bump to a workflow that holds secrets used to merge with no human approval. Now neither Renovate nor Dependabot merges a PR that touches `.github/workflows/**` or `.github/cli-smoke/**`:

- **Renovate.** A `packageRules` entry in `renovate.json` sets `automerge: false` for those paths. It sits after every rule that turns automerge on, because Renovate applies rules in order. A second entry keeps the weekly lock-file refresh of `.github/cli-smoke/**` on its own branch, so the repository-root refresh can still automerge.
- **Dependabot.** `dependabot-approve-and-auto-merge.yml` reads the PR file list and skips the merge for both directories. A failed read fails the step.

The CLI smoke installs each CLI with `npm ci` from a committed lockfile under `.github/cli-smoke/<cli>/`. Renovate maintains each pair.

1. Run the tests that pin the rule:

   ```bash
   uv run pytest -n0 -q tests/test_renovate_config.py \
     tests/test_renovate_workflow_exemption.py tests/test_dependabot_workflow_guard.py
   ```

   ```text
   ============================== 30 passed in 0.56s ==============================
   ```

2. When one of these PRs opens, review the diff and merge it yourself. The tool will not.

Watch for these failures:

- **A workflow bump merged on its own.** Check the rule order in `renovate.json`. An automerge rule placed after the exemption would turn it back on.
- **A new directory needs the same limit.** Add it to the Renovate globs and to the Dependabot step. A drift test ties the two lists together.

## Check your result

Every row must match. If one does not, start at the source in the last column.

| Part | You should see | Look here first |
|---|---|---|
| 1 | `83 passed` for the advisory test | `.claude/skills/pr-review/pr-review-config.yaml`, ADR-114 |
| 2 | `9 7 37` and `50 passed` | `scripts/ci/ruleset_required_contexts.py` |
| 3 | Both checks exit 0 | [Ruleset drift alert runbook](../runbooks/ruleset-drift-alert.md) |
| 4 | `WOULD BLOCK` with exit 0, then `[PASS]` exit 0, then `[FAIL]` exit 1 | [Publish failure runbook](../runbooks/publish-failure.md) |
| 5 | `E404` with exit 1 until the first publish | [RELEASING.md](../../RELEASING.md) |
| 6 | `30 passed` | `renovate.json` |

## Next

Read the [runbooks index](../runbooks/README.md) for every incident procedure, and return to the [training index](README.md) for the next page.

Reference sources this page relies on:

- [ADR-114](../../.project-toolkit/architecture/ADR-114-agent-workflows-approval-and-non-blocking.md): agent approval and non-blocking checks.
- [ADR-113](../../.project-toolkit/architecture/ADR-113-promotion-gate-evidence-and-exceptions.md): the promotion gate.
- [ADR-101](../../.project-toolkit/architecture/ADR-101-enforcement-planes.md): enforcement planes.
- [docs/COST-GOVERNANCE.md](../COST-GOVERNANCE.md): what the gated workflows cost.
- [docs/release-notes-styleguide.md](../release-notes-styleguide.md): release notes voice and shape.
