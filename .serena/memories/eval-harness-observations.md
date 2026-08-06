# Skill Sidecar Learnings: Eval Harness

**Last Updated**: 2026-05-30
**Sessions Analyzed**: 1 (wiki-rubric audit #2126/#2136)
**Related**: agent-prompt-optimization-observations.md (fixture-design-for-effectiveness lesson lives there)

## Constraints (HIGH confidence)

- Run one agent's eval: `python3 scripts/eval/eval-agent-vs-baseline.py --agent <name> --fixtures evals/<name>-spike/fixtures --n-runs 3 --model claude-sonnet-4-6` from repo root. `ANTHROPIC_API_KEY` is read from env or `.env`. The agent-under-test "variant" is `templates/agents/<name>.shared.md` (read as the system prompt); baseline prompt is fixed "Review the following input." `--dry-run` validates fixtures + prints the plan with ZERO spend (the only no-API path; no `--mock` exists).
- Custom eval scripts MUST use the repo's own transport `from _anthropic_api import call_api` (urllib-based, `scripts/eval/_anthropic_api.py`). `import anthropic` FAILS because the SDK is not installed. The main harness works because it uses `call_api`, not the SDK. (Bug hit: `eval_skill_router.py` rc=3 "SDK not installed".)

## Preferences (MED confidence)

- Fixture format: JSON, one per file in `evals/<name>-spike/fixtures/*.json`. Fields: `schemaVersion` (must be 1), `id` (unique across corpus), `input`, `provenance` (`synthetic|public-cve|paraphrased-from-public`), `assertions` (each `{"kind":"verdict","expected_value":"IDENTIFY|OK|ESCALATE"}` OR `{"kind":"regex","pattern":"..."}`; never both on one assertion), `tags`. Validated by `FixtureValidator` (`_eval_agent_types.py`). No manifest/registry; the runner globs `fixtures/*.json`.
- Reports: `evals/<name>-spike/reports/<RUN_ID>/report.json` (+ `REPORT.md`); per-call records in `runs/<RUN_ID>/runs.jsonl` (the agent's actual output is the `raw_response` field). `report.json` carries `agent_recall`, `baseline_recall`, `recall_delta`, `bootstrap_ci_95`, `per_fixture_pass_rates`, and `*_sha` provenance. To detect regression after a prompt edit: re-run the SAME fixtures, compare new `recall_delta`/CI to the committed baseline report (comparable only when `fixture_set_sha` matches). The harness has NO built-in diff command.
- Cost ~$0.40-1.40 per agent at `--n-runs 3` (calls = n_runs x fixtures x 2 variants). Flakiness halt: if >30% of fixtures are intra-run-variant flaky, the runner emits informational metrics and exits non-zero (ADR-058), so a delta with flaky=true is directional, not significant.

## Edge Cases (MED confidence)

- DEFERRED agents (no `templates/agents/<name>.shared.md`): the harness cannot load the variant, so it cannot eval them. context-retrieval, quality-auditor, spec-generator are DEFERRED. To eval them you must first author the `.shared.md` template + a spike.
- Two skill eval systems exist: knowledge-integration (`scripts/eval/eval-knowledge-integration.py`, prompts in `tests/evals/skills/*.json`) and agent-vs-baseline. A true skill ROUTER/trigger eval (does query X load skill Y?) does NOT exist; author one if needed (`eval_skill_router.py` was a first attempt that compares before/after skill descriptions on disambiguation queries).
- `validate-skill.py` (SkillForge) has a CWE-22 cwd path guard: it rejects targets outside cwd; `cd` into a worktree to validate its copy. See `mem:ci-infrastructure-observations` for the build/parity/drift model.

## Fingerprint provenance boundary (#4123, 2026-08-03)

- `scripts/eval/_eval_common.py::require_str_or_none` raises
  `MalformedProviderMetadataError` when provider metadata is present but not a
  string. Do not replace it with a generic `RuntimeError`: the broad retry
  handler in `AnthropicAPIAdapter.call_model` categorizes generic exceptions as
  provider failures and retries them.
- `scripts/eval/_eval_api_adapter.py::call_model` re-raises that typed error
  before retry logging and validates the injectable transport seam again before
  emitting a success record. This second check closes custom transports that do
  not use the built-in provider wrappers.
- `scripts/eval/eval-rule-activation.py::eval_one_scenario` has two ordinary
  `RuntimeError` recovery policies, one across mechanisms and one across judge
  samples. Both must propagate `MalformedProviderMetadataError` first, or a
  malformed fingerprint permits more paid calls. The response and judge
  regression tests each assert exactly one call.
- `scripts/eval/_copilot_cli.py` may inspect bounded subprocess stderr only to
  classify a fixed safe error hint. It must never append raw stderr to an
  exception because rule-activation persists ordinary exception text in both
  mechanism and judge artifacts. The credential regression writes both paths
  to a temporary JSON artifact and asserts the token is absent.
- A present non-string `assistant.message.data.model` is corruption, not
  missing attribution. Route it through `require_str_or_none` before the
  unverified-model opt-in. Normal and opted-in tests both assert one subprocess
  call and `MalformedProviderMetadataError`.
- Regression evidence:
  `TestTransportsRefuseAMalformedFingerprint` in
  `tests/evals/test_eval_agent_vs_baseline.py`. Removing the typed boundary
  caused two end-to-end tests to fail; coercing malformed values to `None`
  caused 20 fingerprint tests to fail.

## Text-only Copilot boundary (2026-08-04)

- Repository fixtures and model-authored text are untrusted input. Copilot
  text evals use ACP JSON-RPC over stdin, not `--prompt` argv. A fixed JSON
  envelope retains the system and message role labels while marking every
  content field `untrusted_repository_text`.
- Copilot CLI 1.0.78 reports that `--available-tools` disables every other
  tool. The transport passes `--available-tools=`, disables built-in MCPs,
  remote control, remote export, Bash environment loading, and automatic temp
  access. It no longer passes `--allow-all-tools` or `--no-ask-user`.
- The Copilot child receives an allowlist of runtime and authentication
  variables. It does not inherit arbitrary repository or user secrets. The
  runtime-contract negative control proves the old allow-all plus inherited-env
  shape can write a marker and read a credential-shaped canary, while the
  production shape does neither.
- A real Copilot CLI 1.0.78 ACP call confirmed three properties in one run:
  the fixture fragment was absent from `/proc/<pid>/cmdline`, a requested file
  marker was not created, and the canary value was absent from the answer.
- Suppress `TimeoutExpired` as an exception cause. Even after moving prompt
  text off argv, a future launcher regression must not place a prompt-bearing
  command in a persisted traceback.

## Provider error and harness stop policy (2026-08-04)

- Provider HTTP and SDK response bodies never enter exceptions. Preserve only
  the HTTP status and a fixed category such as `auth`, `rate_limit`,
  `client_error`, or `server_error`; suppress the provider exception cause.
  Tests serialize both judge reasoning and error fields and scan the full
  traceback for a credential shape and a fixture fragment.
- Every eval entrypoint that recovers ordinary provider failures must re-raise
  `MalformedProviderMetadataError` first. The model panel recovers the typed
  stop from its child through a fixed class-name event and stops the matrix.
  The consolidated wiring suite asserts one call for 11 entrypoint boundaries.
- Keep `MalformedProviderMetadataError` in `_eval_errors.py`. Script-style
  tests reload `_eval_common`; defining the class there split exception
  identity between cached normalizers and freshly loaded retry adapters.
- Validate mechanism-response metadata immediately after `_call_api`, before
  sleeping or starting any judge sample. A malformed response must consume
  zero judge calls.
- Resolve one absolute Copilot session-state root before process launch.
  Precedence is `COPILOT_SESSION_STATE_DIR`, then
  `COPILOT_HOME/session-state`, then `~/.copilot/session-state`. Pass that root
  to both the child environment and transcript reader.
- ACP JSON-RPC error messages are inspected only to select a fixed category.
  Authentication maps to `authentication failed`, which the adapter treats as
  non-transient. Join both stdout and stderr reader threads after the process
  exits and before constructing a classified failure.
- Anthropic 404 and model-preflight errors must not include the requested model
  id or any id returned by the provider. Direct model-list queries may return
  ids to their explicit caller; durable error text may not.
- Model-panel child propagation parses each stderr line as JSON and accepts
  only the exact `{"level":"error","event":"MalformedProviderMetadataError"}`
  object. A prose substring is not a typed event.
- Retry budgets are exact positive integers. Reject booleans, floats, strings,
  zero, and negative values before transport resolution or retry loops.
- Start ACP children in an isolated process group. Descendants can retain
  inherited stdout and stderr after the direct child exits, so reader joins
  must be bounded and cleanup must terminate the process tree.
- Enforce protocol bytes before enqueueing, bound the queue, carry protocol
  and answer counters across the full ACP session, and cap prompt bytes before
  process launch. Stdin writes and process shutdown share the session deadline.
- On Windows, create the child suspended, attach a kill-on-close Job Object,
  then resume. Use reparse-safe handles and final-path containment for the
  transcript root, session directory, and events file.
- Enumerate every session directory entry under a deadline. Apply the entry
  cap to all entries, the candidate cap only to fresh regular transcripts, and
  read JSONL with bounded `readline` calls.
- Reject symlinked or non-regular transcript components. POSIX opens each path
  component with `dir_fd` and `O_NOFOLLOW`; Windows validates root, session,
  and file handles against reparse points and final-path containment.
- Reject non-real, non-finite, and non-positive timeouts. Cleanup must force
  kill and reap children, then fail if any reader remains live.
- Close stdin only after its writer exits. On POSIX, observe child exit with
  `waitid(..., WNOWAIT)`, terminate the process group, then reap the leader so
  PID reuse cannot target an unrelated group.
- Close transcript descriptors when metadata reads or parent-directory closes
  fail. Empty and non-text provider errors must redact requested model IDs.
- The default home-derived session root must be absolute, just like explicit
  session and Copilot home overrides. A relative home resolves differently in
  the parent checkout and the isolated child working directory.

## Notes for Review (LOW confidence)

- The verdict-vocabulary confound (harness forces IDENTIFY|OK|ESCALATE) is the single biggest measurement-noise source; fixture-design workaround (score behavioural regex, not verdict token) is documented in agent-prompt-optimization-observations.md.
