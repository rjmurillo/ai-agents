# ADR-101 Requirement 2: Publisher App Research Spike

Issue #5245, the open half of AC1. Owner decision D22: spike first, code only if the spike supports it.

Evidence levels used below: MEASURED (run in this session, command given), READ (file or API read in this session), DOCS (vendor documentation fetched in this session), INFERRED (reasoned, not run).

## Verdict

**Split verdict. Build nothing further until the owner decides.**

1. A dedicated GitHub App meets the identity half of requirement 2. A check run published with an installation token carries the App's id. A ruleset can pin that id. Neither a head-defined workflow nor an exfiltrated `BOT_PAT` can mint it. The plan supports this: the live ruleset already stores `integration_id` per required context (READ, see Evidence 3).
2. No signing scheme closes the residual that ADR-101 says only signed execution evidence closes. That covers an App-authored check run, an artifact attestation, and direct Sigstore. A signature authenticates the signer. The signer learns the test result from a process the candidate controls, and against arbitrary candidate code in that process the signed statement is as forgeable as the unsigned one. I measured one forgery this session, and it is one the ADR does not list (Evidence 1). Base-owned canary tests and `--noconftest` over a base-owned corpus raise the cost of a blanket forgery. They do not close a targeted one.
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
| Trusted observer that traces the candidate from outside its trust domain (syscall or ptrace tracing, a gVisor-style sandbox) | The observer | Syscalls and files, not which assertions ran | Not through reports. It sees behavior rather than rewritten reports, but it cannot map syscalls to "this test body ran and passed" without trusting in-process data. INFERRED, unbuilt, and not available as a GitHub-hosted feature. |
| Base-owned corpus run with `--noconftest` and a base-owned `-c` config, plus a base-owned canary test that must fail | Supervisor | Per-test outcomes from the same process | Raises cost. It removes the conftest vector, so the Evidence 1 forgery needs a test-file or product-code patch instead. A forgery that spares the canary still works. |

Every row ends in the same place for arbitrary candidate code in the test process. The signature is real. What it signs is not independent of the candidate. The two rows above this sentence are cost raisers to evaluate if the owner wants one, not closures. Hardware or VM attestation of the runner was not examined.

### 3. The plan supports pinning by publisher

As of 2026-09-30, `gh api repos/rjmurillo/ai-agents/rulesets/11104075` shows that every required context carries an `integration_id`. All nine are `15368`, the GitHub Actions app. So the field exists and is honored on this repository, which is public and user-owned (`gh api repos/rjmurillo/ai-agents`: `visibility: public`, owner type `User`). Pinning to a different id is a data change, not a new capability.

Docs (DOCS, `docs.github.com/en/rest/checks/runs`): "To create a check run, you must use a GitHub App." The ruleset pins 15368 on contexts that Actions jobs report, so checks from any workflow's own token read as 15368 and cannot be told apart by id (INFERRED from the pin field). A separate App is the only way to get a distinct id.

### 4. The pinned action versions

READ 2026-09-30 through `gh api`:

- `actions/create-github-app-token` v3.2.0 is commit `bcd2ba49218906704ab6c1aa796996da409d3eb1`. Inputs include `client-id`, `app-id`, `private-key`, `owner`, `repositories`, `permission-checks`, `permission-contents`, `permission-pull-requests`, and `skip-token-revoke`. The token is revoked at job end unless `skip-token-revoke` is set.
- `actions/attest` v4.2.2 is commit `1e69f48acb82d1966a394da916b4c1698aa569d6`.
- `gh attestation verify` offers `--signer-workflow`, `--signer-digest`, `--source-ref`, `--source-digest`, `--predicate-type`, and `--deny-self-hosted-runners`.

## Mechanism comparison against the requirement text

| Mechanism | Whose key signs | What the verifier checks | Closes identity (conjunct 2) | Closes "tests executed" |
|---|---|---|---|---|
| App-authored check run, App pinned by `integration_id` in the ruleset | The App, key held in an environment-scoped secret | GitHub matches the context name and `integration_id` at merge time. A verifier script can also read the check run's `app.id`, `head_sha`, and `name`. `external_id` is key-holder-controlled, so it serves correlation only. | Yes | No. It carries `needs.execute.result`. |
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

1. Line 215 carries the phrase "is now the only option that closes this requirement". Lines 195, 219, 221 and 430 repeat the same premise in other words. Replace the claim with a statement that no mechanism authenticates in-process test results against arbitrary candidate code, and move the forged-exit, collected-count and skipped-corpus cases into the accepted residuals beside line 203, citing Evidence 1.
2. Line 430: the research item resolves to "App-authored check run, `integration_id` pinned; execution authenticity bounded as above". That lets requirement 2 enter a phase.
3. Line 143 says `ruleset_required_contexts.py` "pins names alone today" and line 229 says it "pins context names alone today". As of 2026-09-30 the live ruleset records `integration_id: 15368` on every context (READ). The statement that nothing separates publishers stays true, because every pin is the Actions app.
4. Line 100 says the repository has "exactly one environment-gated job". As of 2026-09-30 the repository lists three environments, `bot-secrets`, `copilot`, `vendor-provenance` (READ, `gh api repos/rjmurillo/ai-agents/environments`), and none carries a deployment branch policy.
5. Line 187 names a `workflow_run` trigger. `pull_request_target` also runs the base ref's workflow definition and is the shape `enforcement-closure.yml` already uses. Say which is meant.

## Minimal App permissions

Repository permissions only. No account, organization, or webhook scope.

| Permission | Level | Why |
|---|---|---|
| Checks | Read and write | Create and update the check run. Nothing else needs write. |
| Metadata | Read | Set read-only. Not separately verified as mandatory. |

No `contents`, `pull_requests`, `statuses`, `administration`, `actions`, `secrets`, `workflows`, `members` or `environments` permission. The repository is public, so the SHA compare and the pull request pointer read (ADR line 235) need no App scope. The publication job makes them with its own `GITHUB_TOKEN` under job-level `contents: read` and `pull-requests: read`. If the repository ever goes private, add `contents: read` and `pull_requests: read` to the App then. An App without `administration` cannot edit a ruleset, so a stolen key cannot touch P2. Subscribe to no webhook events.

Request the narrow set at token time too: `permission-checks: write` on `create-github-app-token`. The token is then no wider than the check run call needs.

## How the base-owned job gets a token

1. The publication job runs under `pull_request_target` (or `workflow_run`), so the workflow definition comes from the default branch. The pull request cannot edit the job that reads the key.
2. The job declares `environment: adr101-publisher`. That environment restricts deployment branches to `main`. A head-defined workflow on another branch that names the environment is refused the secret. This contains the push-triggered branch case ADR-101 describes at lines 265-271. It does not contain `pull_request_target`: that trigger runs on the base branch by definition, so `main` admits it. That is a design fact, not something a probe can change. The only containment against a fork pull request is the content of the publication job itself (steps 4 to 7 below), CODEOWNERS on the workflow file, and the lint that the design adds.
3. A step runs `actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1 # v3.2.0` with the App id from an environment variable and the private key from the environment secret.
4. The job checks out the base ref only, with `persist-credentials: false` and no cache restore. It never checks out, imports, or reads an artifact from the head. It fetches the diff from the API by SHA.
5. No job that runs candidate code names the environment, holds the key, or holds `checks: write`. The execution job holds `contents: read` and nothing else.
6. Head-controlled strings (pull request title, head ref name, `workflow_run.head_branch`) never reach a `run:` expression. The job receives only SHAs and numeric ids through `env:`, and the module validates them against `^[0-9a-f]{40}$` and `^[0-9]+$` before use.
7. The key reaches exactly one step, the token step. No `set -x`, and no step logs an API response body or a traceback. Treat every PEM line and fragment as potentially visible in a public run log, and do not rely on secret masking to hide structured values.

The execution job is the second place this design can fail, and it shares a workflow with the publication job when `pull_request_target` is the trigger. A fork pull request then runs its code in base-ref context. The execution job must use no cache restore, because a candidate can poison a base-scoped cache that a later job restores, and must use `persist-credentials: false`. It names no environment and no secret. Plain `pull_request` would remove the base-ref context but makes the execution workflow head-editable, which breaks the "base owns the launch" rule at ADR line 195. So the choice is `pull_request_target` with those constraints, or a design that does not exist yet.

## Threat model notes

| Threat | Path | Effect | Control | Residual |
|---|---|---|---|---|
| Private key theft from a head-defined workflow | Branch pushes `on: push`, names the environment | Attacker mints check runs under the App | Environment secret with deployment branches limited to `main`; no repository-level copy | See the `pull_request_target` and merged-workflow rows below |
| Token theft inside the publication job | A step in that job leaks `GITHUB_OUTPUT` or logs | Short-lived token with `checks: write` only | Token scoped to `checks: write`, revoked at job end, job runs no candidate code, key reaches one step | Assume run logs are readable by anyone: never echo a response body or traceback |
| Forged execution evidence | Candidate conftest or `os._exit` | Green context, no real verification | None available (Evidence 1, 2) | Accepted. Needs the ADR text change above |
| Base moves after a green check | `pull_request_target` fires on head updates, not on a base update; with `strict_required_status_checks_policy` false the ruleset accepts the head's check for a merge tree nobody evaluated (CWE-284) | Merge of an unevaluated tree | ADR line 231: require strict checks, use a merge queue, or key the check to the head and base pair and re-publish when either moves. The Phase 0 strict decision constrains any build | Open until Phase 0 decides |
| Publisher publishes for a stale revision | Branch moved during the run | Success against a different tree | Compare head and base SHAs immediately before publishing; abort without publishing on mismatch (ADR line 235) | Window between compare and publish, accepted by the ADR as CWE-367 |
| Silent skip | Flag off, secrets missing, execute skipped | A missing context read as green | `always()`; typed outcomes; SKIP never accepted by a blocking policy | None known |
| App key reused for a second purpose | Later features add permissions | A bigger blast radius | One App, one permission list, drift check on permissions | Needs a baseline entry in Phase 0 |
| Fork pull request under `pull_request_target` | Fork code runs in base-ref context; the environment policy admits `main` by design | Cache poisoning next to the key, or a code path that reaches the key step | No cache restore, `persist-credentials: false`, no head checkout in the publication job, only validated SHAs and ids through `env:`, CODEOWNERS on the workflow | Content of the publication job is the whole control. The ADR line 322 question, whether the App can attach a check run to a fork head SHA, stays UNKNOWN until probed (checklist step 17) |
| Head-controlled string reaches a shell | PR title, head ref, `head_branch` in a `run:` expression | Command injection in the job holding the key (CWE-78) | Pass SHAs and numeric ids only, validate before use | None known |
| Long-lived key | Stolen `.pem` is a bearer credential | Attacker mints green for any commit under a pinned context | Rotation every 90 days (checklist step 18); a scheduled audit that every successful App check run has a successful publication job run for the same head SHA in the workflow-run API, which the key holder cannot write | Detection lag between audits. The `external_id` field is key-holder-controlled and is not audit evidence |
| Ruleset drift | A context added with a null `integration_id` accepts an App-authored check of that name | A name-matched green | Extend the Phase 0 drift check to fail on a null `integration_id` | Depends on Phase 0 landing |
| Owner-side compromise | Repository admin edits the environment's branch policy or ruleset bypass actors; the personal account that owns the App is taken over | Key access or a green context without the App | Out of reach of any in-tree control (ADR line 130). Alert on audit-log events for environment and App settings changes | Accepted, matches the ADR's P2 root-of-trust statement |
| Key theft from a workflow merged to `main` | A merged step reads the secret | Same as key theft | CODEOWNERS and review on `.github/workflows/` (Phase 0) | Review quality |

## Owner checklist

Only the repository owner can do these. Steps 1 to 15 are for now, in order. Steps 16 to 18 happen after code exists. Nothing in steps 1 to 15 touches a ruleset.

1. Open `https://github.com/settings/apps/new` while signed in as `rjmurillo`.
2. GitHub App name: `rjmurillo-adr101-publisher`. If taken, append a short suffix and use the same name everywhere below.
3. Homepage URL: `https://github.com/rjmurillo/ai-agents`.
4. Identifying and authorizing users: leave the callback URL empty. Clear "Expire user authorization tokens" and "Request user authorization (OAuth) during installation".
5. Webhook: clear "Active". Leave every event unchecked.
6. Repository permissions: Checks = Read and write. Metadata = Read-only. Every other permission stays "No access". Set no account permission and no organization permission.
7. Where can this GitHub App be installed: "Only on this account".
8. Create the App. Record the numeric App ID and the Client ID from the App's settings page.
9. Install the App: App settings, "Install App", account `rjmurillo`, "Only select repositories", choose `ai-agents`.
10. In `rjmurillo/ai-agents` settings, Environments, create `adr101-publisher`. Set "Deployment branches and tags" to "Selected branches and tags" and add the branch `main`. Add no required reviewers and no wait timer.
11. Test the containment with a dummy value first. Add the environment secret `ADR101_PUBLISHER_APP_PRIVATE_KEY` with the text `probe-not-a-key`. Push a throwaway branch whose workflow sets `environment: adr101-publisher` and echoes whether the secret is set, not its value. GitHub must refuse the deployment. If the job runs, delete the secret and stop: the environment policy does not hold. Delete the throwaway branch.
12. Generate the key only after step 11 passes. On the App's settings page choose "Generate a private key". A `.pem` file downloads once.
13. Replace the environment secret `ADR101_PUBLISHER_APP_PRIVATE_KEY` with the full contents of the `.pem`, including the BEGIN and END lines. Add the environment variable `ADR101_PUBLISHER_APP_ID` with the numeric App ID. Create neither at repository or organization level, because a branch-defined `on: push` workflow can read those.
14. Move the `.pem` into your password manager and delete the downloaded copy with `trash`. Do not commit it, paste it into an issue, or put it in a session file. Set a calendar reminder for rotation in 90 days.
15. Leave the repository variable `ADR101_PUBLISHER_ENABLED` unset. It stays off until the job exists and a test pull request has published one check run.
16. After the job exists and has published on a test pull request, read its App id with `gh api repos/rjmurillo/ai-agents/commits/<sha>/check-runs --jq '.check_runs[] | {name, app: .app.id}'`. Then follow the no-gap rename sequence in `.claude/rules/ci-scripts.md` MUST 22: emit the context, merge, require it with that `integration_id`, then remove any old requirement. This step edits the ruleset and is yours to run.
17. Probe a fork. Open a pull request from a fork of `ai-agents` against `main` and read whether the App's check run attaches to the fork head SHA (ADR line 322). Record the answer on issue #5245. Do not assume either result.
18. Rotation, every 90 days: generate a second key in App settings, replace the environment secret, run one test pull request, then delete the first key in App settings.

Names the code would read: environment `adr101-publisher`, secret `ADR101_PUBLISHER_APP_PRIVATE_KEY`, variable `ADR101_PUBLISHER_APP_ID`, repository variable `ADR101_PUBLISHER_ENABLED`.

## If the owner says go

Build, behind `ADR101_PUBLISHER_ENABLED` (default off), a base-owned workflow with these parts. It would deliver the identity, binding, and split properties above and nothing stronger, and its docstring would say so.

- A Python module under `scripts/ci/` owning all logic, returning `evidence.CheckOutcome` values: SKIP with reason `publisher.disabled` when the flag is off, BLOCKED with `auth.unavailable` when the flag is on and the App id or key is absent, FAIL when the supervisor's recorded conclusion is not success or the SHAs moved, PASS only when the check run was published for the captured head and base.
- Workflow YAML with triggers and calls only: an `execute` job on its own GitHub-hosted runner with `contents: read`, no secrets, no environment, running a base-owned harness over the candidate checked out as data; a `publish` job, also on a GitHub-hosted runner, with `needs: execute`, `if: ${{ always() }}`, `environment: adr101-publisher`, and no candidate code.
- A verifier that reads the published check run through the API and checks `app.id`, `head_sha`, and `name`, then cross-checks the run against the workflow-run API for the same head SHA. It uses `external_id`, a digest of the captured SHAs, for correlation only, and rejects tampered or mismatched evidence as FAIL.
- Tests for flag off (SKIP), flag on with secrets absent (BLOCKED), a mocked valid token and evidence (PASS), and tampered evidence (FAIL).
- A test that fails when either job names a `self-hosted` label. ADR line 199 voids the job split on a persistent runner pool, because candidate filesystem state would reach the job holding the key.
- A test or lint that fails when the publication job checks out the head, restores a cache, or interpolates a head-controlled string into `run:`, and a CODEOWNERS entry for the workflow file.
- It would not join `scripts/ci/ruleset_required_contexts.py` or any ruleset.

An honest label on the result would read "published by the pinned App for this head and base; execution authenticity bounded by ADR-101 line 203". It must never read "verified".
