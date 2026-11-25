# Ship as a script driver

Status: Proposed. Owner: Richard Murillo. Scope: ai-agents `/ship` and `/push-pr`.

## Decision of record

Richard ruled on 2026-11-25. `/push-pr` is retired. Its work folds into `/ship`.
Landing (merge and after) becomes a separate skill, specified later.
`/ship` takes the gstack shape. Scripts do the fixed steps.
The skill file is a contract the model acts on and judges.

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
3. The last line is `NEXT: <act>` or `STOP: <reason>`.
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

- No origin remote: `STOP: no origin`, exit 2.
- A failed `gh` or `az` query: `STOP: pr query failed`, exit 3.
  It never prints `PR: none` after a failed query.
- Host rule: match the parsed URL host, not a substring.
  This fixes finding LOW-1 from the 2026-11-25 security review.

### `ship_preflight.py`

Runs the checks that have one right answer.

| Flag | Prints |
|---|---|
| `--check tree` | `CHECK: tree=clean` or `tree=dirty` |
| `--check reviewed` | `CHECK: reviewed=PASS axes=<list>` or `FAIL` |
| `--check pipeline` | `CHECK: pipeline=PASS`, `FAIL`, or `DEFERRED` |

- `pipeline` on GitHub wraps `get_pr_checks.py`. It keeps today's rules.
  PASS needs exit 0, `RequiredState == SUCCESS`, and `AllPassing == true`.
- `pipeline` on ADO moves today's bash policy block into Python.
  Each blocking build policy must be approved on the current merge commit.
- `pipeline` with `PR: none` prints `DEFERRED` and `NEXT: discharge after publish`.
- `reviewed` wraps the existing review-marker validator. It does not reimplement it.

Security scan and tests stay as model-run steps. They need judgment on findings.

### `ship_pr.py`

Owns everything `/push-pr` did after the body is written.

| Subcommand | Does | Prints |
|---|---|---|
| `prepare` | allocates the body file and seeds the template | `BODY_FILE: <path>` |
| `check --title --body-file` | title, body, paths-in-diff, ADO description rules | `CHECK: title=`, `CHECK: body=` |
| `publish --title --body-file` | push, then create the PR | `PUSH:`, `PR:`, `NEXT:` |

`publish` rules, all enforced in code:

- It refuses a dirty tree: `STOP: tree dirty`, exit 1.
- It refuses when HEAD is not the reviewed SHA: `STOP: head not reviewed`, exit 1.
- It refuses `MODE: contributor`: `STOP: contributor mode`, exit 1.
- It never creates a commit.
- It reruns `check` and stops on any failure before the push.
- GitHub create calls `new_pr.py` as today.
- ADO create builds a fixed argument list and runs it without a shell.
  Only `--title`, `--description @<checked body file>`, and `--target-branch` are passed.
- After an ADO create, it reads the JSON `description`.
  If it starts with `@`, it prints `STOP: description upload failed`, exit 3.
  The PR is left open for the user to decide.
- An existing open PR is not recreated. It prints `PR: existing <id>` and pushes only.

Output on success:

```text
PUSH: pushed
PR: host=github number=<n> url=<u>
NEXT: discharge
```

## Permissions

`/ship` grants one form: `Bash(python3:-I */ship/scripts/*.py*)`.
That grant is safe because argparse rejects unknown flags.
The `az` and `gh` argument lists are fixed in code.
So the ADO create no longer prompts, and no `az` grant is needed.
Today's `Edit` grant on the scratch body file stays.

## Skill contract

The new `ship` SKILL.md is a driver. Each phase names one call.

1. Detect: run `ship_detect.py`. A STOP ends the run.
2. Preflight: run `ship_preflight.py` for tree, reviewed, and pipeline.
   Run `security-scan` and the tests. Record each result line.
3. Body: run `ship_pr.py prepare`. Fill the body from the real diff.
   Run `ship_pr.py check` until it passes. This is the model's main judgment step.
4. Publish: run `ship_pr.py publish`. Copy its `PR:` line.
5. Discharge: on `NEXT: discharge`, run `ship_preflight.py --check pipeline --pr <id>`.
6. Report: host, mode, PR link, each `CHECK:` line, and any STOP.

A "where each STOP sends you" table maps each STOP to one fix section.
The skill reads a section only when a STOP sends it there.

## Retiring `/push-pr`

At commit 6a73f1ad30 (2026-11-25), `git grep` finds 226 files naming `push-pr`.
About 60 are live code, tests, docs, or ADRs. The rest are session logs and QA records.

- Remove the `push-pr` template. The build removes its mirrors.
- Move its trigger phrases into the `ship` description.
- Update autoplan routing at `autoplan.SKILL.md.tmpl:161`.
- Update `templates/platforms/hermes.yaml:55`.
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

1. **Draft PRs before review.** `/push-pr` could open a PR with no `/review` marker.
   `/ship` in owner mode requires the marker. Options:
   A) `ship --draft` skips the marker check and opens a draft PR.
   B) No PR before review.
2. **Branch.** The four commits on `refactor/ship-push-pr-pr-creation` moved creation into `/push-pr`.
   This spec reverses that. Options:
   A) Build on a fresh branch from `origin/main` and drop this branch.
   B) Build on this branch and keep the commits as history.
3. **Stub.** Options:
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
