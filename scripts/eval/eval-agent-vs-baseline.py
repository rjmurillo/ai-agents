#!/usr/bin/env python3
"""Eval Agent vs. Baseline runner.

DESIGN-004 §5. Pipeline:

    CLI -> FixtureValidator -> PlanRunner ->
        (dry-run path: print plan, exit)
    or
        (live path: AnthropicAPIAdapter + ScoringEngine + RunPersistence)

T4-1 shipped scaffolding (validator, plan runner, scoring engine).
T4-2 wires the live run loop with retry, idempotency, and `--resume`.
T4-3 adds report aggregation + writing.

Exit codes (AGENTS.md):
    0 = success
    1 = logic error / duplicate run / flakiness halt
    2 = config / fixture invalid
    3 = external (API) failure
    4 = auth
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any, cast

from _eval_agent_types import (
    SCHEMA_VERSION,
    Assertion,
    AssertionKind,
    AssertionResult,
    Fixture,
    FixtureValidationError,
    ProvenanceLiteral,
    RunRecord,
    SchemaVersionError,
    VariantLiteral,
)
from _eval_api_adapter import AnthropicAPIAdapter, APICallResult
from _plan_runner import (
    FORM_FACTOR_VARIANTS,
    VARIANTS,
    PlanRunner,
    UnsupportedModelError,
)
from _report_aggregator import EmptyRunError, ReportAggregator, compute_form_factor
from _report_writer import ReportWriter
from _run_persistence import (
    DuplicateRunError,
    MalformedRunRecordError,
    RunDirectoryNotFreshError,
    RunPersistence,
)
from _scoring_engine import build_default_engine

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3
EXIT_AUTH = 4

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_N_RUNS = 3
ALLOWED_PROVENANCE = frozenset(
    {"synthetic", "public-cve", "paraphrased-from-public"}
)
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9_:-]{0,63}$")

REPO_ROOT = Path(__file__).resolve().parents[2]

# DESIGN-004 §Technology Decisions: deliberately naive baseline. Role-
# neutralization only. The output-shape contract (verdict vocabulary and
# brief-explanation cap) is in OUTPUT_SHAPE_SUFFIX below and applied to
# the user message identically for BOTH variants, so specialization (the
# system prompt) is the only free variable. See
# .agents/critique/SPIKE-1854-methodology-diagnosis.md for the rationale.
BASELINE_PROMPT = "Review the following input."
BASELINE_PROMPT_REF = "<baseline>"

# Shared output-shape contract appended to the user message for BOTH
# variants. The verdict scorer (`_scoring_engine.VerdictScorer`) is
# anchored at the start of the response, so both variants must be told
# to lead with the verdict token. Without this symmetry, an agent whose
# system prompt teaches a different vocabulary (e.g. REJECTED, [PASS])
# scores zero by structure, not by quality.
OUTPUT_SHAPE_SUFFIX = (
    "\n\nBegin your response with exactly one word: IDENTIFY, OK, or "
    "ESCALATE. Then briefly explain in <=80 words."
)
OUTPUT_SHAPE_SUFFIX_REF = "<output-shape-suffix>"

# The agent prompt is sourced from the canonical template path. SHA is
# computed from the file content (UTF-8, no trailing newline trim).
AGENT_PROMPT_REF_TEMPLATE = "templates/agents/{agent}.shared.md"

# Issue #1875: the `skill` variant sources its content from a SKILL.md. The
# default path mirrors the agent name (`security` -> `security-review`); an
# operator can override with `--skill-path`. The same SHA convention as the
# agent prompt applies.
SKILL_PROMPT_REF_TEMPLATE = ".claude/skills/{agent}-review/SKILL.md"

# Error rate cap (REQ-004 AC-3). Above this, the runner exits 1 before
# generating a report. Expressed as the fraction of successful records.
MAX_ERROR_RATE = 0.10

RUNS_DIR_TEMPLATE = "evals/{agent}-spike/runs/{run_id}"
REPORTS_DIR_TEMPLATE = "evals/{agent}-spike/reports"

# CWE-22 mitigation: `--agent`, `--run-id`, and `--resume` all flow into
# filesystem path templates above (templates/agents/<agent>.shared.md,
# evals/<agent>-spike/runs/<run_id>/...). An attacker-controlled value
# could escape REPO_ROOT. Restrict to strict allow-list regexes at parse
# time. Defense in depth: resolved paths are also re-checked against
# REPO_ROOT before any filesystem access (see `_assert_under_repo_root`).
_AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")
# Run IDs are produced by `_generate_run_id` as ISO8601 + UUID4 hex; allow
# the same shape plus a small alphanumeric/underscore extension for
# operator-supplied identifiers.
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
# `--skill-path` flows into REPO_ROOT / <path>. Restrict to a repo-relative
# path under `.claude/skills/` ending in `SKILL.md`; the resolved path is
# re-checked against REPO_ROOT in `_read_skill_prompt`. No `..`, no leading
# slash, no backslash.
_SKILL_PATH_RE = re.compile(
    r"^\.claude/skills/[A-Za-z0-9][A-Za-z0-9._/-]{0,127}/SKILL\.md$"
)


def _agent_name_arg(value: str) -> str:
    """argparse `type=` validator. Returns `value` if it matches the agent
    allow-list; raises `argparse.ArgumentTypeError` otherwise."""
    if not _AGENT_NAME_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"--agent must match {_AGENT_NAME_RE.pattern} (got {value!r})"
        )
    return value


def _run_id_arg(value: str) -> str:
    """argparse `type=` validator for `--run-id` and `--resume`. Same
    threat model as `_agent_name_arg`: raw input flows into directory
    templates that are joined to REPO_ROOT."""
    if not _RUN_ID_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"run id must match {_RUN_ID_RE.pattern} (got {value!r})"
        )
    return value


def _skill_path_arg(value: str) -> str:
    """argparse `type=` validator for `--skill-path`. Same threat model as
    `_agent_name_arg`: the value is joined to REPO_ROOT to read a SKILL.md."""
    has_control_character = any(ord(char) < 32 for char in value)
    if (
        has_control_character
        or Path(value).is_absolute()
        or ".." in value
        or not _SKILL_PATH_RE.match(value)
    ):
        raise argparse.ArgumentTypeError(
            f"--skill-path must match {_SKILL_PATH_RE.pattern} with no '..' "
            f"(got {value!r})"
        )
    return value


def _assert_under_repo_root(path: Path) -> Path:
    """Raise FileNotFoundError if `path` resolves outside REPO_ROOT.
    Defense-in-depth against path-traversal in case the allow-list above
    is ever loosened. Does not require `path` to exist."""
    repo_root = REPO_ROOT.resolve()
    try:
        resolved = path.resolve(strict=False)
    except OSError as exc:
        raise FileNotFoundError(
            f"refusing to resolve path {path!s}: {exc}"
        ) from exc
    if repo_root not in (resolved, *resolved.parents):
        raise FileNotFoundError(
            f"refusing to access {resolved} (outside REPO_ROOT {repo_root})"
        )
    return resolved


# ---------------------------------------------------------------------------
# FixtureValidator (DESIGN-004 §5.2, REQ-004 AC-4)
# ---------------------------------------------------------------------------


class FixtureValidator:
    """Load and validate fixtures before any API call."""

    @staticmethod
    def validate_fixtures(paths: list[Path]) -> list[Fixture]:
        if not paths:
            raise FixtureValidationError("no fixtures supplied")
        fixtures: list[Fixture] = []
        seen_ids: dict[str, Path] = {}
        for path in paths:
            fixture = FixtureValidator._validate_one(path)
            if fixture.id in seen_ids:
                raise FixtureValidationError(
                    f"duplicate fixture id {fixture.id!r}: "
                    f"first in {seen_ids[fixture.id].name}, again in {path.name}"
                )
            seen_ids[fixture.id] = path
            fixtures.append(fixture)
        return fixtures

    @staticmethod
    def _validate_one(path: Path) -> Fixture:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise FixtureValidationError(
                f"{path.name}: cannot parse JSON ({exc})"
            ) from exc

        if not isinstance(data, dict):
            raise FixtureValidationError(f"{path.name}: top-level must be a JSON object")

        FixtureValidator._check_schema_version(path, data)
        fixture_id = FixtureValidator._require_str(path, data, "id")
        fixture_input = FixtureValidator._require_str(path, data, "input")
        provenance = FixtureValidator._require_provenance(path, data)
        assertions = FixtureValidator._require_assertions(path, fixture_id, data)
        tags = FixtureValidator._validate_tags(path, fixture_id, data)

        return Fixture(
            id=fixture_id,
            input=fixture_input,
            provenance=provenance,
            assertions=assertions,
            tags=tags,
            schema_version=SCHEMA_VERSION,
        )

    @staticmethod
    def _check_schema_version(path: Path, data: dict[str, Any]) -> None:
        version = data.get("schemaVersion")
        if version != SCHEMA_VERSION:
            raise SchemaVersionError(
                f"{path.name}: schemaVersion must be {SCHEMA_VERSION}, got {version!r}"
            )

    @staticmethod
    def _require_str(path: Path, data: dict[str, Any], field: str) -> str:
        value = data.get(field)
        if not isinstance(value, str) or not value:
            raise FixtureValidationError(
                f"{path.name}: missing or empty required field '{field}'"
            )
        return value

    @staticmethod
    def _require_provenance(path: Path, data: dict[str, Any]) -> ProvenanceLiteral:
        provenance = data.get("provenance")
        # `provenance` may be any JSON-decoded type; non-hashable values
        # (list, dict) would raise TypeError on `in frozenset[str]`. Guard
        # before the membership check so callers get a typed validation
        # error instead of a generic TypeError.
        if not isinstance(provenance, str) or provenance not in ALLOWED_PROVENANCE:
            raise FixtureValidationError(
                f"{path.name}: provenance must be one of {sorted(ALLOWED_PROVENANCE)}, "
                f"got {provenance!r}"
            )
        return cast(ProvenanceLiteral, provenance)

    @staticmethod
    def _require_assertions(
        path: Path, fixture_id: str, data: dict[str, Any]
    ) -> list[Assertion]:
        raw = data.get("assertions")
        if not isinstance(raw, list) or not raw:
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): 'assertions' must be a non-empty list"
            )
        result: list[Assertion] = []
        for index, item in enumerate(raw):
            result.append(
                FixtureValidator._validate_assertion(path, fixture_id, index, item)
            )
        return result

    @staticmethod
    def _validate_assertion(
        path: Path, fixture_id: str, index: int, item: Any
    ) -> Assertion:
        if not isinstance(item, dict):
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): assertions[{index}] must be an object"
            )
        kind_raw = item.get("kind")
        try:
            kind = AssertionKind(kind_raw)
        except ValueError as exc:
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): assertions[{index}].kind={kind_raw!r} "
                f"must be one of {[k.value for k in AssertionKind]}"
            ) from exc
        pattern = item.get("pattern")
        expected_value = item.get("expected_value")
        normalized_pattern = pattern if isinstance(pattern, str) else None
        normalized_expected = (
            expected_value if isinstance(expected_value, str) else None
        )

        # Reject malformed regex patterns at fixture-load time so a bad
        # fixture cannot consume an API call before failing at score
        # time. `Assertion.__post_init__` enforces kind-vs-field shape;
        # this layer adds compile-time validation of the regex.
        if kind is AssertionKind.REGEX and normalized_pattern is not None:
            try:
                re.compile(normalized_pattern)
            except re.error as exc:
                raise FixtureValidationError(
                    f"{path.name} ({fixture_id}): assertions[{index}].pattern "
                    f"is not a valid regex ({exc})"
                ) from exc
        if kind is AssertionKind.VERDICT and not normalized_expected:
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): assertions[{index}].expected_value "
                f"must be a non-empty string for verdict assertions"
            )

        try:
            return Assertion(
                kind=kind,
                pattern=normalized_pattern,
                expected_value=normalized_expected,
            )
        except ValueError as exc:
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): assertions[{index}] {exc}"
            ) from exc

    @staticmethod
    def _validate_tags(
        path: Path, fixture_id: str, data: dict[str, Any]
    ) -> list[str]:
        raw = data.get("tags", [])
        if not isinstance(raw, list):
            raise FixtureValidationError(
                f"{path.name} ({fixture_id}): 'tags' must be a list"
            )
        for tag in raw:
            if not isinstance(tag, str) or not TAG_RE.match(tag):
                raise FixtureValidationError(
                    f"{path.name} ({fixture_id}): invalid tag {tag!r}; "
                    f"must match {TAG_RE.pattern}"
                )
        return list(raw)


# ---------------------------------------------------------------------------
# Helpers shared by run loop and report (T4-3 will reuse).
# ---------------------------------------------------------------------------


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_agent_prompt(agent: str) -> tuple[str, str]:
    """Return (prompt_text, prompt_ref). Raises FileNotFoundError on miss."""
    rel = AGENT_PROMPT_REF_TEMPLATE.format(agent=agent)
    path = _assert_under_repo_root(REPO_ROOT / rel)
    if not path.exists():
        raise FileNotFoundError(
            f"agent prompt not found at {path} (looked for {agent}.shared.md)"
        )
    return path.read_text(encoding="utf-8"), rel


def _read_skill_prompt(agent: str, skill_rel: str | None) -> tuple[str, str]:
    """Return (skill_text, skill_ref) for the `skill` variant (Issue #1875).

    `skill_rel`, when given, is the operator-supplied `--skill-path` (already
    validated against the path allow-list and re-checked under REPO_ROOT
    here). When None, the default mirrors the agent name
    (`.claude/skills/<agent>-review/SKILL.md`). Raises FileNotFoundError on
    miss so the runner exits config (2) rather than ship a skill-variant run
    with no skill content.
    """
    rel = skill_rel if skill_rel is not None else SKILL_PROMPT_REF_TEMPLATE.format(
        agent=agent
    )
    path = _assert_under_repo_root(REPO_ROOT / rel)
    if not path.exists():
        raise FileNotFoundError(
            f"skill prompt not found at {path} (looked for {rel}). The skill "
            "variant needs a SKILL.md; create it or pass --skill-path."
        )
    return path.read_text(encoding="utf-8"), rel


def _fixture_sha(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def _fixture_set_sha(paths: list[Path]) -> str:
    """SHA-256 of the joined `<filename>:<file_sha>` lines, sorted by filename.

    DESIGN-004 §5.6 schema: stable identifier for the corpus across reruns
    that allows the report consumer to verify that two runs hit the same set.
    """
    lines = sorted(f"{p.name}:{_fixture_sha(p)}" for p in paths)
    return _sha256_text("\n".join(lines))


def _generate_run_id() -> str:
    """ISO8601 compact timestamp + UUID4 short tail. Collision-free by construction."""
    now = _dt.datetime.now(_dt.timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid.uuid4().hex[:8]
    return f"{stamp}-{suffix}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_fixture_paths(fixtures_dir: Path) -> list[Path]:
    if not fixtures_dir.exists() or not fixtures_dir.is_dir():
        raise FileNotFoundError(f"no fixtures found at {fixtures_dir}")
    paths = sorted(fixtures_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"no fixtures found at {fixtures_dir}")
    return paths


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval-agent-vs-baseline",
        description="Eval the agent prompt vs. a generic baseline prompt.",
    )
    parser.add_argument(
        "--agent",
        required=True,
        type=_agent_name_arg,
        help="agent name (allow-listed; e.g. security)",
    )
    parser.add_argument(
        "--fixtures",
        required=True,
        type=Path,
        help="directory of fixture JSON files",
    )
    parser.add_argument(
        "--n-runs",
        type=int,
        default=DEFAULT_N_RUNS,
        help=f"runs per (fixture, variant) (default: {DEFAULT_N_RUNS})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"model id (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate fixtures and print plan; no API calls",
    )
    parser.add_argument(
        "--include-skill",
        action="store_true",
        help=(
            "Issue #1875: add the `skill` variant (parent-inline SKILL.md) "
            "alongside agent and baseline so the report computes the three "
            "pairwise CIs (agent-baseline, skill-baseline, agent-skill)"
        ),
    )
    parser.add_argument(
        "--skill-path",
        default=None,
        type=_skill_path_arg,
        help=(
            "repo-relative path to the SKILL.md for the skill variant "
            "(default: .claude/skills/<agent>-review/SKILL.md). Implies "
            "--include-skill"
        ),
    )
    parser.add_argument(
        "--run-id",
        default=None,
        type=_run_id_arg,
        help="run id (default: ISO8601 + UUID4); used by RunPersistence",
    )
    parser.add_argument(
        "--resume",
        default=None,
        type=_run_id_arg,
        metavar="RUN_ID",
        help="resume an interrupted run; skip already-completed triples",
    )
    return parser


def _print_plan(plan_lines: list[str]) -> None:
    for line in plan_lines:
        print(line)


def _build_prompt(
    variant: VariantLiteral,
    agent_prompt: str,
    fixture_input: str,
    skill_prompt: str | None = None,
) -> tuple[str, str]:
    """Compose the (system, user) message pair for a variant.

    Agent variant: system = agent prompt; user = fixture input + suffix.
    Baseline variant: system = baseline prompt; user = fixture input + suffix.
    Skill variant (Issue #1875): system = SKILL.md content; user = fixture
    input + suffix. The skill content is the same domain knowledge the agent
    carries, delivered as a single parent-inline call rather than a subagent
    dispatch. The system prompt remains the only free variable across all
    three variants.
    OUTPUT_SHAPE_SUFFIX is appended to the user message for ALL variants so
    the verdict-vocabulary contract is symmetric.
    Returns (system, user_prompt) so token estimates split cleanly.
    """
    user_prompt = fixture_input + OUTPUT_SHAPE_SUFFIX
    if variant == "agent":
        return agent_prompt, user_prompt
    if variant == "skill":
        if skill_prompt is None:
            raise ValueError(
                "skill variant requires skill_prompt; pass --skill-path or "
                "--include-skill so the runner reads the SKILL.md content"
            )
        return skill_prompt, user_prompt
    return BASELINE_PROMPT, user_prompt


def _resolve_prompt_metadata(
    variant: str,
    agent_prompt: str,
    agent_prompt_ref: str,
    skill_prompt: str | None = None,
    skill_prompt_ref: str | None = None,
) -> tuple[str, str]:
    """(prompt_sha, prompt_ref) for the variant. Same SHA convention for all."""
    if variant == "agent":
        return _sha256_text(agent_prompt), agent_prompt_ref
    if variant == "skill":
        if skill_prompt is None or skill_prompt_ref is None:
            raise ValueError(
                "skill variant requires skill_prompt and skill_prompt_ref"
            )
        return _sha256_text(skill_prompt), skill_prompt_ref
    return _sha256_text(BASELINE_PROMPT), BASELINE_PROMPT_REF


def _execute_one(
    *,
    fixture: Fixture,
    fixture_path: Path,
    variant: str,
    run_index: int,
    model_id: str,
    agent_prompt: str,
    agent_prompt_ref: str,
    adapter: AnthropicAPIAdapter,
    scoring_engine,
    skill_prompt: str | None = None,
    skill_prompt_ref: str | None = None,
) -> RunRecord:
    """Run one (fixture, variant, run_index) call and score the result."""
    system, user = _build_prompt(
        variant, agent_prompt, fixture.input, skill_prompt=skill_prompt
    )
    prompt_sha, prompt_ref = _resolve_prompt_metadata(
        variant,
        agent_prompt,
        agent_prompt_ref,
        skill_prompt=skill_prompt,
        skill_prompt_ref=skill_prompt_ref,
    )
    fixture_sha = _fixture_sha(fixture_path)

    api_result: APICallResult = adapter.call_model(
        prompt=user,
        model_id=model_id,
        fixture_id=fixture.id,
        variant=variant,
        run_index=run_index,
        system=system,
    )

    if api_result.outcome == "success" and api_result.raw_response is not None:
        scored = scoring_engine.score_all(fixture.assertions, api_result.raw_response)
    else:
        # Record the assertion shape with passed=False so downstream
        # aggregation can decide to count or exclude per AC-3.
        scored = [
            _make_failed_assertion_result(a) for a in fixture.assertions
        ]

    return RunRecord(
        fixture_id=fixture.id,
        variant=variant,
        run_index=run_index,
        model_id=model_id,
        prompt_sha=prompt_sha,
        prompt_ref=prompt_ref,
        fixture_sha=fixture_sha,
        raw_response=api_result.raw_response,
        assertions=scored,
        outcome=api_result.outcome,
        latency_ms=api_result.latency_ms,
        tokens_in=api_result.tokens_in,
        tokens_out=api_result.tokens_out,
        error_category=api_result.error_category,
        attempts=api_result.attempts,
        tokens_estimated=getattr(api_result, "tokens_estimated", True),
    )


def _make_failed_assertion_result(assertion: Assertion) -> AssertionResult:
    """Construct an AssertionResult representing 'not scored, treat as failed'.

    Used when the API call errored; the caller decides via outcome whether
    to count this in `recall_with_errors` vs `recall_excluding_errors`.
    """
    return AssertionResult(
        kind=assertion.kind,
        pattern=assertion.pattern,
        expected_value=assertion.expected_value,
        passed=False,
        extracted=None,
    )


def _run_live(
    *,
    args: argparse.Namespace,
    fixtures: list[Fixture],
    fixture_paths: list[Path],
    plan,
) -> int:
    """Execute the live run loop. Returns exit code."""
    try:
        agent_prompt, agent_prompt_ref = _read_agent_prompt(args.agent)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    # Issue #1875: when the plan includes the `skill` variant, read its
    # SKILL.md content once. A missing skill file is a config error, the same
    # class as a missing agent prompt.
    skill_prompt: str | None = None
    skill_prompt_ref: str | None = None
    if "skill" in plan.variants:
        try:
            skill_prompt, skill_prompt_ref = _read_skill_prompt(
                args.agent, args.skill_path
            )
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG

    if args.resume and args.run_id and args.run_id != args.resume:
        print(
            "error: --run-id and --resume cannot specify different ids",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    run_id = args.resume or args.run_id or _generate_run_id()
    run_dir = _assert_under_repo_root(
        REPO_ROOT / RUNS_DIR_TEMPLATE.format(agent=args.agent, run_id=run_id)
    )

    try:
        persistence = RunPersistence(run_dir, resume=bool(args.resume))
    except RunDirectoryNotFreshError as exc:
        # Fresh-run mode is forbidden against a populated runs.jsonl.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LOGIC
    except DuplicateRunError as exc:
        # Bad existing JSONL detected at startup.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_LOGIC
    except (SchemaVersionError, MalformedRunRecordError) as exc:
        # Existing JSONL carries an unsupported schemaVersion, or a
        # line cannot be parsed back into a record. Per DESIGN-004
        # §Failure Modes, both are config-class failures: the on-disk
        # data needs operator repair before the runner can proceed.
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    fixture_path_by_id = {f.id: p for f, p in zip(fixtures, fixture_paths)}
    adapter = AnthropicAPIAdapter()
    engine = build_default_engine()

    import time as _time
    wall_start = _time.monotonic()
    error_count = 0
    total_records = 0
    resume_skips_count = 0
    # REQ-004 AC-3: the >10% halt threshold is computed per fixture, not
    # per record. A localized outage that errors every variant/run for
    # one fixture out of ten matches the spec at 10% even though the
    # per-record fraction may be much higher; conversely, scattered
    # transient errors across many fixtures must not silently slip under
    # the gate. Track unique fixture IDs that touched the runner and
    # those that produced at least one `outcome="error"`.
    executed_fixtures: set[str] = set()
    fixtures_with_errors: set[str] = set()

    for fixture in plan.fixtures:
        fixture_path = fixture_path_by_id[fixture.id]
        for variant in plan.variants:
            for run_index in range(plan.n_runs):
                # Pre-call skip is only valid under --resume. In fresh-run
                # mode, RunDirectoryNotFreshError already prevented us from
                # opening a populated dir, so `is_completed` cannot be True.
                # Guarding here keeps the contract explicit.
                if args.resume and persistence.is_completed(
                    fixture.id, variant, run_index
                ):
                    print(
                        json.dumps(
                            {
                                "level": "info",
                                "event": "resume_skip",
                                "fixture_id": fixture.id,
                                "variant": variant,
                                "run_index": run_index,
                            }
                        ),
                        file=sys.stderr,
                    )
                    resume_skips_count += 1
                    total_records += 1
                    continue
                try:
                    record = _execute_one(
                        fixture=fixture,
                        fixture_path=fixture_path,
                        variant=variant,
                        run_index=run_index,
                        model_id=plan.model_id,
                        agent_prompt=agent_prompt,
                        agent_prompt_ref=agent_prompt_ref,
                        adapter=adapter,
                        scoring_engine=engine,
                        skill_prompt=skill_prompt,
                        skill_prompt_ref=skill_prompt_ref,
                    )
                except RuntimeError as exc:
                    # Defense in depth: prior to commit 0df0f324 the
                    # adapter propagated `RuntimeError` from
                    # `load_api_key()`; that was caught here and mapped
                    # to `EXIT_AUTH`. The adapter now returns
                    # `APICallResult(error_category="auth")` instead, so
                    # this branch is reached only by genuinely
                    # unexpected propagation. Keep the substring match
                    # as a safety net for any future construction-time
                    # raise the adapter does not categorize.
                    if "ANTHROPIC_API_KEY" in str(exc):
                        print(
                            json.dumps(
                                {
                                    "level": "error",
                                    "event": "auth_failure",
                                    "message": str(exc),
                                }
                            ),
                            file=sys.stderr,
                        )
                        return EXIT_AUTH
                    raise
                # Adapter-categorized auth failure (transport
                # construction failed; today: missing
                # `ANTHROPIC_API_KEY`). Honor the AGENTS.md exit-code
                # contract: auth-class errors exit with `EXIT_AUTH`.
                if record.error_category == "auth":
                    print(
                        json.dumps(
                            {
                                "level": "error",
                                "event": "auth_failure",
                                "fixture_id": record.fixture_id,
                                "variant": record.variant,
                                "run_index": record.run_index,
                            }
                        ),
                        file=sys.stderr,
                    )
                    return EXIT_AUTH
                try:
                    persistence.write_record(record)
                except DuplicateRunError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return EXIT_LOGIC
                except SchemaVersionError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    return EXIT_CONFIG
                executed_fixtures.add(fixture.id)
                if record.outcome == "error":
                    error_count += 1
                    fixtures_with_errors.add(fixture.id)
                total_records += 1

    if resume_skips_count > 0:
        print(
            json.dumps(
                {
                    "level": "info",
                    "event": "resume_skip_summary",
                    "resume_skips_count": resume_skips_count,
                }
            ),
            file=sys.stderr,
        )

    wall_clock_seconds = _time.monotonic() - wall_start

    executed_records = total_records - resume_skips_count
    if executed_fixtures:
        # Per-fixture error rate: REQ-004 AC-3. Keep `error_count` and
        # `executed_records` in the structured log so operators can
        # correlate with the per-record counts in the report.
        fixtures_with_errors_count = len(fixtures_with_errors)
        executed_fixtures_count = len(executed_fixtures)
        error_rate = fixtures_with_errors_count / executed_fixtures_count
        if error_rate > MAX_ERROR_RATE:
            print(
                json.dumps(
                    {
                        "level": "error",
                        "message": (
                            "fixture-level error rate exceeds 10%; "
                            "halting before report"
                        ),
                        "fixtures_with_errors": fixtures_with_errors_count,
                        "executed_fixtures": executed_fixtures_count,
                        "error_count": error_count,
                        "executed_records": executed_records,
                        "error_rate": round(error_rate, 4),
                    }
                ),
                file=sys.stderr,
            )
            return EXIT_LOGIC

    return _generate_report(
        records=list(persistence.iter_records()),
        run_id=run_id,
        model_id=plan.model_id,
        agent=args.agent,
        agent_prompt=agent_prompt,
        fixture_paths=fixture_paths,
        wall_clock_seconds=wall_clock_seconds,
        run_dir=run_dir,
        persistence=persistence,
        error_count=error_count,
    )


def _generate_report(
    *,
    records: list[RunRecord],
    run_id: str,
    model_id: str,
    agent: str,
    agent_prompt: str,
    fixture_paths: list[Path],
    wall_clock_seconds: float,
    run_dir: Path,
    persistence: RunPersistence,
    error_count: int,
) -> int:
    """Aggregate records and write report. Halts on >30% flakiness."""
    aggregator = ReportAggregator(records, model_id=model_id)
    try:
        aggregate = aggregator.aggregate()
    except EmptyRunError as exc:
        print(
            json.dumps(
                {
                    "level": "error",
                    "event": "empty_run",
                    "message": str(exc),
                    "run_id": run_id,
                }
            ),
            file=sys.stderr,
        )
        return EXIT_LOGIC
    except UnsupportedModelError as exc:
        print(
            json.dumps(
                {
                    "level": "error",
                    "event": "unsupported_model",
                    "message": str(exc),
                    "model_id": model_id,
                }
            ),
            file=sys.stderr,
        )
        return EXIT_CONFIG
    form_factor = None
    if any(record.variant == "skill" for record in records):
        try:
            form_factor = compute_form_factor(records)
        except (EmptyRunError, ValueError) as exc:
            print(
                json.dumps(
                    {
                        "level": "error",
                        "event": "form_factor_invalid",
                        "message": str(exc),
                        "run_id": run_id,
                    }
                ),
                file=sys.stderr,
            )
            return EXIT_LOGIC

    # Halt-due-to-flakiness is a verdict per ADR-058 amendment 3. Emit
    # the report (with `recommendation="halt-due-to-flakiness"`) before
    # returning EXIT_LOGIC so the audit trail is reproducible from the
    # runner; without this, halt-flakiness produces no committed
    # artifact and the v2 spike report has to be hand-curated.
    halt = aggregate.halt_due_to_flakiness
    writer = ReportWriter(
        _assert_under_repo_root(REPO_ROOT / REPORTS_DIR_TEMPLATE.format(agent=agent))
    )
    json_path, md_path = writer.write(
        aggregate=aggregate,
        run_id=run_id,
        model_id=model_id,
        agent_prompt_sha=_sha256_text(agent_prompt),
        baseline_prompt_sha=_sha256_text(BASELINE_PROMPT),
        fixture_set_sha=_fixture_set_sha(fixture_paths),
        wall_clock_seconds=wall_clock_seconds,
        recommendation="halt-due-to-flakiness" if halt else None,
        form_factor=form_factor,
    )
    if halt:
        print(
            json.dumps(
                {
                    "level": "error",
                    "message": (
                        "flaky fixture count reached the N-aware halt "
                        "threshold; methodology unstable"
                    ),
                    "flaky_fixtures": aggregate.flaky_fixtures_detected,
                    "report_json": str(json_path),
                    "report_md": str(md_path),
                    # Informational metrics: even though halt blocks the
                    # graduate/keep/scrap verdict, operators still want
                    # the recall numbers and CI for the audit trail.
                    "informational_metrics": {
                        "agent_recall": aggregate.agent_recall,
                        "baseline_recall": aggregate.baseline_recall,
                        "recall_delta": aggregate.recall_delta,
                        "bootstrap_ci_95": list(aggregate.bootstrap_ci_95),
                        "recall_with_errors": aggregate.recall_with_errors,
                        "recall_excluding_errors": aggregate.recall_excluding_errors,
                        "total_tokens_in": aggregate.total_tokens_in,
                        "total_tokens_out": aggregate.total_tokens_out,
                        "cost_estimate_usd": aggregate.cost_estimate_usd,
                        "error_count": aggregate.error_count,
                    },
                }
            ),
            file=sys.stderr,
        )
        return EXIT_LOGIC
    if aggregate.flaky_halt_threshold_crossed:
        # Flag-and-continue: the flaky count crossed AC-10's "more than
        # 30%" gate but the halt was suppressed. Surface the crossing so
        # the flag in "flag-and-continue" is not lost when the process
        # exits; the run still completes on the stable subset.
        print(
            json.dumps(
                {
                    "level": "warning",
                    "event": "flaky_halt_threshold_crossed",
                    "message": (
                        "flaky fixture count crossed the N-aware halt "
                        "threshold but flag-and-continue suppressed the "
                        "halt; verdict is provisional"
                    ),
                    "flaky_fixtures": aggregate.flaky_fixtures_detected,
                    "flaky_fixtures_excluded": aggregate.flaky_fixtures_excluded,
                    "report_json": str(json_path),
                    "report_md": str(md_path),
                }
            ),
            file=sys.stderr,
        )
    print(
        json.dumps(
            {
                "level": "info",
                "message": "run complete; report written",
                "run_id": run_id,
                "run_dir": str(run_dir),
                "report_json": str(json_path),
                "report_md": str(md_path),
                "written": persistence.written_count(),
                "skipped_resume": persistence.skipped_count(),
                "errors": error_count,
            }
        ),
        file=sys.stderr,
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    try:
        paths = _load_fixture_paths(args.fixtures)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    try:
        fixtures = FixtureValidator.validate_fixtures(paths)
    except (FixtureValidationError, SchemaVersionError) as exc:
        print(f"fixture validation failed: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    # --skill-path implies --include-skill: supplying a path is an explicit
    # opt-in to the third variant.
    include_skill = args.include_skill or args.skill_path is not None
    variants = FORM_FACTOR_VARIANTS if include_skill else VARIANTS
    try:
        plan = PlanRunner.build_plan(
            fixtures=fixtures,
            model_id=args.model,
            n_runs=args.n_runs,
            variants=variants,
        )
    except (ValueError, UnsupportedModelError) as exc:
        print(f"plan error: {exc}", file=sys.stderr)
        return EXIT_CONFIG

    if include_skill:
        try:
            _read_skill_prompt(args.agent, args.skill_path)
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_CONFIG

    if args.dry_run:
        _print_plan(PlanRunner.format_plan_lines(plan))
        return EXIT_OK

    return _run_live(args=args, fixtures=fixtures, fixture_paths=paths, plan=plan)


if __name__ == "__main__":
    sys.exit(main())
