# Decision: the `validate` job of ai-session-protocol.yml is stdlib-only

## Question

Can a validation script invoked by `.github/workflows/ai-session-protocol.yml`
import a third-party package?

## Conventional answer

Everywhere else in this repo, Python scripts run under `uv run --frozen`, so
the project venv resolves `yaml`, `jsonschema`, `packaging`, and the rest.
The obvious move when adding a rule to the session-protocol workflow is to
call an existing module such as `scripts/validation/git_hook_policy.py`.

## First-principles position

Read the job, do not assume it matches its siblings. The `validate` job's
steps are: checkout, `git fetch origin main --unshallow || git fetch origin
main`, a pwsh validate step, and upload-artifact. There is **no**
`actions/setup-python`, **no** `astral-sh/setup-uv`, and **no** dependency
install. It calls bare `python3` and inherits whatever the runner image
carries.

## Evidence

- Live job log, run 30216991768 job 89832864004: bare
  `python3 ./scripts/validate_session_json.py` returns verdict COMPLIANT with
  exit 0, so `jsonschema` happens to be on `ubuntu-24.04-arm`.
- `git_hook_policy.py` imports `yaml` at module level. Nothing guarantees
  `yaml` on that image, and the failure mode is a traceback in a job whose
  whole purpose is a clean verdict.

## Decision

Issue #3385's rule lives in `scripts/validation/session_scope.py`, which
imports only `subprocess`, `collections.abc.Iterable`, and `pathlib.Path`.
`tests/test_validate_session_json.py::test_the_shared_module_imports_no_third_party_package`
pins that import list literally, so the constraint fails loudly rather than at
the next CI run.

**Rule for the next editor:** anything the `validate` job invokes must be
standard library only, or the job needs a Python setup step first. Do not
reason from what other jobs in the same file do.
