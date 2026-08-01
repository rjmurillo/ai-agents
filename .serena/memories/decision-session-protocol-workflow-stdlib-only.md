# Decision: stdlib-only binds per job in ai-session-protocol.yml, not per file

## Question

Can a validation script invoked by `.github/workflows/ai-session-protocol.yml`
import a third-party package?

## Conventional answer

Everywhere else in this repo, Python scripts run under `uv run --frozen`, so
the project venv resolves `yaml`, `jsonschema`, `packaging`, and the rest.
The obvious move when adding a rule to the session-protocol workflow is to
call an existing module such as `scripts/validation/git_hook_policy.py`.

## First-principles position

Read the job, do not assume it matches its siblings. Jobs in this file differ:

- `validate` **does** install dependencies. It runs
  `uv run --frozen python3 scripts/ci/validate_session_protocol.py` after an
  `astral-sh/setup-uv` step, so the project venv from `uv.lock` is available.
- `detect-changes`, `validate-investigation-claims`, and `aggregate` install
  **nothing**. They call bare `python3` and inherit whatever the runner image
  carries, so every script they reach must be standard library only.

## Evidence

- Issue #3806. The `validate` job used to call bare `python3`, but the chain it
  starts ends at `scripts/validate_session_json.py`, which imports `jsonschema`
  at module level. That resolved only because `ubuntu-24.04-arm` happened to
  carry the package. `grep -c -i jsonschema` on that image's readme returns 0,
  so nothing documented it. `uv run --no-project --isolated python
  scripts/validate_session_json.py --help` reproduces the failure mode:
  `ModuleNotFoundError` at line 39.
- The dependency travels through a `subprocess` spawn, not an import
  (`scripts/ci/validate_session_protocol.py` builds an argv with
  `sys.executable` and a script path string), which is why an import-only scan
  of the entrypoint missed it for months.
- `git_hook_policy.py` imports `yaml` at module level. Nothing guarantees
  `yaml` on that image, so it stays out of the bare-python3 jobs.

## Decision

Issue #3385's rule lives in `scripts/validation/session_scope.py`, which
imports only `subprocess`, `collections.abc.Iterable`, and `pathlib.Path`.
`tests/test_validate_session_json.py::test_the_shared_module_imports_no_third_party_package`
pins that import list literally.

`tests/ci/test_validate_session_protocol.py::TestEachJobInstallsWhatItsScriptsNeed`
enforces the per-job rule. It parses the workflow, pairs each job's
install status with the scripts that job runs, and walks the transitive closure
of both imports and subprocess-spawned script paths. No hand-kept script list
to go stale.

**Rule for the next editor:** check whether the specific job installs
dependencies before you reach for a third-party import. If it does not, either
keep the whole reachable chain stdlib-only or add `astral-sh/setup-uv` to that
job and run through `uv run --frozen`. Do not reason from what other jobs in
the same file do, and do not stop at the entrypoint's own imports: follow the
subprocess spawns too.
