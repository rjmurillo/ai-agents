# ADR Review: SESSION-PROTOCOL interpreter portability (issue #3791)

/ adr-review skill, ADR Review Protocol applied to `.agents/SESSION-PROTOCOL.md`.

## Change under review

Four documented commands change interpreter token only:

| Line | Script | Module needed at import | Before | After |
|------|--------|-------------------------|--------|-------|
| 723 | `scripts/validation/pre_pr.py` | `yaml` | `python3` | `uv run python` |
| 961 | `scripts/validate_session_json.py` | `jsonschema` | `python3` | `uv run python` |
| 1111 | `scripts/validate_session_json.py` | `jsonschema` | `python3` | `uv run python` |
| 1165 | `scripts/sync_adr_protocol.py` | `yaml` | `python3` | `uv run python` |

No MUST or SHOULD requirement, gate, phase, schema, or exit-code contract changes. `grep -nE "MUST.*python3|python3.*MUST"` returns nothing, so no normative clause names the interpreter.

## Phase 0: related work

| Reference | Bearing |
|-----------|---------|
| `.claude/skills/ai-agents-generation-and-release/SKILL.md:84` | Canonical guidance, prescribes this exact fix: "Run them as `uv run python <script>` locally so the project venv supplies it. CI can invoke bare `python3` because `.github/actions/setup-code-env` installs the locked dependencies system-wide first." |
| `.claude/skills/ai-agents-build-and-env/SKILL.md:146` | Same failure mode named verbatim: bare `python3` throws `ModuleNotFoundError: No module named 'yaml'`; remedy is `uv run python`. |
| Issue #1844 (CLOSED) | Same defect class for skill scripts. |
| Issue #3806 (OPEN, P1) | CI session-protocol validate job depends on `jsonschema` from the runner image. Adjacent, not addressed here. |
| Issue #4210 (OPEN, P1) | Same defect class in a workflow. Confirms the class is live; out of scope for a docs change. |
| PR #3793 (CLOSED unmerged) | Rejected the alternative of deleting `import yaml`. Six measured divergences from `yaml.safe_load`. Settles direction as docs, not code. |

## Phase 1: independent review

**architect.** The file is protocol, and the edit touches illustrative commands, not protocol structure. Numbering, phases, and gate tables are untouched. Conforms to canonical guidance at SKILL.md:84 rather than inventing a local convention. Accept.

**critic.** Completeness: does the change fix every instance in this file? The guard reports the file at zero after the change, down from five findings; the fifth (`scripts/memory/validate_memory_sizes.py`, line 727) was a false positive, confirmed by `python3 -S` running it clean. So the file is fully migrated, not partially. Accept.

**independent-thinker.** Challenges the premise that `uv run` is strictly better. Issue #3085 records `uv run` triggering a PyPI resolve that downloaded `anthropic` and timed out in a network-restricted sandbox. If that reproduced, this change would trade a clear failure for an intermittent hang, which is worse. Tested: `UV_OFFLINE=1 uv run python -c "import yaml, jsonschema"` prints `offline OK` in this worktree, so a synced venv needs no network. CONTRIBUTING.md setup step 4 mandates `uv sync --frozen --extra dev` before any of these commands appear. Reservation stands as P2, recorded below. Accept with reservation.

**security.** No trust boundary, credential, or input-validation surface. `uv run` executes the project environment defined by the committed `pyproject.toml` and `uv.lock`, which is a narrower and more auditable supply chain than an ambient system interpreter of unknown provenance. Accept.

**analyst.** Root cause confirmed by direct reproduction, not inference: `python3 -S scripts/sync_adr_protocol.py` exits with `ModuleNotFoundError: No module named 'yaml'` at line 24; `python3 -S scripts/validate_session_json.py` fails at line 39 on `jsonschema`. Post-change, `uv run python scripts/sync_adr_protocol.py` completes and prints a result line. Accept.

**high-level-advisor.** Proportionality: a four-token docs edit carrying no semantic change does not warrant deferral. The competing risk (leaving a mandatory documented step broken on a clean machine) is larger than the residual risk the independent-thinker names. Accept.

## Phase 2: consolidation

Consensus 6/6 Accept, one recorded reservation. No Zimmermann anti-pattern triggered: every lens produced a substantive finding, none editorial-only, none re-raised across rounds.

Disclosure on method: this review was conducted by applying the six lenses directly rather than by spawning six separate agents, because the Task tool is not available in this execution context. That makes it a single-reasoner review, which is weaker than independent agents on correlated blind spots. The mitigation is that every load-bearing claim above is grounded in a command output or a quoted file line rather than in reasoning alone.

## Phase 3: issues

| ID | Priority | Issue | Resolution |
|----|----------|-------|------------|
| 1 | P2 | `uv run` resolves dependencies if the venv is not synced, which issue #3085 saw hit PyPI and time out offline | Documented. `UV_OFFLINE=1 uv run python` verified working here; CONTRIBUTING.md step 4 mandates `uv sync --frozen --extra dev` first. No blocking action. |
| 2 | P2 | Issues #3806 and #4210 carry the same defect class in CI and workflow surfaces | Out of scope. This change is documentation only; workflow invocations are correct bare because `setup-code-env` installs locked deps system-wide (SKILL.md:84). |

No P0. No P1.

## Phase 4: strategic review

- **Chesterton's Fence**: PASS. The bare `python3` form predates the uv-managed environment. Its original purpose (name the system interpreter) no longer holds now that dependencies are declared in `pyproject.toml` and resolved by uv.
- **Path Dependence**: PASS. Fully reversible; a four-token text edit with no migration or lock-in.
- **Core vs Context**: N/A. Documentation accuracy, not a build-or-buy capability.
- **Second-System Effect**: PASS. Scope is four tokens. No adjacent rewriting of protocol content.

**Strategic assessment**: APPROVED.

## Verdict

Accept. 6/6 consensus, two P2 items documented, no blocking issues.
