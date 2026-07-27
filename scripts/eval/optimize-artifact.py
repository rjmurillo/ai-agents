#!/usr/bin/env python3
"""Held-out-gated optimization rails for agents, rules, and hooks.

The optimizing agent proposes the edits. This CLI decides whether they
survive. Splitting that responsibility is the whole point: an author who
scores an edit on the material they were reading while making it learns
nothing about whether the edit generalizes, and the existing eval harness
scores exactly that way.

A loop step looks like this. Every command reads and writes JSON on stdout,
so the loop is drivable from a shell or from an agent's tool calls.

    optimize-artifact.py extract --kind agent --input report.json > base.json
    optimize-artifact.py split --results base.json --seed run-7 > split.json
    optimize-artifact.py budget --step 3 --total 12
    optimize-artifact.py buffer-check --buffer rejected.json --patches p.json
    optimize-artifact.py apply --file target.md --patches p.json --budget 3
    # rerun the real scorer here, then extract its output to cand.json
    optimize-artifact.py gate --incumbent base.json --candidate cand.json \\
        --split split.json --incumbent-fingerprint "$FP"

`gate` scores both sides itself from the split's held-out `sel` group rather
than accepting two numbers. Taking bare numbers would make the loop's most
damaging mistake, gating on optimize-set scores, a typo away at every step.

Exit codes follow ADR-035:

    0  accept, novel, or plain success
    1  reject, already-rejected, or a refused patch
    2  bad arguments, unreadable input, or malformed data

A REJECT is exit 1 because it is a decision, not a crash, and a shell loop
wants to branch on it. Every path this module reaches prints JSON, so a
caller that needs to tell REJECT from a config failure can read `decision`
instead of guessing from the code, and a config failure prints an `error`
field the same way. Argparse rejects a malformed command line before this
module runs and prints its own plain-text usage to stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from pathlib import Path
from typing import Any, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _optimizer_adapters import (  # noqa: E402
    AdapterError,
    agent_results,
    pytest_results,
    rule_results,
)
from _optimizer_core import (  # noqa: E402
    Patch,
    apply_patches,
    buffer_contains,
    edit_budget,
    gate,
    guard_refusal,
    mcnemar_exact,
    patch_fingerprint,
    score,
    split_tasks,
)

_GATE_GROUP = "sel"

EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

_GROUPS = ("opt", "sel", "test")


class ConfigError(Exception):
    """Input was unreadable or malformed. Maps to exit 2."""


class LedgerMismatchError(Exception):
    """The ledger describes a different run. A decision, not a crash.

    Raised when the recorded split fingerprint or the recorded cap disagrees
    with the invocation. Both mean the run changed underneath the budget, and
    the loop driving this CLI has to be able to branch on that, so the message
    is built here and reported verbatim rather than reassembled by the caller.
    """


def _emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"no such file: {path}") from exc
    except UnicodeDecodeError as exc:
        # UnicodeDecodeError subclasses ValueError, so `main` caught it and the
        # loop kept running, but the error document named the decoder's class
        # instead of ConfigError. `_read_text` already wraps it; two readers of
        # the same bytes reported the same failure two ways.
        raise ConfigError(f"{path} is not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        # Deeply nested arrays exhaust the decoder's stack rather than failing
        # its grammar, so this is a second exception family out of one call
        # that every caller reads as one. The gate's preflight promises it
        # cannot raise on content; leaving this uncaught let a nested file
        # crash the run ahead of an exhausted-budget refusal.
        raise ConfigError(f"{path} is nested too deeply to parse") from exc
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc


def _absent(path: Path) -> bool:
    """Whether `path` genuinely does not exist.

    `Path.exists()` cannot answer this. It returns False when the file is
    absent and also when whether it is absent is unknowable, because it
    swallows every `OSError` from `stat` and reports the same False. Callers
    that read that False as "nothing recorded yet" are right for the first
    case and quietly wrong for the second: an unreadable rejection buffer
    reads as an empty one, which un-rejects every patch in it, and an
    unreadable ledger reads as an unspent budget.

    Only `FileNotFoundError` means absent. Everything else is a config error,
    which is what `_read_json` already does one call further in, so the pair
    now reports one failure one way.
    """
    try:
        path.stat()
    except FileNotFoundError:
        return True
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc
    return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigError(f"no such file: {path}") from exc
    except UnicodeDecodeError as exc:
        # UnicodeDecodeError subclasses ValueError, not OSError, so the arm
        # below never caught it and a binary artifact crashed the loop.
        raise ConfigError(f"{path} is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc


def _covers_holdout(results: Mapping[str, Any], sel_ids: list[str]) -> bool:
    """Whether these results carry a usable verdict for every held-out task.

    The gate asks this instead of letting `score` and `mcnemar_exact` report
    what is missing, because both name the offending task ids, and the ids they
    would name are held-out ids. A fourth adversarial review (gpt-5.6-sol,
    2026-07-26) found the consequence: a candidate results file with no keys at
    all printed the entire held-out membership in one error message, and the
    error arrived before the ledger advanced, so it cost nothing.

    The answer is one bit on purpose. A count would be an oracle: `split`
    already publishes the held-out size, so "three of five missing" tells a
    caller how many of the keys it chose to omit were held out, and a few
    chosen omissions recover the membership. One bit, charged a consultation,
    is the least informative answer that still tells an honest caller what to
    fix.
    """
    return all(isinstance(results.get(task_id), bool) for task_id in sel_ids)


class ResultsFile(NamedTuple):
    """A scored task set plus the identity of the corpus it was scored against.

    The two travel together because a verdict about the first is meaningless
    without the second. `corpus` is None when the upstream scorer publishes no
    corpus identity, which is the honest answer for the rule and hook paths
    today; it is never synthesized from the task ids, because ids matching is
    exactly the condition under which a mismatched pair slips through.
    """

    results: dict[str, bool]
    corpus: str | None


_RESULTS_SCHEMA = "optimizer-results/1"

# A corpus identity is the producer's sha256 hex digest of the task set. The
# form is checked rather than taken on faith because an unchecked string makes
# the guard report success on values that identify nothing: two reports both
# carrying `fixture_set_sha: ""` compared as verified until a fifteenth review
# pointed at it. Lowercase only, because `hexdigest()` has exactly one spelling
# and accepting a second would make two names for one corpus look like two
# corpora.
_CORPUS_RE = re.compile(r"\A[0-9a-f]{64}\Z")

# A split written before the pin existed says nothing about the corpus, which is
# different from one that pinned an unknown. A sentinel keeps the two apart;
# `None` cannot, because `None` is a legal pin. JSON cannot produce this value,
# so no split file can forge an absent pin.
_UNPINNED = object()


def _checked_corpus(path: Path, value: object) -> str | None:
    """The value if it is a corpus identity, None if absent, else a refusal."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigError(f"{path} corpus must be a string or null, got {type(value).__name__}")
    if not _CORPUS_RE.match(value):
        raise ConfigError(
            f"{path} corpus is not a sha256 hex digest. A corpus identity that "
            "is not one cannot be compared against another, and an empty or "
            "truncated value would report a verified match it never made."
        )
    return value


def _read_results(path: Path) -> ResultsFile:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a JSON object of task id to boolean")
    # A bare mapping is all-boolean by construction, so a string-valued
    # `schema` is unambiguous. Keying on the presence of the word alone would
    # misread a legacy file whose task happened to be named `schema`.
    if isinstance(data.get("schema"), str):
        return _read_results_envelope(path, data)
    return ResultsFile(_checked_verdicts(path, data), None)


def _read_results_envelope(path: Path, data: dict[str, Any]) -> ResultsFile:
    schema = data["schema"]
    if schema != _RESULTS_SCHEMA:
        raise ConfigError(
            f"{path} declares schema {schema!r}, which this build cannot read; "
            f"expected {_RESULTS_SCHEMA!r}"
        )
    results = data.get("results")
    if not isinstance(results, dict):
        raise ConfigError(f"{path} envelope needs a 'results' object of task id to boolean")
    return ResultsFile(_checked_verdicts(path, results), _checked_corpus(path, data.get("corpus")))


def _corpus_header(path: Path) -> str | None:
    """The file's declared corpus, read without validating anything else.

    Best-effort on purpose: every content problem answers None rather than
    raising. This runs before the ledger lock so the corpus refusal costs
    nothing, and a read that could raise there would let a malformed verdict
    mapping answer in place of the ledger. An exhausted budget is the
    authoritative refusal and must not be masked by a parse error that the full
    read, after the guards, reports properly anyway.

    Only `OSError` escapes, and the caller runs this under `_digest_scrubbed`
    because a failing open names the file. `RecursionError` joins `ValueError`
    because a deeply nested array exhausts the decoder's stack rather than
    failing its grammar, and letting it out would break the promise above.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict) or data.get("schema") != _RESULTS_SCHEMA:
        return None
    value = data.get("corpus")
    return value if isinstance(value, str) and _CORPUS_RE.match(value) else None


def _checked_verdicts(path: Path, data: dict[str, Any]) -> dict[str, bool]:
    bad = [k for k, v in data.items() if not isinstance(v, bool)]
    if bad:
        raise ConfigError(
            f"{path} has non-boolean results for: {', '.join(sorted(bad)[:5])}"
        )
    return data


def _read_patches(path: Path) -> list[Patch]:
    data = _read_json(path)
    if not isinstance(data, list):
        raise ConfigError(f"{path} must hold a JSON array of patches")
    patches: list[Patch] = []
    for index, raw in enumerate(data):
        if not isinstance(raw, dict) or "op" not in raw:
            raise ConfigError(f"{path} patch {index} needs an 'op' key")
        patches.append(
            Patch(op=raw["op"], anchor=raw.get("anchor"), text=raw.get("text"))
        )
    if not patches:
        raise ConfigError(f"{path} holds no patches")
    return patches


def _read_split(path: Path) -> dict[str, Any]:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a split object")
    required = (*_GROUPS, "fingerprint", "seed", "sel_ratio", "test_ratio")
    missing = [key for key in required if key not in data]
    if missing:
        raise ConfigError(
            f"{path} is missing split keys: {', '.join(missing)}. A split file "
            "that cannot be re-fingerprinted cannot be verified; re-run split."
        )
    for group in _GROUPS:
        value = data[group]
        if not isinstance(value, list) or not all(isinstance(t, str) for t in value):
            raise ConfigError(
                f"{path} group '{group}' must be a list of strings"
            )
    if not isinstance(data["fingerprint"], str):
        # Same defect as the `corpus` pin below, in the same field position.
        # An unhashable fingerprint reaches a set membership test in
        # `_split_drifted` that sits one line past the `except TypeError`
        # written to catch exactly this, so it escaped on scope rather than
        # on intent. Checked here because this is where the file's shape is
        # already settled for both callers.
        raise ConfigError(
            f"{path} fingerprint must be a string, not "
            f"{type(data['fingerprint']).__name__}. A split file that cannot "
            "be re-fingerprinted cannot be verified; re-run split."
        )
    if "corpus" in data:
        # Optional, and caller-supplied like the rest of the file. Unvalidated
        # it reached the conflict rule as-is, where a list pin raised
        # `TypeError` out of a set comprehension and a truncated string named a
        # corpus that identifies nothing.
        data["corpus"] = _checked_corpus(path, data["corpus"])
    return data


def _split_drifted(split: Mapping[str, Any]) -> bool:
    """Has the split file changed since it was written?

    Redrawn from the file's own recorded inputs rather than compared against a
    value the caller passes, because a caller who forgets the flag would
    otherwise get no check at all.

    Both halves are needed and neither is redundant. The fingerprint covers the
    split's inputs (seed, task set, ratios), so it catches an added or removed
    task. It cannot catch a task moved between groups, because the union it
    hashes is unchanged by a move. Redrawing the split catches that: the draw is
    seeded, so the groups are a pure function of the inputs, and any membership
    that the recorded inputs would not produce is drift.
    """
    try:
        tasks = [str(t) for group in _GROUPS for t in split[group]]
        seed = str(split["seed"])
        raw_sel_ratio = split["sel_ratio"]
        raw_test_ratio = split["test_ratio"]
        sel_ratio = str(raw_sel_ratio)
        test_ratio = str(raw_test_ratio)
        redrawn = split_tasks(
            tasks,
            seed=seed,
            sel_ratio=sel_ratio,
            test_ratio=test_ratio,
            min_sel=int(split.get("min_sel", 3)),
        )
        compatible_fingerprints = {redrawn.fingerprint}
        if _is_json_number(raw_sel_ratio) and _is_json_number(raw_test_ratio):
            compatible_fingerprints.add(
                _legacy_numeric_split_fingerprint(
                    tasks,
                    seed=seed,
                    sel_ratio=float(raw_sel_ratio),
                    test_ratio=float(raw_test_ratio),
                )
            )
    except (TypeError, ValueError, OverflowError) as exc:
        # `OverflowError` is a sibling of `ValueError`, not a subclass, so a
        # JSON `Infinity` in `min_sel` walked through a clause written to
        # turn exactly this into a refusal.
        raise ConfigError(f"split file holds unusable seed or ratios: {exc}") from exc
    if split["fingerprint"] not in compatible_fingerprints:
        return True
    return any(sorted(getattr(redrawn, g)) != sorted(split[g]) for g in _GROUPS)


def _is_json_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _legacy_numeric_split_fingerprint(
    task_ids: list[str], *, seed: str, sel_ratio: float, test_ratio: float
) -> str:
    payload = json.dumps(
        {
            "seed": seed,
            "tasks": sorted(task_ids),
            "sel_ratio": sel_ratio,
            "test_ratio": test_ratio,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


def _rule_scenarios(payload: object) -> list[Any]:
    """Pull scenarios from a bare array or a 'scenarios' wrapper."""
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else payload
    if not isinstance(scenarios, list):
        raise ConfigError("rule input must be a scenario array or an object with 'scenarios'")
    typed: list[Any] = scenarios
    return typed


def _rule_degraded_scenario_ids(
    scenarios: Sequence[object], mechanism: str, *, prefix: str | None = None
) -> list[str]:
    degraded: list[str] = []
    for index, scenario in enumerate(scenarios, 1):
        if not isinstance(scenario, Mapping):
            continue
        raw_id = scenario.get("id") or f"S{index}"
        sid = str(raw_id)
        task_id = f"{prefix}::{sid}" if prefix is not None else sid
        mechanisms = scenario.get("mechanisms")
        if not isinstance(mechanisms, Mapping):
            degraded.append(task_id)
            continue
        mech_data = mechanisms.get(mechanism)
        if not isinstance(mech_data, Mapping) or "error" in mech_data:
            degraded.append(task_id)
            continue
        scores = mech_data.get("scores")
        if isinstance(scores, Mapping) and scores.get("judge_failed"):
            degraded.append(task_id)
        elif not isinstance(scores, Mapping) or not scores:
            # Missing or empty scores: scoring never completed. Fail closed.
            degraded.append(task_id)
    return degraded


def _refuse_degraded_rule_report(task_ids: list[str]) -> None:
    if not task_ids:
        return
    shown = ", ".join(sorted(task_ids)[:20])
    suffix = "" if len(task_ids) <= 20 else f", and {len(task_ids) - 20} more"
    raise ConfigError(
        "refusing to extract degraded rule report: "
        f"{len(task_ids)} scenario(s) have missing mechanism output, mechanism "
        f"errors, missing scores, or judge failures: {shown}{suffix}"
    )


def _extract_rules_envelope(rules: object, args: argparse.Namespace) -> dict[str, bool]:
    """Extract the multi-rule shape eval-rule-activation.py --output writes.

    Scenario ids restart at S1 inside every rule, so they are namespaced as
    `<rule>::<scenario-id>`. A live run over the seven scenario files in
    tests/evals/rule-scenarios/ produced 24 scenarios carrying only 4 distinct
    ids; merging them raw would silently drop 20 tasks, and a smaller
    denominator reads as a higher score.
    """
    if not isinstance(rules, Mapping) or not rules:
        raise ConfigError("'rules' must be a non-empty mapping of rule name to result")
    out: dict[str, bool] = {}
    degraded: list[str] = []
    for name, entry in rules.items():
        if not isinstance(entry, Mapping) or "scenarios" not in entry:
            raise ConfigError(f"rule {name!r} has no 'scenarios' list")
        scenarios = _rule_scenarios(entry)
        degraded.extend(
            _rule_degraded_scenario_ids(scenarios, args.mechanism, prefix=str(name))
        )
        summary = entry.get("summary")
        if isinstance(summary, Mapping) and summary.get("verdict") == "FAIL_JUDGE_ERRORS":
            if not any(task_id.startswith(f"{name}::") for task_id in degraded):
                degraded.append(f"{name}::<FAIL_JUDGE_ERRORS>")
        scored: dict[str, bool] = rule_results(
            scenarios, args.mechanism, min_score=args.min_score
        )
        for sid, passed in scored.items():
            out[f"{name}::{sid}"] = passed
    _refuse_degraded_rule_report(degraded)
    return out


def _extract_rule(payload: object, args: argparse.Namespace) -> dict[str, bool]:
    # eval-rule-activation.py --output writes {"rules": {name: {...}}}. A bare
    # scenario array and a {"scenarios": [...]} wrapper are also accepted so a
    # caller can gate one rule without the envelope.
    if isinstance(payload, dict) and "rules" in payload:
        return _extract_rules_envelope(payload["rules"], args)
    # Annotated locals here and below: the sibling modules are imported by
    # path (this file is a hyphenated script), so mypy resolves them as Any
    # under ignore_missing_imports. The annotation restates the contract the
    # tests already enforce.
    scenarios = _rule_scenarios(payload)
    _refuse_degraded_rule_report(
        _rule_degraded_scenario_ids(scenarios, args.mechanism)
    )
    extracted: dict[str, bool] = rule_results(
        scenarios, args.mechanism, min_score=args.min_score
    )
    return extracted


def cmd_extract(args: argparse.Namespace) -> int:
    corpus: str | None = None
    if args.kind == "hook":
        results = pytest_results(_read_text(args.input), on_skip=args.on_skip)
    elif args.kind == "agent":
        report = _read_json(args.input)
        if not isinstance(report, Mapping):
            raise ConfigError(f"{args.input} must hold an agent report object")
        corpus = _report_corpus(args.input, report)
        results = agent_results(
            report,
            args.variant,
            reduce=args.reduce,
            pass_threshold=args.pass_threshold,
        )
    else:
        results = _extract_rule(_read_json(args.input), args)
    _emit({"schema": _RESULTS_SCHEMA, "corpus": corpus, "results": results})
    return EXIT_OK


def _report_corpus(path: Path, report: Mapping[str, Any]) -> str | None:
    """The agent report's own answer to "which task set was this scored on".

    `eval-agent-vs-baseline.py` writes `fixture_set_sha` and its docstring says
    the field exists so a report consumer can verify two runs hit the same set.
    This is the consumer. Reading it here is the whole fix: on 2026-07-27 a pair
    that disagreed on this field was gated, accepted, and published as a null
    control, because the comparison tool ignored the field that falsifies the
    comparison.

    Absent stays absent. Older reports predate the field and a value invented
    for them would assert a match this function cannot know.
    """
    return _checked_corpus(path, report.get("fixture_set_sha"))


# ---------------------------------------------------------------------------
# split, budget, score
# ---------------------------------------------------------------------------


def cmd_split(args: argparse.Namespace) -> int:
    pinned: dict[str, Any] = {}
    if args.results:
        source = _read_results(args.results)
        task_ids = sorted(source.results)
        # The baseline commitment carries the corpus rather than the comparison
        # inferring it from the pair. Without the pin, a mismatch is reachable
        # by omission: stripping the envelope off either side leaves two
        # unknowns, and two unknowns have nothing to disagree about. The pin
        # gives the gate a value neither results file can delete.
        pinned["corpus"] = source.corpus
    else:
        task_ids = [
            line.strip() for line in _read_text(args.tasks).splitlines() if line.strip()
        ]
    try:
        result = split_tasks(
            task_ids,
            seed=args.seed,
            sel_ratio=args.sel_ratio,
            test_ratio=args.test_ratio,
            min_sel=args.min_sel,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    record = {
        "opt": list(result.opt),
        "sel": list(result.sel),
        "test": list(result.test),
        "fingerprint": result.fingerprint,
        "seed": args.seed,
        "sel_ratio": args.sel_ratio,
        "test_ratio": args.test_ratio,
        "min_sel": args.min_sel,
        **pinned,
    }
    _write_atomic(args.out, json.dumps(record, indent=2, sort_keys=True) + "\n")
    # The full record goes to the file the gate reads. Stdout, which is what
    # the optimizing agent sees, gets the optimize ids and the sizes and
    # fingerprint it needs to verify the split was not redrawn. Publishing
    # held-out membership here would make the withholding nominal: an agent
    # could read the answers it is being measured against for free.
    _emit(
        {
            "opt": list(result.opt),
            "n_sel": len(result.sel),
            "n_test": len(result.test),
            "fingerprint": result.fingerprint,
            "seed": args.seed,
            "split": str(args.out),
        }
    )
    return EXIT_OK


def cmd_budget(args: argparse.Namespace) -> int:
    try:
        value = edit_budget(
            args.step, args.total, max_edits=args.max_edits, min_edits=args.min_edits
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    _emit({"budget": value, "step": args.step, "total": args.total})
    return EXIT_OK


def _group_ids(split: dict[str, Any], group: str) -> list[str]:
    ids: list[str] = list(split[group])
    return ids


def _score_group(results: dict[str, bool], split: dict[str, Any], group: str) -> float:
    try:
        fraction: float = score(results, split[group])
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return fraction


def cmd_score(args: argparse.Namespace) -> int:
    split = _read_split(args.split)
    if _split_drifted(split):
        # `_read_split` refuses a file it cannot re-fingerprint and says the
        # reason is that such a file cannot be verified. It then does not
        # verify, which left this command echoing a fingerprint below that no
        # longer describes the groups it just scored: two documents, one
        # fingerprint, different numbers. `gate` covers itself with this same
        # call and refuses, so nothing unsound reached a verdict; the cost was
        # that the operator learned it after paying for the candidates rather
        # than at the first read. Raising rather than emitting a refusal keeps
        # this the same class of report as a malformed split, which is what a
        # hand-edited one is. `gate` still emits `decision: REJECT` because its
        # caller is a loop that branches on the document.
        raise ConfigError(
            f"{args.split} does not match its own recorded inputs; the groups "
            "or the seed were edited after the split was drawn. Scoring it "
            "would report a number under a fingerprint that no longer names "
            "it. Re-split and re-baseline."
        )
    results = _read_results(args.results).results
    value = _score_group(results, split, args.group)
    # The fingerprint rides along because `gate` requires it and this is the
    # only command that reads the split on the caller's behalf. Without it the
    # caller has to open the split file to satisfy a required flag, which is
    # how the check ended up optional in the first place.
    _emit(
        {
            "score": value,
            "group": args.group,
            "n": len(split[args.group]),
            "fingerprint": split["fingerprint"],
        }
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def cmd_apply(args: argparse.Namespace) -> int:
    document = _read_text(args.file)
    patches = _read_patches(args.patches)
    if args.budget < 0:
        # Checked ahead of the try, because the block below reports what it
        # catches as a refused patch and a negative budget is not one. Left to
        # fall through, an operator's argument error was published as
        # `applied: 0`, which tells the loop its candidate proposed an
        # unusable edit when the candidate did nothing. A negative `--min-sel`
        # is already a config error; this matches it.
        raise ConfigError(f"--budget must be non-negative, got {args.budget}")
    try:
        updated = apply_patches(document, patches, budget=args.budget)
    except ValueError as exc:
        # A refused patch is a decision the loop branches on, not a crash. The
        # file is left untouched so the caller can propose a different edit.
        _emit({"applied": 0, "error": str(exc), "type": type(exc).__name__})
        return EXIT_LOGIC
    if args.dry_run:
        _emit({"applied": len(patches), "result": updated, "written": False})
        return EXIT_OK
    _write_atomic(args.file, updated)
    _emit({"applied": len(patches), "written": True, "path": str(args.file)})
    return EXIT_OK


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


_LEDGER_DIR_ENV = "EVAL_LEDGER_DIR"
_HELD_OUT_PLACEHOLDER = "<held-out group>"


def _ledger_root() -> Path:
    """The one directory every consultation ledger lives in.

    Fixed rather than relative to the split, because anything derived from a
    path the caller supplies is a path the caller can change. `$EVAL_LEDGER_DIR`
    exists so tests do not write to a real user directory; setting it is a
    deliberate act outside the loop's argument surface, which is the line this
    mechanism draws everywhere else too.
    """
    override = os.environ.get(_LEDGER_DIR_ENV)
    if override:
        return Path(override)
    state = os.environ.get("XDG_STATE_HOME")
    if not state:
        try:
            state = str(Path.home() / ".local" / "state")
        except RuntimeError as exc:
            # An eleventh review found this escaping as RuntimeError, which main
            # does not catch, so the caller got a traceback where the module
            # docstring promises a JSON error document. Reached on the default
            # configuration by any container running as a uid with no passwd
            # entry: Path.home() consults $HOME first and the passwd database
            # second, and gives up when both are absent.
            raise ConfigError(
                f"cannot resolve a ledger directory ({exc}). Neither "
                f"${_LEDGER_DIR_ENV} nor $XDG_STATE_HOME is set and the home "
                f"directory is undeterminable, which is what a container running "
                f"as a numeric uid with no passwd entry looks like. Set "
                f"${_LEDGER_DIR_ENV} to a writable path."
            ) from exc
    return Path(state) / "ai-agents-eval" / "ledgers"


def _holdout_key(split: dict[str, Any]) -> str:
    """The identity of the held-out group itself, which is what a budget counts.

    Three earlier versions keyed the ledger on something upstream of the group:
    `--ledger` directly, then the `--split` path, then the split fingerprint.
    Each one admitted a different input that reached the same held-out tasks
    under a new key, and a missing ledger starts at zero, so each was a reset.

    The fingerprint was the closest miss. It covers the seed, the task ids, and
    the ratios, which are the *inputs* to the selection rather than its result,
    and the group sizes are rounded. Adversarial review (gpt-5.6-sol,
    2026-07-26) reproduced it: ten tasks at sel_ratio 0.40 and 0.41 both round
    to four held out and select the identical four tasks, but fingerprint the
    differently, so the same group got two budgets.

    Keying on the sorted membership removes the whole class. Any two splits
    that hold out the same tasks share the budget those tasks have already
    paid, whatever produced them. Sorting rather than preserving rank order is
    deliberate: the ranking is a function of the seed, and two seeds that
    happen to hold out the same set are still selecting on the same set.

    No corpus namespace is mixed in, though a collision is possible in
    principle: two unrelated eval sets whose task ids and held-out membership
    both coincide would share a budget. A namespace would have to come from the
    caller, and a caller-supplied key is the exact defect this function exists
    to close. A namespace derived from task contents or from trusted corpus
    provenance would work and needs a seam that carries one; the seam here
    carries task ids and pass booleans. Sharing is the conservative direction,
    so the collision is accepted rather than reopened.
    """
    sel = sorted(str(task_id) for task_id in _group_ids(split, _GATE_GROUP))
    # JSON rather than a NUL join: joining is not injective when an id may
    # itself contain the separator, and ["a", "b\0c"] would key the same
    # budget as ["a\0b", "c"].
    canonical = json.dumps(sel, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scrub(text: str, holdout_key: str) -> str:
    """Replace the held-out digest wherever it appears in `text`.

    One definition rather than a `.replace` at each site. A tenth review found
    the release warning redacting by hand and getting it wrong, one round after
    a ninth review found the same at the cause chain. Two consecutive rounds
    finding a defect at a hand-written redaction site is the argument for
    having exactly one.

    Case-insensitive because a hex digest has an uppercase spelling and
    `$EVAL_LEDGER_DIR` can carry it. Hex is the one alphabet where folding has
    no surprises. That path only fires for a caller who already knows the
    digest, so the reason to close it is the stated property, not the threat.
    """
    return re.sub(re.escape(holdout_key), _HELD_OUT_PLACEHOLDER, text, flags=re.IGNORECASE)


_ACTIVE_HOLDOUT_KEY: ContextVar[str | None] = ContextVar(
    "_ACTIVE_HOLDOUT_KEY", default=None
)


def _warn(message: str) -> None:
    """Report a loss that must not abort the caller and must not leak.

    Three rules that kept being written separately and therefore kept being
    missed one at a time. Rounds twenty and twenty-one each fixed the rule in
    front of them and each left the next one open, so they are named here
    together rather than discovered in sequence a fourth time.

    The stream is the only state this reads outside the guard, and it is read
    totally. It has to be outside, because it decides the early return that
    keeps the message off stdout, and `sys.stderr` is an attribute lookup, so
    a harness that deletes it rather than blanking it turns the read itself
    into the abort. `getattr` routes that case into the `None` branch already
    here instead of adding a second one.

    The key read was outside too and had no reason to be. Rounds twenty
    through twenty-five each answered "why is this one safe" for a different
    expression out there, and the sixth answer is that the question was
    avoidable: the key is read where it is used, under the guard, so nothing
    about `_ACTIVE_HOLDOUT_KEY` has to hold for the caller to survive. It is
    still declared with `default=None`, which after the move buys a printed
    diagnostic rather than an unaborted caller. What remains outside is the
    guard's own construction, which no docstring can promise against a caller
    who reassigns this module's globals.

    One reason this paragraph is shorter than the argument that produced it.
    It was wrong in four consecutive rounds, each time immediately after being
    corrected, and the corrections were not careless: it asserted a count of
    the expressions out here, a line distance to a declaration, and a number
    of tests, and every one of those rotted. A sentence that can be falsified
    by adding a test is a liability in a docstring, so the counts are in the
    review log where they are dated. Everything
    that can do work is inside the guard, including the redaction. Writing the
    opposite down is what exposed it: a redaction that raises would leave the
    message unprinted either way, so suppressing costs a diagnostic and
    excluding it costs the caller the abort that rounds twenty through
    twenty-two were all spent removing. Nothing reaches `print` unredacted,
    because a raise from `_scrub` skips the print with the message still bound
    to its unscrubbed value.

    It must not leak. `_digest_scrubbed` is a seam over raised exceptions, and
    its own reasoning is that a wrapper covers the paths someone remembered
    while a seam covers the one added next year. A diagnostic that prints and
    returns never reaches that seam, so the next one added inherits none of
    its protection: a twenty-first review found exactly that, at a warning
    added in the twentieth, naming a `$EVAL_LEDGER_DIR` root in full one round
    after the tenth review fixed the same leak at the lock warning by hand.
    Reading the key from the active scrub rather than taking it as an argument
    is what makes this a seam too. A caller who has no key to pass is the
    caller most likely to be the one that leaks.

    It must not fail. Every caller here is reporting something that already
    succeeded or that is being cleaned up after, so the decision is either on
    stdout already or about to be. Both sites sit inside a region that
    converts `OSError` into a refusal, so an unguarded warning hands back the
    abort it was written to avoid. Losing the warning to a broken stream costs
    a diagnostic; raising costs a charged consultation and returns no verdict.
    So the write suppresses `Exception` and not `OSError`: a twenty-first
    review demonstrated the crash with a double whose `write` raised
    `OSError(32)`, the guard was written to that demonstration, and a
    twenty-second review closed a real stream and got `ValueError: I/O
    operation on closed file` straight through it. Guarding the exception a
    reviewer happened to raise is not the same as guarding the rule.

    It must not land on stdout. `sys.stderr` is `None` under a pythonw-style
    launcher and after a harness detaches it, and `print(file=None)` does not
    silence the line, it redirects it to `sys.stdout`, which carries the JSON
    verdict the caller parses. A diagnostic that corrupts the payload is worse
    than one that is lost, so a missing stream drops the message.
    """
    stream = getattr(sys, "stderr", None)
    if stream is None:
        return
    with suppress(Exception):
        key = _ACTIVE_HOLDOUT_KEY.get()
        if key is not None:
            message = _scrub(message, key)
        print(message, file=stream)


@contextmanager
def _digest_scrubbed(holdout_key: str) -> Iterator[None]:
    """Keep the held-out digest out of whatever goes wrong under the ledger.

    Every ledger and lock filename ends in the digest, and the digest is an
    unsalted hash of a set the caller can enumerate. The three hand-written
    errors were redacted one at a time and that left every other way to fail
    intact: a ledger that is not JSON, a write that cannot land, an os.open
    that fails for any errno but EEXIST. Each raises with the full path.

    Scrubbing at the seam rather than sanitizing each call site is the point.
    A wrapper covers the paths someone remembered; a seam covers the one
    added next year. The message survives with the name replaced, because an
    error that says nothing about what failed is a worse trade than the leak.

    Every `OSError` becomes a `ConfigError` whether or not it carried the
    digest, because `main` catches `ConfigError` and not `OSError`, and an
    eighth review found the first draft re-raising the pathless ones raw. An
    `os.write` that runs out of space and an `os.close` that hits EIO name no
    file, so they missed the redaction branch and escaped as tracebacks: the
    same shape of defect the scrub exists to fix, one layer down. A
    `ConfigError` without the digest is re-raised as itself rather than
    rewrapped, so nothing that inspects the exception object loses it.

    The key is published while the block runs so `_warn` can reach it. A
    warning prints and returns, so it never passes through the handler below,
    and a twenty-first review found one naming a digest-bearing ledger root in
    full. Publishing it here rather than threading it through every signature
    keeps the same property the handler has: the site added next year is
    covered without being told to be.
    """
    token = _ACTIVE_HOLDOUT_KEY.set(holdout_key)
    try:
        yield
    except (ConfigError, OSError) as exc:
        text = str(exc)
        # `_scrub` decides whether the digest is here, rather than a separate
        # `holdout_key in text`. A twelfth review found that guard reading case
        # sensitively one round after `_scrub` learned to fold case, so an
        # uppercase digest failed the test, skipped the scrub, and printed
        # whole. Two answers to one question is what keeps going wrong; asking
        # `_scrub` leaves nothing to keep in step.
        scrubbed = _scrub(text, holdout_key)
        if scrubbed != text:
            # `from None`, not `from exc`. Chaining would set __cause__ to the
            # exception whose message is the reason this branch exists, and a
            # printed traceback walks the chain. Round 9 found the redaction
            # handing the digest straight back that way.
            raise ConfigError(scrubbed) from None
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(text) from exc
    finally:
        # Restoring the previous value rather than clearing: the seam nests,
        # and an inner block that cleared unconditionally would leave the
        # outer one unprotected for the rest of its body.
        #
        # A `ContextVar` token rather than a module global and a saved
        # variable. A twenty-second review ran two scopes concurrently and got
        # both a disclosed key and a stale one left active after both had
        # exited, because a global is shared by every thread that reads it. A
        # context variable is not. What a token does not fix is unwinding two
        # scopes in one context in the order they were entered rather than the
        # reverse, which leaves the first one's value behind; nothing here can
        # do that, because both scopes are `with` statements and a `with`
        # statement unwinds last-entered-first. What a token also does not fix
        # is exiting a scope in a different context than it was entered in:
        # `reset` refuses a foreign token with `ValueError`, where the global
        # it replaced would have restored something. Every scope here is a
        # plain `with` in straight-line synchronous code, so no call site can
        # reach it, and guarding an unreachable path would only hide the day
        # one appears.
        _ACTIVE_HOLDOUT_KEY.reset(token)


def _ledger_path(holdout_key: str) -> Path:
    """Where the budget for one held-out group lives."""
    return _ledger_root() / f"{holdout_key}.ledger"


def _lock_refused(lock: Path, exc: OSError) -> str:
    """Why the lock could not be taken, in the shape the other errors use.

    Named rather than inlined at both raise sites so the acquire and the pid
    write cannot drift into reporting the same failure two ways.
    """
    return (
        f"could not take the lock {lock} ({exc.strerror or exc.errno}); the "
        f"read-modify-write it serializes was not attempted."
    )


def _close_quietly(handle: int) -> None:
    """Release a descriptor when the failure that stopped the write is known.

    POSIX frees the descriptor even when close reports an error, so there is
    nothing to retry and nothing a caller can do with the news. Reporting it
    would replace the cause an operator can act on with one raised while
    cleaning up after it.
    """
    with suppress(OSError):
        os.close(handle)


@contextmanager
def _lock_held(
    lock: Path,
    contention: str,
    cleanup_warning: Callable[[OSError], str],
) -> Iterator[None]:
    """Serialize a read-modify-write on one file behind an exclusive create.

    Atomic replacement keeps a file whole. It does not make the sequence that
    produced the replacement a transaction, so two callers that read the same
    document, each change their own copy, and each replace the file leave only
    the later one's change. Both are told they succeeded.

    An exclusive create is the lock rather than ``fcntl``, which is POSIX only.
    A stale lock left by a killed process is reported rather than broken, since
    guessing that the holder is gone is how a lock becomes advisory.

    The two messages are the caller's because the two callers do not agree on
    what may be said. A ledger lock's name digests held-out membership and has
    to be withheld; a buffer lock's name came from the command line and
    withholding it would turn a stale lock into a puzzle.

    Every failure to take the lock is a `ConfigError`, which is what the rest
    of this module does: `_read_buffer` reports "could not read", and
    `_write_atomic` reports "could not write". This helper did not, and did not
    have to, while its only caller ran inside `_digest_scrubbed`, whose handler
    converts every `OSError` raised under the ledger. A thirty-third review
    found that the extraction gave it a second caller with no such cover, so an
    unwritable buffer directory printed a traceback where the module docstring
    promises a JSON document and exited 1, the code a loop reads as a decision
    rather than a crash. Converting here rather than at the new call site is
    the same argument the scrub makes: a wrapper covers the caller someone
    remembered. `_digest_scrubbed` catches `ConfigError` as well, so the ledger
    caller's redaction survives the change.

    A thirty-fourth review found that fix incomplete. The lock has five
    filesystem stages, and it had converted three: a close-only failure still
    escaped raw. That is not a rare shape, because a write to a network or
    quota backed filesystem can be buffered past `os.write` and reported by
    `close`, which is why POSIX documents `EIO` and `ENOSPC` there. Close now
    converts too, and deliberately outside a `finally`: when the write has
    already failed it is the cause an operator can act on, and a `finally`
    that raised would replace it with the consequence.

    The acquire runs its two calls under separate `try` blocks because they do
    not agree on what `FileExistsError` means. For `os.open` with `O_EXCL` it
    is the whole signal: a lock file already on disk is what one holder looks
    like to another. For `mkdir` it is a different fact, since `exist_ok=True`
    swallows the error only when what it found is a directory and re-raises
    otherwise, so a plain file sitting where the lock's parent belongs raises
    the same errno with nothing holding anything. Sharing one block told that
    operator to wait for a process that does not exist. Splitting is preferred
    to re-checking `is_dir()` in the handler, which would decide the cause from
    a second look at a filesystem that has since been free to change.
    """
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(_lock_refused(lock, exc)) from exc
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ConfigError(contention) from None
    except OSError as exc:
        raise ConfigError(_lock_refused(lock, exc)) from exc
    try:
        try:
            os.write(handle, str(os.getpid()).encode("utf-8"))
        except OSError as exc:
            # Converted here rather than left to escape, for the reason above:
            # the descriptor is released on the next line and the lock file by
            # the outer finally, so the only thing left to decide is which
            # document the caller reads.
            _close_quietly(handle)
            raise ConfigError(_lock_refused(lock, exc)) from exc
        # Not in a `finally`. A close that fails while the write is already
        # failing would replace the cause with the consequence, and the write
        # is the one an operator can act on. Ordering the two statements says
        # that; a `finally` cannot.
        try:
            os.close(handle)
        except OSError as exc:
            raise ConfigError(_lock_refused(lock, exc)) from exc
        yield
    finally:
        try:
            lock.unlink(missing_ok=True)
        except OSError as exc:
            # The command's own document is already on stdout. Letting this
            # reach main would print a second JSON document after it and
            # return the config-failure code for work that succeeded, and the
            # module docstring promises one readable document. Silence would
            # hide a lock that now blocks the next run, so it goes to stderr.
            #
            # Through _warn, which cannot itself fail: this sits in a finally
            # after the result is already on stdout, so a closed stderr would
            # replace completed work with a traceback about the cleanup.
            _warn(cleanup_warning(exc))


@contextmanager
def _ledger_held(holdout_key: str) -> Iterator[None]:
    """Serialize the read, compare, and write of one ledger.

    Without this, two gates started together both read the same count, both
    compare, and both write count + 1, so N concurrent gates spend one
    consultation between them.

    The mechanism is `_lock_held`, shared with the rejection buffer. It was not
    shared originally, and the cost was measurable: a thirty-first review found
    `buffer-add` performing the same read-modify-write with no lock, losing a
    rejection and reporting it stored. The analysis that would have prevented
    it was already written here, one screen away, about a different file. What
    stays here is what only the ledger needs: the digest scrub, and messages
    that withhold a name the buffer's messages may print.
    """
    lock = _ledger_root() / f"{holdout_key}.lock"
    # The scrub spans the whole lifecycle, not just the acquire. A seventh
    # review found the release outside it: the unlink in the finally block
    # names the lock, the lock's name is the digest, and main() does not catch
    # OSError, so a cleanup failure printed the group as an uncaught traceback.
    # A tenth review found the mkdir outside it too, which cost more than the
    # leak: an unwritable ledger root raised PermissionError past main's
    # handler list, so a read-only home returned a traceback where the module
    # docstring promises a JSON error document.
    # The contention branch nests inside because its own message carries no
    # digest and an operator needs it to clear a stale lock.
    with _digest_scrubbed(holdout_key):
        contention = (
            f"another gate holds a lock under {lock.parent}; consultations "
            f"against one held-out group are serialized so a concurrent "
            f"pair cannot spend one budget twice. Remove the lock file "
            f"there if no gate is running. Its name is withheld: the name "
            f"digests the held-out membership, and an unsalted digest of a "
            f"set the caller can enumerate is that set."
        )

        def cleanup_warning(exc: OSError) -> str:
            # Named by its directory rather than by itself, because naming a
            # directory was justified in review by the claim that a directory
            # carries no digest, and a tenth review falsified it:
            # $EVAL_LEDGER_DIR can name one. Hence _warn, which scrubs.
            return (
                f"warning: could not remove the lock under {lock.parent} "
                f"({exc.strerror or exc.errno}); the next gate against "
                f"this held-out group reports contention until it is "
                f"removed. Its name is withheld: the name digests the "
                f"membership."
            )

        with _lock_held(lock, contention, cleanup_warning):
            yield


def _read_ledger(path: Path, holdout_key: str, cap: int, max_p: float | None) -> int:
    """Return the consultations already spent against this split.

    The count lives here rather than on the command line because a budget the
    caller supplies is not a budget: passing zero every time yields an
    unlimited one while still looking capped. The cap is recorded for the same
    reason. Pinning only the count left the limit re-suppliable, so a caller
    that hit the budget could raise it and carry on, which is the defect the
    ledger was written to close wearing a different hat.

    The significance bar is pinned for exactly that reason too. A candidate
    refused at 0.05 could otherwise be gated again at 0.1 against the same
    held-out group until it passed. Its absence is pinned as firmly as its
    presence, because omitting the flag is the loosest setting there is. An
    older ledger written before the bar existed records no key, which reads as
    the absent policy it was in fact opened under.

    The ledger records the held-out key it was opened under. That is the same
    value its filename carries, so the check catches a ledger moved or renamed
    into another group's place rather than an honest redraw: a genuinely new
    held-out group has a different key and therefore its own file.
    """
    if _absent(path):
        return 0
    data = _read_json(path)
    if not isinstance(data, Mapping):
        raise ConfigError(f"the ledger under {path.parent} must hold a JSON object")
    spent = data.get("consultations")
    if not isinstance(spent, int) or isinstance(spent, bool) or spent < 0:
        raise ConfigError(
            f"the ledger under {path.parent} needs consultations to be a "
            f"non-negative integer"
        )
    recorded_cap = data.get("max_consultations")
    if not isinstance(recorded_cap, int) or isinstance(recorded_cap, bool) or recorded_cap < 1:
        raise ConfigError(
            f"the ledger under {path.parent} needs max_consultations to be a "
            f"positive integer"
        )
    recorded = data.get("holdout")
    if recorded != holdout_key:
        raise LedgerMismatchError(
            f"the ledger under {path.parent} records a different held-out "
            f"group than this split holds out; a ledger under another group's "
            f"name is a moved or edited file, not a redraw. Neither group is "
            f"named here, because the name digests its membership"
        )
    if recorded_cap != cap:
        raise LedgerMismatchError(
            f"this held-out group was opened with a cap of {recorded_cap} and "
            f"this invocation asks for {cap}; the budget for a held-out group "
            f"is fixed when the run starts, so re-split to change it"
        )
    recorded_bar = data.get("max_p")
    if recorded_bar is not None and (
        isinstance(recorded_bar, bool) or not isinstance(recorded_bar, (int, float))
    ):
        raise ConfigError(
            f"the ledger under {path.parent} needs max_p to be a number or absent"
        )
    if recorded_bar is not None and not 0.0 <= recorded_bar <= 1.0:
        raise ConfigError(
            f"the ledger under {path.parent} has max_p={recorded_bar}, "
            f"which is outside [0, 1]; this is a corrupted ledger, not a "
            f"gate refusal"
        )
    if recorded_bar != max_p:
        raise LedgerMismatchError(
            f"this held-out group was opened under a significance bar of "
            f"{_bar_name(recorded_bar)} and this invocation asks for "
            f"{_bar_name(max_p)}; the bar is fixed when the run starts, so "
            f"re-split to change it. A bar you can loosen after seeing a "
            f"refusal is not a bar"
        )
    return spent


def _bar_name(bar: float | None) -> str:
    return "none" if bar is None else f"{bar:g}"


def _write_ledger(
    path: Path, holdout_key: str, spent: int, cap: int, max_p: float | None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "consultations": spent,
        "holdout": holdout_key,
        "max_consultations": cap,
        "max_p": max_p,
    }
    _write_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _guard(args: argparse.Namespace, split: Mapping[str, Any], spent: int) -> str | None:
    """Ask whether a comparison may happen, reporting nonsense input cleanly.

    ``guard_refusal`` raises on a cap below one rather than treating it as a
    permanently exhausted budget. That is a caller mistake, not a gate verdict,
    so it becomes a config error instead of a REJECT that would read as real
    discipline.
    """
    try:
        refusal: str | None = guard_refusal(
            sel_consultations=spent,
            max_consultations=args.max_consultations,
            split_fingerprint=split["fingerprint"],
            incumbent_fingerprint=args.incumbent_fingerprint,
        )
        return refusal
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def cmd_gate(args: argparse.Namespace) -> int:
    # Before anything reads the split or the ledger. A bar outside [0, 1] is
    # decidable without the held-out group, so it must not cost a consultation
    # and must not be masked by an exhausted budget refusing first.
    if args.max_p is not None and not 0.0 <= args.max_p <= 1.0:
        raise ConfigError(f"--max-p must be in [0, 1], got {args.max_p}")

    split = _read_split(args.split)
    if _split_drifted(split):
        _emit(
            {
                "decision": "REJECT",
                "reason": (
                    "split fingerprint does not match the split file's own "
                    "contents; the groups or the seed were edited after the "
                    "split was drawn. Re-split and re-baseline."
                ),
                "compared": False,
                "consultations": 0,
            }
        )
        return EXIT_LOGIC

    # Headers only, and before the lock, so the corpus refusal costs nothing.
    # Reading them is not a reveal: the caller supplied both files, and the
    # refusal below prints neither task ids nor verdicts. The scrubber is here
    # because a failing open names the file, and the ledger directory can carry
    # the digest.
    with _digest_scrubbed(_holdout_key(split)):
        pin = split.get("corpus", _UNPINNED)
        incumbent_corpus = _corpus_header(args.incumbent)
        candidate_corpus = _corpus_header(args.candidate)
    if _corpus_conflict(pin, incumbent_corpus, candidate_corpus):
        _emit(_corpus_refusal())
        return EXIT_LOGIC

    # The lock spans read, compare, and write. A drifted split never reaches it
    # because that refusal reads no ledger and spends nothing.
    with _ledger_held(_holdout_key(split)):
        return _gate_decision(args, split)


def _corpus_conflict(pin: object, incumbent: str | None, candidate: str | None) -> bool:
    """Whether the split and the two results files name more than one corpus.

    One rule covers every case worth refusing. A pinned digest that a file does
    not carry conflicts, which is what closes the strip: stripping the envelope
    turns a digest into an unknown, and an unknown beside a pin is a
    disagreement rather than a pair of blanks. One known corpus beside an
    unknown one conflicts for the same reason even with no pin at all, because
    a pair scored on one corpus does not have one side that forgot.

    Unknown everywhere is not a conflict. The rule and hook paths publish no
    corpus identity, so refusing there would disable the gate for two of the
    three artifact classes to guard a case it cannot detect there anyway. The
    verdict reports `corpus_verified` instead, which is the difference between
    a check that passed and a check that never ran.
    """
    declared = (pin, incumbent, candidate)
    return len({d for d in declared if d is not _UNPINNED}) > 1


def _corpus_refusal() -> dict[str, object]:
    """The one refusal both corpus checks emit.

    The preflight reads headers and the gate reads bodies. Two call sites
    phrasing the same refusal would let the caller tell which read caught it,
    and would drift the moment one of them is edited.

    The gate's copy briefly added `sel_consultations`, which broke the first
    property by key set alone. It was also the wrong number to report there.
    `_guard` runs before the recheck, so an exhausted budget has already
    refused by then, and prior ledger spend cannot change what the caller must
    do next. Both sites report `consultations: 0` instead, which is the one
    claim each can make honestly: this run charged nothing.

    The advice restates `_corpus_conflict`'s rule rather than naming a file to
    copy a value from. `(_UNPINNED, SHA_A, SHA_B)` is a refusing row, so a
    split that names no corpus can reach here, and advice to re-score against
    the corpus the split names sends that caller to a key their split does not
    have. The rule is the one instruction true for every refusing row, and it
    is falsified only by editing the predicate above.
    """
    return {
        "decision": "REJECT",
        "reason": (
            "the split and the two results files do not agree on one corpus, "
            "so a comparison between them measures the corpus change as well "
            "as the edit. Re-score both artifacts so that only one corpus is "
            "named across all three, and gate again."
        ),
        "compared": False,
        "consultations": 0,
    }


def _gate_decision(args: argparse.Namespace, split: dict[str, Any]) -> int:
    """Spend at most one consultation and report what it bought."""
    holdout_key = _holdout_key(split)
    ledger = _ledger_path(holdout_key)
    try:
        with _digest_scrubbed(holdout_key):
            spent = _read_ledger(ledger, holdout_key, args.max_consultations, args.max_p)
    except LedgerMismatchError as exc:
        _emit({
            "decision": "REJECT",
            "reason": str(exc),
            "compared": False,
            # No running total. The count parses before the mismatch is
            # raised, so a number exists, but on a key mismatch it belongs to
            # a different group and naming it would leak that group's history
            # through a refusal that deliberately withholds the group itself.
            # The old literal 0 was worse than silence: it claimed nothing had
            # ever been spent, which is false whenever the ledger holds a
            # count, and false in the direction that invites another look.
            "consultations": 0,
            "group": _GATE_GROUP,
            "fingerprint": split["fingerprint"],
        })
        return EXIT_LOGIC

    # Guards first, scoring second. Both refusals are decidable from
    # bookkeeping alone, and scoring before asking would read the held-out
    # group to produce a verdict that says the held-out group must not be read.
    refusal = _guard(args, split, spent)
    if refusal is not None:
        _emit(
            {
                "decision": "REJECT",
                "reason": refusal,
                "consultations": 0,
                "sel_consultations": spent,
                "compared": False,
                "group": _GATE_GROUP,
                "fingerprint": split["fingerprint"],
            }
        )
        return EXIT_LOGIC

    # The full read lands here, after the guards and before the charge. Doing
    # it before the lock would let a bad verdict mapping answer in place of an
    # exhausted budget, which tells the caller to fix the wrong thing; doing it
    # after the charge would bill a consultation for a file that never parsed.
    incumbent_file = _read_results(args.incumbent)
    candidate_file = _read_results(args.candidate)

    # The preflight read headers; this read produced the numbers the comparison
    # is scored from. Only the second pair is authoritative, so the conflict
    # rule runs again against it. Without this the two reads never had to
    # agree, and the gap between them was a window a file could change in.
    pin = split.get("corpus", _UNPINNED)
    if _corpus_conflict(pin, incumbent_file.corpus, candidate_file.corpus):
        _emit(_corpus_refusal())
        return EXIT_LOGIC

    incumbent_results = incumbent_file.results
    candidate_results = candidate_file.results
    sel_ids = _group_ids(split, _GATE_GROUP)

    # Charge before reading the group, not after reaching a verdict. Two things
    # made the old order wrong. A crash between scoring and the write left the
    # held-out group read and the consultation unrecorded, so a retry got the
    # comparison for free. And any refusal decided after scoring was equally
    # free, which is what made the reveal below worth buying.
    spent_after = spent + 1
    with _digest_scrubbed(holdout_key):
        _write_ledger(ledger, holdout_key, spent_after, args.max_consultations, args.max_p)
    # Derived rather than written as 1 twice below. The charge and the ledger
    # would then be two numbers that have to agree, and this session has
    # already paid for one figure copied into several places and corrected in
    # only some of them.
    charged = spent_after - spent

    if not _covers_holdout(incumbent_results, sel_ids) or not _covers_holdout(
        candidate_results, sel_ids
    ):
        _emit(
            {
                "decision": "REJECT",
                "reason": (
                    "the results do not cover the held-out group; score both "
                    "artifacts over the whole task set and gate again. Which "
                    "tasks are missing is withheld: with a test group drawn, "
                    "naming them would say which of the two withheld groups "
                    "each one belongs to."
                ),
                "consultations": charged,
                "sel_consultations": spent_after,
                "compared": False,
                "group": _GATE_GROUP,
                "fingerprint": split["fingerprint"],
            }
        )
        return EXIT_LOGIC

    incumbent = _score_group(incumbent_results, split, _GATE_GROUP)
    candidate = _score_group(candidate_results, split, _GATE_GROUP)
    gain, loss, p_value = mcnemar_exact(incumbent_results, candidate_results, sel_ids)
    try:
        result = gate(
            candidate,
            incumbent,
            sel_consultations=spent,
            max_consultations=args.max_consultations,
            split_fingerprint=split["fingerprint"],
            incumbent_fingerprint=args.incumbent_fingerprint,
            discordant_loss=loss,
            p_value=p_value,
            max_p=args.max_p,
        )
    except ValueError as exc:
        # Defense in depth. cmd_gate rejects an out-of-range bar before the
        # ledger is touched, so reaching this is a caller contract violation
        # rather than operator error, and the consultation is already spent.
        raise ConfigError(str(exc)) from exc

    _emit(
        {
            "decision": result.decision,
            "reason": result.reason,
            "candidate": result.candidate,
            "incumbent": result.incumbent,
            # Discordant pairs are the only tasks that carry evidence about the
            # edit. p is the one-sided exact McNemar tail. It is reported
            # always and enforced only when --max-p is set: a three-task
            # held-out group cannot reach 0.05, so enforcing a conventional
            # floor by default would make the common case unpassable instead
            # of informative.
            "discordant_gain": gain,
            "discordant_loss": loss,
            "p_value": p_value,
            # Both bars travel with the verdict so a reader can tell an accept
            # under no bar from an accept that cleared one, and so the
            # Bonferroni correction is visible rather than implied.
            "max_p": args.max_p,
            "max_p_per_comparison": (
                None if args.max_p is None else args.max_p / args.max_consultations
            ),
            # Two counts, two questions. `consultations` is what this run
            # charged, which is the field a caller checks to learn whether a
            # refusal was free. `sel_consultations` is the running total
            # against the held-out group including that charge, which is the
            # field a caller checks against the cap.
            "consultations": charged,
            "sel_consultations": spent_after,
            "compared": result.compared,
            # False means the check never ran, not that it failed: a mismatch
            # refuses before this point. It is reported so an accept on a path
            # with no corpus source cannot be read as an accept that was
            # checked.
            "corpus_verified": incumbent_file.corpus is not None
            and incumbent_file.corpus == candidate_file.corpus,
            # Whether the split named the corpus the results carry. A caller
            # who deletes the split's `corpus` key leaves two agreeing files
            # and nothing to contradict them, so the guard cannot refuse that
            # pair; refusing it would also disable the gate for the rule and
            # hook paths, which pin nothing at all. The verdict names the
            # weaker guarantee rather than letting `corpus_verified` be read
            # as the stronger one.
            "corpus_pinned": pin is not _UNPINNED and pin is not None,
            "group": _GATE_GROUP,
            "fingerprint": split["fingerprint"],
        }
    )
    return EXIT_OK if result.decision == "ACCEPT" else EXIT_LOGIC


# ---------------------------------------------------------------------------
# buffer
# ---------------------------------------------------------------------------


def _fsync_dir(directory: Path) -> None:
    """Persist the directory entry that ``os.replace`` just created.

    Fsyncing the temporary file makes its bytes durable. It does not make the
    rename durable: the entry pointing at those bytes lives in the parent
    directory, and a host that loses power before that entry reaches the disk
    comes back with the rename undone. For the consultation ledger that hands
    back a charged look for free, which is the one outcome charging before
    scoring exists to prevent, so a charge a crash can erase defeats the
    ordering it was written to protect.

    Failure here is reported, not raised, and the split matters. Every other
    failure in ``_write_atomic`` precedes ``os.replace`` and leaves the
    destination untouched, so refusing costs the caller nothing. This one
    fires after the write has already succeeded, and in the ledger's case
    after a consultation has already been charged, so raising would spend a
    look and return no verdict: a durability fix turned into an availability
    regression. Staying silent is equally wrong, because it leaves the caller
    believing a guarantee that did not hold. So the loss goes through
    ``_warn``, which withholds the held-out digest a ledger root can carry and
    cannot itself fail, onto stderr, which the exit-code contract keeps free
    for exactly this while stdout carries the one JSON document a caller
    parses.

    Windows cannot open a directory as a descriptor, so there is nothing to
    sync and ``os.replace`` is atomic there regardless. That is a skip rather
    than a warning.
    """
    if os.name == "nt":  # pragma: no cover - POSIX-only durability primitive
        return
    try:
        fd = os.open(str(directory), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            # Quietly, for two reasons that point the same way. On the failure
            # path the fsync is the actionable cause and a raising close would
            # replace it, so the warning would name the wrong call. On the
            # success path the guarantee already held and the replace already
            # happened, and this runs inside `_write_atomic`'s try, so an
            # escaping close error would report a completed write as a failed
            # one. Either way the descriptor is freed regardless.
            _close_quietly(fd)
    except OSError as exc:
        _warn(
            f"warning: wrote and renamed into {directory}, but could not fsync the "
            f"directory ({exc}); the file is intact and its durability across a "
            "host crash is not guaranteed"
        )


def _write_atomic(path: Path, text: str) -> None:
    """Replace `path` with `text` so no reader ever sees a partial file.

    `apply` overwrites the artifact the loop is optimizing. A direct write
    truncates before it fills, so an interrupt or a full disk mid-write
    destroys the artifact and leaves the loop nothing to fall back to. The
    temp file is created beside the target so os.replace stays on one
    filesystem and therefore stays atomic.
    """
    # Preserve the destination's mode if it exists; mkstemp defaults to 0o600.
    try:
        mode = path.stat().st_mode
    except OSError:
        mode = None

    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    except OSError as exc:
        # This call sat outside the block below, which is the only place that
        # turns a write failure into a ConfigError. A missing or unwritable
        # parent therefore left the CLI as a traceback on stderr rather than
        # one JSON document on stdout, and `split --out` into a directory that
        # does not exist is an ordinary caller mistake, not a crash.
        raise ConfigError(f"could not write {path}: {exc}") from exc
    tmp = Path(tmp_name)
    try:
        try:
            handle = os.fdopen(fd, "w", encoding="utf-8")
        except BaseException:
            # os.fdopen did not take ownership, so nothing else closes it. The
            # comment that used to sit in the handler below claimed this was
            # already done. It was not: no call closed the descriptor, so this
            # path leaked one while the comment said otherwise.
            #
            # Quietly, because a primary failure is already in flight and this
            # runs inside its handler. A raising close would propagate instead
            # of the cause, and `fdopen` can fail for reasons that are not I/O
            # at all, so the caller would get a `ConfigError` about the close
            # standing in for something that was never an `OSError`.
            _close_quietly(fd)
            raise
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException as exc:
        # Cleanup cannot stand in for the failure it cleans up after. An
        # OSError raised here would propagate from inside the handler, so the
        # caller got a traceback naming the unlink instead of one JSON
        # document naming the write. A parent whose permissions are revoked
        # after mkstemp fails both calls, which is the pair that produces it.
        # After a successful replace the temp name is already gone, so this is
        # a no-op and never touches the destination.
        with suppress(OSError):
            tmp.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            raise ConfigError(f"could not write {path}: {exc}") from exc
        raise


def _read_buffer(path: Path) -> list[dict[str, Any]]:
    if _absent(path):
        # A first run has no buffer yet. Treating that as empty keeps the loop
        # from needing a separate init step. `_absent` rather than `exists`,
        # because a buffer that cannot be read is not one with nothing in it.
        return []
    data = _read_json(path)
    if not isinstance(data, list):
        raise ConfigError(f"{path} must hold a JSON array of rejection entries")
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ConfigError(f"{path} entry {index} must be an object, got {entry!r}")
    return data


def cmd_buffer_check(args: argparse.Namespace) -> int:
    # No lock. `_write_atomic` replaces the file, so a reader sees the whole
    # old document or the whole new one, never a torn one, and serializing
    # readers would let a stale lock block the question the loop asks most.
    entries = _read_buffer(args.buffer)
    patches = _read_patches(args.patches)
    seen = buffer_contains(entries, patches)
    _emit({"seen": seen, "fingerprint": patch_fingerprint(patches)})
    return EXIT_LOGIC if seen else EXIT_OK


def _buffer_lock(buffer: Path) -> Path:
    """Beside the buffer rather than under the ledger root.

    The buffer's path is a command-line argument and two loops can run against
    two different buffers concurrently, so the lock has to be keyed by the
    file it protects rather than by a single shared location.
    """
    return Path(f"{buffer}.lock")


def cmd_buffer_add(args: argparse.Namespace) -> int:
    # Patches are parsed before the lock is taken. A malformed patch file is a
    # refusal that touches no shared state, so serializing it would make one
    # caller's bad argument another caller's contention error.
    patches = _read_patches(args.patches)
    fingerprint = patch_fingerprint(patches)
    lock = _buffer_lock(args.buffer)
    contention = (
        f"another buffer-add holds {lock}; rejections against one buffer are "
        f"serialized because the file is read, appended to, and replaced, and "
        f"an unserialized pair loses the earlier append while telling its "
        f"caller the rejection was stored. Remove that file if no buffer-add "
        f"is running."
    )

    def cleanup_warning(exc: OSError) -> str:
        return (
            f"warning: could not remove {lock} "
            f"({exc.strerror or exc.errno}); the next buffer-add against this "
            f"buffer reports contention until it is removed."
        )

    with _lock_held(lock, contention, cleanup_warning):
        entries = _read_buffer(args.buffer)
        added = not any(e.get("fingerprint") == fingerprint for e in entries)
        if added:
            entries.append(
                {
                    "fingerprint": fingerprint,
                    "reason": args.reason,
                    "patches": [
                        {"op": p.op, "anchor": p.anchor, "text": p.text} for p in patches
                    ],
                }
            )
            _write_atomic(args.buffer, json.dumps(entries, indent=2))
    _emit({"added": added, "fingerprint": fingerprint, "entries": len(entries)})
    return EXIT_OK


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


def _arith_int(text: str) -> int:
    """An integer this tool can still do arithmetic with.

    `type=int` accepts any magnitude, because Python integers are unbounded,
    but five of these arguments reach float arithmetic: the budget curve
    multiplies a span by 0.5 and divides a step by a total, and the Bonferroni
    correction divides `--max-p` by the consultation cap. Past the float range
    each raises `OverflowError`, a sibling of `ValueError` rather than a
    subclass, so it escaped every clause written to turn unusable numbers into
    refusals.

    Refused here rather than caught at the arithmetic, because `gate` charges
    the consultation to the held-out ledger before it reaches its second
    division. A value caught later has already spent budget and written its
    own cap into the ledger, where it refuses every later run against that
    group for asking a different cap. The remedy that refusal offers is to
    re-split, which destroys the held-out group. Parsing finishes before any
    command runs, so a value rejected here has charged nothing.

    The bar is what the arithmetic can carry, not a policy ceiling. No rule
    here says a budget of 10 ** 300 is wrong, only that a number the tool
    cannot compute with is not a number it can accept.
    """
    value = int(text)
    try:
        float(value)
    except OverflowError:
        raise argparse.ArgumentTypeError(
            f"{text} is too large to compute with; pass a value inside the "
            "range this tool can convert to a float"
        ) from None
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="optimize-artifact.py",
        description="Held-out-gated optimization rails for agents, rules, and hooks.",
    )
    sub = parser.add_subparsers(dest="command")

    extract = sub.add_parser("extract", help="convert a scorer's output to task pass or fail")
    extract.add_argument("--kind", choices=("agent", "rule", "hook"), required=True)
    extract.add_argument("--input", type=Path, required=True)
    extract.add_argument("--variant", default="agent", help="agent eval variant column")
    extract.add_argument("--reduce", default="mean", choices=("mean", "min", "max", "median"))
    extract.add_argument("--pass-threshold", type=float, default=1.0)
    extract.add_argument("--mechanism", default="full", help="rule eval mechanism column")
    extract.add_argument("--min-score", type=float, default=3.5)
    extract.add_argument("--on-skip", default="fail", choices=("fail", "exclude"))
    extract.set_defaults(func=cmd_extract)

    split = sub.add_parser("split", help="partition tasks into opt, sel, and test")
    source = split.add_mutually_exclusive_group(required=True)
    source.add_argument("--results", type=Path, help="extract output; task ids are its keys")
    source.add_argument("--tasks", type=Path, help="newline-delimited task ids")
    split.add_argument("--seed", required=True)
    split.add_argument(
        "--out",
        type=Path,
        required=True,
        help="file the gate reads; holds the full split including held-out ids",
    )
    split.add_argument("--sel-ratio", default="0.4")
    split.add_argument("--test-ratio", default="0.0")
    split.add_argument("--min-sel", type=int, default=3)
    split.set_defaults(func=cmd_split)

    budget = sub.add_parser("budget", help="edits allowed at this step")
    budget.add_argument("--step", type=_arith_int, required=True)
    budget.add_argument("--total", type=_arith_int, required=True)
    budget.add_argument("--max-edits", type=_arith_int, default=5)
    budget.add_argument("--min-edits", type=_arith_int, default=1)
    budget.set_defaults(func=cmd_budget)

    score_cmd = sub.add_parser("score", help="fraction of one split group passing")
    score_cmd.add_argument("--results", type=Path, required=True)
    score_cmd.add_argument("--split", type=Path, required=True)
    # Only the optimize group. The gate scores the selection group itself,
    # inside a decision that consumes a consultation. A free-standing score on
    # a held-out group is exactly the unmetered read the budget exists to
    # count, so the flag does not offer one.
    score_cmd.add_argument("--group", default="opt", choices=("opt",))
    score_cmd.set_defaults(func=cmd_score)

    apply_cmd = sub.add_parser("apply", help="apply bounded patches to an artifact")
    apply_cmd.add_argument("--file", type=Path, required=True)
    apply_cmd.add_argument("--patches", type=Path, required=True)
    apply_cmd.add_argument("--budget", type=int, required=True)
    apply_cmd.add_argument("--dry-run", action="store_true")
    apply_cmd.set_defaults(func=cmd_apply)

    gate_cmd = sub.add_parser("gate", help="decide whether a candidate replaces the incumbent")
    gate_cmd.add_argument("--incumbent", type=Path, required=True)
    gate_cmd.add_argument("--candidate", type=Path, required=True)
    gate_cmd.add_argument("--split", type=Path, required=True)
    # No --group. A gate reads the held-out group by definition, and offering
    # the choice let a caller gate on the group it had already optimized against.
    # No --ledger either: see _ledger_path for why the caller does not choose it.
    gate_cmd.add_argument(
        "--max-consultations",
        type=_arith_int,
        required=True,
        help="how many comparisons this split may ever answer; fixed at the first gate",
    )
    gate_cmd.add_argument(
        "--incumbent-fingerprint",
        required=True,
        help="split fingerprint the incumbent was scored against; `score` reports it",
    )
    gate_cmd.add_argument(
        "--max-p",
        type=float,
        default=None,
        help=(
            "largest one-sided exact McNemar tail this gate accepts; "
            "omit on a small held-out group, where no tail can clear a "
            "conventional floor"
        ),
    )
    gate_cmd.set_defaults(func=cmd_gate)

    check = sub.add_parser("buffer-check", help="has this edit already been rejected")
    check.add_argument("--buffer", type=Path, required=True)
    check.add_argument("--patches", type=Path, required=True)
    check.set_defaults(func=cmd_buffer_check)

    add = sub.add_parser("buffer-add", help="record a rejected edit")
    add.add_argument("--buffer", type=Path, required=True)
    add.add_argument("--patches", type=Path, required=True)
    add.add_argument("--reason", required=True)
    add.set_defaults(func=cmd_buffer_add)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return EXIT_CONFIG
    try:
        # argparse.Namespace attributes are Any; every registered handler
        # returns an exit code.
        exit_code: int = args.func(args)
    except (ConfigError, AdapterError, ValueError) as exc:
        # JSON, not a bare message, because the module docstring promises a
        # caller can tell a REJECT from a config failure by reading a field
        # rather than guessing from the exit code. A plain-text error breaks
        # that promise for any driver piping stdout through a JSON reader.
        #
        # ValueError joins them so the core's own validation surfaces the same
        # way. Wrapping one call site left the policy in two places and the
        # wrapper unreachable once its inputs were validated upstream.
        _emit({"error": str(exc), "type": type(exc).__name__})
        return EXIT_CONFIG
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
