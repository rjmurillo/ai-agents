# Ship as a script driver

Status: Proposed, with one decision open (the stub). Owner: Richard Murillo. Scope: ai-agents `/ship` and `/push-pr`.

## Decision of record

Richard ruled on 2026-11-25. `/push-pr` is retired. Its work folds into `/ship`.
Landing (merge and after) becomes a separate skill, specified later.
`/ship` takes the gstack shape. Scripts do the fixed steps.
The skill file is a contract the model acts on and judges.

Also decided:

1. **Draft PRs before review.** Richard ruled on 2026-11-25, recorded on #7581.
   `ship --draft` skips the review marker check only for a new draft PR, or an open PR the host reports as a draft.
   An unknown draft state is refused, and an existing non-draft PR still needs the marker.
   This narrows the earlier option A, which skipped the marker for any `--draft` run.
2. **Branch.** Option A: build on a fresh branch from `origin/main` and drop the old branch.
   The four commits on `refactor/ship-push-pr-pr-creation` moved creation into `/push-pr`, and this spec reverses that.
   The work is on `feat/ship-driver-scripts`, a fresh branch.
   No owner ruled on this. The choice was made in practice on 2026-11-25, when this branch was cut.

## Problem

`/ship` and `/push-pr` hold their fixed steps as prose today.
The model must copy shell blocks and obey MUST NOT lists.
Examples at commit 6a73f1ad30 (2026-11-25):

- Host detection is the same shell block in both skills.
- The ADO create needs about 10 prose rules the model must follow.
  They ban extra `az` flags, ban other `@` arguments, and check the `@` fallback.
- The ADO policy check is a 40-line bash block inside the skill.
- `az` cannot be granted, because a prefix grant allows any flag.
  So every ADO create prompts the user.

Prose rules drift and get skipped. A script enforces them every run.

## Shape

The pattern comes from gstack `ship/DRIVER.md`.

1. Each phase is one script call.
2. A script prints `KEY: value` result lines and nothing else of note.
3. The last line is `NEXT: <act>` or `STOP: <reason> [detail]`.
4. Exit codes follow the repo standard: 0 ok, 1 logic, 2 config, 3 external, 4 auth.
   A `STOP:` line always pairs with a non-zero exit.
5. The model keeps only judgment work.
   It writes the title and body, fixes findings, and handles a STOP.
   It also writes the final report.
6. The model never runs `git push`, `gh pr create`, or `az repos pr create` itself.

## Scripts

All scripts are Python (ADR-042) and live under the ship skill's `scripts/`.
They ship through the same plugin-root resolver as `skills/github/scripts/`.
They run through `lib/ptk_run.py`, like `new_pr.py` today.

### `ship_detect.py`

Replaces both host-detection blocks and the PR ownership prose.

| Line | Values |
|---|---|
| `HOST:` | `github` or `ado` |
| `MODE:` | `owner` or `contributor` |
| `PR:` | `none` or the PR number or `pullRequestId` |
| `BASE:` | the target branch |
| `HEAD:` | the full HEAD SHA |

- No origin remote: `STOP: no-origin`, exit 2. A remote that is not `https`, `ssh`, or scp-style: `STOP: unsupported-remote`, exit 2.
- A failed `gh` or `az` query: `STOP: pr-query-failed`, exit 3, or `STOP: auth-failed`, exit 4.
- An open PR with no author in the host reply: `STOP: pr-author-unknown`, exit 3.
  It never prints `PR: none` after a failed query.
- In owner mode with no open PR, a base branch (`main`, `master`, the origin default, or `--base`) is `STOP: on-base-branch`, exit 1.
- On Windows, a checkout root or current directory that holds a file named `git`, `gh`, or `az` with a `PATHEXT` suffix, such as `git.exe`, is `STOP: unsafe-checkout`, exit 2.
  CreateProcess searches the current directory before `PATH`, so that file would run in place of the installed program (CWE-427).
  Helpers run in the checkout root and may spawn a bare `git` themselves. The current-directory check is defense in depth for a helper run without a working directory.
- Host rule: match the parsed URL host, not a substring.
  This fixes finding LOW-1 from the 2026-11-25 security review.

### `ship_preflight.py`

Runs the checks that have one right answer.

| Flag | Prints |
|---|---|
| `--check tree` | `CHECK: tree=clean` or `tree=dirty` (`.project-toolkit/scratch/` is not counted) |
| `--check reviewed` | `CHECK: reviewed=PASS axes=<list>`, `FAIL`, `SKIPPED` (draft), or `ADVISORY` (contributor) |
| `--check pipeline` | `CHECK: pipeline=PASS`, `FAIL`, `PENDING`, or `DEFERRED` |

- `pipeline` on GitHub wraps `get_pr_checks.py`. It keeps today's rules.
  PASS needs exit 0, `RequiredState == SUCCESS`, and `AllPassing == true`.
- `pipeline` on ADO moves today's bash policy block into Python.
  Each blocking build policy must be approved on the current merge commit.
- `pipeline` with `PR: none` prints `DEFERRED` and `NEXT: publish-then-discharge`.
- `pipeline` reads checks only when the PR head branch and SHA match the local branch and HEAD.
  A stale head is `DEFERRED` before publish and `PENDING` after it.
  A contributor never publishes, so a contributor `DEFERRED` pipeline ends on `NEXT: report`.
- `PENDING` ends on `NEXT: rerun-pipeline` with a `PIPELINE_DEADLINE:` line. Past the 30-minute deadline it is `FAIL`.
  The first `PENDING` result stores that deadline in a scratch state file keyed by host, PR, and HEAD, so a rerun cannot extend it.
  A corrupt or linked state file is replaced. When the deadline cannot be stored, the run ends on `STOP: deadline-unstored`, exit 2.
- On GitHub each call waits at most 300 seconds (`_ship_pipeline.py` clamps the wait to `CHECKS_TIMEOUT_SECONDS`).
  Required checks still running when the call returns are `PENDING`, unless a required check already failed.
  A failed required check is `FAIL` even while others still run, including on helper exit 7.
- `reviewed` wraps the existing review-marker validator. It does not reimplement it.

Security scan and tests stay as model-run steps. They need judgment on findings.

### `ship_pr.py`

Owns everything `/push-pr` did after the body is written.

| Subcommand | Does | Prints |
|---|---|---|
| `branch --name <type>/<slug>` | creates and switches to a feature branch | `BRANCH:` |
| `prepare [--base <ref>]` | allocates the body file and seeds the template | `BODY_FILE: <path>` |
| `check --title --body-file [--base <ref>]` | title, body, paths-in-diff, ADO description rules | `CHECK: title=`, `CHECK: body=`, `CHECK: paths=` |
| `publish --title --body-file [--base <ref>] [--draft] [--require-axis A] [--paths-checked-by-hand]` | push, then create the PR | `PUSH:`, `PR:`, `NEXT:` |

`publish` rules, all enforced in code:

- It refuses to publish from a base branch (`main`, `master`, the origin default, or `--base`): `STOP: on-base-branch`, exit 1. `--draft` does not lift this.
- It refuses a dirty tree: `STOP: tree-dirty`, exit 1.
- It refuses when HEAD is not the reviewed SHA: `STOP: head-not-reviewed`, exit 1.
  `--draft` skips that check only for a new PR or an open PR the host reports as a draft.
  An open PR whose draft state is unknown or false still needs the marker (owner ruling, 2026-11-25, #7581).
- It refuses `MODE: contributor`: `STOP: contributor-mode`, exit 1.
- It never creates a commit.
- It reruns `check` and stops on any failure before the push.
- GitHub create calls `new_pr.py` as today.
- ADO create builds a fixed argument list and runs it without a shell.
- On Windows, `az` is `az.cmd`, which runs through cmd.exe. The scripts find it on absolute `PATH` entries only, never the current directory.
  Every argument is double-quoted, and an argument holding `%`, `!`, a quote, a line break, or a trailing backslash is refused (exit 126, so a STOP).
  `check`, which `publish` reruns, fails such a title or body file path first, so the refusal never comes after the push.
  Only `--output json`, `--title`, `--description @<checked body file>`, `--target-branch`, and `--draft true|false` are passed.
- After an ADO create, it reads the JSON `description`.
  If it starts with `@`, it prints `STOP: description-upload-failed`, exit 3.
  The PR is left open for the user to decide.
- An existing open PR is not recreated. It prints `PR: host=<h> number=<id> url=<u> existing` and pushes only.
- The paths-in-diff check never runs code from the branch being shipped (owner ruling, 2026-11-25).
  It reads `scripts/validation/pr_description.py` and its `scripts/github_core/` import closure with `git show origin/<base>:<path>`.
  It writes them to a private temporary tree (directory 0700, files 0600) and runs that copy with `python3 -I`.
  The body file and the branch diff are its data. `uv` is not used, so the branch's lockfile builds nothing.
- Accepted trade-off: a PR that changes the validator itself is checked by the base version until it merges.
- When the base has no validator, or the base copy cannot run, `check` prints `CHECK: paths=NOT-RUN` and ends on `NEXT: compare-paths-by-hand`.
  `publish` then stops with `STOP: paths-not-checked` unless the model passes `--paths-checked-by-hand`.

Output on success:

```text
PUSH: pushed
PR: host=github number=<n> url=<u>
NEXT: discharge
```

## Result contract

Every script prints `KEY: value` lines and ends on one `NEXT:` or `STOP:` line.
Every script accepts `--output-format json|human|auto`, before or after a subcommand.
A run that spills output to a file prints `DETAIL_FILE: <path>`.
A STOP detail is at most 500 characters.

| Script | Result keys | NEXT acts | Flags |
|---|---|---|---|
| `ship_detect.py` | `HOST`, `REMOTE_HOST`, `BRANCH`, `BASE`, `HEAD`, `PR`, `PR_URL`, `PR_AUTHOR`, `PR_DRAFT`, `MODE` | `preflight`, `validate-only` | `--base` |
| `ship_preflight.py` | the detect keys, `CHECK`, `PIPELINE_DEADLINE` | `write-body`, `report`, `publish-then-discharge`, `rerun-pipeline` | `--check` (repeatable), `--base`, `--pr`, `--draft`, `--require-axis`, `--deadline`, `--wait-seconds` (0 to 540) |
| `ship_pr.py` | `BRANCH`, `BODY_FILE`, `CHECK`, `FINDING`, `PUSH`, `PR`, and the detect keys with `PR_AT_PREFLIGHT` in place of `PR` | `commit-then-review`, `write-body`, `compare-paths-by-hand`, `publish`, `discharge` | per subcommand, in the table above |

`--wait-seconds` defaults to 480 and takes at most 540. These are upper bounds, not the wait you get.
Each wait is clamped to the run budget (540 seconds, `RUN_BUDGET_SECONDS` in `_ship_common.py`) less a 120-second reserve for the calls after it.
So one run waits about 420 seconds at most, and less when earlier calls used time.
On GitHub each wait is also capped at 300 seconds.
The host kills a tool call at 600 seconds, so the caller sets its tool timeout near 600, not the default 120.
`--deadline` can only shorten the stored 30-minute window. A value past 30 minutes from the call is refused, and an omitted value reuses the stored deadline.
The base branch defaults to `origin/HEAD`, else `origin/main` or `origin/master`, else `main`.
A failed paths check prints one `FINDING: <issue>: <file>` line per critical finding, at most 10. The Azure DevOps description check reads the helper's JSON `ErrorCount`.

STOP reasons, by the script that first declares them. A later script also uses the reasons of the scripts it builds on.

| Script | STOP reasons |
|---|---|
| `ship_detect.py` | `bad-arguments`, `no-repo`, `no-origin`, `unsupported-remote`, `detached-head`, `on-base-branch`, `pr-query-failed`, `user-query-failed`, `auth-failed`, `pr-author-unknown`, `unsafe-checkout` |
| `ship_preflight.py` | `check-failed`, `validator-missing`, `validator-config`, `checks-query-failed`, `pipeline-query-failed`, `deadline-unstored` |
| `ship_pr.py` | `bad-branch-name`, `branch-create-failed`, `prepare-failed`, `bad-body-file`, `contributor-mode`, `tree-dirty`, `head-not-reviewed`, `paths-not-checked`, `push-rejected`, `push-failed`, `pr-create-failed`, `description-upload-failed` |

## Permissions

`/ship` grants one entry per script it calls, with no wildcard (ADR-127 decision 3 item 7).
Those grants are safe because each parser sets `allow_abbrev=False` and rejects unknown flags.
The `az` and `gh` argument lists are fixed in code.
So the ADO create no longer prompts, and no `az` grant is needed.
Today's `Edit` grant on the scratch body file stays.

## Skill contract

The new `ship` SKILL.md is a driver. Each phase names one call.

1. Detect: run `ship_detect.py`. A STOP ends the run.
2. Preflight: run `ship_preflight.py` for tree, reviewed, and pipeline.
   Run `security-scan` and the tests. Record each result line.
   With `--draft`, the marker check is skipped only for a new draft PR or an open PR the host reports as a draft.
   An unknown draft state needs the marker (owner ruling, 2026-11-25, #7581).
3. Body: run `ship_pr.py prepare`. Fill the body from the real diff.
   Run `ship_pr.py check` until it passes. This is the model's main judgment step.
4. Publish: run `ship_pr.py publish`. Copy its `PR:` line.
5. Discharge: on `NEXT: discharge`, run `ship_preflight.py --check pipeline --pr <id>`.
6. Report: host, mode, PR link, each `CHECK:` line, and any STOP.

A "where each STOP sends you" table maps each STOP to one fix section.
The skill reads a section only when a STOP sends it there.

The contract states the paths-check trust boundary in the body step:
the check runs the base branch's validator, so a PR that edits the validator is checked by the old version until it merges.
`paths=NOT-RUN` is never a pass. The model compares each path in the body to the diff by hand, then passes `--paths-checked-by-hand`.

## Retiring `/push-pr`

At commit 6a73f1ad30 (2026-11-25), `git grep` finds 226 files naming `push-pr`.
About 60 are live code, tests, docs, or ADRs. The rest are session logs and QA records.

- Remove the `push-pr` template. The build removes its mirrors.
- Move its trigger phrases into the `ship` description.
- Update autoplan routing at `autoplan.SKILL.md.tmpl:161`.
- Update `templates/platforms/hermes.yaml:53`.
- Update docs under `docs/skills/` and the `takeover`, `validate-pr-description`, and `checkpoint` skills.
- Drop `push-pr` rows from the portability and trigger-resolution baselines.
- Replace the prose tests with behavior tests on the scripts.
  They use fake `git`, `gh`, and `az` binaries on `PATH`.
- Leave session logs, QA records, and retrospectives as written. They are history.

## ADRs touched

ADR-049 says to integrate the pre-PR gate into `push-pr`.
ADR-064 lists `push-pr` among migrated skills.
Both need an amendment through `adr-review`.
Twelve more ADRs and one design review mention `push-pr` as context. They stay unchanged unless review says otherwise.

## Landing seam

`/ship` ends with an open PR and a pipeline verdict.
The landing skill starts from an open PR with a green pipeline.
It owns merge, auto-merge, and post-merge checks. It is out of scope here.

## Open decisions for Richard

1. **Stub.** Options:
   A) Delete `/push-pr` outright.
   B) Keep a one-line stub for one release that points to `/ship`.

## Slices

Each slice is one commit with its own tests.

1. `ship_detect.py` and its tests. Both skills call it.
2. `ship_pr.py` and its tests. `/ship` step 3 calls it instead of `/push-pr`.
3. `ship_preflight.py` and its tests. The ADO bash block moves into Python.
4. Rewrite `ship` SKILL.md as the driver contract.
5. Retire `/push-pr` across routing, docs, baselines, and tests.
6. ADR-049 and ADR-064 amendments through `adr-review`.

## Acceptance criteria

- [ ] No skill file holds a host-detection shell block.
- [ ] No skill file runs `git push`, `gh pr create`, or `az repos pr create` directly.
- [ ] `ship` grants no `az` or `gh` entry.
- [ ] `ship_pr.py publish` refuses a dirty tree, an unreviewed HEAD, and contributor mode.
- [ ] An ADO create with an `@` fallback description exits 3 with a STOP line.
- [ ] Each script has positive, negative, and edge tests with fake binaries.
- [ ] `build_all.py --check` passes with no `push-pr` mirror left.
- [ ] The full test sweep shows no failure that main does not also show.

## Non-goals

- Merge, auto-merge, and post-merge work. The landing skill owns them.
- Version bumps, CHANGELOG writes, and review dispatch from gstack.
- Changes to `new_pr.py` behavior on GitHub.
