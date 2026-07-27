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
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc


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


def _read_results(path: Path) -> dict[str, bool]:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must hold a JSON object of task id to boolean")
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
        redrawn = split_tasks(
            tasks,
            seed=str(split["seed"]),
            sel_ratio=float(split["sel_ratio"]),
            test_ratio=float(split["test_ratio"]),
            min_sel=int(split.get("min_sel", 3)),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"split file holds unusable seed or ratios: {exc}") from exc
    if redrawn.fingerprint != split["fingerprint"]:
        return True
    return any(sorted(getattr(redrawn, g)) != sorted(split[g]) for g in _GROUPS)


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
    if args.kind == "hook":
        results = pytest_results(_read_text(args.input), on_skip=args.on_skip)
    elif args.kind == "agent":
        report = _read_json(args.input)
        if not isinstance(report, Mapping):
            raise ConfigError(f"{args.input} must hold an agent report object")
        results = agent_results(
            report,
            args.variant,
            reduce=args.reduce,
            pass_threshold=args.pass_threshold,
        )
    else:
        results = _extract_rule(_read_json(args.input), args)
    _emit(results)
    return EXIT_OK


# ---------------------------------------------------------------------------
# split, budget, score
# ---------------------------------------------------------------------------


def cmd_split(args: argparse.Namespace) -> int:
    if args.results:
        task_ids = sorted(_read_results(args.results))
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
    results = _read_results(args.results)
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
    """
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


def _ledger_path(holdout_key: str) -> Path:
    """Where the budget for one held-out group lives."""
    return _ledger_root() / f"{holdout_key}.ledger"


@contextmanager
def _ledger_held(holdout_key: str) -> Iterator[None]:
    """Serialize the read, compare, and write of one ledger.

    Without this, two gates started together both read the same count, both
    compare, and both write count + 1, so N concurrent gates spend one
    consultation between them. Atomic replacement keeps the file whole; it does
    not make the read-modify-write sequence a transaction.

    An exclusive create is the lock rather than `fcntl`, which is POSIX only.
    A stale lock left by a killed process is reported rather than broken, since
    guessing that the holder is gone is how a lock becomes advisory.
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
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise ConfigError(
                f"another gate holds a lock under {lock.parent}; consultations "
                f"against one held-out group are serialized so a concurrent "
                f"pair cannot spend one budget twice. Remove the lock file "
                f"there if no gate is running. Its name is withheld: the name "
                f"digests the held-out membership, and an unsalted digest of a "
                f"set the caller can enumerate is that set."
            ) from None
        try:
            try:
                os.write(handle, str(os.getpid()).encode("utf-8"))
            finally:
                # Its own finally, so a write that fails on a full disk still
                # releases the descriptor. POSIX frees the descriptor even when
                # close reports EIO, so this must never be retried.
                os.close(handle)
            yield
        finally:
            try:
                lock.unlink(missing_ok=True)
            except OSError as exc:
                # The decision is already on stdout. Letting this reach main
                # would print a second JSON document after it and return the
                # config-failure code for a comparison that succeeded, and the
                # module docstring promises one readable document. Silence
                # would hide a lock that now blocks the next run, so it goes to
                # stderr, named by its directory rather than by itself.
                #
                # Through _scrub, because naming the directory was justified in
                # review by the claim that a directory carries no digest, and a
                # tenth review falsified it: $EVAL_LEDGER_DIR can name one.
                print(
                    _scrub(
                        f"warning: could not remove the lock under {lock.parent} "
                        f"({exc.strerror or exc.errno}); the next gate against "
                        f"this held-out group reports contention until it is "
                        f"removed. Its name is withheld: the name digests the "
                        f"membership.",
                        holdout_key,
                    ),
                    file=sys.stderr,
                )


def _read_ledger(path: Path, holdout_key: str, cap: int) -> int:
    """Return the consultations already spent against this split.

    The count lives here rather than on the command line because a budget the
    caller supplies is not a budget: passing zero every time yields an
    unlimited one while still looking capped. The cap is recorded for the same
    reason. Pinning only the count left the limit re-suppliable, so a caller
    that hit the budget could raise it and carry on, which is the defect the
    ledger was written to close wearing a different hat.

    The ledger records the held-out key it was opened under. That is the same
    value its filename carries, so the check catches a ledger moved or renamed
    into another group's place rather than an honest redraw: a genuinely new
    held-out group has a different key and therefore its own file.
    """
    if not path.exists():
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
    return spent


def _write_ledger(path: Path, holdout_key: str, spent: int, cap: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"consultations": spent, "holdout": holdout_key, "max_consultations": cap}
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

    # The lock spans read, compare, and write. A drifted split never reaches it
    # because that refusal reads no ledger and spends nothing.
    with _ledger_held(_holdout_key(split)):
        return _gate_decision(args, split)


def _gate_decision(args: argparse.Namespace, split: dict[str, Any]) -> int:
    """Spend at most one consultation and report what it bought."""
    holdout_key = _holdout_key(split)
    ledger = _ledger_path(holdout_key)
    try:
        with _digest_scrubbed(holdout_key):
            spent = _read_ledger(ledger, holdout_key, args.max_consultations)
    except LedgerMismatchError as exc:
        _emit({
            "decision": "REJECT",
            "reason": str(exc),
            "compared": False,
            "sel_consultations": 0,
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
                "sel_consultations": spent,
                "compared": False,
                "group": _GATE_GROUP,
                "fingerprint": split["fingerprint"],
            }
        )
        return EXIT_LOGIC

    incumbent_results = _read_results(args.incumbent)
    candidate_results = _read_results(args.candidate)
    sel_ids = _group_ids(split, _GATE_GROUP)

    # Charge before reading the group, not after reaching a verdict. Two things
    # made the old order wrong. A crash between scoring and the write left the
    # held-out group read and the consultation unrecorded, so a retry got the
    # comparison for free. And any refusal decided after scoring was equally
    # free, which is what made the reveal below worth buying.
    spent_after = spent + 1
    with _digest_scrubbed(holdout_key):
        _write_ledger(ledger, holdout_key, spent_after, args.max_consultations)

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
    result = gate(
        candidate,
        incumbent,
        sel_consultations=spent,
        max_consultations=args.max_consultations,
        split_fingerprint=split["fingerprint"],
        incumbent_fingerprint=args.incumbent_fingerprint,
        discordant_loss=loss,
    )

    _emit(
        {
            "decision": result.decision,
            "reason": result.reason,
            "candidate": result.candidate,
            "incumbent": result.incumbent,
            # Discordant pairs are the only tasks that carry evidence about the
            # edit. p is the one-sided exact McNemar tail, reported rather than
            # enforced: a three-task held-out group cannot reach 0.05, so
            # enforcing a conventional floor would make the common case
            # unpassable instead of informative.
            "discordant_gain": gain,
            "discordant_loss": loss,
            "p_value": p_value,
            "sel_consultations": spent_after,
            "compared": result.compared,
            "group": _GATE_GROUP,
            "fingerprint": split["fingerprint"],
        }
    )
    return EXIT_OK if result.decision == "ACCEPT" else EXIT_LOGIC


# ---------------------------------------------------------------------------
# buffer
# ---------------------------------------------------------------------------


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

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException as exc:
        # Close the fd if os.fdopen failed (fd not yet owned by the handle).
        # If os.fdopen succeeded, the with-block already closed it.
        tmp.unlink(missing_ok=True)
        if isinstance(exc, OSError):
            raise ConfigError(f"could not write {path}: {exc}") from exc
        raise


def _read_buffer(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        # A first run has no ledger yet. Treating that as empty keeps the loop
        # from needing a separate init step.
        return []
    data = _read_json(path)
    if not isinstance(data, list):
        raise ConfigError(f"{path} must hold a JSON array of rejection entries")
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ConfigError(f"{path} entry {index} must be an object, got {entry!r}")
    return data


def cmd_buffer_check(args: argparse.Namespace) -> int:
    entries = _read_buffer(args.buffer)
    patches = _read_patches(args.patches)
    seen = buffer_contains(entries, patches)
    _emit({"seen": seen, "fingerprint": patch_fingerprint(patches)})
    return EXIT_LOGIC if seen else EXIT_OK


def cmd_buffer_add(args: argparse.Namespace) -> int:
    entries = _read_buffer(args.buffer)
    patches = _read_patches(args.patches)
    fingerprint = patch_fingerprint(patches)
    if any(e.get("fingerprint") == fingerprint for e in entries):
        _emit({"added": False, "fingerprint": fingerprint, "entries": len(entries)})
        return EXIT_OK
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
    _emit({"added": True, "fingerprint": fingerprint, "entries": len(entries)})
    return EXIT_OK


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


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
    split.add_argument("--sel-ratio", type=float, default=0.4)
    split.add_argument("--test-ratio", type=float, default=0.0)
    split.add_argument("--min-sel", type=int, default=3)
    split.set_defaults(func=cmd_split)

    budget = sub.add_parser("budget", help="edits allowed at this step")
    budget.add_argument("--step", type=int, required=True)
    budget.add_argument("--total", type=int, required=True)
    budget.add_argument("--max-edits", type=int, default=5)
    budget.add_argument("--min-edits", type=int, default=1)
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
        type=int,
        required=True,
        help="how many comparisons this split may ever answer; fixed at the first gate",
    )
    gate_cmd.add_argument(
        "--incumbent-fingerprint",
        required=True,
        help="split fingerprint the incumbent was scored against; `score` reports it",
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
