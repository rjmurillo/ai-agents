# ADR-101 Requirement 2: Publisher App Research Spike

Issue #5245, the open half of AC1. Owner decision D22: spike first, code only if the spike supports it.

Evidence levels used below: MEASURED (run in this session, command given), READ (file or API read in this session), DOCS (vendor documentation fetched in this session), INFERRED (reasoned, not run).

## Verdict

**Split verdict. Build nothing further until the owner decides.**

1. A dedicated GitHub App meets the identity half of requirement 2. A check run published with an installation token carries the App's id. A ruleset can pin that id. Neither a head-defined workflow nor an exfiltrated `BOT_PAT` can mint it. The plan supports this: the live ruleset already stores `integration_id` per required context (READ, see Evidence 3).
2. No signing scheme closes the residual that ADR-101 says only signed execution evidence closes. That covers an App-authored check run, an artifact attestation, and direct Sigstore. A signature authenticates the signer. The signer learns the test result from a process the candidate controls. So the signed statement is exactly as forgeable as the unsigned one. This is measured below, including a third forgery the ADR does not list.
3. The stop clause in D22 reads "cannot be met by a GitHub App on this plan". Read literally, point 2 triggers it. Read as a plan-availability test, point 1 passes it. I read it literally and stopped. The owner can overrule that reading, and "If the owner says go" below states exactly what would be built.
4. ADR-101 needs a text change, reported here and not made: its claim that signed evidence "is now the only option that closes this requirement" does not hold. Changing it needs a debate log under `adr-review`.

## What requirement 2 asks for, quoted

Source: `.project-toolkit/architecture/ADR-101-enforcement-planes.md` at commit 3f27efd8d. Line numbers are that file's.

Line 195, the research obligation:

> The one alternative is execution evidence authenticated independently of the head, for example a signed attestation from a runner identity the pull request cannot assume, and an implementer taking that path owes a statement of whose key signs it and what the base-owned job verifies before believing it.

Line 201, what may cross between the two jobs:

> What crosses between them is the execution job's conclusion, not its output.

Line 201, the artifact rule:

> Artifacts, logs, and result files are P0 content the candidate can edit, and the publication job must not read any of them

Line 215, the claim this spike tests:

> Anything stronger, that tests were collected and executed, needs evidence signed by an identity the pull request cannot assume, which is the third option and is now the only option that closes this requirement.

Line 221, where the determination is said to live:

> Under signed execution evidence that determination is made by the signing identity and carried in the signature.

Line 430, the entry condition for a phase:

> requirement 2 enters a phase only once a design names whose key signs the execution evidence and what the base-owned job verifies before believing it.

The three questions this spike must answer: whose key signs, what the verifier believes, and whether that belief is true of the execution.

## Evidence

### 1. Forged execution is cheap and survives every floor the ADR lists

Method (MEASURED 2026-09-30): two failing tests, one candidate-authored `conftest.py`, `python3 -m pytest -q -p no:cacheprovider --junitxml=j.xml`.

```python
# test_real.py
def test_a(): assert 1 == 2
def test_b(): assert False

# conftest.py (candidate-authored)
import pytest
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == "call" and rep.failed:
        rep.outcome = "passed"
        rep.longrepr = None
```

Result with the conftest: `2 passed in 0.04s`, exit 0, the JUnit XML pytest wrote reads `tests="2" errors="0" failures="0" skipped="0"`, with both `testcase` elements clean. Result with the conftest removed: `2 failed in 0.02s`.

This is a third forgery. ADR-101 lists two: `os._exit(0)` from a session hook (line 207, measured at 213) and a conftest that marks every item skipped (line 205). The ADR answers the second with an "executed-and-not-skipped floor". This third one defeats that floor: every test is collected, executed, and reported passed. A supervisor that checks counts, skips, and the JUnit file reads a clean run.

### 2. Where each signer sits and what it can observe

| Signer position | Who signs | What it observes | Can the candidate forge the input? |
|---|---|---|---|
| Publication job (separate runner) | App installation token, check run | `needs.execute.result` only, which is the execution job's exit status | Yes. Exit 0 is candidate-authored (Evidence 1, first forgery, ADR line 213). |
| Execution job, in-process | Workflow OIDC identity via `actions/attest` | Whatever the harness wrote | Yes, and worse: the OIDC request variables are runner environment, so the candidate can request the token itself (INFERRED from the documented `ACTIONS_ID_TOKEN_REQUEST_URL` mechanism; the design would grant `id-token` to no execution job). |
| Execution job, supervisor outside a container | Supervisor plus OIDC after the container exits | Container exit status, files the candidate wrote | Yes. Same input, one hop later. ADR line 211 already says the sandbox authenticates termination, not collection. |
| Trusted observer that traces the candidate from outside its trust domain | None exists on GitHub-hosted runners | Would have to observe test bodies running without trusting the process that runs them | Not buildable here. Any base-owned reader of a Python process's reports reads what in-process code may rewrite. |

Every row ends in the same place. The signature is real. What it signs is not independent of the candidate.

### 3. The plan supports pinning by publisher

READ 2026-09-30, `gh api repos/rjmurillo/ai-agents/rulesets/11104075`. Every required context carries an `integration_id`. All nine are `15368`, the GitHub Actions app. So the field exists and is honored on this repository, which is public and user-owned (`gh api repos/rjmurillo/ai-agents`: `visibility: public`, owner type `User`). Pinning to a different id is a data change, not a new capability.

Docs (DOCS, `docs.github.com/en/rest/checks/runs`): "To create a check run, you must use a GitHub App." The token a `GITHUB_TOKEN` carries belongs to the Actions app, id 15368. So a check run from any workflow's own token reads as `15368` and is indistinguishable by id from every other Actions check. A separate App is the only way to get a distinct id.

### 4. The pinned action versions

READ 2026-09-30 through `gh api`:

- `actions/create-github-app-token` v3.2.0 is commit `bcd2ba49218906704ab6c1aa796996da409d3eb1`. Inputs include `client-id`, `app-id`, `private-key`, `owner`, `repositories`, `permission-checks`, `permission-contents`, `permission-pull-requests`, and `skip-token-revoke`. The token is revoked at job end unless `skip-token-revoke` is set.
- `actions/attest` v4.2.2 is commit `1e69f48acb82d1966a394da916b4c1698aa569d6`.
- `gh attestation verify` offers `--signer-workflow`, `--signer-digest`, `--source-ref`, `--source-digest`, `--predicate-type`, and `--deny-self-hosted-runners`.

## Mechanism comparison against the requirement text

| Mechanism | Whose key signs | What the verifier checks | Closes identity (conjunct 2) | Closes "tests executed" |
|---|---|---|---|---|
| App-authored check run, App pinned by `integration_id` in the ruleset | The App, key held in an environment-scoped secret | GitHub matches the context name and `integration_id` at merge time. A verifier script can also read the check run's `app.id`, `head_sha`, `name`, and `external_id`. | Yes | No. It carries `needs.execute.result`. |
| `actions/attest` artifact attestation, Sigstore public good | The workflow's OIDC identity, cert names the workflow path and ref | `gh attestation verify --signer-workflow <base workflow> --source-ref refs/heads/main --signer-digest <base sha>` | Yes, for "this base-owned workflow signed it" | No. It names the workflow, not the facts the candidate wrote. |
| Direct Sigstore (cosign keyless) | Same OIDC identity | Same claims, checked by the verifier | Same as above | No. |
| Container or VM supervisor, no signature | None | Exit status from the runtime | No | No. ADR line 215. |

Only the first row also gives GitHub something to enforce at merge. The attestation rows verify after the fact and need a verifier that a required context would then have to call, which makes that verifier a P1 job holding the same App pin anyway. They add a second signing path without adding a second fact.

## What the App does buy

These are the pieces ADR-101 already assigns to Phase 0, and they hold even with the residual open:

- Publication under an identity the head cannot assume: closes conjunct 2.
- A ruleset entry recording that identity: closes conjunct 3, once the owner writes it.
- The execution and publication split with `if: ${{ always() }}`: removes the no-offending-change deadlock and the cancelled-run-goes-green case.
- SHA binding: the publication job names `workflow_run.head_sha` or the `pull_request_target` head SHA and refuses to publish when the pull request's current head or base differ.

What it leaves open, stated in the ADR's own vocabulary: the "candidate forges the exit status" residual and the "executed-and-not-skipped" case. ADR line 203 already accepts "a candidate writes tests that pass and assert nothing". Evidence 1 shows the three forgeries above differ from that accepted residual in effort, not in kind: each needs the candidate to author code that runs inside the test process, and each yields a green context with no real verification. A reviewer who reads the diff sees the conftest. A signature changes nothing about what that reviewer can or cannot see.

## Proposed ADR-101 text change (reported, not made)

1. Line 215 and line 219: replace "is now the only option that closes this requirement" with a statement that no mechanism authenticates in-process test results against candidate-authored code, and move the forged-exit, collected-count and skipped-corpus cases into the accepted residuals beside line 203, citing Evidence 1.
2. Line 430: the research item resolves to "App-authored check run, `integration_id` pinned; execution authenticity bounded as above". That lets requirement 2 enter a phase.
3. Lines 143 and 229 say the ruleset "pins context names alone today". The live ruleset records `integration_id: 15368` on every context (READ). The statement that nothing separates publishers stays true, because every pin is the Actions app.
4. Line 100 says the repository has "exactly one environment-gated job". The repository now lists three environments, `bot-secrets`, `copilot`, `vendor-provenance` (READ, `gh api repos/rjmurillo/ai-agents/environments`), and none carries a deployment branch policy.
5. Line 187 names a `workflow_run` trigger. `pull_request_target` also runs the base ref's workflow definition and is the shape `enforcement-closure.yml` already uses. Say which is meant.

## Minimal App permissions

Repository permissions only. No account, organization, or webhook scope.

| Permission | Level | Why |
|---|---|---|
| Checks | Read and write | Create and update the check run. Nothing else needs write. |
| Pull requests | Read | Compare the pull request's current head and base to the SHAs the run captured (CWE-367 guard, ADR line 235). |
| Contents | Read | Resolve the diff and base SHA by immutable SHA through the compare API. |
| Metadata | Read | Mandatory for every App. |

No `statuses`, `administration`, `actions`, `secrets`, `workflows`, `members` or `environments` permission. An App without `administration` cannot edit a ruleset, so a stolen key cannot touch P2. Subscribe to no webhook events.

Request the same three at token time with `permission-checks: write`, `permission-pull-requests: read`, `permission-contents: read` on `create-github-app-token`. The token is then narrower than the installation, which limits a leaked step output.

## How the base-owned job gets a token

1. The publication job runs under `pull_request_target` (or `workflow_run`), so the workflow definition comes from the default branch. The pull request cannot edit the job that reads the key.
2. The job declares `environment: adr101-publisher`. That environment restricts deployment branches to `main`. A head-defined workflow on another branch that names the environment is refused the secret. This is the containment ADR-101 describes for repository-level secrets, applied to this one.
3. A step runs `actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0` with the App id from an environment variable and the private key from the environment secret.
4. The job checks out the base ref only. It never checks out, imports, or reads an artifact from the head. It fetches the diff from the API by SHA.
5. No job that runs candidate code names the environment, holds the key, or holds `checks: write`. The execution job holds `contents: read` and nothing else.

INFERRED, to be probed after the App exists: that `pull_request_target` runs on `refs/heads/main` for the environment's branch policy, so the policy admits it. The owner checklist includes the probe.

## Threat model notes

| Threat | Path | Effect | Control | Residual |
|---|---|---|---|---|
| Private key theft from a head-defined workflow | Branch pushes `on: push`, names the environment | Attacker mints check runs under the App | Environment secret with deployment branches limited to `main`; no repository-level copy | A workflow merged to `main` that reads it. CODEOWNERS and review on `.github/workflows/` (Phase 0) |
| Token theft inside the publication job | A step in that job leaks `GITHUB_OUTPUT` or logs | One-hour token with `checks: write` | Token scoped to three permissions, revoked at job end, job runs no candidate code | Logs are public on a public repo: mask, never echo |
| Forged execution evidence | Candidate conftest or `os._exit` | Green context, no real verification | None available (Evidence 1, 2) | Accepted. Needs the ADR text change above |
| Publisher publishes for a stale revision | Branch moved during the run | Success against a different tree | Compare head and base SHAs immediately before publishing; abort without publishing on mismatch (ADR line 235) | Window between compare and publish, accepted by the ADR as CWE-367 |
| Silent skip | Flag off, secrets missing, execute skipped | A missing context read as green | `always()`; typed outcomes; SKIP never accepted by a blocking policy | None known |
| App key reused for a second purpose | Later features add permissions | A bigger blast radius | One App, one permission list, drift check on permissions | Needs a baseline entry in Phase 0 |
| Fork pull request | Fork head SHA | App may be unable to attach a check run | ADR line 322 already marks this as a probe, not an assumption | UNKNOWN until probed (checklist step 12) |

## Owner checklist

Only the repository owner can do these. Do them in order. Nothing here touches a ruleset.

1. Open `https://github.com/settings/apps/new` while signed in as `rjmurillo`.
2. GitHub App name: `rjmurillo-adr101-publisher`. If taken, append a short suffix and use the same name everywhere below.
3. Homepage URL: `https://github.com/rjmurillo/ai-agents`.
4. Identifying and authorizing users: leave the callback URL empty. Clear "Expire user authorization tokens" and "Request user authorization (OAuth) during installation".
5. Webhook: clear "Active". Leave every event unchecked.
6. Repository permissions: Checks = Read and write; Contents = Read-only; Pull requests = Read-only; Metadata = Read-only. Every other permission stays "No access". Set no account permission and no organization permission.
7. Where can this GitHub App be installed: "Only on this account".
8. Create the App. Record the numeric App ID and the Client ID from the App's settings page.
9. On the App's settings page choose "Generate a private key". A `.pem` file downloads once.
10. Install the App: App settings, "Install App", account `rjmurillo`, "Only select repositories", choose `ai-agents`.
11. In `rjmurillo/ai-agents` settings, Environments, create `adr101-publisher`. Set "Deployment branches and tags" to "Selected branches and tags" and add the branch `main`. Add no required reviewers and no wait timer. Under the environment add:
    - Secret `ADR101_PUBLISHER_APP_PRIVATE_KEY`: the full contents of the `.pem` file, including the BEGIN and END lines.
    - Variable `ADR101_PUBLISHER_APP_ID`: the numeric App ID.
    Do not create either at repository or organization level. A branch-defined `on: push` workflow can read those.
12. Move the `.pem` into your password manager and delete the downloaded copy with `trash`. Do not commit it, paste it into an issue, or put it in a session file.
13. Probe the containment before anything else relies on it. Push a throwaway branch whose workflow sets `environment: adr101-publisher` and reads the secret. GitHub must refuse the deployment. If it runs, stop and tell the orchestrator.
14. Leave the repository variable `ADR101_PUBLISHER_ENABLED` unset. It stays off until the job exists and a test pull request has published one check run.
15. Do not add the new context to any ruleset yet. When the job has published on a test pull request, read its App id with `gh api repos/rjmurillo/ai-agents/commits/<sha>/check-runs --jq '.check_runs[] | {name, app: .app.id}'`, then follow the no-gap rename sequence in `.claude/rules/ci-scripts.md` MUST 22: emit the context, merge, require it with that `integration_id`, then remove any old requirement.
16. Rotation: generate a second key in App settings, replace the environment secret, run one test pull request, then delete the first key in App settings.

Names the code would read: environment `adr101-publisher`, secret `ADR101_PUBLISHER_APP_PRIVATE_KEY`, variable `ADR101_PUBLISHER_APP_ID`, repository variable `ADR101_PUBLISHER_ENABLED`.

## If the owner says go

Build, behind `ADR101_PUBLISHER_ENABLED` (default off), a base-owned workflow with these parts. It would deliver the identity, binding, and split properties above and nothing stronger, and its docstring would say so.

- A Python module under `scripts/ci/` owning all logic, returning `evidence.CheckOutcome` values: SKIP with reason `publisher.disabled` when the flag is off, BLOCKED with `auth.unavailable` when the flag is on and the App id or key is absent, FAIL when the supervisor's recorded conclusion is not success or the SHAs moved, PASS only when the check run was published for the captured head and base.
- Workflow YAML with triggers and calls only: an `execute` job on its own runner with `contents: read`, no secrets, no environment, running a base-owned harness over the candidate checked out as data; a `publish` job with `needs: execute`, `if: ${{ always() }}`, `environment: adr101-publisher`, and no candidate code.
- A verifier that reads the published check run through the API and checks `app.id`, `head_sha`, `name`, and a base-owned `external_id` digest of the captured SHAs. It rejects tampered or mismatched evidence as FAIL.
- Tests for flag off (SKIP), flag on with secrets absent (BLOCKED), a mocked valid token and evidence (PASS), and tampered evidence (FAIL).
- It would not join `scripts/ci/ruleset_required_contexts.py` or any ruleset.

An honest label on the result would read "published by the pinned App for this head and base; execution authenticity bounded by ADR-101 line 203". It must never read "verified".
