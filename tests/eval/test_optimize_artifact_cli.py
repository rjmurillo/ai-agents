"""Tests for scripts/eval/optimize-artifact.py (issue #3422).

The CLI is the surface an optimizing agent drives. Its job is to make the
held-out discipline mechanical: the agent proposes edits, the CLI decides
whether they survive, and the agent cannot reach the accept decision without
going through a split it did not choose.

The safety property worth testing hardest is that `gate` scores both sides
itself from the split's `sel` group. If the gate took bare numbers, the
easiest mistake in the whole loop would be handing it optimize-set scores,
which is precisely the overfitting the gate exists to stop.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import os
import re
import stat
import subprocess
import sys
import traceback
from contextvars import copy_context
from pathlib import Path

import pytest

from scripts.utils.markdown_parser import _create_parser

_EVAL_DIR = Path(__file__).resolve().parents[2] / "scripts" / "eval"
# Scope the sys.path mutation to the module load and remove it afterward so it
# does not leak into other tests (mirrors tests/eval/test_variance_control.py).
_path_added = str(_EVAL_DIR) not in sys.path
try:
    if _path_added:
        sys.path.insert(0, str(_EVAL_DIR))
    _SCRIPT = _EVAL_DIR / "optimize-artifact.py"
    _spec = importlib.util.spec_from_file_location("optimize_artifact", _SCRIPT)
    assert _spec is not None and _spec.loader is not None
    oa = importlib.util.module_from_spec(_spec)
    sys.modules["optimize_artifact"] = oa
    _spec.loader.exec_module(oa)
    # Loaded separately rather than read off `oa`. A test that compares
    # `oa.X` to the parser `oa` built resolves both sides through the
    # module under test, so it passes even when that module stops
    # importing the constant and hardcodes its own copy, which is the one
    # defect the comparison exists to catch.
    adapters = importlib.import_module("_optimizer_adapters")
    core = importlib.import_module("_optimizer_core")
finally:
    if _path_added and str(_EVAL_DIR) in sys.path:
        sys.path.remove(str(_EVAL_DIR))


EXIT_OK = 0
EXIT_LOGIC = 1
EXIT_CONFIG = 2

# `--artifact` became required on buffer-add and buffer-check once dedup
# started keying on artifact_fingerprint too, not only patch fingerprint.
# The lock and error-handling tests below exercise buffer-add/buffer-check
# failure paths unrelated to that dedup key, so they all point at this one
# always-readable file (the test module itself) instead of threading a
# constructed artifact through every call site.
_STATIC_ARTIFACT = Path(__file__)

# Several tests build a barrier out of file permissions. Root ignores the mode
# bits and Windows does not carry them, so on either the barrier is not there
# and the command under test succeeds where the test expects a refusal. That
# reads as a failure in the code rather than an absent precondition, which is
# what this skips instead.
_NO_PERMISSION_BARRIER = os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0)
_NEEDS_PERMISSION_BARRIER = pytest.mark.skipif(
    _NO_PERMISSION_BARRIER, reason="root and Windows do not honour the barrier this needs"
)


def _key_of(split_path):
    """The held-out key the gate will use for this split file."""
    return oa._holdout_key(json.loads(Path(split_path).read_text(encoding="utf-8")))


def _raise_boom(*_args, **_kwargs):
    """Stand-in for any failure between taking the lock and releasing it."""
    raise RuntimeError("boom")


def _legacy_split_fingerprint(task_ids, *, seed, sel_ratio, test_ratio=0.0):
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
    return oa.hashlib.sha256(payload.encode()).hexdigest()


@pytest.fixture(autouse=True)
def _isolated_ledger_root(tmp_path_factory, monkeypatch):
    """Point the consultation ledgers at this test's own directory.

    They are keyed by split fingerprint in one fixed root, which is what stops
    a caller buying a fresh budget by renaming the split. The same property
    means two tests that draw the same split share a ledger, so the root has to
    move per test rather than the key. It sits outside `tmp_path` because tests
    that assert on the contents of `tmp_path` should not see it.
    """
    monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path_factory.mktemp("ledgers")))


def _provenance(name: str, results: dict) -> dict:
    return {
        "schema": oa._PROVENANCE_SCHEMA,
        "extractor_version": oa._EXTRACTOR_VERSION,
        "input_path": name,
        "input_digest": "0" * 64,
        "results_digest": oa._results_digest(results),
        "upstream_scorer": "test",
        "upstream_model": "test-model",
        "upstream_seed": "test-seed",
    }


def _enveloped(corpus, results: dict, *, name: str = "test-input") -> dict:
    """A results file in the envelope the extractor writes."""
    return {
        "schema": "optimizer-results/1",
        "corpus": corpus,
        "provenance": _provenance(name, results),
        "results": results,
    }


def _env_file(tmp_path, name: str, corpus, n: int = 10):
    """An enveloped results file of `n` passing tasks."""
    results = {f"t{i}": True for i in range(n)}
    return _write(tmp_path, name, _enveloped(corpus, results, name=name))


def _results_from_file(path: Path) -> dict[str, bool]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("schema") == "optimizer-results/1":
        data = data["results"]
    if not isinstance(data, dict):
        raise ValueError("results fixture is not an object")
    return data


def _reject_duplicate_keys(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate keys")
    return dict(pairs)


def _enveloped_copy(path: Path) -> Path:
    # A file the strict reader would refuse must reach the CLI untranslated,
    # so the refusal under test happens in the CLI rather than in this shim.
    json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and data.get("schema") == "optimizer-results/1":
        return path
    results = _results_from_file(path)
    copy = path.with_name(f"{path.stem}-enveloped{path.suffix}")
    copy.write_text(json.dumps(_enveloped(None, results, name=path.name)), encoding="utf-8")
    return copy


def _tasks_copy(path: Path) -> Path:
    results = _results_from_file(path)
    copy = path.with_name(f"{path.stem}.tasks")
    copy.write_text("\n".join(sorted(results)) + "\n", encoding="utf-8")
    return copy


def _translated_argv(argv: tuple[str | Path, ...]) -> list[str]:
    translated = [str(a) for a in argv]
    if not translated:
        return translated
    command = translated[0]
    if command == "split" and "--results" in translated:
        index = translated.index("--results")
        try:
            source = Path(translated[index + 1])
            data = json.loads(source.read_text(encoding="utf-8"))
            corpus = data.get("corpus") if isinstance(data, dict) else None
            translated[index] = "--tasks"
            translated[index + 1] = str(_tasks_copy(source))
            if corpus is not None and "--corpus" not in translated:
                translated += ["--corpus", str(corpus)]
        except (OSError, ValueError, RecursionError):
            pass
    if command in {"gate", "score"}:
        for flag in ("--incumbent", "--candidate", "--results"):
            if flag in translated:
                index = translated.index(flag)
                try:
                    translated[index + 1] = str(_enveloped_copy(Path(translated[index + 1])))
                except (OSError, ValueError, RecursionError):
                    pass
    return translated


class _Unflushable(io.TextIOBase):
    """A stream whose flush fails the way a closed pipe's does.

    `close` is overridden because `io.TextIOBase` finalization flushes, which
    would raise during garbage collection and surface as
    PytestUnraisableExceptionWarning in whichever test happened to trigger it.
    """

    def flush(self) -> None:
        raise BrokenPipeError(32, "broken pipe")

    def close(self) -> None:
        """Finalization calls close, which would flush and raise again."""


_LOAD_MODULE = """
import importlib.util, io, sys
spec = importlib.util.spec_from_file_location("oa", sys.argv[1])
oa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oa)
"""

_CLOSED_STDOUT_DRIVER = _LOAD_MODULE + """
sys.stdout.close()
raise SystemExit(oa._final_exit_code(oa.main(["budget", "--step", "1", "--total", "9"])))
"""

_NO_FILENO_DRIVER = _LOAD_MODULE + """
class _NoDescriptor(io.TextIOBase):
    def flush(self):
        raise BrokenPipeError(32, "broken pipe")

    def close(self):
        pass

sys.stdout = _NoDescriptor()
raise SystemExit(oa._final_exit_code(oa.EXIT_OK))
"""


def _markdown_block(text: str, marker: str) -> str:
    """The one Markdown block in ``text`` containing ``marker``.

    Documentation tests need a window or they assert nothing, and every window
    this file has tried was too wide. A file-wide search passes on an unrelated
    historical mention elsewhere, which is the state the `--on-skip` gap was
    found in: the words existed and the contract did not. A fixed character
    count silently changes meaning whenever correct prose grows. Bounding at
    the next heading looked principled and was not: the enclosing section
    already said "consultations" three paragraphs down, so an assertion meant
    for the new prose passed on someone else's.

    A blank-line-delimited paragraph was the fourth, and the closest, and it
    still borrows from its neighbours. CommonMark lets a heading, a list, a
    blockquote, and a fence interrupt a paragraph with no blank line before
    them, so `prose\\n### Heading\\nmore prose` is three blocks to every
    renderer and was one window here.

    Bounding on hand-written patterns for those starts was the fifth, and it
    lost on the constructs the list did not name: a thematic break, a setext
    underline, a blockquote written without its space, an indented run of
    backticks that is not a fence, and prose on the line after a fence
    closes. Each is a separate patch, and the next construct is another one.

    Ask the parser instead. `markdown-it-py` reports a line range for every
    block it finds, so the window is whatever the renderer drew, including
    the constructs nobody thought to enumerate. The narrowest range covering
    the marker is its block: a paragraph inside a list item is the item's
    prose rather than the whole list, and a fence is the whole listing, which
    matters because the README opens with a `bash` block whose comments start
    with `#`.

    The dialect comes from `scripts/utils/markdown_parser`, the parser this
    repo already reads Markdown with, so this window and every other reader
    of a repo document agree about what a block is.

    Raises:
        AssertionError: ``marker`` is absent or repeated. Absent means the
            prose was rewritten and the test needs updating rather than
            quietly widening; repeated means the window would be arbitrary.
    """
    found = [m.start() for m in re.finditer(re.escape(marker), text)]
    assert len(found) == 1, (
        f"README contains {marker!r} {len(found)} times; a marker that is not "
        "unique picks an arbitrary block, so choose a longer one"
    )
    target = text.count("\n", 0, found[0])

    narrowest: tuple[int, int] | None = None
    narrowest_type = ""
    for token in _create_parser().parse(text):
        # `inline` carries a block's content, not the block, and for a setext
        # heading its range excludes the underline. Blocks only, so the window
        # is what the renderer drew rather than what it drew inside.
        if token.map is None or token.type == "inline":
            continue
        start, end = token.map
        if start <= target < end and (
            narrowest is None or end - start < narrowest[1] - narrowest[0]
        ):
            narrowest = (start, end)
            narrowest_type = token.type
    if narrowest is None:
        raise AssertionError(
            f"{marker!r} is on no block the renderer draws, so there is no "
            "window to assert on: it is on a blank line, or inside a "
            "construct the parser consumes without emitting, such as a link "
            "reference definition"
        )
    if narrowest_type == "html_block":
        raise AssertionError(
            f"{marker!r} is inside raw HTML, where one Markdown block can be "
            "several elements the reader sees: CommonMark ends the block at a "
            "blank line, not at the end of an element. The window would "
            "borrow a sibling's words, so assert on Markdown prose instead"
        )
    return "\n".join(text.split("\n")[narrowest[0]:narrowest[1]])


def _readme_paragraph(marker: str) -> str:
    """The one block of the eval README containing `marker`.

    Kept separate from `_markdown_block` so the windowing rule can be tested
    against written-out cases rather than against whatever the README happens
    to say today. The four earlier windows were each correct for the README
    that motivated them, so pinning the rule to the current file is how a
    fifth one would go unnoticed.
    """
    return _markdown_block((_EVAL_DIR / "README.md").read_text(encoding="utf-8"), marker)


def _run(capsys, *argv: str | Path) -> tuple[int, dict]:
    """Invoke the CLI and return (exit code, parsed stdout JSON)."""
    code = oa.main(_translated_argv(argv))
    out = capsys.readouterr().out.strip()
    return code, (json.loads(out) if out else {})


def _run_raw(capsys, *argv: str | Path) -> tuple[int, dict]:
    code = oa.main([str(a) for a in argv])
    out = capsys.readouterr().out.strip()
    return code, (json.loads(out) if out else {})


def _split(capsys, tmp_path, *args, name="split.json"):
    """Run `split` and return the full record from the file the gate reads.

    Stdout deliberately redacts held-out membership, so any test that needs
    the whole split has to read it the way the gate does.
    """
    path = tmp_path / name
    code, stdout = _run(capsys, "split", *args, "--out", path)
    if code != EXIT_OK:
        return code, stdout
    return code, json.loads(path.read_text(encoding="utf-8"))


def _run_gate(capsys, tmp_path, *args, spent=None, cap=100):
    """Run `gate`, supplying the two arguments it now requires.

    The consultation count used to arrive on the command line, which meant a
    caller that passed zero every time had an unlimited budget. The cap and
    the incumbent fingerprint went the same way: both defaulted to a value
    that skipped the check. Tests that are not about those arguments get
    working defaults here; `spent` pre-seeds the derived ledger for tests that
    need the gate to believe consultations have already happened.
    """
    argv = list(args)
    if "--max-consultations" not in argv:
        argv += ["--max-consultations", str(cap)]
    effective = int(argv[argv.index("--max-consultations") + 1])
    split = _split_of(argv)
    if "--incumbent-fingerprint" not in argv and isinstance(split, dict):
        argv += ["--incumbent-fingerprint", str(split.get("fingerprint", "unknown"))]
    if spent is not None and isinstance(split, dict):
        key = oa._holdout_key(split)
        seeded = oa._ledger_path(key)
        seeded.parent.mkdir(parents=True, exist_ok=True)
        seeded.write_text(
            json.dumps({"consultations": spent, "holdout": key,
                        "max_consultations": effective}),
            encoding="utf-8",
        )
    return _run(capsys, "gate", *argv)


def _split_of(argv):
    """The split record behind `--split`, or None when it is unreadable.

    Config-error tests deliberately point `--split` at missing or malformed
    files, and the helper still has to run them.
    """
    if "--split" not in argv:
        return None
    try:
        return json.loads(Path(argv[argv.index("--split") + 1]).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def _boom(*_args, **_kwargs):
    raise OSError("disk full")


def _write(tmp_path: Path, name: str, payload: object) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _results(passing: int, failing: int) -> dict:
    out = {f"p{i}": True for i in range(passing)}
    out.update({f"f{i}": False for i in range(failing)})
    return out


def _passing_results(n: int = 10) -> dict[str, bool]:
    return {f"t{i}": True for i in range(n)}


# ---------------------------------------------------------------------------
# extract
# ---------------------------------------------------------------------------


class TestExtract:
    def test_agent_report(self, tmp_path, capsys):
        report = _write(
            tmp_path,
            "report.json",
            {
                "error_count": 0,
                "per_fixture_pass_rates": {"C1": {"agent": [1.0]}, "C2": {"agent": [0.0]}},
            },
        )
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_OK
        assert out["results"] == {"C1": True, "C2": False}

    def test_agent_report_honors_variant_and_threshold(self, tmp_path, capsys):
        report = _write(
            tmp_path,
            "report.json",
            {
                "error_count": 0,
                "per_fixture_pass_rates": {"C1": {"baseline": [0.6]}},
            },
        )
        code, out = _run(
            capsys,
            "extract",
            "--kind",
            "agent",
            "--input",
            report,
            "--variant",
            "baseline",
            "--pass-threshold",
            "0.5",
        )
        assert code == EXIT_OK
        assert out["results"] == {"C1": True}

    def test_rule_scenarios(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": 5,
                                "citation_score": 5,
                                "behavior_score": 5,
                            }
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_OK
        assert out["results"] == {"S1": True}

    def test_rule_extract_refuses_errored_mechanism(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "error": "model timeout",
                            "scores": {
                                "activation_score": 0,
                                "citation_score": 0,
                                "behavior_score": 0,
                            },
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded rule report" in out["error"]
        assert "S1" in out["error"]

    def test_rule_extract_refuses_empty_scores(self, tmp_path, capsys):
        """Missing or empty scores block is degraded (fail closed)."""
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {},
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded rule report" in out["error"]
        assert "S1" in out["error"]

    def test_rule_extract_refuses_missing_scores(self, tmp_path, capsys):
        """None scores block is degraded (fail closed)."""
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {}
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded rule report" in out["error"]
        assert "S1" in out["error"]

    def test_rule_extract_clean_report_succeeds(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S2",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": 5,
                                "citation_score": 4,
                                "behavior_score": 5,
                            }
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_OK
        assert out["results"] == {"S2": True}

    def test_rule_extract_reduces_persisted_judge_samples(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": 1,
                                "citation_score": 1,
                                "behavior_score": 1,
                            },
                            "score_samples": [
                                {
                                    "activation_score": 1,
                                    "citation_score": 1,
                                    "behavior_score": 1,
                                    "judge_failed": False,
                                },
                                {
                                    "activation_score": 5,
                                    "citation_score": 5,
                                    "behavior_score": 5,
                                    "judge_failed": False,
                                },
                                {
                                    "activation_score": 5,
                                    "citation_score": 5,
                                    "behavior_score": 5,
                                    "judge_failed": False,
                                },
                            ],
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_OK
        assert out["schema"] == "optimizer-results/1"
        assert out["corpus"] is None
        assert out["results"] == {"S1": True}

    def test_rule_extract_refuses_judge_failed_sample(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": 5,
                                "citation_score": 5,
                                "behavior_score": 5,
                            },
                            "score_samples": [
                                {
                                    "activation_score": 5,
                                    "citation_score": 5,
                                    "behavior_score": 5,
                                    "judge_failed": False,
                                },
                                {"judge_failed": True, "reasoning": "timeout"},
                                {
                                    "activation_score": 5,
                                    "citation_score": 5,
                                    "behavior_score": 5,
                                    "judge_failed": False,
                                },
                            ],
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded rule report" in out["error"]
        assert "S1" in out["error"]

    def test_rule_extract_refuses_missing_sample_scores(self, tmp_path, capsys):
        scenarios = _write(
            tmp_path,
            "scen.json",
            [
                {
                    "id": "S1",
                    "negative_case": False,
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": 5,
                                "citation_score": 5,
                                "behavior_score": 5,
                            },
                            "score_samples": [
                                {
                                    "activation_score": 5,
                                    "citation_score": 5,
                                    "judge_failed": False,
                                }
                            ],
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "behavior_score" in out["error"]

    def test_rule_extract_refuses_judge_failure_verdict(self, tmp_path, capsys):
        envelope = {
            "rules": {
                "refactoring": {
                    "summary": {"verdict": "FAIL_JUDGE_ERRORS"},
                    "scenarios": [
                        {
                            "id": "S3",
                            "negative_case": False,
                            "mechanisms": {
                                "full": {
                                    "scores": {
                                        "activation_score": 0,
                                        "citation_score": 0,
                                        "behavior_score": 0,
                                        "judge_failed": True,
                                    }
                                }
                            },
                        }
                    ],
                }
            }
        }
        path = _write(tmp_path, "rules.json", envelope)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "refactoring::S3" in out["error"]

    def test_a_scenario_that_is_not_an_object_is_not_called_degraded(self, tmp_path, capsys):
        """A non-object entry has no id to report, so the scan skips it.

        The degraded scan reports task ids. A bare string or number in the
        array supplies none, so naming it would mean inventing one. The
        scorer refuses the same input on its own terms, which is where a
        malformed array should be caught.
        """
        scenarios = _write(tmp_path, "scen.json", ["not-an-object"])
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded" not in out["error"]

    def test_a_scenario_with_no_mechanisms_block_is_degraded(self, tmp_path, capsys):
        """No mechanisms block at all is the same loss as an errored one.

        A scenario that never ran and a scenario that ran and failed both
        yield no score. Treating the absent block as a pass would score a
        measurement that does not exist.
        """
        scenarios = _write(
            tmp_path, "scen.json", [{"id": "S9", "negative_case": False}]
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG
        assert "degraded rule report" in out["error"]
        assert "S9" in out["error"]

    def test_a_judge_failure_verdict_is_reported_when_no_scenario_carries_it(
        self, tmp_path, capsys
    ):
        """The summary verdict is the only witness when the scenarios look clean.

        A report whose scenarios all scored but whose summary says the judge
        failed is still degraded, and nothing under that rule names the loss.
        The placeholder id exists so the refusal has something to point at.
        """
        envelope = {
            "rules": {
                "refactoring": {
                    "summary": {"verdict": "FAIL_JUDGE_ERRORS"},
                    "scenarios": [
                        {
                            "id": "S4",
                            "negative_case": False,
                            "mechanisms": {
                                "full": {
                                    "scores": {
                                        "activation_score": 5,
                                        "citation_score": 5,
                                        "behavior_score": 5,
                                    }
                                }
                            },
                        }
                    ],
                }
            }
        }
        path = _write(tmp_path, "rules.json", envelope)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "refactoring::<FAIL_JUDGE_ERRORS>" in out["error"]

    def test_rule_scenarios_accept_a_wrapped_object(self, tmp_path, capsys):
        """A bare scenario list may also arrive wrapped in a 'scenarios' key."""
        scenarios = _write(
            tmp_path,
            "scen.json",
            {
                "scenarios": [
                    {
                        "id": "S1",
                        "negative_case": False,
                        "mechanisms": {
                            "full": {
                                "scores": {
                                    "activation_score": 5,
                                    "citation_score": 5,
                                    "behavior_score": 5,
                                }
                            }
                        },
                    }
                ]
            },
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_OK
        assert out["results"] == {"S1": True}

    def test_rule_scenario_scored_below_the_bar_is_a_failure(self, tmp_path, capsys):
        """Complete scores under `--min-score` fail rather than refuse.

        The distinction this pins is between a scenario that was measured and
        lost and one that was never measured. Both were reachable through the
        same shape here, because the fixture above once carried a single score
        key: the scenario failed, but for the missing keys rather than the low
        one, so nothing covered a complete block that simply scored badly.

        Kept as its own case because the sibling above now scores at the top of
        the scale to prove the wrapper parses. One fixture cannot assert both
        directions, and dropping either leaves the boundary between them
        untested.
        """
        scenarios = _write(
            tmp_path,
            "low.json",
            {
                "scenarios": [
                    {
                        "id": "S1",
                        "negative_case": False,
                        "mechanisms": {
                            "full": {
                                "scores": {
                                    "activation_score": 1,
                                    "citation_score": 1,
                                    "behavior_score": 1,
                                }
                            }
                        },
                    }
                ]
            },
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_OK
        assert out["results"] == {"S1": False}

    def test_hook_junit(self, tmp_path, capsys):
        junit = tmp_path / "j.xml"
        junit.write_text(
            "<testsuites><testsuite>"
            "<testcase classname='tests.test_a' name='test_x'/>"
            "<testcase classname='tests.test_a' name='test_y'><failure/></testcase>"
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        code, out = _run(capsys, "extract", "--kind", "hook", "--input", junit)
        assert code == EXIT_OK
        assert out["results"] == {"tests.test_a::test_x": True, "tests.test_a::test_y": False}

    def test_missing_input_is_a_config_error(self, tmp_path, capsys):
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", tmp_path / "nope.json")
        assert code == EXIT_CONFIG

    def test_malformed_json_is_a_config_error(self, tmp_path, capsys):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", bad)
        assert code == EXIT_CONFIG

    def test_adapter_rejection_is_a_config_error(self, tmp_path, capsys):
        report = _write(tmp_path, "report.json", {"wrong": "shape"})
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_CONFIG

    def test_non_object_agent_report_is_a_config_error(self, tmp_path, capsys):
        report = _write(tmp_path, "report.json", ["not", "an", "object"])
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_CONFIG

    def test_non_array_rule_input_is_a_config_error(self, tmp_path, capsys):
        scenarios = _write(tmp_path, "scen.json", {"scenarios": "not a list"})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == EXIT_CONFIG


class TestExtractRealRuleEnvelope:
    """The shape eval-rule-activation.py --output actually writes.

    Verified against a live run over tests/evals/rule-scenarios/*.json: the
    file is {"rules": {<rule-name>: {"rule_path", "scenarios", "summary"}}}.
    Scenario ids restart at S1 inside every rule, so 24 real scenarios carry
    only 4 distinct ids and must be namespaced before they can be task ids.
    """

    @staticmethod
    def _scenario(sid: str, score: int) -> dict:
        return {
            "id": sid,
            "negative_case": False,
            "mechanisms": {
                "full": {
                    "scores": {
                        "activation_score": score,
                        "citation_score": score,
                        "behavior_score": score,
                    }
                }
            },
        }

    def _envelope(self) -> dict:
        return {
            "rules": {
                "clean-architecture": {
                    "rule_path": ".claude/rules/clean-architecture.md",
                    "scenarios": [self._scenario("S1", 5), self._scenario("S2", 1)],
                    "summary": {"verdict": "PASS"},
                },
                "refactoring": {
                    "rule_path": ".claude/rules/refactoring.md",
                    "scenarios": [self._scenario("S1", 1)],
                    "summary": {"verdict": "PASS"},
                },
            }
        }

    def test_accepts_the_rules_envelope(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", self._envelope())
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_OK
        assert len(out["results"]) == 3

    def test_namespaces_scenario_ids_by_rule(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", self._envelope())
        _, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert out["results"] == {
            "clean-architecture::S1": True,
            "clean-architecture::S2": False,
            "refactoring::S1": False,
        }

    def test_a_single_rule_is_namespaced_too(self, tmp_path, capsys):
        """Namespacing must not depend on how many rules the file holds.

        If it did, adding a second rule would rewrite every existing task id
        and move the split fingerprint, which the gate refuses to compare.
        """
        envelope = {"rules": {"refactoring": {"scenarios": [self._scenario("S1", 5)]}}}
        path = _write(tmp_path, "rules.json", envelope)
        _, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert out["results"] == {"refactoring::S1": True}

    def test_a_non_mapping_rules_value_is_a_config_error(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", {"rules": ["not", "a", "mapping"]})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG

    def test_a_rule_entry_without_scenarios_is_a_config_error(self, tmp_path, capsys):
        """Fail closed. Skipping the rule would shrink the denominator."""
        path = _write(tmp_path, "rules.json", {"rules": {"refactoring": {"summary": {}}}})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG

    def test_a_non_mapping_rule_entry_is_a_config_error(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", {"rules": {"refactoring": "oops"}})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG

    def test_an_empty_rules_envelope_is_a_config_error(self, tmp_path, capsys):
        path = _write(tmp_path, "rules.json", {"rules": {}})
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# split
# ---------------------------------------------------------------------------


class TestSplit:
    def test_partitions_every_task(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(6, 4))
        code, out = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert code == EXIT_OK
        assert sorted(out["opt"] + out["sel"] + out["test"]) == sorted(_results(6, 4))
        assert out["fingerprint"]

    def test_is_deterministic_for_a_seed(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(6, 4))
        _, first = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        _, second = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert first == second

    def test_seed_changes_the_split(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(6, 4))
        _, first = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        _, second = _split(capsys, tmp_path, "--results", results, "--seed", "s2")
        assert first["fingerprint"] != second["fingerprint"]

    def test_reads_a_plain_task_id_list(self, tmp_path, capsys):
        tasks = tmp_path / "ids.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(10)) + "\n", encoding="utf-8")
        code, out = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "s1")
        assert code == EXIT_OK
        assert len(out["opt"] + out["sel"] + out["test"]) == 10

    def test_blank_lines_in_a_task_list_are_ignored(self, tmp_path, capsys):
        tasks = tmp_path / "ids.txt"
        tasks.write_text("t0\n\n  \nt1\nt2\nt3\nt4\nt5\nt6\nt7\n", encoding="utf-8")
        code, out = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "s1")
        assert code == EXIT_OK
        assert len(out["opt"] + out["sel"] + out["test"]) == 8

    def test_too_few_tasks_is_a_config_error(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(2, 0))
        code, _ = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert code == EXIT_CONFIG

    def test_requires_a_task_source(self, capsys):
        with pytest.raises(SystemExit):
            oa.main(["split", "--seed", "s1", "--out", "x.json"])

    def test_rejects_both_task_sources(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(6, 4))
        with pytest.raises(SystemExit):
            oa.main(
                ["split", "--results", str(results), "--tasks", "x", "--seed", "s",
                 "--out", "x.json"]
            )


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------


class TestBudget:
    def test_first_step_gets_the_maximum(self, capsys):
        code, out = _run(capsys, "budget", "--step", "0", "--total", "10")
        assert code == EXIT_OK
        assert out["budget"] == 5

    def test_last_step_gets_the_minimum(self, capsys):
        code, out = _run(capsys, "budget", "--step", "10", "--total", "10")
        assert code == EXIT_OK
        assert out["budget"] == 1

    def test_decays_monotonically(self, capsys):
        seen = [
            _run(capsys, "budget", "--step", str(s), "--total", "8")[1]["budget"]
            for s in range(9)
        ]
        assert seen == sorted(seen, reverse=True)

    def test_custom_bounds(self, capsys):
        code, out = _run(
            capsys, "budget", "--step", "0", "--total", "4", "--max-edits", "9", "--min-edits", "2"
        )
        assert code == EXIT_OK
        assert out["budget"] == 9

    def test_invalid_bounds_are_a_config_error(self, capsys):
        code, _ = _run(
            capsys, "budget", "--step", "0", "--total", "4", "--max-edits", "1", "--min-edits", "3"
        )
        assert code == EXIT_CONFIG

    def test_zero_total_is_a_config_error(self, capsys):
        code, _ = _run(capsys, "budget", "--step", "0", "--total", "0")
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# score
# ---------------------------------------------------------------------------


class TestScore:
    def _split_file(self, tmp_path, capsys, results_path) -> Path:
        _split(capsys, tmp_path, "--results", results_path, "--seed", "s1")
        return tmp_path / "split.json"

    def test_scores_the_optimize_group_by_default(self, tmp_path, capsys):
        """This test used to assert a default of `sel`, which was the hole.

        A free-standing unmetered score on the held-out group hands the
        optimizer the answer the gate is supposed to charge a consultation
        for. `opt` is the only group this command will read.
        """
        results = _write(tmp_path, "r.json", _results(10, 0))
        split = self._split_file(tmp_path, capsys, results)
        code, out = _run(capsys, "score", "--results", results, "--split", split)
        assert code == EXIT_OK
        assert out["score"] == 1.0
        assert out["group"] == "opt"
        assert out["n"] > 0

    def test_scores_a_named_group(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(0, 10))
        split = self._split_file(tmp_path, capsys, results)
        code, out = _run(capsys, "score", "--results", results, "--split", split, "--group", "opt")
        assert code == EXIT_OK
        assert out["score"] == 0.0

    def test_missing_result_is_a_config_error(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(10, 0))
        split = self._split_file(tmp_path, capsys, results)
        truncated = _write(tmp_path, "trunc.json", {"p0": True})
        code, _ = _run(capsys, "score", "--results", truncated, "--split", split)
        assert code == EXIT_CONFIG

    def test_unknown_group_is_rejected(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(10, 0))
        split = self._split_file(tmp_path, capsys, results)
        with pytest.raises(SystemExit):
            oa.main(["score", "--results", str(results), "--split", str(split), "--group", "nope"])


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


class TestApply:
    def test_appends_in_place(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "line two"}])
        code, out = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_OK
        assert target.read_text(encoding="utf-8") == "line one\nline two\n"
        assert out["applied"] == 1

    def test_dry_run_leaves_the_file_alone(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "line two"}])
        code, out = _run(
            capsys, "apply", "--file", target, "--patches", patches, "--budget", "1", "--dry-run"
        )
        assert code == EXIT_OK
        assert target.read_text(encoding="utf-8") == "line one\n"
        assert "line two" in out["result"]

    def test_over_budget_is_a_logic_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(
            tmp_path,
            "p.json",
            [{"op": "append", "text": "a"}, {"op": "append", "text": "b"}],
        )
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_LOGIC
        assert target.read_text(encoding="utf-8") == "line one\n"

    def test_protected_section_edit_is_a_logic_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text(
            "<!-- SLOW_UPDATE_START -->\nrails\n<!-- SLOW_UPDATE_END -->\ntail\n",
            encoding="utf-8",
        )
        patches = _write(tmp_path, "p.json", [{"op": "delete", "anchor": "rails"}])
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_LOGIC
        assert "rails" in target.read_text(encoding="utf-8")

    def test_unknown_anchor_is_a_logic_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(
            tmp_path, "p.json", [{"op": "insert_after", "anchor": "ghost", "text": "x"}]
        )
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_LOGIC

    def test_malformed_patch_shape_is_a_config_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"text": "no op key"}])
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_CONFIG

    def test_patches_must_be_a_list(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", {"op": "append", "text": "x"})
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_CONFIG

    def test_missing_target_is_a_config_error(self, tmp_path, capsys):
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, _ = _run(
            capsys, "apply", "--file", tmp_path / "ghost.md", "--patches", patches, "--budget", "1"
        )
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


class TestGateHoldsOutOnly:
    """The gate must read sel and nothing else.

    The PR claimed gating on the optimize group was impossible to express, but
    --group was wired straight through to the scorer, so `gate --group opt`
    scored the visible group and reported a verdict. The flag is gone; sel is
    the only group a gate can read.
    """

    def _setup(self, tmp_path, capsys, incumbent: dict, candidate: dict):
        inc = _write(tmp_path, "inc.json", incumbent)
        cand = _write(tmp_path, "cand.json", candidate)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return inc, cand, _write(tmp_path, "split.json", split)

    def test_the_group_flag_is_gone(self, tmp_path, capsys):
        inc, cand, split_path = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        with pytest.raises(SystemExit):
            _run_gate(
                capsys,
                tmp_path,
                "--incumbent",
                inc,
                "--candidate",
                cand,
                "--split",
                split_path,
                "--group",
                "opt",
            )

    def test_the_verdict_names_the_group_it_read(self, tmp_path, capsys):
        inc, cand, split_path = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert out["group"] == "sel"


class TestGateRefusalCostsNothing:
    """A refused comparison must not report the held-out scores.

    Scoring ran before the guards, so a call refused for an exhausted budget
    still printed both sel scores. That hands over the number the budget exists
    to ration, and it is free: the caller is told not to advance its counter.
    """

    def _setup(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return inc, cand, _write(tmp_path, "split.json", split), split

    def test_an_exhausted_budget_withholds_the_scores(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--max-consultations",
            "3",
            spent=3,
        )
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert "candidate" not in out
        assert "incumbent" not in out

    def test_a_moved_fingerprint_withholds_the_scores(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale",
        )
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert "candidate" not in out

    def test_a_refusal_still_reports_the_decision_and_reason(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        _, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale",
        )
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

    def test_a_permitted_call_still_reports_the_scores(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(tmp_path, capsys)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert out["compared"] is True
        assert out["candidate"] == 1.0
        assert out["incumbent"] == 0.0


class TestGateReportsPairedEvidence:
    """Every compared verdict carries the discordant counts and an exact p."""

    def _gate(self, tmp_path, capsys, incumbent: dict, candidate: dict):
        inc = _write(tmp_path, "inc.json", incumbent)
        cand = _write(tmp_path, "cand.json", candidate)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        split_path = _write(tmp_path, "split.json", split)
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
        )

    def test_a_clean_win_reports_gains_and_no_losses(self, tmp_path, capsys):
        _, out = self._gate(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        assert out["discordant_gain"] == 4
        assert out["discordant_loss"] == 0
        assert out["p_value"] == pytest.approx(0.0625)

    def test_no_movement_reports_a_p_of_one(self, tmp_path, capsys):
        same = {f"t{i}": True for i in range(10)}
        _, out = self._gate(tmp_path, capsys, same, dict(same))
        assert out["discordant_gain"] == 0
        assert out["discordant_loss"] == 0
        assert out["p_value"] == 1.0

    def test_a_refusal_reports_no_paired_evidence(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale",
        )
        assert "p_value" not in out


class TestGate:
    def _setup(self, tmp_path, capsys, incumbent: dict, candidate: dict):
        inc = _write(tmp_path, "inc.json", incumbent)
        cand = _write(tmp_path, "cand.json", candidate)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return inc, cand, _write(tmp_path, "split.json", split), split

    def test_accepts_a_strict_improvement(self, tmp_path, capsys):
        inc, cand, split_path, split = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_OK
        assert out["decision"] == "ACCEPT"
        assert out["candidate"] > out["incumbent"]

    def test_rejects_a_tie(self, tmp_path, capsys):
        same = {f"t{i}": True for i in range(10)}
        inc, cand, split_path, _ = self._setup(tmp_path, capsys, same, dict(same))
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "tie" in out["reason"]

    def test_rejects_a_regression(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": True for i in range(10)},
            {f"t{i}": False for i in range(10)},
        )
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_LOGIC
        assert "regress" in out["reason"]

    def test_scores_the_held_out_group_not_the_optimize_group(self, tmp_path, capsys):
        """The candidate wins only on opt tasks, so the gate must reject it."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        split_path = _write(tmp_path, "split.json", split)
        candidate = {t: True for t in split["opt"]}
        candidate.update({t: False for t in split["sel"] + split["test"]})
        cand = _write(tmp_path, "cand.json", candidate)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", split_path
        )
        assert code == EXIT_LOGIC
        assert out["candidate"] == 0.0

    def test_refuses_when_the_split_moved(self, tmp_path, capsys):
        inc, cand, split_path, split = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale-fingerprint",
        )
        assert code == EXIT_LOGIC
        assert "fingerprint" in out["reason"]

    def test_accepts_when_the_fingerprint_matches(self, tmp_path, capsys):
        inc, cand, split_path, split = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            split["fingerprint"],
        )
        assert code == EXIT_OK
        assert out["decision"] == "ACCEPT"

    def test_refuses_once_consultations_are_exhausted(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--max-consultations",
            "5",
            spent=5,
        )
        assert code == EXIT_LOGIC
        assert "exhaust" in out["reason"]

    def test_reports_the_incremented_consultation_count(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            spent=2,
        )
        assert code == EXIT_OK
        assert out["sel_consultations"] == 3

    def test_a_fingerprint_refusal_does_not_burn_a_consultation(self, tmp_path, capsys):
        inc, cand, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            "stale",
            spent=2,
        )
        assert code == EXIT_LOGIC
        assert out["sel_consultations"] == 2
        assert out["compared"] is False

    def test_missing_candidate_result_is_a_config_error(self, tmp_path, capsys):
        inc, _, split_path, _ = self._setup(
            tmp_path,
            capsys,
            {f"t{i}": False for i in range(10)},
            {f"t{i}": True for i in range(10)},
        )
        truncated = _write(tmp_path, "trunc.json", {"t0": True})
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", truncated, "--split", split_path
        )
        assert (code, out["decision"], out["compared"]) == (EXIT_LOGIC, "REJECT", False)

    def test_malformed_split_is_a_config_error(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        bad_split = _write(tmp_path, "split.json", {"opt": ["t0"]})
        code, _ = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc, "--split", bad_split
        )
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# buffer
# ---------------------------------------------------------------------------


class TestBuffer:
    def _artifact(self, tmp_path: Path, text: str = "artifact v1") -> Path:
        path = tmp_path / f"artifact-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def _check(self, capsys, buffer: Path, patches: Path, artifact: Path):
        return _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            artifact,
        )

    def _add(self, capsys, buffer: Path, patches: Path, artifact: Path, reason: str = "no"):
        return _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            artifact,
            "--reason",
            reason,
        )

    def test_novel_patch_passes_the_check(self, tmp_path, capsys):
        buffer = _write(tmp_path, "b.json", [])
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        artifact = self._artifact(tmp_path)
        code, out = self._check(capsys, buffer, patches, artifact)
        assert code == EXIT_OK
        assert out["seen"] is False

    def test_missing_buffer_file_is_treated_as_empty(self, tmp_path, capsys):
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        artifact = self._artifact(tmp_path)
        code, out = self._check(capsys, tmp_path / "none.json", patches, artifact)
        assert code == EXIT_OK
        assert out["seen"] is False

    def test_add_then_check_reports_seen(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        artifact = self._artifact(tmp_path)
        code, _ = self._add(capsys, buffer, patches, artifact, "regressed")
        assert code == EXIT_OK
        code, out = self._check(capsys, buffer, patches, artifact)
        assert code == EXIT_LOGIC
        assert out["seen"] is True

    def test_same_patch_can_be_retried_after_artifact_changes(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        old_artifact = self._artifact(tmp_path, "artifact v1")
        new_artifact = self._artifact(tmp_path, "artifact v2")
        self._add(capsys, buffer, patches, old_artifact)

        code, out = self._check(capsys, buffer, patches, new_artifact)

        assert code == EXIT_OK
        assert out["seen"] is False

    def test_legacy_buffer_entries_without_artifact_state_are_expired(self, tmp_path, capsys):
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        fingerprint = oa.patch_fingerprint([oa.Patch("append", None, "x")])
        buffer = _write(tmp_path, "b.json", [{"fingerprint": fingerprint}])
        artifact = self._artifact(tmp_path)

        code, out = self._check(capsys, buffer, patches, artifact)

        assert code == EXIT_OK
        assert out["seen"] is False

    def test_a_reflowed_patch_is_a_different_edit(self, tmp_path, capsys):
        """Whitespace is content: a newline in patch text splits one line into two.

        Treating the reflow as the same edit let one rejection permanently ban
        an edit that was never tried, and the buffer has no expiry.
        """
        buffer = tmp_path / "b.json"
        original = _write(tmp_path, "p.json", [{"op": "append", "text": "alpha beta"}])
        reflowed = _write(tmp_path, "p2.json", [{"op": "append", "text": "alpha   \n beta"}])
        artifact = self._artifact(tmp_path)
        self._add(capsys, buffer, original, artifact)
        code, out = self._check(capsys, buffer, reflowed, artifact)
        assert code == EXIT_OK
        assert out["seen"] is False

    def test_only_line_endings_are_normalized(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        original = _write(tmp_path, "p.json", [{"op": "append", "text": "alpha\r\nbeta"}])
        same = _write(tmp_path, "p2.json", [{"op": "append", "text": "alpha\nbeta"}])
        artifact = self._artifact(tmp_path)
        self._add(capsys, buffer, original, artifact)
        code, out = self._check(capsys, buffer, same, artifact)
        assert code == EXIT_LOGIC
        assert out["seen"] is True

    def test_add_records_the_reason_and_fingerprint(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        artifact = self._artifact(tmp_path)
        self._add(capsys, buffer, patches, artifact, "regressed")
        entries = json.loads(buffer.read_text(encoding="utf-8"))
        assert len(entries) == 1
        assert entries[0]["reason"] == "regressed"
        assert entries[0]["fingerprint"]
        assert entries[0]["artifact_fingerprint"]
        assert entries[0]["patches"] == [{"op": "append", "anchor": None, "text": "x"}]

    def test_add_appends_rather_than_replacing(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        first = _write(tmp_path, "p1.json", [{"op": "append", "text": "x"}])
        second = _write(tmp_path, "p2.json", [{"op": "append", "text": "y"}])
        artifact = self._artifact(tmp_path)
        self._add(capsys, buffer, first, artifact, "a")
        self._add(capsys, buffer, second, artifact, "b")
        assert len(json.loads(buffer.read_text(encoding="utf-8"))) == 2

    def test_add_is_idempotent_for_the_same_patch(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        artifact = self._artifact(tmp_path)
        self._add(capsys, buffer, patches, artifact, "a")
        self._add(capsys, buffer, patches, artifact, "a")
        assert len(json.loads(buffer.read_text(encoding="utf-8"))) == 1

    def test_add_records_the_same_patch_for_a_new_artifact_state(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        first_artifact = self._artifact(tmp_path, "artifact v1")
        second_artifact = self._artifact(tmp_path, "artifact v2")
        self._add(capsys, buffer, patches, first_artifact, "a")
        self._add(capsys, buffer, patches, second_artifact, "a")
        assert len(json.loads(buffer.read_text(encoding="utf-8"))) == 2

    def test_corrupt_buffer_is_a_config_error(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        buffer.write_text("{oops", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        artifact = self._artifact(tmp_path)
        code, _ = self._check(capsys, buffer, patches, artifact)
        assert code == EXIT_CONFIG


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_no_subcommand_exits_nonzero(self, capsys):
        assert oa.main([]) != EXIT_OK

    def test_unknown_subcommand_exits(self, capsys):
        with pytest.raises(SystemExit):
            oa.main(["frobnicate"])


# ---------------------------------------------------------------------------
# malformed inputs
# ---------------------------------------------------------------------------


class TestMalformedInputs:
    def test_unreadable_json_path_is_a_config_error(self, tmp_path, capsys):
        """A directory where a file belongs raises OSError, not FileNotFoundError."""
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", tmp_path)
        assert code == EXIT_CONFIG

    def test_unreadable_text_path_is_a_config_error(self, tmp_path, capsys):
        code, _ = _run(capsys, "extract", "--kind", "hook", "--input", tmp_path)
        assert code == EXIT_CONFIG

    def test_results_must_be_an_object(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", ["t0", "t1"])
        code, _ = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert code == EXIT_CONFIG

    def test_results_must_be_boolean_valued(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", {"t0": 1, "t1": "yes"})
        code, _ = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        assert code == EXIT_CONFIG

    def test_empty_patch_array_is_a_config_error(self, tmp_path, capsys):
        target = tmp_path / "a.md"
        target.write_text("line one\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [])
        code, _ = _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert code == EXIT_CONFIG

    def test_split_must_be_an_object(self, tmp_path, capsys):
        results = _write(tmp_path, "r.json", _results(10, 0))
        split = _write(tmp_path, "split.json", ["opt", "sel", "test"])
        code, _ = _run(capsys, "score", "--results", results, "--split", split)
        assert code == EXIT_CONFIG

    def test_a_negative_ledger_count_is_a_config_error(self, tmp_path, capsys):
        """This used to arrive as `--consultations -1` on the command line.

        The count moved into a ledger the gate writes, so the malformed input
        moved with it. A negative count is still refused rather than treated
        as zero.
        """
        results = _write(tmp_path, "r.json", _results(10, 0))
        _, split = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        split_path = _write(tmp_path, "split2.json", split)
        code, _ = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            results,
            "--candidate",
            results,
            "--split",
            split_path,
            spent=-1,
        )
        assert code == EXIT_CONFIG

    def test_buffer_must_be_an_array(self, tmp_path, capsys):
        buffer = _write(tmp_path, "b.json", {"not": "a list"})
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        artifact = tmp_path / "artifact.md"
        artifact.write_text("artifact", encoding="utf-8")
        code, _ = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            artifact,
        )
        assert code == EXIT_CONFIG


class TestSplitFileIsSelfValidating:
    """A split file has to prove its own integrity, with no flag to remember.

    Two adversarial reviewers plus both PR bots flagged the same hole
    independently: the only drift check compared the split file's stored
    fingerprint against a --incumbent-fingerprint the caller supplied, so a
    caller who omitted the flag got no check at all, and the stored value was
    trusted even when the group membership beside it had been edited. A
    guarantee that is opt-in is not a guarantee. The gate now recomputes the
    fingerprint from the split file's own contents on every call.
    """

    def _setup(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return inc, cand, split

    def test_an_untampered_split_gates_normally(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == 0
        assert out["decision"] == "ACCEPT"

    def test_an_untampered_legacy_numeric_ratio_split_gates_normally(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = 0.4
        split["test_ratio"] = 0.0
        tasks = [str(t) for group in ("opt", "sel", "test") for t in split[group]]
        split["fingerprint"] = _legacy_split_fingerprint(
            tasks, seed=split["seed"], sel_ratio=0.4, test_ratio=0.0
        )
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == 0
        assert out["decision"] == "ACCEPT"

    def test_legacy_numeric_inexact_ratio_redraws_with_legacy_membership(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(25)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(25)})
        tasks = [f"t{i}" for i in range(25)]
        ranked = sorted(
            tasks,
            key=lambda task_id: oa.hashlib.sha256(
                f"s1\x00{task_id}".encode()
            ).hexdigest(),
        )
        split = {
            "opt": ranked[14:],
            "sel": ranked[:14],
            "test": [],
            "fingerprint": _legacy_split_fingerprint(
                tasks, seed="s1", sel_ratio=0.58, test_ratio=0.0
            ),
            "seed": "s1",
            "sel_ratio": 0.58,
            "test_ratio": 0.0,
            "min_sel": 0,
        }
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert len(split["sel"]) == 14
        assert code == 0
        assert out["decision"] == "ACCEPT"

    def test_legacy_numeric_plain_integer_test_ratio_gates_normally(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = 0.4
        split["test_ratio"] = 0
        tasks = [str(t) for group in ("opt", "sel", "test") for t in split[group]]
        split["fingerprint"] = _legacy_split_fingerprint(
            tasks, seed=split["seed"], sel_ratio=0.4, test_ratio=0.0
        )
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == EXIT_OK
        assert out["decision"] == "ACCEPT"

    def test_legacy_numeric_false_test_ratio_is_a_schema_error(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = 0.4
        split["test_ratio"] = False
        tasks = [str(t) for group in ("opt", "sel", "test") for t in split[group]]
        split["fingerprint"] = _legacy_split_fingerprint(
            tasks, seed=split["seed"], sel_ratio=0.4, test_ratio=0.0
        )
        path = _write(tmp_path, "split.json", split)

        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", path
        )

        assert code == EXIT_CONFIG
        assert "legacy numeric schema or both use string schema" in out["error"]

    @pytest.mark.parametrize(
        ("sel_ratio", "test_ratio"),
        [
            (None, 0.0),
            (True, 0.0),
            (10 ** 309, 0.0),
            ({"value": 0.4}, 0.0),
            (0.4, "0.0"),
        ],
    )
    def test_unusable_split_ratio_schemas_are_config_errors(
        self, tmp_path, capsys, sel_ratio, test_ratio
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = sel_ratio
        split["test_ratio"] = test_ratio
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert "split file holds unusable seed or ratios" in out["error"]

    def test_legacy_numeric_fingerprint_does_not_alias_precise_string_ratio(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        tasks = [str(t) for group in ("opt", "sel", "test") for t in split[group]]
        split["sel_ratio"] = "0.40000000000000000000000000000000001"
        split["test_ratio"] = "0.0"
        split["fingerprint"] = _legacy_split_fingerprint(
            tasks, seed=split["seed"], sel_ratio=0.4, test_ratio=0.0
        )
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

    def test_string_schema_ratio_split_round_trips_without_legacy_float_fallback(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                        "--sel-ratio", "0.5", "--min-sel", "0")
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == 0
        assert out["decision"] == "ACCEPT"

    def test_string_schema_inexact_ratio_uses_exact_membership(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(25)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                        "--sel-ratio", "0.58", "--min-sel", "0")
        assert len(split["sel"]) == 15
        assert len(split["opt"]) == 10

    def test_a_task_moved_between_groups_is_refused(self, tmp_path, capsys):
        """The union is unchanged, so only recomputation catches this."""
        inc, cand, split = self._setup(tmp_path, capsys)
        moved = split["opt"][0]
        split["opt"] = [t for t in split["opt"] if t != moved]
        split["sel"] = [*split["sel"], moved]
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]
        assert "score" not in out and "candidate" not in out

    def test_a_task_moved_in_legacy_numeric_ratio_split_is_refused(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = 0.4
        split["test_ratio"] = 0.0
        tasks = [str(t) for group in ("opt", "sel", "test") for t in split[group]]
        split["fingerprint"] = _legacy_split_fingerprint(
            tasks, seed=split["seed"], sel_ratio=0.4, test_ratio=0.0
        )
        moved = split["opt"][0]
        split["opt"] = [t for t in split["opt"] if t != moved]
        split["sel"] = [*split["sel"], moved]
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

    def test_an_added_task_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel"] = [*split["sel"], "smuggled"]
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"
        assert "fingerprint" in out["reason"]

    def test_an_edited_fingerprint_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["fingerprint"] = "0" * 64
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"

    def test_an_edited_seed_is_refused(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["seed"] = "s2"
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                         "--split", path)
        assert out["decision"] == "REJECT"

    def test_a_refused_split_costs_no_consultation(self, tmp_path, capsys):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel"] = [*split["sel"], "smuggled"]
        path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                           "--split", path, "--max-consultations", "3")
        assert out["consultations"] == 0
        assert not (tmp_path / "ledger.json").exists()

    def test_a_split_file_without_ratios_is_refused(self, tmp_path, capsys):
        """Older split files cannot be verified, so they cannot be trusted."""
        inc, cand, split = self._setup(tmp_path, capsys)
        del split["sel_ratio"]
        path = _write(tmp_path, "split.json", split)
        code, _ = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                       "--split", path)
        assert code == EXIT_CONFIG

    def test_a_non_numeric_ratio_is_a_config_error(self, tmp_path, capsys):
        """The keys are present, so only the redraw catches the bad value."""
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = "half"
        path = _write(tmp_path, "split.json", split)
        code, _ = _run_gate(capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
                       "--split", path)
        assert code == EXIT_CONFIG

    @pytest.mark.parametrize("ratio", ["1/0", "1/2"])
    def test_split_rejects_non_decimal_ratio_syntax_without_traceback(
        self, tmp_path, capsys, ratio
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        code, out = _run(capsys, "split", "--results", inc, "--seed", "s1",
                         "--sel-ratio", ratio, "--out", tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert "decimal ratio" in out["error"]

    @pytest.mark.parametrize("ratio", ["1e20000000", "1e-20000000", "-1e20000000"])
    def test_split_rejects_absurd_decimal_exponents_without_traceback(
        self, tmp_path, capsys, ratio
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        code, out = _run(capsys, "split", "--results", inc, "--seed", "s1",
                         "--sel-ratio", ratio, "--out", tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert "decimal ratio" in out["error"]

    def test_split_rejects_absurd_decimal_coefficients_without_traceback(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        ratio = "0." + "1" * 65
        code, out = _run(capsys, "split", "--results", inc, "--seed", "s1",
                         "--sel-ratio", ratio, "--out", tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert "coefficient digits" in out["error"]
        assert len(out["error"]) < 200

    def test_split_accepts_the_largest_allowed_decimal_coefficient(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(25)})
        ratio = "0." + "1" * 64
        code, out = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                           "--sel-ratio", ratio, "--min-sel", "0")
        assert code == EXIT_OK
        assert len(out["sel"]) == 3

    @staticmethod
    def _assert_truncated_ratio_value(message: str, original_length: int) -> None:
        assert "..." in message
        assert f"(length {original_length})" in message
        assert len(message) < 200

    def test_split_million_digit_ratio_uses_text_length_guard(self, tmp_path):
        tasks = tmp_path / "tasks.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(10)) + "\n", encoding="utf-8")
        out_path = tmp_path / "split.json"
        script = f"""
import importlib.util
import json
import sys

spec = importlib.util.spec_from_file_location("optimize_artifact", {str(_SCRIPT)!r})
module = importlib.util.module_from_spec(spec)
sys.modules["optimize_artifact"] = module
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
class BoomDecimal:
    def __init__(self, *_args, **_kwargs):
        raise AssertionError("Decimal must not parse overlong ratios")
sys.modules["_optimizer_core"].Decimal = BoomDecimal
code = module.main([
    "split",
    "--tasks",
    {str(tasks)!r},
    "--seed",
    "s1",
    "--sel-ratio",
    "0." + "1" * 1_000_000,
    "--out",
    {str(out_path)!r},
])
print(code)
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            check=False,
            capture_output=True,
            cwd=_EVAL_DIR,
            text=True,
            timeout=2,
        )
        assert result.returncode == 0
        assert result.stdout.splitlines()[-1] == str(EXIT_CONFIG)
        payload = json.loads("\n".join(result.stdout.splitlines()[:-1]))
        assert "at most 128 characters" in payload["error"]
        assert "coefficient digits" not in payload["error"]
        self._assert_truncated_ratio_value(payload["error"], 1_000_002)

    @pytest.mark.parametrize(
        ("argv", "pattern", "lengths"),
        [
            (("--sel-ratio", "0." + "0" * 64), "strictly between 0 and 1", (66,)),
            (("--test-ratio", "1." + "0" * 63), "test_ratio must be in", (65,)),
            (
                ("--sel-ratio", "0." + "9" * 64, "--test-ratio", "0." + "1" * 64),
                "leave at least one opt task",
                (66, 66),
            ),
            (
                ("--sel-ratio", "0." + "4" * 64, "--test-ratio", "0." + "4" * 64),
                "leaves no opt tasks",
                (66, 66),
            ),
            (("--sel-ratio", "0." + "0" * 63 + "1"), "holds out no tasks", (66,)),
        ],
    )
    def test_split_semantic_ratio_errors_truncate_long_values(
        self, tmp_path, capsys, argv, pattern, lengths
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(2)})
        code, out = _run(capsys, "split", "--results", inc, "--seed", "s1",
                         *argv, "--min-sel", "0", "--out", tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert pattern in out["error"]
        for original_length in lengths:
            self._assert_truncated_ratio_value(out["error"], original_length)

    def test_legacy_min_sel_shortfall_error_truncates_long_values(
        self, tmp_path, capsys
    ):
        inc, cand, split = self._setup(tmp_path, capsys)
        split["sel_ratio"] = 0.4
        split["test_ratio"] = 0.0
        split["min_sel"] = int("1" * 309)
        path = _write(tmp_path, "split.json", split)

        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand, "--split", path
        )

        assert code == EXIT_CONFIG
        assert "below min_sel" in out["error"]
        self._assert_truncated_ratio_value(out["error"], 309)

    def test_split_writes_the_ratios_it_used(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                        "--sel-ratio", "0.4", "--test-ratio", "0.2")
        assert split["sel_ratio"] == "0.4"
        assert split["test_ratio"] == "0.2"

    def test_split_uses_raw_decimal_ratio_text_for_half_up_rounding(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(25)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1",
                        "--sel-ratio", "0.58", "--min-sel", "0")
        assert len(split["sel"]) == 15
        assert len(split["opt"]) == 10
        assert split["sel_ratio"] == "0.58"


class TestMalformedInputsAreConfigErrors:
    """Broken input files must name themselves, not raise a traceback.

    Every one of these was found by CodeRabbit on PR #3430 and reproduced
    before being fixed. The CLI is driven by an unattended loop, so a
    traceback is not a diagnostic anyone reads; it is a crash the loop cannot
    branch on.
    """

    def test_a_non_utf8_artifact_is_a_config_error(self, tmp_path, capsys):
        """UnicodeDecodeError subclasses ValueError, so the OSError arm missed it."""
        target = tmp_path / "artifact.md"
        target.write_bytes(b"valid ascii \xff\xfe then garbage")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(capsys, "apply", "--file", target, "--patches", patches,
                         "--budget", "1")
        assert code == EXIT_CONFIG
        assert "artifact.md" in out["error"]

    def test_a_buffer_of_non_objects_is_a_config_error(self, tmp_path, capsys):
        buf = _write(tmp_path, "buf.json", [1, 2])
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        artifact = tmp_path / "artifact.md"
        artifact.write_text("artifact", encoding="utf-8")
        code, _ = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buf,
            "--patches",
            patches,
            "--artifact",
            artifact,
        )
        assert code == EXIT_CONFIG


class TestApplyWritesAtomically:
    """A half-written artifact is worse than a refused edit.

    `apply` overwrites the artifact the loop is optimizing. A direct
    write_text truncates first, so an interrupt or a full disk mid-write
    leaves the artifact destroyed and the loop with nothing to fall back to.
    """

    def _setup(self, tmp_path):
        target = tmp_path / "artifact.md"
        target.write_text("original\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "added"}])
        return target, patches

    def test_a_normal_apply_still_writes(self, tmp_path, capsys):
        target, patches = self._setup(tmp_path)
        code, out = _run(capsys, "apply", "--file", target, "--patches", patches,
                         "--budget", "1")
        assert code == 0 and out["written"] is True
        assert "added" in target.read_text(encoding="utf-8")

    def test_a_failed_replace_leaves_the_original_intact(
        self, tmp_path, capsys, monkeypatch
    ):
        target, patches = self._setup(tmp_path)
        monkeypatch.setattr(oa.os, "replace", _boom)
        code, out = _run(capsys, "apply", "--file", target, "--patches", patches,
                         "--budget", "1")
        assert code == EXIT_CONFIG
        assert target.read_text(encoding="utf-8") == "original\n"

    def test_a_failed_replace_leaves_no_temp_file(
        self, tmp_path, capsys, monkeypatch
    ):
        target, patches = self._setup(tmp_path)
        monkeypatch.setattr(oa.os, "replace", _boom)
        _run(capsys, "apply", "--file", target, "--patches", patches, "--budget", "1")
        assert sorted(p.name for p in tmp_path.iterdir()) == ["artifact.md", "p.json"]


class TestHeldOutGroupsAreNotReadable:
    """The optimizer-facing surface must not hand back what the gate withholds.

    An adversarial review (gpt-5.6-sol, 2026-07-26) found the withholding was
    nominal: `split` printed every selection and test id, and `score` defaulted
    to the selection group and accepted the test group, unmetered. An agent
    could read the held-out answers for free and never touch the consultation
    budget. A hash around openly published data is not withholding.
    """

    def _tasks(self, tmp_path):
        return _write(tmp_path, "res.json", {f"t{i}": True for i in range(10)})

    def test_split_prints_optimize_ids_but_not_held_out_ids(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        code, out = _run(capsys, "split", "--results", self._tasks(tmp_path),
                         "--seed", "s", "--out", out_path)
        assert code == 0
        assert out["opt"], "the optimizer needs to know what it may work on"
        assert "sel" not in out and "test" not in out

    def test_split_reports_held_out_sizes_without_membership(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        _, out = _run(capsys, "split", "--results", self._tasks(tmp_path),
                      "--seed", "s", "--out", out_path)
        assert out["n_sel"] == 4 and out["n_test"] == 0

    def test_the_full_split_still_reaches_the_gate_through_the_file(
        self, tmp_path, capsys
    ):
        out_path = tmp_path / "split.json"
        _run(capsys, "split", "--results", self._tasks(tmp_path), "--seed", "s",
             "--out", out_path)
        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert len(written["sel"]) == 4
        assert written["fingerprint"]

    def test_score_refuses_the_selection_group(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        _run(capsys, "split", "--results", self._tasks(tmp_path), "--seed", "s",
             "--out", out_path)
        with pytest.raises(SystemExit):
            _run(capsys, "score", "--results", self._tasks(tmp_path),
                 "--split", out_path, "--group", "sel")

    def test_score_refuses_the_test_group(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        _run(capsys, "split", "--results", self._tasks(tmp_path), "--seed", "s",
             "--out", out_path)
        with pytest.raises(SystemExit):
            _run(capsys, "score", "--results", self._tasks(tmp_path),
                 "--split", out_path, "--group", "test")

    def test_score_still_reads_the_optimize_group(self, tmp_path, capsys):
        out_path = tmp_path / "split.json"
        _run(capsys, "split", "--results", self._tasks(tmp_path), "--seed", "s",
             "--out", out_path)
        code, out = _run(capsys, "score", "--results", self._tasks(tmp_path),
                         "--split", out_path)
        assert code == 0 and out["group"] == "opt" and out["score"] == 1.0


class TestConsultationLedgerIsHeldByTheGate:
    """A budget the caller passes in is not a budget.

    `--consultations` defaulted to 0 and arrived on the command line on every
    invocation, so a loop that simply never incremented it had an unlimited
    budget while appearing to respect a cap. An adversarial review
    (gpt-5.6-sol, 2026-07-26) reproduced ACCEPT twice under a cap of one by
    passing zero both times. The count now lives in a ledger the gate writes,
    bound to the split fingerprint so redrawing cannot reset it either.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, cand, split, oa._ledger_path(oa._holdout_key(record))

    def _gate(self, capsys, inc, cand, split, _ledger, cap=100):
        """The ledger path is derived, so tests receive it rather than choose it."""
        fingerprint = _split_of(["--split", str(split)]) or {}
        return _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                    "--split", split, "--max-consultations", str(cap),
                    "--incumbent-fingerprint",
                    str(fingerprint.get("fingerprint", "unknown")))

    def test_a_compared_decision_writes_the_count(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        _, out = self._gate(capsys, inc, cand, split, ledger)
        assert out["sel_consultations"] == 1
        assert json.loads(ledger.read_text(encoding="utf-8"))["consultations"] == 1

    def test_the_cap_holds_across_separate_invocations(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        first, _ = self._gate(capsys, inc, cand, split, ledger, cap=1)
        assert first == EXIT_OK
        second, out = self._gate(capsys, inc, cand, split, ledger, cap=1)
        assert second == EXIT_LOGIC
        assert "exhaust" in out["reason"]

    def test_a_refused_decision_does_not_spend_budget(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        tampered = json.loads(split.read_text(encoding="utf-8"))
        tampered["sel"], tampered["opt"] = tampered["opt"], tampered["sel"]
        split.write_text(json.dumps(tampered), encoding="utf-8")
        self._gate(capsys, inc, cand, split, ledger)
        assert not ledger.exists()

    def test_a_ledger_from_a_different_split_is_refused(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        ledger.write_text(
            json.dumps({"consultations": 0, "fingerprint": "not-this-split",
                        "max_consultations": 100}),
            encoding="utf-8",
        )
        code, out = self._gate(capsys, inc, cand, split, ledger)
        assert code == EXIT_LOGIC
        assert "ledger" in out["reason"]
        assert "candidate" not in out

    @pytest.mark.parametrize("payload", [
        '{"consultations": "many"}',
        '{"consultations": true}',
        '["not", "an", "object"]',
    ])
    def test_a_malformed_ledger_is_a_config_error(self, tmp_path, capsys, payload):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        ledger.write_text(payload, encoding="utf-8")
        code, _ = self._gate(capsys, inc, cand, split, ledger)
        assert code == EXIT_CONFIG

    @pytest.mark.parametrize("bad_bar", [1.5, -0.1, 2.0, -1])
    def test_a_ledger_with_out_of_range_max_p_is_a_config_error(
        self, tmp_path, capsys, bad_bar
    ):
        """An out-of-range max_p in the ledger is data corruption, not a gate refusal."""
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        record = json.loads(split.read_text(encoding="utf-8"))
        holdout_key = oa._holdout_key(record)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({
                "consultations": 0,
                "holdout": holdout_key,
                "max_consultations": 100,
                "max_p": bad_bar,
            }),
            encoding="utf-8",
        )
        code, _ = self._gate(capsys, inc, cand, split, ledger)
        assert code == EXIT_CONFIG

    def test_a_first_run_needs_no_existing_ledger(self, tmp_path, capsys):
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        code, _ = self._gate(capsys, inc, cand, split, ledger)
        assert code == EXIT_OK and ledger.exists()

    def test_a_negative_cap_is_a_config_error(self, tmp_path, capsys):
        """`gate()` rejects a nonsense cap; the CLI reports it rather than crashing."""
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        code, out = self._gate(capsys, inc, cand, split, ledger, cap=-1)
        assert code == EXIT_CONFIG
        assert not ledger.exists()
        assert out["error"]

    def test_a_result_missing_a_held_out_task_refuses_without_naming_it(self, tmp_path, capsys):
        """The gate cannot score a held-out task the run never reported.

        Distinct from a malformed file: this one parses and is short on one
        task. Whole-universe coverage is checked before the held-out group is
        read, so it refuses without naming the task and costs no consultation.
        """
        inc, cand, split, ledger = self._fixture(tmp_path, capsys)
        partition = json.loads(split.read_text(encoding="utf-8"))
        dropped = partition["sel"][0]
        short = {k: v for k, v in json.loads(Path(cand).read_text(encoding="utf-8")).items()
                 if k != dropped}
        short_path = _write(tmp_path, "short.json", short)
        code, out = self._gate(capsys, inc, short_path, split, ledger)
        assert (code, out["decision"], out["compared"]) == (EXIT_LOGIC, "REJECT", False)
        assert dropped not in json.dumps(out)
        assert "whole task set" in out["reason"]
        assert not ledger.exists()


class TestTheBudgetCapIsPinnedByTheLedger:
    """A cap the caller re-supplies every invocation is not a cap.

    The ledger fixed the count but left the limit on the command line, where
    `--max-consultations` defaulted to unlimited. A second adversarial review
    (gpt-5.6-sol, 2026-07-26) named the two remaining ways out: never pass the
    flag, or raise it once the budget bites. Both are the same defect the
    ledger was written to close, so the limit is now pinned the same way the
    count is.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        fingerprint = json.loads(split.read_text(encoding="utf-8"))["fingerprint"]
        return inc, cand, split, fingerprint

    def _gate(self, capsys, inc, cand, split, fingerprint, cap):
        return _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                    "--split", split, "--max-consultations", str(cap),
                    "--incumbent-fingerprint", fingerprint)

    def test_a_missing_cap_is_a_usage_error(self, tmp_path, capsys):
        """No default. An unlimited budget must be typed, not inherited."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        with pytest.raises(SystemExit) as exc:
            _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                 "--split", split, "--incumbent-fingerprint", fingerprint)
        assert exc.value.code == EXIT_CONFIG

    def test_the_first_gate_records_the_cap(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        code, _ = self._gate(capsys, inc, cand, split, fingerprint, 3)
        assert code == EXIT_OK
        key = oa._holdout_key(json.loads(split.read_text(encoding="utf-8")))
        ledger = json.loads(oa._ledger_path(key).read_text(encoding="utf-8"))
        assert ledger["max_consultations"] == 3

    def test_raising_the_cap_mid_run_is_refused(self, tmp_path, capsys):
        """The reproduced attack: gate under one, then ask for five."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        assert self._gate(capsys, inc, cand, split, fingerprint, 1)[0] == EXIT_OK
        code, out = self._gate(capsys, inc, cand, split, fingerprint, 5)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False
        assert "1" in out["reason"] and "5" in out["reason"]

    def test_lowering_the_cap_mid_run_is_refused(self, tmp_path, capsys):
        """Symmetric on purpose: any cap change means a different run."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        assert self._gate(capsys, inc, cand, split, fingerprint, 4)[0] == EXIT_OK
        code, out = self._gate(capsys, inc, cand, split, fingerprint, 2)
        assert code == EXIT_LOGIC
        assert out["compared"] is False

    def test_the_same_cap_is_not_a_change(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        assert self._gate(capsys, inc, cand, split, fingerprint, 4)[0] == EXIT_OK
        code, out = self._gate(capsys, inc, cand, split, fingerprint, 4)
        assert code == EXIT_OK
        assert out["sel_consultations"] == 2

    @pytest.mark.parametrize("recorded", ["five", -1, None, True])
    def test_a_malformed_recorded_cap_is_a_config_error(self, tmp_path, capsys, recorded):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(json.loads(split.read_text(encoding="utf-8")))
        seeded = oa._ledger_path(key)
        seeded.parent.mkdir(parents=True, exist_ok=True)
        seeded.write_text(
            json.dumps({"consultations": 0, "holdout": key,
                        "max_consultations": recorded}),
            encoding="utf-8",
        )
        code, _ = self._gate(capsys, inc, cand, split, fingerprint, 3)
        assert code == EXIT_CONFIG


class TestTheBudgetIsKeyedByTheSplitItself:
    """A ledger path derived from a caller-supplied path is still caller-supplied.

    `--ledger` was replaced by a path derived from `--split`, which moved the
    reset instead of closing it: a third adversarial review (gpt-5.6-sol,
    2026-07-26) pointed out that the caller still names the split, so copying
    `split.json` to `split2.json` produced an identical fingerprint with no
    ledger beside it, and the budget started over. The key is now the
    fingerprint in one fixed directory. Same split content, same budget,
    whatever the file is called. A fresh budget needs a fresh seed.
    """

    def _fixture(self, tmp_path, capsys, seed="s1"):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", seed,
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, cand, split, record["fingerprint"]

    def _gate(self, capsys, inc, cand, split, fingerprint, cap=3):
        return _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                    "--split", split, "--max-consultations", str(cap),
                    "--incumbent-fingerprint", fingerprint)

    def test_the_ledger_is_written_under_the_state_root(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, fingerprint)
        key = oa._holdout_key(json.loads(split.read_text(encoding="utf-8")))
        assert oa._ledger_path(key).exists()

    def test_a_copied_split_shares_the_budget(self, tmp_path, capsys):
        """The reported attack: copy the split, keep the fingerprint, reset the count."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        _, first = self._gate(capsys, inc, cand, split, fingerprint)
        copy = tmp_path / "split-copy.json"
        copy.write_text(split.read_text(encoding="utf-8"), encoding="utf-8")
        _, second = self._gate(capsys, inc, cand, copy, fingerprint)
        assert (first["sel_consultations"], second["sel_consultations"]) == (1, 2)

    def test_a_renamed_split_shares_the_budget(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, fingerprint)
        moved = tmp_path / "nested" / "renamed.json"
        moved.parent.mkdir()
        moved.write_text(split.read_text(encoding="utf-8"), encoding="utf-8")
        split.unlink()
        _, second = self._gate(capsys, inc, cand, moved, fingerprint)
        assert second["sel_consultations"] == 2

    def test_exhaustion_survives_the_copy(self, tmp_path, capsys):
        """The budget is only real if the copy cannot buy one more comparison."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, fingerprint, cap=1)
        copy = tmp_path / "elsewhere.json"
        copy.write_text(split.read_text(encoding="utf-8"), encoding="utf-8")
        code, out = self._gate(capsys, inc, cand, copy, fingerprint, cap=1)
        assert (code, out["compared"], out["decision"]) == (EXIT_LOGIC, False, "REJECT")

    def test_a_redrawn_split_gets_its_own_budget(self, tmp_path, capsys):
        """The honest reset is a new seed, which is a new held-out group."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, fingerprint, cap=1)
        other = tmp_path / "redrawn.json"
        _run(capsys, "split", "--results", inc, "--seed", "s2", "--out", other)
        redrawn = json.loads(other.read_text(encoding="utf-8"))["fingerprint"]
        assert redrawn != fingerprint
        _, out = self._gate(capsys, inc, cand, other, redrawn, cap=1)
        assert out["sel_consultations"] == 1

    def test_the_ledger_flag_is_gone(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            _run(capsys, "gate", "--ledger", tmp_path / "elsewhere.json")
        assert exc.value.code == EXIT_CONFIG

    def test_two_held_out_groups_never_share_a_file(self, tmp_path):
        assert oa._ledger_path("aaaa") != oa._ledger_path("bbbb")

    def test_two_ratios_that_select_the_same_tasks_share_the_budget(self, tmp_path, capsys):
        """The fifth reset: rounding makes distinct ratios select one group.

        A fourth adversarial review (gpt-5.6-sol, 2026-07-26) reproduced this
        against the fingerprint key. Ten tasks at 0.40 and at 0.41 both round to
        four held out and pick the same four, but the fingerprint covers the raw
        ratio, so the identical group got two budgets.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        for name, ratio in (("a.json", "0.40"), ("b.json", "0.41")):
            _run(capsys, "split", "--results", inc, "--seed", "s1",
                 "--sel-ratio", ratio, "--out", tmp_path / name)
        first, second = (json.loads((tmp_path / n).read_text(encoding="utf-8"))
                         for n in ("a.json", "b.json"))
        assert first["fingerprint"] != second["fingerprint"]
        assert sorted(first["sel"]) == sorted(second["sel"])
        _, one = self._gate(capsys, inc, cand, tmp_path / "a.json", first["fingerprint"])
        _, two = self._gate(capsys, inc, cand, tmp_path / "b.json", second["fingerprint"])
        assert (one["sel_consultations"], two["sel_consultations"]) == (1, 2)

    def test_rank_order_does_not_change_the_key(self, tmp_path):
        """Two seeds that hold out the same set are selecting on the same set."""
        assert oa._holdout_key({"sel": ["b", "a"]}) == oa._holdout_key(
            {"sel": ["a", "b"]}
        )

    def test_a_different_membership_changes_the_key(self, tmp_path):
        assert oa._holdout_key({"sel": ["a", "b"]}) != oa._holdout_key(
            {"sel": ["a", "c"]}
        )

    def test_the_root_defaults_to_the_state_directory(self, monkeypatch, tmp_path):
        """Unset override falls back to XDG rather than the working directory."""
        monkeypatch.delenv("EVAL_LEDGER_DIR", raising=False)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        assert oa._ledger_root() == tmp_path / "state" / "ai-agents-eval" / "ledgers"

    def test_the_root_falls_back_to_home_without_xdg(self, monkeypatch, tmp_path):
        monkeypatch.delenv("EVAL_LEDGER_DIR", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setattr(oa.Path, "home", classmethod(lambda cls: tmp_path))
        assert oa._ledger_root() == tmp_path / ".local" / "state" / "ai-agents-eval" / "ledgers"


class TestOneGateAtATimePerSplit:
    """Atomic writes keep a file whole; they do not make a sequence a transaction.

    The same review found that two gates started together both read the same
    count, both compare, and both write count + 1, so a concurrent pair spends
    one consultation between them. The read, the comparison, and the write now
    happen under an exclusive lock file keyed by the same fingerprint.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, cand, split, record["fingerprint"]

    def test_a_held_lock_refuses_the_second_gate(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        lock = oa._ledger_root() / f"{_key_of(split)}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("999", encoding="utf-8")
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", split, "--max-consultations", "3",
                         "--incumbent-fingerprint", fingerprint)
        assert code == EXIT_CONFIG and "another gate holds" in out["error"]

    def test_the_lock_is_released_when_the_gate_returns(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
             "--split", split, "--max-consultations", "3",
             "--incumbent-fingerprint", fingerprint)
        assert not (oa._ledger_root() / f"{_key_of(split)}.lock").exists()

    def test_the_lock_is_released_when_the_gate_raises(self, tmp_path, capsys, monkeypatch):
        """A lock held past a crash would wedge every later run."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        monkeypatch.setattr(oa, "_gate_decision", _raise_boom)
        with pytest.raises(RuntimeError):
            _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                 "--split", split, "--max-consultations", "3",
                 "--incumbent-fingerprint", fingerprint)
        assert not (oa._ledger_root() / f"{_key_of(split)}.lock").exists()

    def test_a_drifted_split_takes_no_lock(self, tmp_path, capsys):
        """The refusal that reads no ledger must not serialize against one."""
        inc, cand, split, fingerprint = self._fixture(tmp_path, capsys)
        record = json.loads(split.read_text(encoding="utf-8"))
        record["fingerprint"] = "tampered"
        split.write_text(json.dumps(record), encoding="utf-8")
        lock = oa._ledger_root() / f"{_key_of(split)}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("999", encoding="utf-8")
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", split, "--max-consultations", "3",
                         "--incumbent-fingerprint", fingerprint)
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")


class TestTheGateNeverNamesAHeldOutTask:
    """An error message that lists what is missing lists the held-out group.

    `score` and `mcnemar_exact` both report which task ids they could not find,
    which is the right message everywhere except here: the ids they would name
    are the held-out ones. A fourth adversarial review (gpt-5.6-sol,
    2026-07-26) found that a candidate results file with no keys at all printed
    the whole membership in a single error, before the ledger advanced, so the
    reveal was also free. The gate now answers one bit and charges for it.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, split, record

    def _gate(self, capsys, inc, cand, split, record, cap=5):
        return _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                    "--split", split, "--max-consultations", str(cap),
                    "--incumbent-fingerprint", record["fingerprint"])

    def test_an_empty_candidate_reveals_no_membership(self, tmp_path, capsys):
        """The reported attack: ask for everything by supplying nothing."""
        inc, split, record = self._fixture(tmp_path, capsys)
        empty = _write(tmp_path, "empty.json", {})
        code, out = self._gate(capsys, inc, empty, split, record)
        assert (code, out["compared"]) == (EXIT_LOGIC, False)
        assert not any(task_id in json.dumps(out) for task_id in record["sel"])

    def test_the_refusal_costs_no_consultation(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        empty = _write(tmp_path, "empty.json", {})
        _, out = self._gate(capsys, inc, empty, split, record)
        assert out["sel_consultations"] == 0

    def test_probing_does_not_exhaust_the_budget(self, tmp_path, capsys):
        """Whole-universe coverage refuses before a held-out read."""
        inc, split, record = self._fixture(tmp_path, capsys)
        empty = _write(tmp_path, "empty.json", {})
        for _ in range(2):
            self._gate(capsys, inc, empty, split, record, cap=2)
        code, out = self._gate(capsys, inc, empty, split, record, cap=2)
        assert (code, out["compared"]) == (EXIT_LOGIC, False)
        assert "whole task set" in out["reason"]

    def test_a_missing_incumbent_result_refuses_the_same_way(self, tmp_path, capsys):
        """Both sides are read against the held-out group, so both must redact."""
        inc, split, record = self._fixture(tmp_path, capsys)
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        short = _write(tmp_path, "short-inc.json",
                       {k: v for k, v in json.loads(Path(inc).read_text(encoding="utf-8")).items()
                        if k != record["sel"][0]})
        code, out = self._gate(capsys, short, cand, split, record)
        assert (code, out["compared"]) == (EXIT_LOGIC, False)
        assert record["sel"][0] not in json.dumps(out)

    def test_a_non_bool_result_is_refused_before_the_split_is_consulted(self, tmp_path, capsys):
        """`score` would name the offending task, and that id can be held out.

        It never gets there: `_read_results` rejects a non-boolean at the file
        boundary, and the ids it echoes are the caller's own keys from the
        caller's own file, so nothing about the split is disclosed. The check
        lands before the reserve, so a malformed file of one's own costs no
        budget. `_covers_holdout` keeps its own type check anyway; a predicate
        that trusts its caller is one refactor away from leaking again.
        """
        inc, split, record = self._fixture(tmp_path, capsys)
        poisoned = {f"t{i}": True for i in range(12)}
        poisoned[record["sel"][0]] = "yes"
        cand = _write(tmp_path, "poison.json", poisoned)
        code, out = self._gate(capsys, inc, cand, split, record)
        assert code == EXIT_CONFIG and "non-boolean" in out["error"]
        assert not oa._ledger_path(oa._holdout_key(record)).exists()

    def test_full_coverage_still_compares(self, tmp_path, capsys):
        """The redaction must not swallow the ordinary path."""
        inc, split, record = self._fixture(tmp_path, capsys)
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        code, out = self._gate(capsys, inc, cand, split, record)
        assert (code, out["compared"]) == (EXIT_OK, True)

    def test_the_predicate_accepts_a_complete_boolean_mapping(self):
        assert oa._covers_holdout({"a": True, "b": False}, ["a", "b"])

    def test_the_predicate_rejects_a_missing_task(self):
        assert not oa._covers_holdout({"a": True}, ["a", "b"])

    def test_the_predicate_rejects_a_non_boolean(self):
        assert not oa._covers_holdout({"a": True, "b": 1}, ["a", "b"])

    def test_the_predicate_accepts_an_empty_requirement(self):
        """No held-out ids means nothing to cover; the split guard rejects that
        case earlier, so this only pins the predicate as total."""
        assert oa._covers_holdout({}, [])


class TestTheIncumbentFingerprintIsRequired:
    """An optional integrity check is an integrity check nobody runs.

    `--incumbent-fingerprint` defaulted to None, and the guard compares only
    when both sides are present, so omitting the flag silently skipped the
    one check that catches a stale baseline: redraw the split, gate against
    an incumbent scored on the old one, and the comparison is between two
    different eval sets. `score` now reports the fingerprint so supplying it
    costs the caller nothing.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        return inc, cand, tmp_path / "split.json"

    def test_a_missing_incumbent_fingerprint_is_a_usage_error(self, tmp_path, capsys):
        inc, cand, split = self._fixture(tmp_path, capsys)
        with pytest.raises(SystemExit) as exc:
            _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                 "--split", split, "--max-consultations", "3")
        assert exc.value.code == EXIT_CONFIG

    def test_score_reports_the_fingerprint_the_gate_will_demand(self, tmp_path, capsys):
        inc, _cand, split = self._fixture(tmp_path, capsys)
        _, out = _run(capsys, "score", "--results", inc, "--split", split)
        recorded = json.loads(split.read_text(encoding="utf-8"))["fingerprint"]
        assert out["fingerprint"] == recorded

    def test_the_fingerprint_score_reports_is_the_one_the_gate_accepts(self, tmp_path, capsys):
        """End to end: the value `score` prints must satisfy `gate`."""
        inc, cand, split = self._fixture(tmp_path, capsys)
        _, scored = _run(capsys, "score", "--results", inc, "--split", split)
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", split, "--max-consultations", "3",
                         "--incumbent-fingerprint", scored["fingerprint"])
        assert code == EXIT_OK and out["compared"] is True


class TestTheGateNeverPublishesTheHoldoutKey:
    """The key digests the held-out membership, so printing it is printing them.

    A fifth adversarial review (gpt-5.6-sol, 2026-07-26) found the digest in
    three error paths. It is an unsalted sha256 over a set the caller can
    enumerate: the universe is the caller's own results file, `opt` and the
    two group sizes are published, so a caller hashes every subset of the
    complement of the right size and matches. Whenever a test group exists the
    complement is not the held-out group, and that reversal is the only way to
    tell the two apart.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate(self, capsys, inc, cand, split, record, cap="2"):
        return _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split, "--max-consultations", cap,
            "--incumbent-fingerprint", record["fingerprint"],
        )

    def test_lock_contention_does_not_publish_the_key(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        lock = oa._ledger_root() / f"{key}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()
        code, out = self._gate(capsys, inc, inc, split, record)
        assert code == EXIT_CONFIG and "another gate" in out["error"]
        assert key not in json.dumps(out)

    def test_lock_contention_still_says_where_to_look(self, tmp_path, capsys):
        """Redaction that hides the directory turns a stale lock into a puzzle."""
        inc, split, record = self._fixture(tmp_path, capsys)
        lock = oa._ledger_root() / f"{oa._holdout_key(record)}.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()
        _, out = self._gate(capsys, inc, inc, split, record)
        assert str(oa._ledger_root()) in out["error"]

    def test_a_ledger_under_another_group_does_not_publish_either_key(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({"consultations": 0, "holdout": "f" * 64, "max_consultations": 2})
        )
        code, out = self._gate(capsys, inc, inc, split, record)
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")
        assert key not in json.dumps(out) and "f" * 64 not in json.dumps(out)

    def test_a_cap_mismatch_does_not_publish_the_key(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        self._gate(capsys, inc, inc, split, record, cap="2")
        code, out = self._gate(capsys, inc, inc, split, record, cap="5")
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")
        assert "cap of 2" in out["reason"] and key not in json.dumps(out)

    def test_a_malformed_ledger_does_not_publish_the_key(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(json.dumps({"consultations": -1, "holdout": key, "max_consultations": 2}))
        code, out = self._gate(capsys, inc, inc, split, record)
        assert code == EXIT_CONFIG
        assert key not in json.dumps(out)

    def test_the_decision_block_does_not_publish_the_key(self, tmp_path, capsys):
        """The ordinary success path is the one a caller reads every time."""
        inc, split, record = self._fixture(tmp_path, capsys)
        _, out = self._gate(capsys, inc, inc, split, record)
        assert oa._holdout_key(record) not in json.dumps(out)

    def test_the_key_separates_ids_that_contain_a_null_byte(self):
        """Joining on NUL is not injective when an id may contain one."""
        assert oa._holdout_key({"sel": ["a", "b\x00c"]}) != oa._holdout_key(
            {"sel": ["a\x00b", "c"]}
        )

    def test_the_key_still_ignores_the_order_it_is_given(self):
        assert oa._holdout_key({"sel": ["b", "a"]}) == oa._holdout_key({"sel": ["a", "b"]})

    def test_the_key_still_separates_different_members(self):
        assert oa._holdout_key({"sel": ["a", "b"]}) != oa._holdout_key({"sel": ["a", "c"]})


class TestAtomicWriteDoesNotDisguiseNonIOFailures:
    """A ConfigError means the disk refused. Anything else must keep its type.

    The cleanup arm catches BaseException so an interrupt still removes the
    temp file. Converting everything it caught into ConfigError would tell a
    caller the write failed when what actually happened was Ctrl-C, and would
    swallow an interrupt the operator meant to be immediate.
    """

    def test_an_interrupt_propagates_unchanged(self, tmp_path, monkeypatch):
        target = tmp_path / "artifact.md"
        target.write_text("before", encoding="utf-8")

        def _interrupt(src, dst):
            raise KeyboardInterrupt

        monkeypatch.setattr(oa.os, "replace", _interrupt)
        with pytest.raises(KeyboardInterrupt):
            oa._write_atomic(target, "after")
        assert target.read_text(encoding="utf-8") == "before"
        assert list(tmp_path.iterdir()) == [target]

    def test_an_os_error_becomes_a_config_error(self, tmp_path, monkeypatch):
        target = tmp_path / "artifact.md"
        target.write_text("before", encoding="utf-8")

        def _refuse(src, dst):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(oa.os, "replace", _refuse)
        with pytest.raises(oa.ConfigError, match="could not write"):
            oa._write_atomic(target, "after")
        assert list(tmp_path.iterdir()) == [target]

    def test_a_write_that_works_replaces_the_file(self, tmp_path):
        target = tmp_path / "artifact.md"
        target.write_text("before", encoding="utf-8")
        oa._write_atomic(target, "after")
        assert target.read_text(encoding="utf-8") == "after"
        assert list(tmp_path.iterdir()) == [target]


class TestASplitFileMustHoldGroupsOfTaskIds:
    """The gate indexes into every group, so a wrong shape must fail at the file.

    Added by the incoming review-thread commit; these cover its branch. A
    group holding numbers, or holding a bare string instead of a list, would
    otherwise surface as a TypeError deep in the comparison, long after the
    file that caused it went out of scope.
    """

    def _split_with(self, tmp_path, groups):
        record = {"opt": ["a"], "sel": ["b"], "test": [],
                  "seed": "s", "sel_ratio": 0.4, "test_ratio": 0.0,
                  "fingerprint": "x" * 64}
        record.update(groups)
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    @pytest.mark.parametrize("groups", [
        {"opt": "a"},
        {"sel": [1, 2]},
        {"test": [None]},
        {"opt": {"a": True}},
    ])
    def test_a_group_that_is_not_a_list_of_strings_is_refused(
        self, tmp_path, capsys, groups
    ):
        split = self._split_with(tmp_path, groups)
        inc = _write(tmp_path, "inc.json", {"a": True, "b": True})
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", inc,
                         "--split", split, "--max-consultations", "2",
                         "--incumbent-fingerprint", "x" * 64)
        assert code == EXIT_CONFIG
        assert "must be a list of strings" in out["error"]

    def test_a_well_formed_split_passes_the_shape_check(self, tmp_path, capsys):
        """The negative cases must not be passing for an unrelated reason."""
        split = self._split_with(tmp_path, {})
        assert "must be a list of strings" not in json.dumps(
            _run(capsys, "gate", "--incumbent",
                 _write(tmp_path, "i.json", {"a": True, "b": True}),
                 "--candidate", _write(tmp_path, "c.json", {"a": True, "b": True}),
                 "--split", split, "--max-consultations", "2",
                 "--incumbent-fingerprint", "x" * 64)[1]
        )


class TestNoLedgerFailureLeaksTheDigest:
    """The explicit messages were redacted; the generic ones still carried it.

    A sixth adversarial review (gpt-5.6-sol, 2026-07-26) found that redacting
    the three hand-written errors left every other way of failing on a ledger
    path intact: `_read_json` interpolates the file it could not parse, the
    atomic write interpolates the file it could not replace, and `os.open`
    raises with the lock's name for any errno but EEXIST. All three names end
    in the digest. The fix is one scrub at the exception seam rather than
    three sanitized wrappers, because a wrapper covers the paths someone
    remembered and a seam covers the ones added later.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate(self, capsys, inc, split, record):
        return _run(
            capsys, "gate", "--incumbent", inc, "--candidate", inc,
            "--split", split, "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        )

    def test_an_unparseable_ledger_does_not_leak_the_digest(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{not json")
        code, out = self._gate(capsys, inc, split, record)
        assert code == EXIT_CONFIG and key not in json.dumps(out)

    def test_an_unparseable_ledger_still_says_it_could_not_be_read(self, tmp_path, capsys):
        """Scrubbing that erases the diagnosis is worse than the leak."""
        inc, split, record = self._fixture(tmp_path, capsys)
        ledger = oa._ledger_path(oa._holdout_key(record))
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{not json")
        _, out = self._gate(capsys, inc, split, record)
        assert "not valid JSON" in out["error"] and "ledger" in out["error"]

    def test_an_unwritable_ledger_does_not_leak_the_digest(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)

        def _deny(path, _text):
            raise OSError(28, "No space left on device", str(path))

        monkeypatch.setattr(oa, "_write_atomic", _deny)
        code, out = self._gate(capsys, inc, split, record)
        assert code == EXIT_CONFIG and key not in json.dumps(out)

    def test_a_lock_cleanup_failure_does_not_leak(self, tmp_path, capsys, monkeypatch):
        """The unlink in the finally block names the lock, and the lock is the digest.

        Before round 7 this escaped as an uncaught PermissionError, since main
        catches ConfigError and not OSError. Round 9 then stopped it reaching
        main at all, because release runs after the decision is emitted and a
        second document on stdout breaks every reader of the first. So the
        assertions here are on the leak, which is the invariant, and both
        streams are checked; the exit code and the stream split belong to
        TestCleanupFailureDoesNotRewriteTheDecision.
        """
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        real_unlink = Path.unlink

        def _boom(self, missing_ok=False):
            if self.suffix == ".lock":
                raise OSError(13, "Permission denied", str(self))
            return real_unlink(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", _boom)
        inc = _enveloped_copy(inc)
        code = oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])
        captured = capsys.readouterr()
        text = captured.out + captured.err
        assert code != EXIT_CONFIG
        assert key not in text
        for task in record["sel"]:
            assert task not in text

    def test_a_lock_that_fails_for_any_other_reason_does_not_leak(
        self, tmp_path, capsys, monkeypatch
    ):
        """os.open raises for more than EEXIST, and the name is the digest."""
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)

        def _deny(path, *args, **kwargs):
            raise PermissionError(13, "Permission denied", str(path))

        monkeypatch.setattr(oa.os, "open", _deny)
        code, out = self._gate(capsys, inc, split, record)
        assert code == EXIT_CONFIG and key not in json.dumps(out)

    def test_the_scrub_leaves_messages_without_the_digest_alone(self):
        with pytest.raises(oa.ConfigError, match="plain trouble"):
            with oa._digest_scrubbed("a" * 64):
                raise oa.ConfigError("plain trouble")

    def test_the_scrub_replaces_the_digest_wherever_it_appears(self):
        key = "a" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise oa.ConfigError(f"could not read /x/{key}.ledger")
        assert key not in str(caught.value) and "/x/" in str(caught.value)

    def test_the_scrub_passes_a_clean_block_through(self):
        with oa._digest_scrubbed("a" * 64):
            pass


class TestLedgerFailuresKeepTheJsonErrorContract:
    """A scrub that re-raises a raw OSError breaks the promise it protects.

    An eighth review (Copilot, PR #3458) found that `_digest_scrubbed` re-raised
    `OSError` untouched whenever the message did not contain the digest, and
    `main` catches `ConfigError`, `AdapterError`, and `ValueError` but not
    `OSError`. So the failures that name a path stayed inside the contract while
    the failures that do not, an `os.write` that runs out of space or an
    `os.close` that hits EIO, escaped as an uncaught traceback.

    That is the same defect the scrub was added to fix, one layer down: the
    handled paths are the ones somebody enumerated. The seam now converts every
    `OSError` it sees, and redacts the digest only when the message carries it,
    so the two concerns stay separate.
    """

    def test_an_oserror_without_the_digest_still_emits_json(self, capsys):
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("a" * 64):
                raise OSError(28, "No space left on device")
        assert "No space left on device" in str(caught.value)

    def test_the_json_contract_holds_end_to_end_for_a_pathless_oserror(
        self, tmp_path, capsys, monkeypatch
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        record = json.loads(split.read_text())

        def _boom(_handle, _payload):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(oa.os, "write", _boom)
        inc = _enveloped_copy(inc)
        code = oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])
        out = capsys.readouterr().out
        assert code == oa.EXIT_CONFIG
        payload = json.loads(out)
        assert payload["type"] == "ConfigError"
        assert "No space left on device" in payload["error"]

    def test_an_oserror_carrying_the_digest_is_still_redacted(self, capsys):
        key = "b" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise OSError(13, f"Permission denied: /state/{key}.lock")
        assert key not in str(caught.value)
        assert "<held-out group>" in str(caught.value)

    def test_a_config_error_without_the_digest_is_reraised_as_itself(self, capsys):
        original = oa.ConfigError("the split file is not JSON")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("c" * 64):
                raise original
        assert caught.value is original

    def test_a_ledger_mismatch_passes_through_the_seam_untouched(self, capsys):
        with pytest.raises(oa.LedgerMismatchError):
            with oa._digest_scrubbed("c" * 64):
                raise oa.LedgerMismatchError("the cap moved")

    def test_a_non_oserror_passes_through_untouched(self, capsys):
        with pytest.raises(KeyboardInterrupt):
            with oa._digest_scrubbed("d" * 64):
                raise KeyboardInterrupt


class TestTheSeamLeaksNothingThroughTheCauseChain:
    """A scrubbed message with an unscrubbed `__cause__` is not scrubbed.

    A ninth review (gemini-3.1-pro-preview, 2026-07-26) found the redaction
    handing the digest straight back: `raise ConfigError(scrubbed) from exc`
    sets `__cause__` to the original, and a printed traceback walks the chain.
    The contention branch was worse, because its message withholds the lock
    name on purpose and then attached the `FileExistsError` that spells it out.

    The chain is severed exactly where it carries the digest. Where the message
    never had it, `from exc` stays, because the original raise site is worth
    keeping and there is nothing there to leak.
    """

    def _traceback(self, exc):
        return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    def test_a_scrubbed_oserror_leaks_nothing_through_the_chain(self):
        key = "a" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise OSError(2, "No such file", f"/state/{key}.lock")
        assert key not in self._traceback(caught.value)

    def test_lock_contention_leaks_nothing_through_the_chain(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "ledgers"))
        key = "b" * 64
        root = oa._ledger_root()
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{key}.lock").write_text("999")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._ledger_held(key):
                pass
        assert key not in self._traceback(caught.value)

    def test_a_pathless_oserror_keeps_its_cause_for_debugging(self):
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("c" * 64):
                raise OSError(28, "No space left on device")
        assert isinstance(caught.value.__cause__, OSError)


class TestCleanupFailureDoesNotRewriteTheDecision:
    """The gate had already answered; removing the lock is bookkeeping.

    The same ninth review found that an unlink failure in the `finally` reached
    `main` after `_emit` had printed the decision, so stdout carried two JSON
    documents and a successful comparison returned the config-failure exit
    code. The module docstring promises a caller can read a field instead of
    guessing from the exit code, and two documents break every reader of it.

    Swallowing it silently would hide a lock that now blocks the next run, so
    the failure goes to stderr and the decision keeps stdout to itself.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate(self, inc, split, record):
        inc = _enveloped_copy(inc)
        return oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])

    def _break_unlink(self, monkeypatch):
        original = Path.unlink

        def refuse(self, missing_ok=False):
            if str(self).endswith(".lock"):
                raise OSError(13, "Permission denied", str(self))
            return original(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", refuse)

    def test_stdout_still_holds_exactly_one_document(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break_unlink(monkeypatch)
        self._gate(inc, split, record)
        payload = json.loads(capsys.readouterr().out)
        assert payload["decision"] in {"ACCEPT", "REJECT"}

    def test_the_decision_keeps_its_exit_code(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break_unlink(monkeypatch)
        code = self._gate(inc, split, record)
        assert code != oa.EXIT_CONFIG

    def test_the_stale_lock_is_reported_on_stderr(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break_unlink(monkeypatch)
        self._gate(inc, split, record)
        assert "Permission denied" in capsys.readouterr().err

    def test_the_warning_withholds_the_digest(self, tmp_path, capsys, monkeypatch):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        self._break_unlink(monkeypatch)
        self._gate(inc, split, record)
        captured = capsys.readouterr()
        assert key not in captured.err
        assert key not in captured.out

    def test_a_clean_release_says_nothing(self, tmp_path, capsys):
        inc, split, record = self._fixture(tmp_path, capsys)
        self._gate(inc, split, record)
        assert capsys.readouterr().err == ""


class TestTheLedgerRootIsNotOutsideTheSeam:
    """One line in `_ledger_held` sat outside the scrub, and it was the first one.

    A tenth review found `lock.parent.mkdir(...)` above the `with` rather than
    inside it. That has two costs and only the second one needs a contrived
    setup.

    The first is the round-8 contract defect, unfixed at this line. `mkdir` on a
    ledger root the process cannot create raises `PermissionError`, `main`
    catches `(ConfigError, AdapterError, ValueError)` and not `OSError`, so the
    caller piping stdout through a JSON reader gets a traceback instead of the
    error document the module docstring promises. A read-only home or a
    sandboxed runner reaches this with no help from anyone.

    The second is the leak. `$EVAL_LEDGER_DIR` can name a directory that
    contains the digest, and both the `mkdir` traceback and the release warning
    render that directory. A caller who set that variable already knows the
    digest, so this leaks to someone holding the secret. It is fixed anyway,
    because the standing rule from nine rounds is that a path by which the
    withheld thing is readable is not withholding it, and because the release
    warning was justified in review by the claim that a directory carries no
    digest. That justification was wrong, which is reason enough.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate(self, inc, split, record):
        inc = _enveloped_copy(inc)
        return oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])

    def _break(self, monkeypatch, method):
        original = getattr(Path, method)

        def refuse(self, *args, **kwargs):
            if method == "mkdir" or str(self).endswith(".lock"):
                raise PermissionError(13, "Permission denied", str(self))
            return original(self, *args, **kwargs)

        monkeypatch.setattr(Path, method, refuse)

    def test_an_unwritable_ledger_root_keeps_the_json_contract(
        self, tmp_path, capsys, monkeypatch
    ):
        """No digest anywhere. The contract still has to hold."""
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "plain"))
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break(monkeypatch, "mkdir")
        code = self._gate(inc, split, record)
        payload = json.loads(capsys.readouterr().out)
        assert code == EXIT_CONFIG
        assert payload["type"] == "ConfigError"

    def test_a_digest_bearing_root_is_scrubbed_from_the_mkdir_failure(
        self, tmp_path, capsys, monkeypatch
    ):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / f"root-{key}"))
        self._break(monkeypatch, "mkdir")
        self._gate(inc, split, record)
        captured = capsys.readouterr()
        assert key not in captured.out + captured.err

    def test_a_digest_bearing_root_is_scrubbed_from_the_release_warning(
        self, tmp_path, capsys, monkeypatch
    ):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / f"root-{key}"))
        self._break(monkeypatch, "unlink")
        self._gate(inc, split, record)
        captured = capsys.readouterr()
        assert key not in captured.out + captured.err
        assert "<held-out group>" in captured.err

    def test_a_plain_root_is_still_named_so_the_lock_can_be_cleared(
        self, tmp_path, capsys, monkeypatch
    ):
        """Redaction that redacts everything is not redaction, it is silence."""
        root = tmp_path / "plain"
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(root))
        inc, split, record = self._fixture(tmp_path, capsys)
        self._break(monkeypatch, "unlink")
        self._gate(inc, split, record)
        assert str(root) in capsys.readouterr().err


class TestOneDefinitionOfHowWeRedact:
    """The release warning was a second, hand-written redaction site, and it was wrong.

    Two rounds in a row found a redaction defect at a site that had been
    written by hand rather than routed through the seam. The rule the code now
    states once is the rule every site gets.
    """

    def test_a_digest_in_the_text_is_replaced(self):
        assert oa._scrub("under /x/abc123/y", "abc123") == "under /x/<held-out group>/y"

    def test_text_without_the_digest_is_returned_unchanged(self):
        assert oa._scrub("under /x/y", "abc123") == "under /x/y"

    def test_every_occurrence_is_replaced_not_only_the_first(self):
        out = oa._scrub("abc123 and abc123", "abc123")
        assert "abc123" not in out
        assert out.count("<held-out group>") == 2

    def test_empty_text_is_not_a_special_case(self):
        assert oa._scrub("", "abc123") == ""


class TestTheRootResolvesInsideTheContract:
    """An eleventh review found the seam's first line had moved, not vanished.

    Round 10 pulled `lock.parent.mkdir(...)` inside `_digest_scrubbed` and left
    `_ledger_root()` on the line above it. `Path.home()` raises `RuntimeError`
    when `$HOME` is unset and the uid has no passwd entry, which is an ordinary
    container running as a numeric user, and it happens on the DEFAULT
    configuration: `_ledger_root` consults home only when neither
    `$EVAL_LEDGER_DIR` nor `$XDG_STATE_HOME` is set.

    `main` catches `(ConfigError, AdapterError, ValueError)`, so that escaped as
    a traceback where the module docstring promises a JSON error document. The
    conversion belongs in `_ledger_root` rather than at either call site,
    because the failure is there and both callers need it.
    """

    @staticmethod
    def _no_home(monkeypatch):
        monkeypatch.delenv("EVAL_LEDGER_DIR", raising=False)
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        monkeypatch.setattr(
            Path, "home",
            staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("no home"))),
        )

    def test_an_unresolvable_home_is_a_config_error_not_a_runtime_error(self, monkeypatch):
        self._no_home(monkeypatch)
        with pytest.raises(oa.ConfigError) as caught:
            oa._ledger_root()
        assert "EVAL_LEDGER_DIR" in str(caught.value)

    def test_the_gate_still_emits_one_json_document(self, tmp_path, capsys, monkeypatch):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        record = json.loads(split.read_text())
        self._no_home(monkeypatch)
        inc = _enveloped_copy(inc)
        code = oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])
        assert code == EXIT_CONFIG
        assert json.loads(capsys.readouterr().out)["type"] == "ConfigError"

    def test_an_explicit_root_never_consults_home(self, tmp_path, monkeypatch):
        self._no_home(monkeypatch)
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "explicit"))
        assert oa._ledger_root() == tmp_path / "explicit"

    def test_xdg_state_home_also_never_consults_home(self, tmp_path, monkeypatch):
        self._no_home(monkeypatch)
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg"))
        assert oa._ledger_root().is_relative_to(tmp_path / "xdg")


class TestTheLockDescriptorIsAlwaysReleased:
    """The write and the close were in one try, so a failed write skipped the close.

    `os.write` on a full disk jumped straight to the `finally`, which unlinks
    the lock and never closes the descriptor. A one-shot CLI exits and the
    kernel reclaims it, so the practical cost is small; the reason to fix it is
    that `main` is importable and the module is used from tests, where the leak
    accumulates across a session.
    """

    def _fd_state(self, monkeypatch, tmp_path, fail_write):
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "root"))
        seen = {}
        real_open = oa.os.open

        def spy(*args, **kwargs):
            seen["fd"] = real_open(*args, **kwargs)
            return seen["fd"]

        monkeypatch.setattr(oa.os, "open", spy)
        if fail_write:
            monkeypatch.setattr(
                oa.os, "write",
                lambda *a, **k: (_ for _ in ()).throw(OSError(28, "No space left")),
            )
        return seen

    @staticmethod
    def _is_open(fd):
        try:
            os.fstat(fd)
        except OSError:
            return False
        return True

    def test_a_failed_write_still_closes_the_descriptor(self, tmp_path, monkeypatch):
        seen = self._fd_state(monkeypatch, tmp_path, fail_write=True)
        with pytest.raises(oa.ConfigError):
            with oa._ledger_held("d" * 64):
                pass
        assert self._is_open(seen["fd"]) is False

    def test_the_normal_path_closes_it_exactly_once(self, tmp_path, monkeypatch):
        seen = self._fd_state(monkeypatch, tmp_path, fail_write=False)
        with oa._ledger_held("e" * 64):
            pass
        assert self._is_open(seen["fd"]) is False


class TestRedactionIsNotCaseSensitive:
    """A hex digest has an uppercase spelling, and a path can carry either.

    Only reachable when the caller put the digest in `$EVAL_LEDGER_DIR`, which
    means the caller already knows it, so this is not a confidentiality bypass.
    It is fixed because the stated property is that the key is never printed,
    and hex is the one alphabet where case-insensitive matching carries no
    folding surprises.
    """

    def test_an_uppercase_digest_is_replaced(self):
        key = "f" * 60 + "abcd"
        assert key.upper() not in oa._scrub(f"/root-{key.upper()}/x", key)

    def test_a_mixed_case_digest_is_replaced(self):
        key = "abcdef" + "0" * 58
        mixed = "AbCdEf" + "0" * 58
        assert mixed not in oa._scrub(f"/root-{mixed}/x", key)

    def test_the_lowercase_case_still_works(self):
        key = "a" * 64
        assert oa._scrub(f"/root-{key}/x", key) == "/root-<held-out group>/x"

    def test_unrelated_text_is_untouched(self):
        assert oa._scrub("/root/ABCDEF/x", "a" * 64) == "/root/ABCDEF/x"


class TestTheGuardIsNotASecondDefinitionOfRedaction:
    """A twelfth review found the round-11 fix applied to only half the pair.

    Round 11 made `_scrub` case-insensitive and left the call site that decides
    whether to call it reading `if holdout_key in text`, which is case
    sensitive. So an uppercase digest failed the guard, skipped the scrub the
    round-11 fix had just corrected, and printed whole.

    That is the recurring shape once more, in its twelfth spelling: two places
    answer "does this text carry the key" and only one of them was fixed. The
    round-11 tests asserted on `_scrub` directly, which is why four passing
    tests said the case bug was closed while the CLI still printed the digest.
    Testing the function that changed is not testing the property that matters.

    Fixed by deleting the second definition rather than teaching it to fold
    case: `_scrub` returning a different string is the answer to both questions,
    so there is nothing left to keep in step.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        split = tmp_path / "split.json"
        _run(capsys, "split", "--results", inc, "--seed", "s", "--out", split)
        return inc, split, json.loads(split.read_text())

    def _gate_denied(self, monkeypatch, tmp_path, capsys, spell):
        inc, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        monkeypatch.setenv(oa._LEDGER_DIR_ENV, str(tmp_path / f"denied-{spell(key)}"))
        monkeypatch.setattr(
            Path,
            "mkdir",
            lambda self, *a, **k: (_ for _ in ()).throw(
                PermissionError(13, "Permission denied", str(self))
            ),
        )
        inc = _enveloped_copy(inc)
        code = oa.main([
            "gate", "--incumbent", str(inc), "--candidate", str(inc),
            "--split", str(split), "--max-consultations", "2",
            "--incumbent-fingerprint", record["fingerprint"],
        ])
        return key, code, capsys.readouterr()

    def test_an_uppercase_digest_does_not_reach_stdout(self, tmp_path, monkeypatch, capsys):
        key, code, out = self._gate_denied(monkeypatch, tmp_path, capsys, str.upper)
        assert code == oa.EXIT_CONFIG
        assert key.upper() not in out.out
        assert key.upper() not in out.err

    def test_an_uppercase_digest_still_leaves_a_readable_error(
        self, tmp_path, monkeypatch, capsys
    ):
        _key, _code, out = self._gate_denied(monkeypatch, tmp_path, capsys, str.upper)
        payload = json.loads(out.out)
        assert payload["type"] == "ConfigError"
        assert oa._HELD_OUT_PLACEHOLDER in payload["error"]

    def test_a_lowercase_digest_does_not_reach_stdout(self, tmp_path, monkeypatch, capsys):
        key, code, out = self._gate_denied(monkeypatch, tmp_path, capsys, str.lower)
        assert code == oa.EXIT_CONFIG
        assert key not in out.out
        assert key not in out.err

    def test_the_seam_scrubs_an_uppercase_digest_in_an_oserror(self):
        key = "b" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise OSError(13, "denied", f"/root-{key.upper()}/x")
        assert key.upper() not in str(caught.value)
        assert oa._HELD_OUT_PLACEHOLDER in str(caught.value)

    def test_the_seam_scrubs_a_mixed_case_digest(self):
        key = "abcdef" + "0" * 58
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise oa.ConfigError(f"/root-{'AbCdEf' + '0' * 58}/x")
        assert "AbCdEf" not in str(caught.value)

    def test_a_scrubbed_error_still_breaks_the_cause_chain(self):
        key = "c" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                raise OSError(13, "denied", f"/root-{key.upper()}/x")
        assert caught.value.__cause__ is None

    def test_an_error_without_the_digest_keeps_its_message(self):
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("d" * 64):
                raise OSError(28, "No space left on device")
        assert "No space left on device" in str(caught.value)

    def test_a_config_error_without_the_digest_is_reraised_as_itself(self):
        original = oa.ConfigError("nothing secret here")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed("e" * 64):
                raise original
        assert caught.value is original


class TestTheReportedTailCanAlsoRefuse:
    """`--max-p` promotes the printed McNemar tail into a gate.

    A live run over the seven files in tests/evals/rule-scenarios/ scored the
    identical rule text twice. Five of 24 tasks flipped with no input change
    and the held-out group moved 6/10 to 7/10, so on a nondeterministic scorer
    a strictly-greater rule accepts variance. The tail was already computed
    and printed; before this flag it could not refuse anything.

    Default stays absent: a held-out group of three cannot reach a
    conventional floor, and a bar nothing can clear is not a gate.
    """

    def _gate(self, tmp_path, capsys, *extra, cap=1, seed="s1"):
        """Budget of one by default: the bar is family-wise, so a larger
        budget divides it and these cases are about the bar itself. `seed`
        draws a different held-out group, and so a different ledger, for
        cases that gate twice under different settings."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", seed)
        split_path = _write(tmp_path, "split.json", split)
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, *extra, cap=cap,
        )

    def test_the_bar_is_divided_across_the_budget_it_was_declared_with(
        self, tmp_path, capsys
    ):
        """A tail that clears the bar at a budget of one misses it at ten."""
        _, tight = self._gate(tmp_path, capsys, "--max-p", "0.1", cap=1)
        assert tight["decision"] == "ACCEPT"
        _, spread = self._gate(tmp_path, capsys, "--max-p", "0.1", cap=10, seed="s2")
        assert spread["decision"] == "REJECT"
        assert spread["max_p_per_comparison"] == pytest.approx(0.01)

    def test_without_the_flag_a_win_with_a_wide_tail_still_accepts(self, tmp_path, capsys):
        code, out = self._gate(tmp_path, capsys)
        assert out["p_value"] == pytest.approx(0.0625)
        assert out["decision"] == "ACCEPT"
        assert code == EXIT_OK

    def test_the_same_win_is_refused_under_a_conventional_bar(self, tmp_path, capsys):
        code, out = self._gate(tmp_path, capsys, "--max-p", "0.05")
        assert out["decision"] == "REJECT"
        assert code == EXIT_LOGIC
        assert "0.0625" in out["reason"] and "0.05" in out["reason"]

    def test_a_bar_the_tail_clears_still_accepts(self, tmp_path, capsys):
        _, out = self._gate(tmp_path, capsys, "--max-p", "0.1")
        assert out["decision"] == "ACCEPT"

    def test_the_reported_tail_is_unchanged_by_the_bar(self, tmp_path, capsys):
        """The bar decides; it must not edit the evidence it decided on."""
        _, loose = self._gate(tmp_path, capsys, "--max-p", "1.0")
        assert loose["p_value"] == pytest.approx(0.0625)

    def test_a_refused_win_still_spends_its_consultation(self, tmp_path, capsys):
        """The held-out group was read to compute the tail. Reading is the cost."""
        _, out = self._gate(tmp_path, capsys, "--max-p", "0.0")
        assert out["decision"] == "REJECT"
        assert out["sel_consultations"] == 1

    def test_a_bar_outside_the_unit_interval_is_a_config_error(self, tmp_path, capsys):
        code, _ = self._gate(tmp_path, capsys, "--max-p", "1.5")
        assert code == EXIT_CONFIG

    def test_a_non_numeric_bar_is_refused_by_the_parser(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            self._gate(tmp_path, capsys, "--max-p", "nope")


class TestTheBarIsPinnedLikeTheBudget:
    """Round fourteen: a re-suppliable bar is not a bar.

    An adversarial reviewer (gpt-5.6-terra, 2026-07-27) pointed out that the
    ledger pins the consultation cap precisely so a caller who hits the budget
    cannot raise it and carry on, but left `--max-p` re-suppliable. A candidate
    refused at 0.05 could be gated again at 0.1 against the same held-out group
    and accepted. That is the mutable-cap defect wearing a different hat, so it
    gets the same treatment: the bar is fixed when the group is opened, and its
    absence is pinned just as firmly as its presence.

    Validating the flag before the ledger write matters for the same reason the
    write happens early. A nonsense bar is decidable without reading the group,
    so it must not cost a consultation.
    """

    def _fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 2 for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, record = _split(capsys, tmp_path, "--results", inc, "--seed", "pin")
        return inc, cand, _write(tmp_path, "split.json", record), record

    def _gate(self, capsys, inc, cand, split, record, *extra, cap="4"):
        return _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split, "--max-consultations", cap,
            "--incumbent-fingerprint", str(record["fingerprint"]), *extra,
        )

    def test_a_bar_cannot_be_loosened_after_the_group_was_opened(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, record, "--max-p", "0.05")
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")
        assert "0.05" in out["reason"]

    def test_a_bar_cannot_be_dropped_after_the_group_was_opened(self, tmp_path, capsys):
        """Omitting the flag is the loosest setting of all, so it is pinned too."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, record, "--max-p", "0.05")
        code, out = self._gate(capsys, inc, cand, split, record)
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")

    def test_a_bar_cannot_be_added_after_the_group_was_opened_without_one(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, record)
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.05")
        assert (code, out["decision"]) == (EXIT_LOGIC, "REJECT")

    def test_the_same_bar_twice_is_not_a_mismatch(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert out.get("reason", "") == "" or "opened under" not in out["reason"]
        assert code in (EXIT_OK, EXIT_LOGIC)

    def test_a_pinned_bar_mismatch_does_not_publish_the_key(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        self._gate(capsys, inc, cand, split, record, "--max-p", "0.05")
        _, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert key not in json.dumps(out)

    def test_a_nonsense_bar_costs_no_consultation(self, tmp_path, capsys):
        """Decidable without reading the group, so it must not charge for one."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        code, _ = self._gate(capsys, inc, cand, split, record, "--max-p", "1.5")
        assert code == EXIT_CONFIG
        assert not oa._ledger_path(oa._holdout_key(record)).exists()

    def test_a_nonsense_bar_is_config_error_even_on_an_exhausted_budget(self, tmp_path, capsys):
        """The flag is wrong whether or not the budget would have refused."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        for _ in range(2):
            self._gate(capsys, inc, cand, split, record, "--max-p", "0.5", cap="2")
        code, _ = self._gate(capsys, inc, cand, split, record, "--max-p", "-1", cap="2")
        assert code == EXIT_CONFIG

    def test_the_verdict_reports_the_bar_it_applied(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        _, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert out["max_p"] == 0.5
        assert out["max_p_per_comparison"] == 0.125

    def test_the_verdict_reports_an_absent_bar_as_absent(self, tmp_path, capsys):
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        _, out = self._gate(capsys, inc, cand, split, record)
        assert out["max_p"] is None and out["max_p_per_comparison"] is None

    def test_a_malformed_bar_in_the_ledger_is_named(self, tmp_path, capsys):
        """A hand-edited ledger says so rather than comparing a string to a float."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps(
                {
                    "consultations": 0,
                    "holdout": key,
                    "max_consultations": 4,
                    "max_p": "loose",
                }
            ),
            encoding="utf-8",
        )
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert code == EXIT_CONFIG
        assert "max_p" in out["error"] and key not in json.dumps(out)

    def test_a_ledger_written_before_the_bar_existed_reads_as_no_bar(
        self, tmp_path, capsys
    ):
        """An absent key is the absent policy, so old ledgers keep working."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)
        key = oa._holdout_key(record)
        ledger = oa._ledger_path(key)
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text(
            json.dumps({"consultations": 0, "holdout": key, "max_consultations": 4}),
            encoding="utf-8",
        )
        code, out = self._gate(capsys, inc, cand, split, record)
        assert code in (EXIT_OK, EXIT_LOGIC)
        assert out["max_p"] is None

    def test_a_contract_violation_inside_the_gate_exits_as_config(
        self, tmp_path, capsys, monkeypatch
    ):
        """Defense in depth: cmd_gate screens the flag, but the library still
        refuses an incoherent call rather than escaping as a traceback."""
        inc, cand, split, record = self._fixture(tmp_path, capsys)

        def _explode(*_args, **_kwargs):
            raise ValueError("max_p needs a p_value to judge")

        monkeypatch.setattr(oa, "gate", _explode)
        code, out = self._gate(capsys, inc, cand, split, record, "--max-p", "0.5")
        assert code == EXIT_CONFIG
        assert "p_value" in out["error"]


# The two corpus identities the architect incident actually disagreed on,
# padded to the sha256 width the producer emits.
_CORPUS_ONE = "be99fa1b1180".ljust(64, "0")
_CORPUS_TWO = "26136df314d6".ljust(64, "0")


class TestTheSeamCarriesTheCorpusItWasScoredAgainst:
    """A comparison of two results files says nothing unless both scored the
    same tasks, and until now the seam could not tell.

    On 2026-07-27 two architect-spike runs were gated against each other and
    read as a null control. They agreed on `model_id` and `agent_prompt_sha`
    and disagreed on `fixture_set_sha`: every one of the eight fixture files
    had changed between them. The accept was published before the mismatch was
    found. The report format already carried the falsifier, and
    `_fixture_set_sha`'s own docstring says it exists so a report consumer can
    verify two runs hit the same set. `extract` never read it.

    Task ids do not substitute. All eight ids matched across those two runs
    while the contents behind them differed, so a key-set comparison would
    have passed the pair through.
    """

    def _agent_report(self, tmp_path, name, corpus, rates=None):
        payload = {
            "error_count": 0,
            "per_fixture_pass_rates": rates
            or {f"t{i}": {"agent": [1.0 if i < 5 else 0.0]} for i in range(10)},
        }
        if corpus is not None:
            payload["fixture_set_sha"] = corpus
        return _write(tmp_path, name, payload)

    def _extract(self, capsys, report, out_name, tmp_path):
        _, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        return _write(tmp_path, out_name, out)

    def _gate_pair(self, tmp_path, capsys, inc_corpus, cand_corpus, seed="c1"):
        inc = self._extract(
            capsys, self._agent_report(tmp_path, "ri.json", inc_corpus), "inc.json", tmp_path
        )
        cand = self._extract(
            capsys,
            self._agent_report(
                tmp_path,
                "rc.json",
                cand_corpus,
                rates={f"t{i}": {"agent": [1.0]} for i in range(10)},
            ),
            "cand.json",
            tmp_path,
        )
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", seed)
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        return code, out, split

    # -- extract carries it forward ----------------------------------------

    def test_extract_carries_the_report_s_own_corpus_identity(self, tmp_path, capsys):
        report = self._agent_report(tmp_path, "r.json", _CORPUS_ONE)
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_OK
        assert out["corpus"] == _CORPUS_ONE
        assert out["results"]["t0"] is True
        assert out["schema"] == "optimizer-results/1"

    def test_a_report_without_the_field_extracts_an_unknown_corpus(self, tmp_path, capsys):
        """Absent is null, never a value invented from the task ids.

        A synthesized id would make two unrelated corpora compare equal
        whenever their ids matched, which is the exact failure this guards.
        """
        report = self._agent_report(tmp_path, "r.json", None)
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_OK
        assert out["corpus"] is None

    def test_a_non_string_corpus_field_in_the_report_is_refused(self, tmp_path, capsys):
        """A corpus identity that is not an identity is a config error, not a
        value to coerce. Coercing it would let `17` and `"17"` compare equal
        across two reports that meant different things."""
        report = _write(
            tmp_path, "r.json",
            {"per_fixture_pass_rates": {"t0": {"agent": [1.0]}}, "fixture_set_sha": 17},
        )
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_CONFIG

    def test_the_hook_path_has_no_corpus_source_and_says_so(self, tmp_path, capsys):
        junit = tmp_path / "j.xml"
        junit.write_text(
            '<testsuite><testcase classname="tests.a" name="test_x"/></testsuite>',
            encoding="utf-8",
        )
        code, out = _run(capsys, "extract", "--kind", "hook", "--input", junit)
        assert code == EXIT_OK
        assert out["corpus"] is None
        assert out["results"]

    # -- the reader ---------------------------------------------------------

    def test_a_bare_mapping_is_refused_without_provenance(self, tmp_path):
        path = _write(tmp_path, "legacy.json", {"a": True, "b": False})
        with pytest.raises(oa.ConfigError, match="provenance"):
            oa._read_results(path)

    def test_a_task_named_schema_does_not_masquerade_as_an_envelope(self, tmp_path):
        path = _write(tmp_path, "legacy.json", {"schema": True, "results": False})
        with pytest.raises(oa.ConfigError, match="provenance"):
            oa._read_results(path)

    def test_an_unrecognized_envelope_version_is_refused_not_guessed(self, tmp_path):
        path = _write(
            tmp_path, "future.json",
            {"schema": "optimizer-results/2", "corpus": None, "results": {"a": True}},
        )
        with pytest.raises(oa.ConfigError, match="optimizer-results/2"):
            oa._read_results(path)

    def test_an_envelope_whose_corpus_is_not_a_string_is_refused(self, tmp_path):
        path = _write(
            tmp_path, "bad.json",
            {"schema": "optimizer-results/1", "corpus": 17, "results": {"a": True}},
        )
        with pytest.raises(oa.ConfigError, match="corpus"):
            oa._read_results(path)

    def test_an_envelope_without_results_is_refused(self, tmp_path):
        path = _write(tmp_path, "bad.json", {"schema": "optimizer-results/1", "corpus": None})
        with pytest.raises(oa.ConfigError, match="results"):
            oa._read_results(path)

    def test_non_boolean_verdicts_are_still_refused_inside_an_envelope(self, tmp_path):
        path = _write(
            tmp_path, "bad.json",
            {"schema": "optimizer-results/1", "corpus": None, "results": {"a": 1}},
        )
        with pytest.raises(oa.ConfigError, match="non-boolean"):
            oa._read_results(path)

    # -- the refusal --------------------------------------------------------

    def test_two_known_and_different_corpora_are_refused_uncompared(self, tmp_path, capsys):
        code, out, _ = self._gate_pair(tmp_path, capsys, _CORPUS_ONE, _CORPUS_TWO)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False
        assert "corpus" in out["reason"]

    def test_the_refusal_spends_no_consultation(self, tmp_path, capsys):
        """Decidable from two header fields, so it must be free.

        A mismatch that cost a consultation would let a caller burn a budget
        it can never spend usefully, and the pair is unusable no matter how
        much budget remains.
        """
        code, out, split = self._gate_pair(tmp_path, capsys, _CORPUS_ONE, _CORPUS_TWO)
        assert out["consultations"] == 0
        assert not oa._ledger_path(oa._holdout_key(split)).exists()

    def test_matching_corpora_gate_normally(self, tmp_path, capsys):
        code, out, _ = self._gate_pair(tmp_path, capsys, _CORPUS_ONE, _CORPUS_ONE, seed="c2")
        assert out["compared"] is True
        assert out["corpus_verified"] is True

    def test_an_unknown_corpus_beside_a_known_one_is_refused(self, tmp_path, capsys):
        """This assertion is the inverse of the one it replaces.

        The first cut let unknown pass beside known, on the reasoning that the
        rule and hook paths publish no corpus and refusing unknown would
        disable the gate for them. That reasoning holds for a pair where
        *neither* side knows, and a fifteenth review showed it does not survive
        the asymmetric case: it made the refusal deletable, since stripping the
        envelope off either file turns a known mismatch into an unknown that
        compares. A pair scored on one corpus does not have one side that
        forgot.
        """
        code, out, _ = self._gate_pair(tmp_path, capsys, None, _CORPUS_TWO, seed="c3")
        assert code == EXIT_LOGIC
        assert out["compared"] is False

    def test_two_unknown_corpora_are_reported_rather_than_silently_allowed(
        self, tmp_path, capsys
    ):
        """Unknown on both sides is not refused: the rule and hook paths have
        no corpus source at all, so refusing there would disable the gate for
        two of three artifact classes. It is reported so an operator reading
        the verdict knows the comparison was never checked."""
        code, out, _ = self._gate_pair(tmp_path, capsys, None, None, seed="c3b")
        assert out["compared"] is True
        assert out["corpus_verified"] is False

    def test_both_unknown_gates_and_reports_unverified(self, tmp_path, capsys):
        code, out, _ = self._gate_pair(tmp_path, capsys, None, None, seed="c4")
        assert out["compared"] is True
        assert out["corpus_verified"] is False

    def test_the_mismatch_refusal_names_no_held_out_task(self, tmp_path, capsys):
        _, out, split = self._gate_pair(tmp_path, capsys, _CORPUS_ONE, _CORPUS_TWO, seed="c5")
        blob = json.dumps(out)
        for task_id in split["sel"] + split["test"]:
            assert task_id not in blob
        assert oa._holdout_key(split) not in blob

    def test_an_exhausted_budget_does_not_mask_the_mismatch(self, tmp_path, capsys):
        """Same precedent as the `--max-p` range check: a refusal decidable
        without the held-out group must not be reordered behind one that needs
        the ledger, or the caller is told to buy budget for a comparison that
        can never be valid."""
        inc = self._extract(
            capsys, self._agent_report(tmp_path, "ri.json", _CORPUS_ONE), "inc.json", tmp_path
        )
        cand = self._extract(
            capsys, self._agent_report(tmp_path, "rc.json", _CORPUS_TWO), "cand.json", tmp_path
        )
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "c6")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=1, spent=1,
        )
        assert out["decision"] == "REJECT"
        assert "corpus" in out["reason"]

    # -- the other readers keep working -------------------------------------

    def test_split_reads_an_envelope(self, tmp_path, capsys):
        inc = self._extract(
            capsys, self._agent_report(tmp_path, "r.json", _CORPUS_ONE), "inc.json", tmp_path
        )
        code, split = _split(capsys, tmp_path, "--results", inc, "--seed", "c7")
        assert code == EXIT_OK
        assert len(split["opt"]) + len(split["sel"]) + len(split["test"]) == 10

    def test_score_reads_an_envelope(self, tmp_path, capsys):
        inc = self._extract(
            capsys, self._agent_report(tmp_path, "r.json", _CORPUS_ONE), "inc.json", tmp_path
        )
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "c8")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run(
            capsys, "score", "--results", inc, "--split", split_path, "--group", "opt"
        )
        assert code == EXIT_OK
        assert 0.0 <= out["score"] <= 1.0


_SHA_A = "a" * 64
_SHA_B = "b" * 64


class TestTheCorpusPinCannotBeStrippedAway:
    """A refusal a caller can delete their way past is not a refusal.

    The first cut of the corpus guard refused only when both files declared a
    corpus and the two disagreed. That left the mismatch reachable by omission:
    piping either side through anything that emits a bare mapping, which is
    what every consumer wrote before the envelope existed, turned the pair from
    "known to differ" into "unknown", and unknown compared. The bypass needed no
    intent. It is the same shape as the incident it was built for, where nobody
    edited anything and the field simply went unread.

    Two changes close it. `split` pins the corpus of the results it was drawn
    from, so the baseline commitment carries the corpus rather than the
    comparison inferring it. And one known corpus beside an unknown one is a
    conflict, because the asymmetry is itself the evidence: a pair scored on one
    corpus does not have one side that forgot.

    The limit is worth stating. The split file is caller-supplied and its
    corpus pin is outside the fingerprint, so a caller who edits two files in
    concert can still defeat this. That is not what it defends against. It
    defends against omission, which is the failure that actually happened.
    """

    def _report(self, tmp_path, name, corpus, rates=None):
        payload = {
            "error_count": 0,
            "per_fixture_pass_rates": rates
            or {f"t{i}": {"agent": [1.0 if i < 5 else 0.0]} for i in range(10)},
        }
        if corpus is not None:
            payload["fixture_set_sha"] = corpus
        return _write(tmp_path, name, payload)

    def _extract(self, capsys, report, out_name, tmp_path):
        _, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        return _write(tmp_path, out_name, out)

    def _pair(self, tmp_path, capsys, inc_corpus, cand_corpus):
        """Two enveloped results files that differ only in verdicts and corpus."""
        inc = self._extract(
            capsys, self._report(tmp_path, "ri.json", inc_corpus), "inc.json", tmp_path
        )
        cand = self._extract(
            capsys,
            self._report(
                tmp_path, "rc.json", cand_corpus,
                rates={f"t{i}": {"agent": [1.0]} for i in range(10)},
            ),
            "cand.json",
            tmp_path,
        )
        return inc, cand

    def _bare(self, tmp_path, name, path):
        """The same results with the envelope stripped, as an old consumer emits."""
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return _write(tmp_path, name, payload["results"])

    def _gate(self, tmp_path, capsys, inc, cand, seed, split_from=None, **kw):
        _, split = _split(capsys, tmp_path, "--results", split_from or inc, "--seed", seed)
        split_path = _write(tmp_path, "split.json", split)
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5, **kw
        )

    # -- the pin ------------------------------------------------------------

    def test_split_records_the_corpus_of_the_results_it_was_drawn_from(
        self, tmp_path, capsys
    ):
        inc = self._extract(
            capsys, self._report(tmp_path, "r.json", _SHA_A), "inc.json", tmp_path
        )
        code, split = _split(capsys, tmp_path, "--results", inc, "--seed", "p1")
        assert code == EXIT_OK
        assert split["corpus"] == _SHA_A

    def test_a_split_drawn_from_a_task_list_pins_nothing(self, tmp_path, capsys):
        tasks = tmp_path / "tasks.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(10)), encoding="utf-8")
        code, split = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "p2")
        assert code == EXIT_OK
        assert "corpus" not in split

    def test_a_split_drawn_from_a_bare_mapping_pins_nothing(self, tmp_path, capsys):
        legacy = _write(tmp_path, "legacy.json", {f"t{i}": i < 5 for i in range(10)})
        code, split = _split(capsys, tmp_path, "--results", legacy, "--seed", "p3")
        assert code == EXIT_OK
        assert "corpus" not in split

    # -- the bypass, closed -------------------------------------------------

    def test_stripping_one_envelope_does_not_buy_a_comparison(self, tmp_path, capsys):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_B)
        stripped = self._bare(tmp_path, "cand-bare.json", cand)
        code, out = self._gate(tmp_path, capsys, inc, stripped, "p4")
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False
        assert out["consultations"] == 0

    def test_stripping_both_envelopes_does_not_buy_a_comparison(self, tmp_path, capsys):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_B)
        code, split = _split(capsys, tmp_path, "--results", inc, "--seed", "p5")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path,
            "--incumbent", self._bare(tmp_path, "i-bare.json", inc),
            "--candidate", self._bare(tmp_path, "c-bare.json", cand),
            "--split", split_path, cap=5,
        )
        assert out["decision"] == "REJECT"
        assert out["compared"] is False

    def test_one_known_corpus_beside_an_unknown_one_conflicts_without_a_pin(
        self, tmp_path, capsys
    ):
        """No pin at all, so the conflict has to come from the pair itself."""
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, None)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "p6")
        split.pop("corpus")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert out["decision"] == "REJECT"
        assert out["compared"] is False

    # -- what must keep working ---------------------------------------------

    def test_two_unknown_corpora_still_compare(self, tmp_path, capsys):
        """The rule and hook paths publish no corpus and must not be disabled."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        code, out = self._gate(tmp_path, capsys, inc, cand, "p7")
        assert out["compared"] is True
        assert out["corpus_verified"] is False

    def test_a_matching_digest_on_both_sides_compares_and_reports_verified(
        self, tmp_path, capsys
    ):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_A)
        code, out = self._gate(tmp_path, capsys, inc, cand, "p8")
        assert out["compared"] is True
        assert out["corpus_verified"] is True

    def test_a_pinned_digest_that_both_files_match_compares(self, tmp_path, capsys):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_A)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "p9")
        assert split["corpus"] == _SHA_A
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert out["compared"] is True

    # -- the digest has to look like one ------------------------------------

    @pytest.mark.parametrize(
        "bad", ["", "   ", "be99fa1b1180", "A" * 64, "g" * 64, "a" * 63, "a" * 65]
    )
    def test_a_corpus_that_is_not_a_sha256_digest_is_refused_at_extract(
        self, tmp_path, capsys, bad
    ):
        report = self._report(tmp_path, "r.json", bad)
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_CONFIG

    def test_a_lowercase_sha256_digest_survives_extract(self, tmp_path, capsys):
        report = self._report(tmp_path, "r.json", _SHA_A)
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == EXIT_OK
        assert out["corpus"] == _SHA_A

    def test_an_envelope_whose_corpus_is_not_a_digest_is_refused(self, tmp_path):
        path = _write(
            tmp_path, "bad.json",
            {"schema": "optimizer-results/1", "corpus": "", "results": {"a": True}},
        )
        with pytest.raises(oa.ConfigError, match="corpus"):
            oa._read_results(path)

    # -- ordering: a parse error must not stand in for the ledger's answer ---

    def test_malformed_results_do_not_preempt_an_exhausted_ledger(
        self, tmp_path, capsys
    ):
        """The budget refusal is the authoritative one and has to survive.

        Reading both files before the lock is what makes the corpus refusal
        free. Doing the *whole* read there would let a bad verdict mapping
        answer in place of the ledger, which tells the caller to fix the wrong
        thing.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pa")
        split_path = _write(tmp_path, "split.json", split)
        bad = _write(tmp_path, "cand.json", {f"t{i}": "yes" for i in range(10)})
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", bad,
            "--split", split_path, cap=1, spent=1,
        )
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "consultation" in out["reason"]

    def test_unreadable_results_do_not_preempt_an_exhausted_ledger(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pb")
        split_path = _write(tmp_path, "split.json", split)
        junk = tmp_path / "cand.json"
        junk.write_text("{not json", encoding="utf-8")
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", junk,
            "--split", split_path, cap=1, spent=1,
        )
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "consultation" in out["reason"]

    def test_malformed_results_still_fail_loudly_when_the_budget_allows(
        self, tmp_path, capsys
    ):
        """Deferring the full read must not swallow it."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pc")
        split_path = _write(tmp_path, "split.json", split)
        bad = _write(tmp_path, "cand.json", {f"t{i}": "yes" for i in range(10)})
        code, _ = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", bad,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG

    def test_the_preflight_refusal_names_no_task_and_no_digest(
        self, tmp_path, capsys
    ):
        inc, cand = self._pair(tmp_path, capsys, _SHA_A, _SHA_B)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pd")
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        blob = json.dumps(out)
        assert oa._holdout_key(split) not in blob
        assert not any(t in blob for t in split["sel"] + split["test"])

    def test_a_preflight_read_failure_leaves_the_digest_out_of_the_error(
        self, tmp_path, capsys, monkeypatch
    ):
        """Whatever goes wrong under the preflight is still scrubbed.

        The error lands on stdout as JSON, not on stderr: `main` turns a
        `ConfigError` into a payload so a driver can tell a refusal from a
        config failure by reading a field. An earlier version of this test read
        stderr after `_run_gate` had already drained the capture, so it asserted
        the digest was absent from an empty string and could not have failed.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pe")
        split_path = _write(tmp_path, "split.json", split)
        key = oa._holdout_key(split)
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: (_ for _ in ()).throw(
            OSError(f"cannot open {key}")
        ))
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert key not in json.dumps(out)
        assert oa._HELD_OUT_PLACEHOLDER in out["error"]

    def test_that_scrub_test_would_fail_without_the_scrubber(
        self, tmp_path, capsys, monkeypatch
    ):
        """The negative control the tautological version never had.

        Aimed at `_dispatch` rather than `main`. `main` now converts every
        escaping OSError into EXIT_CONFIG so a dead output stream cannot be
        read as a REJECT, which means an escape is no longer observable at
        that boundary. `_dispatch` is the layer the scrubber actually wraps,
        so the control still watches the thing it was built to watch instead
        of being kept green by a guard that answers a different question.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pe2")
        split_path = _write(tmp_path, "split.json", split)
        key = oa._holdout_key(split)
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: (_ for _ in ()).throw(
            OSError(f"cannot open {key}")
        ))
        monkeypatch.setattr(oa, "_digest_scrubbed", contextlib.nullcontext)
        monkeypatch.setattr(oa, "main", oa._dispatch)
        with pytest.raises(OSError) as caught:
            _run_gate(
                capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
                "--split", split_path, cap=5,
            )
        assert key in str(caught.value)

    # -- the predicate on its own -------------------------------------------

    @pytest.mark.parametrize(
        ("pin", "inc", "cand", "conflict"),
        [
            (oa._UNPINNED, None, None, False),
            (oa._UNPINNED, _SHA_A, _SHA_A, False),
            (None, None, None, False),
            (_SHA_A, _SHA_A, _SHA_A, False),
            (oa._UNPINNED, _SHA_A, _SHA_B, True),
            (oa._UNPINNED, _SHA_A, None, True),
            (oa._UNPINNED, None, _SHA_A, True),
            (_SHA_A, _SHA_A, None, True),
            (_SHA_A, None, None, True),
            (_SHA_A, _SHA_B, _SHA_B, True),
            (None, _SHA_A, _SHA_A, True),
        ],
    )
    def test_the_conflict_rule_is_more_than_one_declared_corpus(
        self, pin, inc, cand, conflict
    ):
        assert oa._corpus_conflict(pin, inc, cand) is conflict

    def test_an_absent_pin_is_not_the_same_as_a_pin_of_unknown(self):
        """`None` is a legal pin, so absence needs a value JSON cannot produce.

        Collapsing the two would make a split written before the pin existed
        assert that its corpus was unknown, which would refuse every enveloped
        pair gated against an older split.
        """
        assert oa._corpus_conflict(oa._UNPINNED, _SHA_A, _SHA_A) is False
        assert oa._corpus_conflict(None, _SHA_A, _SHA_A) is True
        assert json.loads(json.dumps({"corpus": None}))["corpus"] is None

    def test_the_refusal_advises_nothing_the_split_may_not_carry(self):
        """The rule refuses splits that name no corpus, so the advice cannot name one.

        `(_UNPINNED, SHA_A, SHA_B)` is a refusing row, and it is what a
        `--tasks` split looks like beside two results that disagree. Advice to
        re-score against the corpus the split names sends that operator to a
        key their split does not have.

        The advice restates the guard's own rule instead. That is the one
        claim true for every refusing row, and the only wording here that a
        reader can check against `_corpus_conflict` rather than against a
        particular caller's files.
        """
        assert oa._corpus_conflict(oa._UNPINNED, _SHA_A, _SHA_B) is True
        reason = str(oa._corpus_refusal()["reason"])
        assert "the corpus the split" not in reason
        assert "only one corpus" in reason


class TestWhatTheVerdictClaimsWasChecked:
    """Round sixteen: the pin is caller-supplied, so say when it was absent.

    `corpus_verified` reports that the two results agree. It cannot report that
    the split was drawn from the corpus they name, because a caller who deletes
    the split's `corpus` key leaves two agreeing files and nothing to contradict
    them. Refusing that pair would disable the gate for the rule and hook paths,
    which pin nothing at all, so the verdict names the weaker guarantee instead
    of hiding it behind the stronger one.
    """

    def test_a_pinned_split_that_agrees_reports_both_facts(self, tmp_path, capsys):
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pin-a")
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert out["corpus_verified"] is True
        assert out["corpus_pinned"] is True

    def test_deleting_the_pin_is_visible_in_the_verdict(self, tmp_path, capsys):
        """The one-file edit the guard cannot refuse is the one it must report."""
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pin-b")
        del split["corpus"]
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert out["corpus_verified"] is True
        assert out["corpus_pinned"] is False

    def test_a_task_list_split_pins_nothing_and_says_so(self, tmp_path, capsys):
        tasks = tmp_path / "ids.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(10)), encoding="utf-8")
        _, split = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "pin-c")
        split_path = _write(tmp_path, "split.json", split)
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert out["corpus_verified"] is True
        assert out["corpus_pinned"] is False

    def test_legacy_files_claim_neither(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pin-d")
        split_path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        assert out["corpus_verified"] is False
        assert out["corpus_pinned"] is False


class TestTheCorpusIsRecheckedAgainstWhatWasActuallyScored:
    """Round sixteen: the preflight reads headers, the gate reads bodies.

    Two reads of one path can disagree, whether because a writer moved under
    them or because the two parsers drift. The values the comparison is scored
    from are the ones in `ResultsFile`, so those are the ones that have to
    agree before a consultation is charged.
    """

    def _swapped(self, tmp_path, capsys, monkeypatch, header_says):
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        cand = _env_file(tmp_path, "cand.json", _CORPUS_TWO)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "toc")
        split_path = _write(tmp_path, "split.json", split)
        real = oa._corpus_header
        monkeypatch.setattr(
            oa, "_corpus_header",
            lambda p: header_says if Path(p) == Path(cand) else real(p),
        )
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )

    def test_a_file_that_changes_after_the_preflight_is_refused(
        self, tmp_path, capsys, monkeypatch
    ):
        code, out = self._swapped(tmp_path, capsys, monkeypatch, _CORPUS_ONE)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False

    def test_the_recheck_refuses_before_the_consultation_is_charged(
        self, tmp_path, capsys, monkeypatch
    ):
        """Round seventeen strengthened this.

        It read `sel_consultations`, which reports prior ledger spend and was
        therefore zero here whether or not this run charged. The claim worth
        making is that no ledger exists at all afterward.
        """
        _, out = self._swapped(tmp_path, capsys, monkeypatch, _CORPUS_ONE)
        assert out["consultations"] == 0
        record = json.loads((tmp_path / "split.json").read_text(encoding="utf-8"))
        assert not oa._ledger_path(oa._holdout_key(record)).exists()

    def test_an_honest_preflight_still_compares(self, tmp_path, capsys, monkeypatch):
        code, out = self._swapped(tmp_path, capsys, monkeypatch, _CORPUS_TWO)
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert "corpus" in out["reason"]


class TestASplitCannotCarryACorpusThatIsNotOne:
    """Round sixteen: the pin comes off a caller-supplied file unvalidated."""

    def _gate_with_pin(self, tmp_path, capsys, pin):
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "bad-pin")
        split["corpus"] = pin
        split_path = _write(tmp_path, "split.json", split)
        return _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )

    @pytest.mark.parametrize("pin", [[], {}, 7, True, "nope", _CORPUS_ONE.upper()])
    def test_a_pin_that_is_not_a_digest_is_a_config_error(self, tmp_path, capsys, pin):
        code, out = self._gate_with_pin(tmp_path, capsys, pin)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert "corpus" in out["error"]

    def test_an_unhashable_pin_does_not_reach_the_set(self, tmp_path, capsys):
        """A list pin used to raise `TypeError` out of the conflict rule."""
        code, out = self._gate_with_pin(tmp_path, capsys, [])
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_a_null_pin_is_still_legal(self, tmp_path, capsys):
        code, out = self._gate_with_pin(tmp_path, capsys, None)
        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert out["compared"] is False

    def test_a_real_digest_pin_is_accepted(self, tmp_path, capsys):
        code, out = self._gate_with_pin(tmp_path, capsys, _CORPUS_ONE)
        assert out.get("corpus_pinned") is True


class TestAParserFailureNeverPreemptsTheLedger:
    """Round sixteen: `_read_json` promised one exception family and had two."""

    def _deep(self, tmp_path, name):
        path = tmp_path / name
        path.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
        return path

    def test_deeply_nested_json_is_a_config_error_not_a_traceback(
        self, tmp_path, capsys
    ):
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "deep")
        split_path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc,
            "--candidate", self._deep(tmp_path, "cand.json"),
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_an_exhausted_budget_still_answers_first(self, tmp_path, capsys):
        """The defect: a parse crash in the preflight outranked the ledger."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "deep2")
        split_path = _write(tmp_path, "split.json", split)
        _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=1,
        )
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc,
            "--candidate", self._deep(tmp_path, "cand.json"),
            "--split", split_path, cap=1,
        )
        assert code == EXIT_LOGIC
        assert "consultation" in out["reason"]
        assert out["compared"] is False


class TestEveryWriteFailurePrintsOneJsonDocument:
    """Round seventeen: `mkstemp` sat outside the block that wraps `OSError`.

    `_write_atomic` carries two promises. The artifact is never left half
    written, and a failure prints one JSON document like every other failure
    the CLI reports. The temp file was created before the `try` that turns
    `OSError` into `ConfigError`, so a missing or unwritable parent escaped as
    a raw traceback and a caller parsing stdout as JSON crashed on it.
    """

    def _tasks(self, tmp_path, n: int = 30):
        path = tmp_path / "tasks.txt"
        path.write_text("\n".join(f"t{i}" for i in range(n)) + "\n", encoding="utf-8")
        return path

    def _split_into(self, tmp_path, capsys, out):
        return _run(
            capsys, "split", "--tasks", self._tasks(tmp_path), "--seed", "w", "--out", out
        )

    def test_a_missing_parent_directory_is_a_config_error(self, tmp_path, capsys):
        code, out = self._split_into(tmp_path, capsys, tmp_path / "absent" / "split.json")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_message_names_the_write_and_the_path(self, tmp_path, capsys):
        target = tmp_path / "absent" / "split.json"
        _, out = self._split_into(tmp_path, capsys, target)
        assert "could not write" in out["error"]
        assert str(target) in out["error"]

    def test_a_parent_that_refuses_the_temp_file_is_a_config_error(
        self, tmp_path, capsys, monkeypatch
    ):
        def _refuse(*_args, **_kwargs):
            raise OSError(13, "permission denied")

        monkeypatch.setattr(oa.tempfile, "mkstemp", _refuse)
        code, out = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_a_non_io_failure_from_mkstemp_still_escapes(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative control: the new arm must not swallow unrelated failures."""

        def _boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(oa.tempfile, "mkstemp", _boom)
        with pytest.raises(RuntimeError, match="boom"):
            self._split_into(tmp_path, capsys, tmp_path / "split.json")

    def test_a_writable_parent_still_writes_the_split(self, tmp_path, capsys):
        """Positive control: the wrapping did not break the normal path."""
        target = tmp_path / "split.json"
        code, _ = self._split_into(tmp_path, capsys, target)
        assert code == EXIT_OK
        assert json.loads(target.read_text(encoding="utf-8"))["sel"]


class TestABinaryFileIsAConfigErrorWhereverItIsRead:
    """Round seventeen: `_read_json` let `UnicodeDecodeError` through by name.

    `_read_text` wraps it because it subclasses `ValueError` rather than
    `OSError`, so the `OSError` arm never caught it. `_read_json` reads text
    the same way and did not, so one reader called a binary artifact a config
    problem and the other reported the decoder's own class instead. The error
    document is part of the contract, so the two readers have to agree.
    """

    def _score_from(self, tmp_path, capsys, name, blob: bytes):
        tasks = tmp_path / "tasks.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(30)) + "\n", encoding="utf-8")
        split_path = tmp_path / "split.json"
        _run(capsys, "split", "--tasks", tasks, "--seed", "u", "--out", split_path)
        path = tmp_path / name
        path.write_bytes(blob)
        return _run(capsys, "score", "--results", path, "--split", split_path)

    def test_invalid_utf8_is_a_config_error(self, tmp_path, capsys):
        code, out = self._score_from(tmp_path, capsys, "bad.json", b"\xff\xfe\x00{")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_message_names_utf8_the_way_the_text_reader_does(self, tmp_path, capsys):
        _, out = self._score_from(tmp_path, capsys, "bad.json", b"\xff\xfe\x00{")
        assert "is not valid UTF-8" in out["error"]

    def test_valid_utf8_that_is_not_json_still_reports_json(self, tmp_path, capsys):
        """Edge: the two failures are different and must stay distinguishable."""
        _, out = self._score_from(tmp_path, capsys, "bad.json", b"not json at all")
        assert out["type"] == "ConfigError"
        assert "is not valid JSON" in out["error"]

    def test_valid_utf8_json_still_parses(self, tmp_path, capsys):
        """Positive control."""
        results = {f"t{i}": True for i in range(30)}
        blob = json.dumps(_enveloped(None, results, name="good.json")).encode("utf-8")
        code, _ = self._score_from(tmp_path, capsys, "good.json", blob)
        assert code == EXIT_OK


class TestBothCorpusChecksSpeakWithOneVoice:
    """Round seventeen: the recheck carried a key the preflight did not.

    `_corpus_refusal` says in its own docstring that two call sites phrasing
    the same refusal would let the caller tell which read caught it. The
    recheck then emitted `_corpus_refusal() | {"sel_consultations": spent}`,
    so the key set alone answered the question the docstring said it must not.
    Reporting the ledger there was also the wrong fact to add: `_guard` runs
    first, so budget is never exhausted by the time the recheck fires, and the
    only honest number both call sites share is that this run charged nothing.
    """

    def _pair(self, tmp_path, capsys):
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        cand = _env_file(tmp_path, "cand.json", _CORPUS_TWO)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "voice")
        split_path = _write(tmp_path, "split.json", split)
        return ("--incumbent", inc, "--candidate", cand, "--split", split_path)

    def _both(self, tmp_path, capsys, monkeypatch):
        argv = self._pair(tmp_path, capsys)
        _, early = _run_gate(capsys, tmp_path, *argv, cap=5)
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: _CORPUS_ONE)
        _, late = _run_gate(capsys, tmp_path, *argv, cap=5)
        return early, late

    def test_the_two_refusals_are_one_document(self, tmp_path, capsys, monkeypatch):
        early, late = self._both(tmp_path, capsys, monkeypatch)
        assert early == late

    def test_neither_refusal_reports_the_ledger(self, tmp_path, capsys, monkeypatch):
        early, late = self._both(tmp_path, capsys, monkeypatch)
        assert "sel_consultations" not in early
        assert "sel_consultations" not in late

    def test_both_report_that_this_run_charged_nothing(
        self, tmp_path, capsys, monkeypatch
    ):
        early, late = self._both(tmp_path, capsys, monkeypatch)
        assert early["consultations"] == 0
        assert late["consultations"] == 0

    def test_the_patched_run_really_reaches_the_second_check(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative control: with an agreeing preflight the bodies must be read.

        Without this the comparison above could be two preflight refusals, and
        the identity it asserts would hold for a reason that proves nothing.
        """
        argv = self._pair(tmp_path, capsys)
        seen: list[Path] = []
        real = oa._read_results
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: _CORPUS_ONE)
        monkeypatch.setattr(
            oa, "_read_results", lambda p: (seen.append(Path(p)), real(p))[1]
        )
        code, out = _run_gate(capsys, tmp_path, *argv, cap=5)
        assert len(seen) == 2
        assert code == EXIT_LOGIC
        assert out["compared"] is False


class TestEveryVerdictNamesWhatThisRunCharged:
    """Round nineteen: `consultations` was missing exactly where it was not zero.

    `_corpus_refusal` established the contract in its own docstring: the
    honest claim a refusal can make is that this run charged nothing, reported
    as `consultations: 0`. The charged paths never reported the other half.
    A caller reading `consultations` got 0 on every refusal and a missing key
    on every verdict, so the one field that answers "what did this cost me"
    was absent from the only outcomes with a nonzero answer.

    `sel_consultations` is the running total against the held-out group after
    this run's charge, which is why the guard refusal reports `spent` and the
    verdict reports `spent + 1`: nothing is charged before the guard. The
    ledger-mismatch refusal reported a literal 0, which is a running total it
    had no basis for. The count is parsed before the mismatch is raised, so
    the number exists, but on a key mismatch it belongs to a different group
    and naming it would leak that group's history through a refusal that
    deliberately withholds the group itself. Absence is the honest report.
    """

    def _pair(self, tmp_path, capsys, cand_all_true=True):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "n19")
        split_path = _write(tmp_path, "split.json", split)
        cand = _write(tmp_path, "cand.json", {f"t{i}": cand_all_true for i in range(12)})
        return ("--incumbent", inc, "--candidate", cand, "--split", split_path)

    def test_a_charged_verdict_reports_one(self, tmp_path, capsys):
        argv = self._pair(tmp_path, capsys)
        _, out = _run_gate(capsys, tmp_path, *argv, cap=5)
        assert out["consultations"] == 1

    def test_a_charged_verdict_still_reports_the_running_total(self, tmp_path, capsys):
        """The running total includes this run's charge, so a first gate reads 1."""
        argv = self._pair(tmp_path, capsys)
        _, out = _run_gate(capsys, tmp_path, *argv, cap=5)
        assert out["sel_consultations"] == 1

    def test_the_two_counts_are_different_numbers_on_a_later_run(
        self, tmp_path, capsys
    ):
        """Edge: with prior spend the charge stays 1 while the total moves.

        Asserting both on a first run cannot distinguish them, because the
        charge and the total are both 1 there.
        """
        argv = self._pair(tmp_path, capsys)
        _, out = _run_gate(capsys, tmp_path, *argv, spent=3, cap=9)
        assert out["consultations"] == 1
        assert out["sel_consultations"] == 4

    def test_a_whole_universe_coverage_refusal_reports_no_holdout_charge(
        self, tmp_path, capsys
    ):
        """Whole-universe coverage rejects before the held-out group is read."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(12)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "n19c")
        split_path = _write(tmp_path, "split.json", split)
        cand = _write(tmp_path, "cand.json", {"t0": True})
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert out["consultations"] == 0

    def test_a_guard_refusal_reports_no_charge(self, tmp_path, capsys):
        """Negative: an exhausted budget spends nothing, so the charge is zero."""
        argv = self._pair(tmp_path, capsys)
        code, out = _run_gate(capsys, tmp_path, *argv, spent=2, cap=2)
        assert code == EXIT_LOGIC
        assert out["consultations"] == 0
        assert out["sel_consultations"] == 2

    def test_a_ledger_mismatch_claims_no_running_total(self, tmp_path, capsys):
        """A cap it cannot honour is not a licence to report a total of zero."""
        argv = self._pair(tmp_path, capsys)
        _run_gate(capsys, tmp_path, *argv, spent=2, cap=9)
        code, out = _run_gate(capsys, tmp_path, *argv, cap=4)
        assert code == EXIT_LOGIC
        assert out["consultations"] == 0
        assert "sel_consultations" not in out

    def test_every_gate_outcome_names_the_charge(self, tmp_path, capsys):
        """One key set for the field that answers what this run cost.

        Four outcomes, reached by four different routes: a verdict, a charged
        coverage refusal, an uncharged guard refusal, and an uncharged drift
        refusal. Each is checked for the same key rather than for its own.
        """
        argv = self._pair(tmp_path, capsys)
        seen = [_run_gate(capsys, tmp_path, *argv, cap=5)[1]]
        seen.append(_run_gate(capsys, tmp_path, *argv, spent=2, cap=2)[1])

        drift_inc = _write(tmp_path, "d_inc.json", {f"t{i}": True for i in range(12)})
        _, split = _split(capsys, tmp_path, "--results", drift_inc, "--seed", "n19d")
        split["sel"] = list(split["sel"])[:-1]
        drift_split = _write(tmp_path, "d_split.json", split)
        drift_cand = _write(tmp_path, "d_cand.json", {f"t{i}": True for i in range(12)})
        seen.append(
            _run_gate(
                capsys, tmp_path, "--incumbent", drift_inc, "--candidate", drift_cand,
                "--split", drift_split, cap=5,
            )[1]
        )
        assert [out.get("consultations", "MISSING") for out in seen] == [1, 0, 0]


class TestWhichRefusalsNameTheGroupTheyOpened:
    """Round twenty-seven: two more keys come and go, and no rule said so.

    `consultations` and `sel_consultations` each have a written presence rule
    and a test class of their own. `group` and `fingerprint` vary the same way
    with neither, which is why a reviewer reading the payloads alone called the
    schema inconsistent and proposed filling every refusal in.

    The rule they follow: both keys name the held-out group whose ledger this
    run opened. They appear on the documents `_gate_decision` emits under
    `_ledger_held`, and are absent from the refusals `cmd_gate` reaches before
    it takes that lock. The corpus refusal is the one exception, because it is
    a single document emitted from both sides of the lock and can carry only
    what the earlier side is able to say.

    Filling them in is wrong twice over. On a drifted split the recorded
    fingerprint is the value the drift check has just disproved, so echoing it
    would report a fact the same document denies. On the corpus refusal a
    second key set would answer which of the two reads caught the disagreement,
    which is the question the one-voice class above exists to keep unanswered.
    """

    def _pair(self, tmp_path, capsys, seed):
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", seed)
        return inc, cand, split

    def test_a_verdict_reached_under_the_lock_names_the_group(self, tmp_path, capsys):
        """Positive control: the compared path carries both keys."""
        inc, cand, split = self._pair(tmp_path, capsys, "g1")
        path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", path, cap=5,
        )
        assert out["compared"] is True
        assert out["group"] == oa._GATE_GROUP
        assert out["fingerprint"] == split["fingerprint"]

    def test_a_refusal_reached_under_the_lock_still_names_the_group(
        self, tmp_path, capsys
    ):
        """An exhausted budget refuses inside the lock, so the group is known."""
        inc, cand, split = self._pair(tmp_path, capsys, "g2")
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", path, "--max-consultations", "3", spent=3,
        )
        assert code == EXIT_LOGIC
        assert out["compared"] is False
        assert out["group"] == oa._GATE_GROUP
        assert out["fingerprint"] == split["fingerprint"]

    def test_a_drifted_split_names_no_group_because_none_was_opened(
        self, tmp_path, capsys
    ):
        """Negative: the drift refusal is decided before the lock is taken."""
        inc, cand, split = self._pair(tmp_path, capsys, "g3")
        split["fingerprint"] = "0" * 64
        path = _write(tmp_path, "split.json", split)
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", path, cap=5,
        )
        assert code == EXIT_LOGIC
        assert "group" not in out
        assert "fingerprint" not in out

    def test_the_refusal_does_not_echo_the_fingerprint_the_check_disproved(
        self, tmp_path, capsys
    ):
        """Edge: the recorded value is exactly what drift means is wrong."""
        inc, cand, split = self._pair(tmp_path, capsys, "g4")
        split["fingerprint"] = "0" * 64
        path = _write(tmp_path, "split.json", split)
        _, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", path, cap=5,
        )
        assert "0" * 64 not in json.dumps(out)

    def test_the_corpus_refusal_names_no_group_from_either_side(
        self, tmp_path, capsys, monkeypatch
    ):
        """Edge: the recheck runs under the lock and still carries neither.

        This is the exception the rule needs, and it is not an oversight. Both
        call sites emit one document, so the later one carries only what the
        earlier one can say.
        """
        inc = _env_file(tmp_path, "inc.json", _CORPUS_ONE)
        cand = _env_file(tmp_path, "cand.json", _CORPUS_TWO)
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "g5")
        path = _write(tmp_path, "split.json", split)
        argv = ("--incumbent", inc, "--candidate", cand, "--split", path)
        _, early = _run_gate(capsys, tmp_path, *argv, cap=5)
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: _CORPUS_ONE)
        _, late = _run_gate(capsys, tmp_path, *argv, cap=5)
        for out in (early, late):
            assert "group" not in out
            assert "fingerprint" not in out
        assert early == late


class TestAFailedCleanupDoesNotReplaceTheFailureItCleansUpAfter:
    """Round nineteen: the unlink in the handler could raise out of the handler.

    Round seventeen moved `mkstemp` inside the guarded block so a write
    failure printed one JSON document instead of a traceback. The cleanup
    itself stayed unguarded. An `OSError` from `tmp.unlink` inside the
    `except` arm propagates in place of the exception being handled, so the
    caller gets a traceback again, and it names the unlink rather than the
    write that actually failed. A parent whose permissions are revoked after
    `mkstemp` fails both calls, which is the pair that produces it.

    The comment in that handler also claimed the descriptor is closed when
    `os.fdopen` fails. It was not: nothing called `os.close`, so that path
    leaked a descriptor while the comment said it did not.
    """

    def _tasks(self, tmp_path):
        path = tmp_path / "tasks.txt"
        path.write_text("\n".join(f"t{i}" for i in range(30)) + "\n", encoding="utf-8")
        return path

    def _split_into(self, tmp_path, capsys, out):
        return _run(
            capsys, "split", "--tasks", self._tasks(tmp_path), "--seed", "n19", "--out", out
        )

    def _both_fail(self, monkeypatch):
        def _no_replace(*_args, **_kwargs):
            raise OSError(13, "replace denied")

        def _no_unlink(*_args, **_kwargs):
            raise OSError(13, "unlink denied")

        monkeypatch.setattr(oa.os, "replace", _no_replace)
        monkeypatch.setattr(oa.Path, "unlink", _no_unlink)

    def test_a_failed_cleanup_is_still_one_json_document(
        self, tmp_path, capsys, monkeypatch
    ):
        self._both_fail(monkeypatch)
        code, out = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_message_names_the_write_not_the_cleanup(
        self, tmp_path, capsys, monkeypatch
    ):
        """The failure a caller must act on is the write, not the tidy-up."""
        self._both_fail(monkeypatch)
        _, out = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert "replace denied" in out["error"]
        assert "unlink denied" not in out["error"]

    def test_a_cleanup_that_works_is_unchanged(self, tmp_path, capsys, monkeypatch):
        """Positive control: the ordinary failure path still reports the write."""

        def _no_replace(*_args, **_kwargs):
            raise OSError(13, "replace denied")

        monkeypatch.setattr(oa.os, "replace", _no_replace)
        code, out = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert "replace denied" in out["error"]

    def test_a_non_io_cleanup_failure_still_escapes(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative control: the new arm must not swallow a real bug."""

        def _no_replace(*_args, **_kwargs):
            raise OSError(13, "replace denied")

        def _boom(*_args, **_kwargs):
            raise RuntimeError("cleanup boom")

        monkeypatch.setattr(oa.os, "replace", _no_replace)
        monkeypatch.setattr(oa.Path, "unlink", _boom)
        with pytest.raises(RuntimeError, match="cleanup boom"):
            self._split_into(tmp_path, capsys, tmp_path / "split.json")

    def test_a_descriptor_is_closed_when_fdopen_fails(
        self, tmp_path, capsys, monkeypatch
    ):
        """Edge: the one path where the with-block never takes the descriptor."""
        closed: list[int] = []
        real_close = oa.os.close

        def _no_fdopen(fd, *_args, **_kwargs):
            raise OSError(13, "fdopen denied")

        monkeypatch.setattr(oa.os, "fdopen", _no_fdopen)
        monkeypatch.setattr(
            oa.os, "close", lambda fd: (closed.append(fd), real_close(fd))[1]
        )
        code, _ = self._split_into(tmp_path, capsys, tmp_path / "split.json")
        assert code == EXIT_CONFIG
        assert closed


class TestTheLedgerRenameIsMadeDurableNotJustTheBytes:
    """Round nineteen: `fsync` on the file does not persist the rename.

    `_write_atomic` fsyncs the temporary file and then calls `os.replace`.
    The bytes are durable; the directory entry that points at them is not.
    A host that loses power after the gate reports a charged consultation can
    come back with the rename undone, which restores the previous ledger and
    hands the caller the consultation again. The whole point of charging
    before scoring is that a crash must not return a free look, so a charge
    that a crash can erase defeats the ordering it was written to protect.
    """

    def _dir_fsyncs(self, monkeypatch):
        kinds: list[bool] = []
        real = oa.os.fsync

        def _record(fd):
            kinds.append(stat.S_ISDIR(os.fstat(fd).st_mode))
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _record)
        return kinds

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_parent_directory_is_fsynced(self, tmp_path, monkeypatch):
        kinds = self._dir_fsyncs(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert any(kinds)

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_file_is_still_fsynced_too(self, tmp_path, monkeypatch):
        """Positive control: the directory fsync must not have replaced it."""
        kinds = self._dir_fsyncs(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert not all(kinds)

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_directory_fsync_follows_the_rename(self, tmp_path, monkeypatch):
        """Edge: fsyncing the directory before the rename persists nothing."""
        order: list[str] = []
        real_fsync = oa.os.fsync
        real_replace = oa.os.replace

        def _fsync(fd):
            order.append("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
            return real_fsync(fd)

        def _replace(src, dst):
            order.append("replace")
            return real_replace(src, dst)

        monkeypatch.setattr(oa.os, "fsync", _fsync)
        monkeypatch.setattr(oa.os, "replace", _replace)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert order.index("dir") > order.index("replace")

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_directory_that_refuses_fsync_does_not_undo_the_write(
        self, tmp_path, capsys, monkeypatch
    ):
        """The bytes and the rename already landed, so the file must stay.

        Round twenty: the first version of this guard raised ConfigError here.
        That made a durability fix into an availability regression. os.replace
        was previously the last operation in the function, so every failure
        path preceded the rename and left the destination untouched. Adding a
        step after the rename created the first failure that can fire once the
        write has already succeeded, and in the ledger's case once a
        consultation has already been charged.
        """
        real = oa.os.fsync
        target = tmp_path / "ledger.json"
        target.write_text("{}\n", encoding="utf-8")

        def _refuse(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        oa._write_atomic(target, '{"spent": 1}\n')
        assert target.read_text(encoding="utf-8") == '{"spent": 1}\n'

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_directory_that_refuses_fsync_does_not_abort_the_caller(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative: aborting after the charge costs a look and returns none.

        _write_atomic writes the ledger before the gate scores. Raising after
        os.replace succeeds means the consultation is spent and the caller
        gets an exception instead of a verdict, which is the one trade the
        charge-before-scoring order exists to avoid in the other direction.
        """
        real = oa.os.fsync

        def _refuse(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_lost_guarantee_is_reported_on_stderr(self, tmp_path, capsys, monkeypatch):
        """Not raising is not the same as not saying.

        Silently continuing would leave the caller believing a durability
        guarantee that did not hold, which is the shape this file keeps
        correcting. stderr is the right channel: the exit-code contract
        reserves stdout for the one JSON document a caller parses.
        """
        real = oa.os.fsync

        def _refuse(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        captured = capsys.readouterr()
        assert "durab" in captured.err.lower()
        assert captured.out == ""

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_warning_does_not_claim_the_write_failed(self, tmp_path, capsys, monkeypatch):
        """Negative: the write succeeded, so saying otherwise is a false claim."""
        real = oa.os.fsync

        def _refuse(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return real(fd)

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert "could not write" not in capsys.readouterr().err

    def test_a_file_fsync_failure_still_refuses(self, tmp_path, capsys, monkeypatch):
        """Control: before the rename nothing landed, so it is still an error.

        The distinction is what makes the change above a correction rather
        than a loosening. A failure that precedes os.replace leaves the
        destination untouched, so refusing is both honest and free.
        """

        def _refuse(fd):
            raise OSError(5, "file fsync denied")

        monkeypatch.setattr(oa.os, "fsync", _refuse)
        with pytest.raises(oa.ConfigError, match="could not write"):
            oa._write_atomic(tmp_path / "ledger.json", "{}\n")


class TestARefusalDoesNotAdviseAnInvocationTheParserRejects:
    """Round twenty: the budget refusal named a command that does not exist.

    The exhausted-budget message told the operator to "report on the test
    group". `score --group` accepts only "opt", and by design: the README
    lists "score --group opt refuses to read any other group" as a property
    the mechanism enforces whether or not the optimizer cooperates. Widening
    the choice to reach the test group would hand the loop unmetered reads of
    the one group held back as a final unbiased look, which is the opposite of
    what the advice was reaching for.

    So the advice is removed rather than implemented. The wording itself is
    asserted in tests/test_eval_optimizer_core.py, next to the function that
    produces it; what belongs here is the boundary that made the advice false.
    """

    def test_the_parser_still_refuses_the_group_the_message_named(self, capsys, tmp_path):
        """Control: the enforced boundary is unchanged by this fix."""
        with pytest.raises(SystemExit) as excinfo:
            oa.main(["score", "--kind", "rule", "--input", "x.json", "--group", "test"])
        assert excinfo.value.code == EXIT_CONFIG
        assert "invalid choice" in capsys.readouterr().err


class TestADiagnosticNeitherLeaksNorFails:
    """Round twenty-one: a warning is still a way out of the process.

    Round twenty stopped the directory-fsync failure from aborting a caller
    whose consultation was already charged, by printing instead of raising.
    That moved the failure rather than removing it. `print` itself raises when
    stderr is closed or broken, and `_write_atomic` converts any `OSError` from
    that region into a `ConfigError`, so the abort round twenty removed came
    straight back one layer down.

    The leak is the same shape. `_digest_scrubbed` is a seam over raised
    exceptions, and its own docstring gives the reason: "a wrapper covers the
    paths someone remembered; a seam covers the one added next year." A warning
    that prints and returns never reaches that seam, so the new diagnostic
    named a ledger directory in full, and `$EVAL_LEDGER_DIR` can carry the
    held-out digest. The tenth review already found and fixed exactly that at
    the lock-cleanup warning; this reintroduced it two rounds later at a site
    the seam does not cover.

    Both are one rule, and it was written down zero times: a diagnostic must
    not leak what raised diagnostics redact, and must not fail where the code
    it reports on already succeeded.
    """

    @staticmethod
    def _stderr_that_refuses(monkeypatch):
        class _Closed:
            def write(self, _text):
                raise OSError(32, "stderr closed")

            def flush(self):
                pass

        monkeypatch.setattr(oa.sys, "stderr", _Closed())

    @staticmethod
    def _fsync_refuses(monkeypatch):
        def _fsync(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(13, "dir fsync denied")
            return None

        monkeypatch.setattr(oa.os, "fsync", _fsync)

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_broken_stderr_does_not_abort_the_write_that_succeeded(
        self, tmp_path, monkeypatch
    ):
        """The exact regression round twenty fixed, one layer down."""
        self._fsync_refuses(monkeypatch)
        self._stderr_that_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", '{"n": 1}\n')
        assert (tmp_path / "ledger.json").read_text(encoding="utf-8") == '{"n": 1}\n'

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_broken_stderr_is_not_reported_as_a_failed_write(
        self, tmp_path, monkeypatch
    ):
        """`_write_atomic` turns any OSError from that region into ConfigError."""
        self._fsync_refuses(monkeypatch)
        self._stderr_that_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_warning_withholds_a_digest_bearing_directory(
        self, tmp_path, capsys, monkeypatch
    ):
        """`$EVAL_LEDGER_DIR` can name the held-out digest; the tenth review
        found the lock warning printing one and fixed it there only."""
        key = "b" * 64
        root = tmp_path / f"ledger-{key}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        with oa._digest_scrubbed(key):
            oa._write_atomic(root / "ledger.json", "{}\n")
        err = capsys.readouterr().err
        assert key not in err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_withheld_digest_is_replaced_not_dropped(
        self, tmp_path, capsys, monkeypatch
    ):
        """An error naming nothing is a worse trade than the leak, so the
        placeholder must survive where the digest was."""
        key = "c" * 64
        root = tmp_path / f"ledger-{key}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        with oa._digest_scrubbed(key):
            oa._write_atomic(root / "ledger.json", "{}\n")
        err = capsys.readouterr().err
        assert oa._HELD_OUT_PLACEHOLDER in err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_an_uppercase_digest_is_withheld_too(self, tmp_path, capsys, monkeypatch):
        """Edge: the same case-folding the twelfth review had to add to `_scrub`."""
        key = "d" * 64
        root = tmp_path / f"ledger-{key.upper()}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        with oa._digest_scrubbed(key):
            oa._write_atomic(root / "ledger.json", "{}\n")
        err = capsys.readouterr().err
        assert key.upper() not in err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_warning_still_reaches_stderr_outside_a_scrub(
        self, tmp_path, capsys, monkeypatch
    ):
        """Positive control: withholding must not become silence."""
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert "durab" in capsys.readouterr().err.lower()

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_scrub_does_not_outlive_its_block(self, tmp_path, capsys, monkeypatch):
        """Negative control: a key left active would redact a later run's
        unrelated output, and hex is common enough in these paths to matter."""
        key = "e" * 64
        with oa._digest_scrubbed(key):
            pass
        root = tmp_path / f"dir-{key}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(root / "ledger.json", "{}\n")
        assert key in capsys.readouterr().err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_the_scrub_is_cleared_when_its_block_raises(
        self, tmp_path, capsys, monkeypatch
    ):
        """Edge: the seam exists to catch exceptions, so the unwinding path is
        the one that must restore state, not the falling-off-the-end path."""
        key = "f" * 64
        with pytest.raises(oa.ConfigError):
            with oa._digest_scrubbed(key):
                raise OSError(5, "nothing to do with the digest")
        root = tmp_path / f"dir-{key}"
        root.mkdir()
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(root / "ledger.json", "{}\n")
        assert key in capsys.readouterr().err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_stream_closed_for_real_does_not_abort_the_write(self, tmp_path, monkeypatch):
        """A closed Python stream raises ValueError, not OSError.

        Round twenty-one demonstrated the crash with a double whose `write`
        raised `OSError(32)`, and the guard was written to the demonstration
        rather than to the class. A genuinely closed stream raises
        `ValueError: I/O operation on closed file`, which walks straight
        through an `OSError`-only suppression into the same abort.
        """
        stream = io.StringIO()
        stream.close()
        monkeypatch.setattr(sys, "stderr", stream)
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", '{"n": 1}\n')
        assert json.loads((tmp_path / "ledger.json").read_text()) == {"n": 1}

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_stderr_that_is_absent_is_treated_like_one_that_is_none(
        self, tmp_path, monkeypatch
    ):
        """Edge: `sys.stderr` can be missing, not only `None` or broken.

        The docstring claimed only the stream check sat outside the guard. The
        stream read sat outside it too, and `sys.stderr` is an attribute lookup
        that raises `AttributeError` when an embedding harness deletes it. That
        raise is the abort rounds twenty through twenty-three were each spent
        removing, arriving through the one expression none of them guarded.
        Reading it totally routes the missing case into the `None` branch that
        already existed, so the rule is enforced without a second one.
        """
        monkeypatch.delattr(sys, "stderr")
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", '{"n": 1}\n')
        assert json.loads((tmp_path / "ledger.json").read_text()) == {"n": 1}

    def test_the_scrub_key_reads_as_none_when_no_scrub_is_active(self):
        """The default is what lets an unscrubbed warning still get printed.

        `_warn` reads the key under the guard, so a raise here costs the
        diagnostic rather than the caller. It should cost neither. The
        `ContextVar` carries `default=None`, and one declared without a
        default raises `LookupError` from `get()` outside a set scope, which
        the guard would swallow into silence. The other tests that fail
        without it report a missing warning, which points at the stream rather
        than at the declaration. This one names the declaration.
        """
        assert oa._ACTIVE_HOLDOUT_KEY.get() is None

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_a_warning_never_lands_on_the_stream_carrying_the_verdict(
        self, tmp_path, capsys, monkeypatch
    ):
        """`print(file=None)` writes to stdout, and stdout carries the payload.

        `sys.stderr` is `None` under a pythonw-style launcher and after a
        harness detaches it. Passing that through as the `file` argument does
        not silence the warning, it redirects it onto the one stream whose
        every byte the caller parses as JSON.
        """
        monkeypatch.setattr(sys, "stderr", None)
        self._fsync_refuses(monkeypatch)
        oa._write_atomic(tmp_path / "ledger.json", "{}\n")
        assert capsys.readouterr().out == ""

    def test_the_lock_cleanup_warning_withholds_the_digest(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative: the leak claim said 'both sites' and tested one.

        Round twenty-one reported it had covered the leak and the crash at
        both warning sites. It had not; all eight tests drove `_write_atomic`.
        A twenty-second review read the tests rather than the prose.
        """
        monkeypatch.setattr(oa, "_ledger_root", lambda: tmp_path)
        key = "d" * 64

        def _refuse(self, **kwargs):
            raise OSError(13, f"cannot unlink {self}")

        with oa._ledger_held(key):
            monkeypatch.setattr(Path, "unlink", _refuse)
        monkeypatch.undo()
        err = capsys.readouterr().err
        assert key not in err
        assert oa._HELD_OUT_PLACEHOLDER in err

    @pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a directory fd")
    def test_an_inner_scrub_restores_the_outer_key_and_not_none(
        self, tmp_path, capsys, monkeypatch
    ):
        """Edge: the claim was 'key restore under nesting', which had no test.

        `_ledger_held` scrubs for the whole lock lifecycle and the contention
        branch nests a second scrub inside it, so nesting is not hypothetical
        here. Clearing on the inner exit rather than restoring the outer key
        would unprotect the rest of the outer block, and every existing test
        would still pass because none of them nests.
        """
        outer = "a" * 64
        inner = "b" * 64
        with oa._digest_scrubbed(outer):
            with oa._digest_scrubbed(inner):
                pass
            root = tmp_path / f"dir-{outer}"
            root.mkdir()
            self._fsync_refuses(monkeypatch)
            oa._write_atomic(root / "ledger.json", "{}\n")
        err = capsys.readouterr().err
        assert outer not in err
        assert oa._HELD_OUT_PLACEHOLDER in err

    def test_a_redaction_that_raises_costs_the_message_and_not_the_caller(
        self, capsys, monkeypatch
    ):
        """Negative: the guard has to cover the redaction, not just the write.

        The first draft of the three-rule docstring asserted the opposite,
        that `_scrub` belonged outside the suppression so a broken redactor
        would fail loudly. Writing that sentence down is what disproved it. A
        redaction that raises leaves the message unprinted either way, because
        the exception skips the `print` with `message` still bound to its
        unscrubbed value. So excluding it buys no leak protection at all and
        costs the caller the abort that rounds twenty through twenty-two were
        spent removing.
        """
        key = "e" * 64

        def _explode(text, holdout_key):
            raise RuntimeError("redactor is broken")

        monkeypatch.setattr(oa, "_scrub", _explode)
        with oa._digest_scrubbed(key):
            oa._warn(f"cannot sync {key}")
        captured = capsys.readouterr()
        assert captured.err == ""
        assert key not in captured.out

    def test_a_scrub_set_in_another_context_cannot_overwrite_this_one(self):
        """Edge: two live scopes at once, which one shared global cannot hold.

        A twenty-second review ran two scopes concurrently against the module
        global this replaced and got a key disclosed under the wrong scope and
        a stale key left active after both had exited.

        No threads here, deliberately. The first draft of this test used two
        and passed against the very global it exists to rule out: the barrier
        releases both, but they still run one at a time, and the second thread
        finished its restore before the first resumed, so each read its own
        key by scheduling luck. A test that passes against the mutation is
        worth less than no test, because it also reports as covered.
        `copy_context` asks the same question with the scheduler removed.

        A twenty-third review pointed out that the first working version drove
        the `ContextVar` directly rather than this module's own scope, which
        tests the standard library instead of the seam. Its proposed repair,
        abandoning a generator mid-scope, does not discriminate as written:
        CPython drops the generator's last reference when the function
        returns, closes it, and runs the very `finally` the test needs left
        undone, so it passes against a module global too. Measured, not
        argued. Holding the reference is what abandons the scope for real.

        Closing it happens inside the same `Context` that opened it. Dropping
        the reference from out here instead leaves CPython to close the
        generator during collection, where `reset` is handed a token from a
        context it is no longer in, refuses it, and pytest reports the
        ignored exception as a warning. That is the limitation the `finally`
        in `_digest_scrubbed` discloses, reached from a test rather than from
        a call site.
        """
        outer = "a" * 64
        inner = "b" * 64
        abandoned = []

        def abandon_a_key_without_restoring_it():
            def never_finishes():
                with oa._digest_scrubbed(inner):
                    yield

            generator = never_finishes()
            abandoned.append(generator)
            next(generator)

        def close_what_was_abandoned():
            while abandoned:
                abandoned.pop().close()

        context = copy_context()
        try:
            with oa._digest_scrubbed(outer):
                context.run(abandon_a_key_without_restoring_it)
                assert oa._ACTIVE_HOLDOUT_KEY.get() == outer
            assert oa._ACTIVE_HOLDOUT_KEY.get() is None
        finally:
            context.run(close_what_was_abandoned)


class TestScoreWillNotVouchForASplitItCannotVerify:
    """Round twenty-eight: the one reader that skipped the check it enables.

    `_read_split` refuses a file missing any key needed to re-fingerprint it,
    and says why: "A split file that cannot be re-fingerprinted cannot be
    verified; re-run split." It then never verifies. `cmd_gate` covers that by
    calling `_split_drifted` on the line after the read. `cmd_score` did not,
    and it echoes `split["fingerprint"]` so the caller can forward it to the
    gate without opening the file.

    So a hand-edited split produced two score documents carrying one
    fingerprint and different numbers, and the fingerprint exists to make that
    impossible. Nothing unsound reached a verdict, because the gate runs the
    check and refuses. The cost was where the operator learns it: after
    however many scored candidates, rather than at the first read.

    `score` raises `ConfigError` rather than emitting a refusal document. A
    drifted file is the same class of problem as a malformed one, which that
    command already reports that way, and `score` has no decision vocabulary
    to refuse in. `gate` keeps emitting `decision: REJECT` because its caller
    is a loop that branches on the document.
    """

    def _drifted(self, tmp_path, capsys, mutate, name="drifted.json"):
        """Draw a real split, then edit it the way an operator would."""
        results = _write(tmp_path, "r.json", {f"t{i}": i % 2 == 0 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        mutate(split)
        path = tmp_path / name
        path.write_text(json.dumps(split), encoding="utf-8")
        return results, path

    def test_an_undrifted_split_still_scores_and_still_forwards(self, tmp_path, capsys):
        """Positive control: the check costs the honest caller nothing."""
        results, path = self._drifted(tmp_path, capsys, lambda s: None)
        code, out = _run(capsys, "score", "--results", results, "--split", path)
        recorded = json.loads(path.read_text(encoding="utf-8"))["fingerprint"]
        assert code == EXIT_OK
        assert out["fingerprint"] == recorded
        assert out["n"] == len(json.loads(path.read_text(encoding="utf-8"))["opt"])

    def test_a_dropped_task_refuses_instead_of_scoring(self, tmp_path, capsys):
        """Negative: the half of the check the fingerprint alone can make."""
        results, path = self._drifted(
            tmp_path, capsys, lambda s: s.__setitem__("opt", s["opt"][:-1])
        )
        code, out = _run(capsys, "score", "--results", results, "--split", path)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert "Re-split and re-baseline." in out["error"]

    def test_a_moved_task_refuses_though_the_fingerprint_matches(self, tmp_path, capsys):
        """Edge: the half only redrawing catches, reached through `score`.

        Moving a task between groups leaves the hashed union unchanged, so the
        recorded fingerprint still verifies. Only redrawing the split from the
        recorded inputs disagrees. This pins that `score` gets both halves of
        `_split_drifted` rather than the cheap one.
        """
        def move(split):
            split["sel"] = [*split["sel"], split["opt"][0]]
            split["opt"] = split["opt"][1:]

        results, path = self._drifted(tmp_path, capsys, move)
        moved = json.loads(path.read_text(encoding="utf-8"))
        tasks = [t for group in ("opt", "sel", "test") for t in moved[group]]
        assert sorted(tasks) == sorted(set(tasks)) and len(tasks) == 10
        code, out = _run(capsys, "score", "--results", results, "--split", path)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_refusal_publishes_no_number_the_caller_could_bank(self, tmp_path, capsys):
        """Edge: a refusal that still printed a score would be worse than none.

        The whole cost of the defect was a number the caller could mistake for
        a baseline, so the repair is not allowed to keep printing one.
        """
        results, path = self._drifted(
            tmp_path, capsys, lambda s: s.__setitem__("opt", s["opt"][:-1])
        )
        _, out = _run(capsys, "score", "--results", results, "--split", path)
        assert "score" not in out
        assert "fingerprint" not in out
        assert "n" not in out
        assert sorted(out) == ["error", "type"]

    def test_score_and_gate_refuse_a_drifted_split_in_one_vocabulary(self, tmp_path, capsys):
        """Edge: two commands, one diagnosis, so the operator reads it once."""
        results, path = self._drifted(
            tmp_path, capsys, lambda s: s.__setitem__("opt", s["opt"][:-1])
        )
        score_code, scored = _run(capsys, "score", "--results", results,
                                  "--split", path)
        gate_code, gated = _run_gate(
            capsys, tmp_path, "--incumbent", results, "--candidate", results,
            "--split", path,
        )
        assert score_code == EXIT_CONFIG and gate_code == EXIT_LOGIC
        remedy = "Re-split and re-baseline."
        assert remedy in scored["error"] and remedy in gated["reason"]
        assert gated["decision"] == "REJECT"


class TestTheDriftGuardCatchesWhatItsExceptClauseNames:
    """Round twenty-nine: a guard defeated one line past its own scope.

    `_split_drifted` wraps its redraw in `except (TypeError, ValueError)` and
    turns either into `ConfigError`, so the author had already decided that a
    split holding an unusable value is a config problem and not a crash. Two
    values escaped that decision anyway.

    The fingerprint comparison sits one line below the `except`, outside the
    block, so a fingerprint that is a list or a dict raises the very
    `TypeError` the clause names and escapes it on a technicality of scope.
    And `int(split["min_sel"])` on a JSON `Infinity` raises `OverflowError`,
    which is a sibling of `ValueError` rather than a subclass, so the clause
    misses it.

    `_read_split` had already fixed this exact bug once, in this exact
    function, for `corpus`: its comment records that an unvalidated list pin
    "raised `TypeError` out of a set comprehension". `fingerprint` is that
    field's twin and went unfixed, which is why the check now sits beside it.

    The harm has a low ceiling and it is worth naming. Both commands die
    before any comparison, so no unsound ACCEPT and no consultation charge is
    reachable. What the operator loses is the contract: a malformed split is
    supposed to exit 2 with a document naming the file, and instead the
    process exits 1 with a traceback, colliding with the exit code that means
    the candidate lost. A loop that branches on the exit code cannot tell a
    lost candidate from an unreadable file.

    Round twenty-eight widened this from one command to two. `cmd_gate` has
    called `_split_drifted` since the beginning; `cmd_score` began calling it
    in the commit before this one, so the fix is owed here.
    """

    def _mangled(self, tmp_path, capsys, key, value, name="mangled.json"):
        """Draw a real split, then put one unusable value in one field."""
        results = _write(tmp_path, "r.json", {f"t{i}": i % 2 == 0 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        split[key] = value
        path = tmp_path / name
        path.write_text(json.dumps(split), encoding="utf-8")
        return results, path

    def test_an_unusable_split_is_still_refused_by_the_honest_path(
        self, tmp_path, capsys
    ):
        """Positive control: the guard still lets a usable split through."""
        results, path = self._mangled(tmp_path, capsys, "seed", "s1")
        code, out = _run(capsys, "score", "--results", results, "--split", path)
        assert code == EXIT_OK
        assert out["fingerprint"] == json.loads(
            path.read_text(encoding="utf-8")
        )["fingerprint"]

    def test_a_list_fingerprint_is_refused_not_raised(self, tmp_path, capsys):
        """Negative: the `TypeError` raised past the clause that names it."""
        results, path = self._mangled(tmp_path, capsys, "fingerprint", [])
        code, out = _run(capsys, "score", "--results", results, "--split", path)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert "fingerprint" in out["error"]

    def test_a_dict_fingerprint_is_refused_too(self, tmp_path, capsys):
        """Edge: the other unhashable JSON type reaches the same set."""
        results, path = self._mangled(tmp_path, capsys, "fingerprint", {"a": 1})
        code, out = _run(capsys, "score", "--results", results, "--split", path)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_gate_refuses_a_list_fingerprint_as_a_config_error(
        self, tmp_path, capsys
    ):
        """Negative: the older of the two callers, unfixed since the start.

        A malformed split is a `ConfigError` from `gate` as well. Only drift
        earns `decision: REJECT`, because only drift is a fact about a
        readable file.
        """
        results, path = self._mangled(tmp_path, capsys, "fingerprint", [])
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", results, "--candidate", results,
            "--split", path,
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_an_infinite_min_sel_is_refused_not_raised(self, tmp_path, capsys):
        """Negative: `OverflowError` is a sibling of `ValueError`, not a child."""
        results, path = self._mangled(tmp_path, capsys, "min_sel", float("inf"))
        code, out = _run(capsys, "score", "--results", results, "--split", path)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_a_merely_wrong_fingerprint_still_reports_drift(self, tmp_path, capsys):
        """Edge: a usable value that is simply wrong keeps its old answer.

        The repair must reject unusable fingerprints without turning a
        readable-but-stale one into a config error, because that is the case
        the drift refusal exists to report.
        """
        results, path = self._mangled(tmp_path, capsys, "fingerprint", "0" * 64)
        code, out = _run(capsys, "score", "--results", results, "--split", path)
        assert code == EXIT_CONFIG
        assert "Re-split and re-baseline." in out["error"]


class TestNumbersTooLargeToComputeWithNeverReachTheLedger:
    """Round twenty-nine, follow-up: the crash that spends before it dies.

    `--max-consultations` and the two budget bounds are `type=int`, and Python
    integers have no ceiling, so `10 ** 400` is accepted as a cap. Three
    arithmetic sites then convert one to a float: the budget curve multiplies
    a span by 0.5, and the Bonferroni correction divides `--max-p` by the cap,
    once inside the decision and once again when the verdict is built.

    Each raises `OverflowError`, a sibling of `ValueError` rather than a
    subclass, so it escaped every clause written to turn unusable numbers into
    refusals. That is the same taxonomy gap as the `min_sel` fix in the
    previous commit, one argument surface further out.

    The gate makes it expensive. It charges the consultation before it reads
    the held-out group, deliberately, so that a crash cannot hand back a free
    comparison on retry. The second division sits after that charge. Measured
    end to end, one typo cost a consultation, wrote `max_consultations` of
    `10 ** 400` into the ledger, and printed no verdict; every later run
    against that group was then refused for asking for a different cap, and
    the remedy the refusal offers is to re-split, which destroys the held-out
    group. One malformed argument bricks the resource the gate exists to
    protect.

    So the check is at the boundary rather than at the three use sites. A
    value rejected by `argparse` has not charged anything, because parsing
    finishes before any command runs. Catching `OverflowError` at the
    divisions would leave the ledger already written.
    """

    _TOO_BIG = str(10**400)

    def test_a_usable_cap_still_gates(self, tmp_path, capsys):
        """Positive control: ordinary numbers are untouched."""
        results = _write(tmp_path, "r.json", {f"t{i}": i % 2 == 0 for i in range(10)})
        _, path = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        split_path = tmp_path / "sp.json"
        split_path.write_text(json.dumps(path), encoding="utf-8")
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", results, "--candidate", results,
            "--split", split_path, "--max-p", "0.05",
        )
        assert code in (EXIT_OK, EXIT_LOGIC)
        assert "decision" in out

    def test_an_unusable_cap_never_reaches_the_ledger(
        self, tmp_path, capsys, monkeypatch
    ):
        """Negative: the whole point, so the assertion is about the ledger.

        A refusal that still charged would be the bug wearing a better error
        message. The ledger directory has to be untouched.
        """
        ledgers = tmp_path / "ledgers"
        ledgers.mkdir()
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(ledgers))
        results = _write(tmp_path, "r.json", {f"t{i}": i % 2 == 0 for i in range(10)})
        _, drawn = _split(capsys, tmp_path, "--results", results, "--seed", "s1")
        split_path = tmp_path / "sp.json"
        split_path.write_text(json.dumps(drawn), encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            _run(
                capsys, "gate", "--incumbent", results, "--candidate", results,
                "--split", split_path, "--max-p", "0.05",
                "--max-consultations", self._TOO_BIG,
                "--incumbent-fingerprint", drawn["fingerprint"],
            )
        assert excinfo.value.code == EXIT_CONFIG
        assert list(ledgers.iterdir()) == []

    def test_budget_refuses_an_unusable_total(self, capsys):
        """Negative: the second arithmetic site, in the budget curve."""
        with pytest.raises(SystemExit) as excinfo:
            _run(capsys, "budget", "--step", "1", "--total", self._TOO_BIG)
        assert excinfo.value.code == EXIT_CONFIG

    def test_budget_refuses_an_unusable_max_edits(self, capsys):
        """Negative: the third site, the span the curve multiplies."""
        with pytest.raises(SystemExit) as excinfo:
            _run(
                capsys, "budget", "--step", "1", "--total", "3",
                "--max-edits", self._TOO_BIG,
            )
        assert excinfo.value.code == EXIT_CONFIG

    def test_a_large_but_usable_number_is_accepted(self, capsys):
        """Edge: the bar is what the arithmetic can carry, not a product cap.

        `10 ** 300` is absurd as a budget and no business rule here forbids
        it. The check refuses values the tool cannot compute with, and
        inventing a smaller ceiling would be a policy decision wearing a bug
        fix's clothes.
        """
        code, out = _run(
            capsys, "budget", "--step", "1", "--total", "3",
            "--max-edits", str(10**300),
        )
        assert code == EXIT_OK
        assert out["budget"] >= 1

    def test_a_non_numeric_cap_is_still_refused(self, capsys):
        """Edge: the new callable must not swallow the old rejection."""
        with pytest.raises(SystemExit) as excinfo:
            _run(capsys, "budget", "--step", "1", "--total", "not-a-number")
        assert excinfo.value.code == EXIT_CONFIG


class TestExtractionProvenanceCustody:
    def _tasks(self, tmp_path, n: int = 10) -> Path:
        path = tmp_path / "tasks.txt"
        path.write_text("\n".join(f"t{i}" for i in range(n)) + "\n", encoding="utf-8")
        return path

    def _split(self, capsys, tmp_path, n: int = 10):
        tasks = self._tasks(tmp_path, n)
        path = tmp_path / "split.json"
        code, _ = _run_raw(capsys, "split", "--tasks", tasks, "--seed", "s", "--out", path)
        assert code == EXIT_OK
        return path, json.loads(path.read_text(encoding="utf-8"))

    def _report(self, tmp_path, name: str, results: dict[str, bool]) -> Path:
        return _write(
            tmp_path,
            name,
            {
                "model_id": "model-a",
                "seed": "seed-a",
                "error_count": 0,
                "per_fixture_pass_rates": {
                    task_id: {"agent": [1.0 if passed else 0.0]}
                    for task_id, passed in results.items()
                },
            },
        )

    def _extract(self, capsys, path: Path, out: Path) -> Path:
        code, payload = _run_raw(capsys, "extract", "--kind", "agent", "--input", path)
        assert code == EXIT_OK
        out.write_text(json.dumps(payload), encoding="utf-8")
        return out

    def _gate(self, capsys, inc: Path, cand: Path, split: Path, record: dict):
        return _run_raw(
            capsys,
            "gate",
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split,
            "--max-consultations",
            "5",
            "--incumbent-fingerprint",
            record["fingerprint"],
        )

    @pytest.mark.parametrize(
        ("name", "payload"),
        [
            (
                "both-provenance-absent",
                {"schema": "optimizer-results/1", "results": _passing_results()},
            ),
            (
                "empty-provenance-maps",
                {
                    "schema": "optimizer-results/1",
                    "provenance": {},
                    "results": _passing_results(),
                },
            ),
            (
                "both-provenance-null",
                {
                    "schema": "optimizer-results/1",
                    "provenance": None,
                    "results": _passing_results(),
                },
            ),
        ],
    )
    def test_missing_empty_or_null_provenance_is_config_error(
        self, tmp_path, capsys, name, payload
    ):
        split, record = self._split(capsys, tmp_path)
        inc = _write(tmp_path, f"{name}-inc.json", payload)
        cand = _write(tmp_path, f"{name}-cand.json", payload)

        code, out = self._gate(capsys, inc, cand, split, record)

        assert code == EXIT_CONFIG
        assert "provenance" in out["error"]

    def test_missing_versus_null_provenance_is_config_error(self, tmp_path, capsys):
        split, record = self._split(capsys, tmp_path)
        missing = _write(
            tmp_path,
            "missing.json",
            {"schema": "optimizer-results/1", "results": _passing_results()},
        )
        null = _write(
            tmp_path,
            "null.json",
            {
                "schema": "optimizer-results/1",
                "provenance": None,
                "results": _passing_results(),
            },
        )

        code, out = self._gate(capsys, missing, null, split, record)

        assert code == EXIT_CONFIG
        assert "provenance" in out["error"]

    def test_transplanted_provenance_is_config_error(self, tmp_path, capsys):
        split, record = self._split(capsys, tmp_path)
        base = _passing_results()
        inc = self._extract(
            capsys, self._report(tmp_path, "inc-report.json", base), tmp_path / "inc.json"
        )
        changed = dict(base)
        changed[record["sel"][0]] = False
        cand = self._extract(
            capsys,
            self._report(tmp_path, "cand-report.json", changed),
            tmp_path / "cand.json",
        )
        cand_payload = json.loads(cand.read_text(encoding="utf-8"))
        inc_payload = json.loads(inc.read_text(encoding="utf-8"))
        cand_payload["provenance"] = inc_payload["provenance"]
        cand.write_text(json.dumps(cand_payload), encoding="utf-8")

        code, out = self._gate(capsys, inc, cand, split, record)

        assert code == EXIT_CONFIG
        assert "does not match its results" in out["error"]

    def test_split_from_results_is_config_error(self, tmp_path, capsys):
        results = _write(tmp_path, "results.json", _enveloped(None, _passing_results(9)))

        code, out = _run_raw(
            capsys, "split", "--results", results, "--seed", "s", "--out", tmp_path / "split.json"
        )

        assert code == EXIT_CONFIG
        assert "--tasks" in out["error"]

    def test_split_from_corpus_rejects_shared_omission(self, tmp_path, capsys):
        split, record = self._split(capsys, tmp_path, n=10)
        nine = _passing_results(9)
        inc = self._extract(
            capsys, self._report(tmp_path, "inc9.json", nine), tmp_path / "inc.json"
        )
        cand = self._extract(
            capsys, self._report(tmp_path, "cand9.json", nine), tmp_path / "cand.json"
        )

        code, out = self._gate(capsys, inc, cand, split, record)

        assert code == EXIT_LOGIC
        assert out["decision"] == "REJECT"
        assert "whole task set" in out["reason"]

    def test_extract_group_requires_reachable_whole_universe_results(self, tmp_path, capsys):
        split, _record = self._split(capsys, tmp_path, n=10)
        split_record = _split_of(["--split", str(split)])
        report = self._report(
            tmp_path,
            "opt-only.json",
            {task_id: True for task_id in split_record["opt"]},
        )

        code, out = _run_raw(
            capsys,
            "extract",
            "--kind",
            "agent",
            "--input",
            report,
            "--split",
            split,
            "--group",
            "opt",
        )

        assert code == EXIT_CONFIG
        assert "whole task set" in out["error"]


class TestAPatchTheBufferCannotFingerprintIsRefusedNotSkipped:
    """A crash in the buffer commands does not merely lose a document.

    `buffer-check` returns EXIT_LOGIC to mean the patch has been tried before,
    which is the answer that tells the loop to skip it. An uncaught exception
    also leaves the process at 1, so a malformed patch reported as a crash is
    indistinguishable from a patch the buffer has genuinely seen. The loop
    skips an edit it never evaluated.

    `_check_patch_fields` already rules that a wrong-typed field is a named
    refusal rather than a fault, and its docstring says the point is that "the
    CLI can report it as a shape problem". `apply_patches` calls it; the two
    commands that fingerprint patches did not, so the same patch got a clean
    refusal from one command and a traceback from the other two.
    """

    def test_buffer_check_refuses_a_patch_whose_text_is_not_a_string(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": 123}])
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "PatchShapeError"
        assert "text must be a string" in out["error"]
        assert "seen" not in out

    def test_buffer_check_refusal_does_not_borrow_the_code_that_means_seen(
        self, tmp_path, capsys
    ):
        """The regression that matters: EXIT_LOGIC here reads as 'already tried'."""
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": 123}])
        code, _ = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code != EXIT_LOGIC

    def test_buffer_add_refuses_a_patch_whose_op_is_not_a_string(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": 7, "text": "x"}])
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "PatchShapeError"
        assert "op must be a string" in out["error"]

    def test_a_refused_patch_is_never_written_to_the_buffer(self, tmp_path, capsys):
        """A patch that cannot be fingerprinted must not enter the ban list."""
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": 123}])
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert not buffer.exists()

    def test_an_anchor_of_the_wrong_type_is_refused_too(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "replace", "anchor": [], "text": "x"}])
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code == EXIT_CONFIG
        assert "anchor must be a string" in out["error"]

    def test_a_seen_patch_still_reports_seen(self, tmp_path, capsys):
        """Control: the code EXIT_LOGIC still means what it meant."""
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code == EXIT_LOGIC
        assert out["seen"] is True

    def test_an_unseen_patch_still_reports_unseen(self, tmp_path, capsys):
        """Control: a well-formed patch is unaffected by the new check."""
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code == EXIT_OK
        assert out["seen"] is False


class TestABadBudgetIsAnOperatorErrorNotAPatchRefusal:
    """`cmd_apply` catches ValueError to report a patch the loop can branch on.

    Its comment names what the block is for: "A refused patch is a decision the
    loop branches on, not a crash." A negative `--budget` is neither. It is an
    operator argument error, and reporting it as `applied: 0` tells the caller
    the candidate proposed an unusable edit when the candidate did nothing
    wrong. The tool already answers a negative `--min-sel` with a ConfigError.
    """

    def test_a_negative_budget_is_a_config_error(self, tmp_path, capsys):
        doc = tmp_path / "d.txt"
        doc.write_text("hello\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(capsys, "apply", "--file", doc, "--patches", patches, "--budget", "-1")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert "applied" not in out

    def test_the_refused_document_is_still_a_refusal(self, tmp_path, capsys):
        """Control: a patch that genuinely cannot apply still reports applied 0."""
        doc = tmp_path / "d.txt"
        doc.write_text("hello\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "replace", "anchor": "nope", "text": "x"}])
        code, out = _run(capsys, "apply", "--file", doc, "--patches", patches, "--budget", "5")
        assert code == EXIT_LOGIC
        assert out["applied"] == 0

    def test_a_zero_budget_is_not_an_error(self, tmp_path, capsys):
        """Control: the bar is negative, not falsy."""
        doc = tmp_path / "d.txt"
        doc.write_text("hello\n", encoding="utf-8")
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(capsys, "apply", "--file", doc, "--patches", patches, "--budget", "0")
        assert code == EXIT_LOGIC
        assert out["type"] == "BudgetExceededError"


class TestTwoBufferAddsCannotLoseARejectionBetweenThem:
    """The buffer is read-modify-written, so it needs what the ledger has.

    `_ledger_held` states the rule this class enforces, about a different
    file: two callers "both read the same count, both compare, and both write
    count + 1", and "atomic replacement keeps the file whole; it does not make
    the read-modify-write sequence a transaction." `cmd_buffer_add` performs
    exactly that sequence and took no lock, so the later writer's copy of the
    list, made before the earlier writer's append, overwrote it. Both callers
    were told `added: true`, and one rejection was gone.

    Losing one costs a duplicate rollout rather than a wrong verdict, since
    the ledger still caps comparisons. The report is the sharper half: a loop
    that reads `added: true` and moves on believes a rejection is recorded
    that is not.

    The ledger's own behavior is already pinned elsewhere, so those tests are
    the regression guard for sharing the lock: `test_a_held_lock_refuses_the
    _second_gate` for contention, `test_lock_contention_does_not_publish_the
    _key` for the withheld name, and the two release tests for cleanup.
    """

    def _patches(self, tmp_path, name, text):
        return _write(tmp_path, name, [{"op": "append", "text": text}])

    def _lock_of(self, buffer):
        return Path(str(buffer) + ".lock")

    def test_a_held_lock_refuses_the_second_add(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        lock = self._lock_of(buffer)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("999", encoding="utf-8")
        patches = self._patches(tmp_path, "p.json", "x")
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert "another buffer-add holds" in out["error"]

    def test_contention_names_the_lock_so_a_stale_one_can_be_cleared(self, tmp_path, capsys):
        """Unlike the ledger's, this name is the caller's own argument.

        The ledger withholds its lock name because the name digests held-out
        membership. A buffer path came from the command line, so naming it
        costs nothing and withholding it would turn a stale lock into a
        puzzle.
        """
        buffer = tmp_path / "b.json"
        lock = self._lock_of(buffer)
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.touch()
        patches = self._patches(tmp_path, "p.json", "x")
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert str(lock) in out["error"]

    def test_the_read_and_the_write_happen_under_the_same_lock(self, tmp_path, capsys):
        """The property, asserted directly rather than raced for.

        A thread test proves a lock exists only when the schedule cooperates.
        This pins the invariant that makes the schedule irrelevant: the lock
        is present when the buffer is read and still present when it is
        written, so no second caller can read between them.
        """
        buffer = tmp_path / "b.json"
        lock = self._lock_of(buffer)
        seen = {}
        real_read, real_write = oa._read_buffer, oa._write_atomic

        def read(path):
            seen["read"] = lock.exists()
            return real_read(path)

        def write(path, text):
            seen["write"] = lock.exists()
            return real_write(path, text)

        oa._read_buffer, oa._write_atomic = read, write
        try:
            patches = self._patches(tmp_path, "p.json", "x")
            _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        finally:
            oa._read_buffer, oa._write_atomic = real_read, real_write
        assert seen == {"read": True, "write": True}

    def test_the_lock_is_released_when_the_add_returns(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = self._patches(tmp_path, "p.json", "x")
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert not self._lock_of(buffer).exists()

    def test_the_lock_is_released_when_the_add_refuses_a_duplicate(self, tmp_path, capsys):
        """The early return is a second exit from the locked region."""
        buffer = tmp_path / "b.json"
        patches = self._patches(tmp_path, "p.json", "x")
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert (code, out["added"]) == (EXIT_OK, False)
        assert not self._lock_of(buffer).exists()

    def test_the_lock_is_released_when_the_write_raises(self, tmp_path, capsys, monkeypatch):
        """A lock held past a crash would wedge every later add."""
        buffer = tmp_path / "b.json"
        monkeypatch.setattr(oa, "_write_atomic", _raise_boom)
        patches = self._patches(tmp_path, "p.json", "x")
        with pytest.raises(RuntimeError):
            _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert not self._lock_of(buffer).exists()

    def test_an_unreadable_patch_file_takes_no_lock(self, tmp_path, capsys):
        """Patches are parsed before the lock, so a refusal serializes nothing."""
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": 7}])
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert (code, out["type"]) == (EXIT_CONFIG, "PatchShapeError")
        assert not self._lock_of(buffer).exists()

    def test_sequential_adds_both_persist(self, tmp_path, capsys):
        """Control: serializing must not cost the ordinary path anything."""
        buffer = tmp_path / "b.json"
        first = self._patches(tmp_path, "p0.json", "alpha")
        second = self._patches(tmp_path, "p1.json", "beta")
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            first,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r0",
        )
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            second,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r1",
        )
        assert (code, out["added"], out["entries"]) == (EXIT_OK, True, 2)
        stored = json.loads(buffer.read_text(encoding="utf-8"))
        assert [entry["reason"] for entry in stored] == ["r0", "r1"]

    def test_buffer_check_takes_no_lock(self, tmp_path, capsys):
        """Control: a pure read needs no lock and must not wait on a stale one.

        `_write_atomic` replaces the file, so a reader sees the whole old
        document or the whole new one. Serializing readers would let a stale
        lock block the question the loop asks most often.
        """
        buffer = tmp_path / "b.json"
        patches = self._patches(tmp_path, "p.json", "x")
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        lock = self._lock_of(buffer)
        lock.write_text("999", encoding="utf-8")
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert (code, out["seen"]) == (EXIT_LOGIC, True)


class TestBufferCleanupFailureDoesNotRewriteTheResult:
    """The rejection is stored; removing the lock is bookkeeping after it.

    Coverage found this: sharing `_lock_held` gave the buffer a release path
    the ledger already had tests for, and no test drove the buffer's half. The
    ledger's three properties have to hold here too, because a warning that
    escaped would print a second document after the result and return the
    config-failure code for work that succeeded.

    One property inverts. The ledger withholds its lock's name because the
    name digests held-out membership. A buffer's path came from the command
    line, so withholding it would turn a stale lock into a puzzle with nothing
    bought.
    """

    def _fixture(self, tmp_path):
        return tmp_path / "b.json", _write(
            tmp_path, "p.json", [{"op": "append", "text": "x"}]
        )

    def _break_unlink(self, monkeypatch):
        original = Path.unlink

        def refuse(self, missing_ok=False):
            if str(self).endswith(".lock"):
                raise OSError(13, "Permission denied", str(self))
            return original(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", refuse)

    def _add(self, buffer, patches):
        """`main` directly, not `_run`, which drains the capture before stderr."""
        return oa.main([
            "buffer-add", "--buffer", str(buffer),
            "--patches", str(patches), "--artifact", str(_STATIC_ARTIFACT),
            "--reason", "r",
        ])

    def test_stdout_still_holds_exactly_one_document(self, tmp_path, capsys, monkeypatch):
        buffer, patches = self._fixture(tmp_path)
        self._break_unlink(monkeypatch)
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert (code, out["added"]) == (EXIT_OK, True)

    def test_the_stale_lock_is_reported_on_stderr(self, tmp_path, capsys, monkeypatch):
        buffer, patches = self._fixture(tmp_path)
        self._break_unlink(monkeypatch)
        self._add(buffer, patches)
        assert "Permission denied" in capsys.readouterr().err

    def test_the_warning_names_the_lock_so_it_can_be_cleared(
        self, tmp_path, capsys, monkeypatch
    ):
        buffer, patches = self._fixture(tmp_path)
        self._break_unlink(monkeypatch)
        self._add(buffer, patches)
        assert f"{buffer}.lock" in capsys.readouterr().err

    def test_the_rejection_is_on_disk_despite_the_failed_cleanup(
        self, tmp_path, capsys, monkeypatch
    ):
        buffer, patches = self._fixture(tmp_path)
        self._break_unlink(monkeypatch)
        self._add(buffer, patches)
        assert len(json.loads(buffer.read_text(encoding="utf-8"))) == 1

    def test_a_clean_release_says_nothing(self, tmp_path, capsys):
        buffer, patches = self._fixture(tmp_path)
        self._add(buffer, patches)
        assert capsys.readouterr().err == ""


class TestTheThreeKindsDisagreeOnDegradedInputAsDocumented:
    """The README claimed one policy for three paths and two exist.

    Its adapter paragraph listed "a fixture the variant never ran, a scenario
    whose judge errored, and a skipped test" as scoring false together. Two of
    the three do. The rule path refuses the whole report with exit 2, because
    `extract --kind rule` runs a degraded scan the other kinds have no
    equivalent of.

    A thirty-second review read that sentence, found the code disagreeing with
    it, and filed the refusal as a Critical. The code is right here: scoring a
    failed judge as a real failure measures the judge rather than the rule, and
    the gate would spend one of a small budget of consultations to reach a
    verdict carrying no information about the candidate. Four earlier rounds had
    the document right and the code wrong; this is the same defect inverted, and
    a reviewer misled by prose is the evidence that an operator would be.

    These tests pin the contrast rather than each path alone, which the existing
    per-path tests already do. The contrast is what the prose asserts.
    """

    def test_a_fixture_with_no_run_under_the_variant_scores_false(self, tmp_path, capsys):
        report = _write(tmp_path, "r.json", {
            "per_fixture_pass_rates": {"f1": {"cand": [1.0]}, "f2": {"other": [1.0]}},
            "error_count": 0,
        })
        code, out = _run(
            capsys, "extract", "--kind", "agent", "--input", report, "--variant", "cand"
        )
        assert (code, out["results"]) == (EXIT_OK, {"f1": True, "f2": False})

    def test_a_skipped_test_scores_false(self, tmp_path, capsys):
        xml = tmp_path / "j.xml"
        xml.write_text(
            '<testsuites><testsuite name="s" tests="2">'
            '<testcase classname="t" name="a"/>'
            '<testcase classname="t" name="b"><skipped message="no"/></testcase>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        code, out = _run(capsys, "extract", "--kind", "hook", "--input", xml)
        assert (code, out["results"]) == (EXIT_OK, {"t::a": True, "t::b": False})

    def test_a_failed_judge_refuses_instead_of_scoring_false(self, tmp_path, capsys):
        scen = _write(tmp_path, "s.json", [
            {"id": "S1", "negative_case": False, "mechanisms": {
                "full": {"scores": {
                    "activation_score": 5, "citation_score": 5, "behavior_score": 5,
                }},
            }},
            {"id": "S2", "negative_case": False, "mechanisms": {
                "full": {"scores": {
                    "activation_score": 5, "citation_score": 5, "behavior_score": 5,
                    "judge_failed": True,
                }},
            }},
        ])
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scen)
        assert code == EXIT_CONFIG
        assert "results" not in out
        assert "S2" in out["error"]

    def test_the_library_still_fails_closed_on_the_same_input(self, tmp_path):
        """The refusal is `extract`'s, not the adapter's.

        The README now says the library keeps one contract and the command that
        spends budget keeps a stricter one. If someone moved the scan down into
        the adapter, this turns red and the prose becomes wrong again.

        Asserted against `rule_results_multi` because that is the entry point
        `extract` calls once the rule path gained multi-run reduction. Guarding
        the function the command no longer reaches would have left the contract
        unguarded while still looking green.
        """
        scenarios = [
            {"id": "S1", "negative_case": False, "mechanisms": {
                "full": {"scores": {
                    "activation_score": 5, "citation_score": 5, "behavior_score": 5,
                }},
            }},
            {"id": "S2", "negative_case": False, "mechanisms": {
                "full": {"scores": {
                    "activation_score": 5, "citation_score": 5, "behavior_score": 5,
                    "judge_failed": True,
                }},
            }},
        ]
        assert oa.rule_results_multi([scenarios], "full") == {"S1": True, "S2": False}

    def test_the_readme_documents_the_flag_where_the_policy_is_stated(self):
        """The paragraph stating the policy has to name the flag that changes it.

        It said a skipped test scores as a failure "rather than being dropped",
        with no qualifier, while `extract --kind hook` has always taken
        `--on-skip exclude`, which drops exactly those. The flag appeared
        nowhere in the README, so a sentence true of the default read as the
        whole contract.

        Scoped to the paragraph rather than the whole file. A file-wide search
        passes on an unrelated historical mention elsewhere, which is the state
        this defect was found in: the words existed, the contract did not.
        """
        para = _readme_paragraph("That is the default and not the only policy.")
        assert [p for p in oa._SKIP_POLICIES if f"`{p}`" not in para] == []
        assert "--on-skip" in para

    def test_the_readme_names_the_measured_cost_of_dropping_a_task(self):
        """Naming the escape hatch is not enough; it has to carry its cost.

        The first version of this paragraph said `exclude` "moves the split
        fingerprint and stops the gate", inherited from the adapter docstring.
        Measured, both halves are false. The fingerprint is the split's own and
        is echoed back unchanged, and the gate does not stop: a dropped
        held-out task charges a consultation and reports REJECT at exit 1 with
        `compared: false`. Naming a harmless-sounding halt understates a cost
        the operator pays out of a small budget.

        Asserts the words the measurement produced, not a positional window.
        The earlier version searched 700 characters after the first backtick,
        which passed on an unrelated nearby "fingerprint" and failed when
        correct prose grew.
        """
        para = _readme_paragraph("That is the default and not the only policy.")
        assert "consultation" in para
        assert "REJECT" in para

    def test_every_accepted_skip_policy_reaches_the_adapter(self, tmp_path, capsys):
        """Accepting a value is not forwarding it.

        The first version of this test only asserted exit 0 for each policy,
        which stays green if the command drops the flag on the floor. This
        pins the command's output to the adapter's own answer for the same
        input, so a lost or reordered argument turns it red.
        """
        xml = tmp_path / "j.xml"
        xml.write_text(
            '<testsuites><testsuite name="s" tests="1">'
            '<testcase classname="t" name="a"><skipped message="no"/></testcase>'
            "</testsuite></testsuites>",
            encoding="utf-8",
        )
        text = xml.read_text(encoding="utf-8")
        for policy in oa._SKIP_POLICIES:
            code, out = _run(
                capsys, "extract", "--kind", "hook", "--input", xml,
                "--on-skip", policy,
            )
            assert (code, out["results"]) == (
                EXIT_OK, oa.pytest_results(text, on_skip=policy)
            )

    def test_a_policy_the_adapter_never_accepts_is_refused(self, tmp_path, capsys):
        """The other direction, which "exactly" needs and forwarding cannot show.

        Driving only the known-good set proves the command accepts everything
        the adapter does, never that it rejects anything else. Without this the
        command could take an unknown policy and hand the adapter a value it
        raises on, turning a typo into a stack trace.
        """
        xml = tmp_path / "j.xml"
        xml.write_text(
            '<testsuites><testsuite name="s" tests="1">'
            '<testcase classname="t" name="a"/></testsuite></testsuites>',
            encoding="utf-8",
        )
        with pytest.raises(SystemExit) as exc:
            oa.main([
                "extract", "--kind", "hook", "--input", str(xml),
                "--on-skip", "drop",
            ])
        assert exc.value.code == EXIT_CONFIG


def _defaults_agree(expected: object, actual: object) -> bool:
    """Whether a parsed flag default matches its owner's, as the system reads it.

    `Ratio` is `float | str`, so argparse hands back the string it was given
    while the owning signature declares a float. The two spellings have to be
    compared through the same canonicalization the product uses, and both of
    the obvious shortcuts are wrong in one direction.

    `float(actual) == expected` is too loose. `float` collapses every decimal
    within one ULP onto the same value, so a default that moved to
    `"0.4000000000000000000000000001"` reads as unchanged here while
    `split_fingerprint` hashes it to a different split.

    `actual == str(expected)` is too tight. The fingerprint runs ratios
    through `Fraction`, so `"0.40"` and `0.4` are the same split; reporting
    that as drift sends a reader looking for a change nobody made.

    `_canonical_ratio` is the function `split_fingerprint` itself calls, so
    reusing it keeps this bar from ever drifting from the thing it protects.

    `bool` subclasses `int` and `int` compares equal to `float`, so plain
    `==` reads `False` as `0`, `True` as `1`, and `5` as `5.0`. Each is a
    different contract: every ratio the product validates refuses a bool by
    name, and `edit_budget` is annotated `max_edits: int -> int` yet answers
    `5.0` when handed one, which the results file publishes as a different
    JSON number. Outside the ratio spelling the two kinds have to match.

    Raises:
        ValueError: when a ratio default is not a decimal, which is louder
            and more specific than reading the same input as a mismatch.
    """
    if isinstance(expected, float) and isinstance(actual, str):
        return core._canonical_ratio(actual) == core._canonical_ratio(expected)
    return type(expected) is type(actual) and actual == expected


class TestOneNameForEachFlagDefaultAndChoiceSet:
    """Every CLI flag whose values a module owns reads them from that module.

    `--on-skip` hardcoded `("fail", "exclude")` beside the adapter's own
    `_SKIP_POLICIES`. The audit that followed found the same split in two more
    places: `--reduce` listed the four `_REDUCERS` keys, and `--min-score`
    repeated the literal 3.5 while `DEFAULT_MIN_ACTIVATION_SCORE` sat in the
    adapter's `__all__`, exported for exactly this use and ignored.

    Each duplicate fails the same way. Add a policy, a reducer, or move a
    threshold in the module that owns it, and argparse refuses the new value
    before the owner sees it, so the operator reads an error naming the wrong
    layer. Each also gives the README a second place to drift from.

    Defaults are read off the parsed namespace rather than the parser's
    private action list, and choice sets are driven through the command,
    because a value that argparse accepts and the command never forwards is
    the failure the introspection spelling cannot see.
    """

    def _extract_args(self, tmp_path, kind, name):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        return ["extract", "--kind", kind, "--input", str(path)]

    # Every flag whose value a module owns, paired with the function whose
    # signature is that owner, then by the parameter name inside that
    # signature. The fourth element is not redundant: `--rule-reduce` and
    # `--reduce` both reach `rule_results_multi` and neither can be named
    # `reduce` on both sides, so a table keyed on `dest` alone would have to
    # leave one of the two unaudited. `Ratio` is `float | str`, so the two
    # split ratios arrive as the string argparse was given while the owner
    # declares a float. `_defaults_agree` reconciles the two through the
    # product's own `_canonical_ratio`, which is neither float-loose nor
    # string-tight.
    _OWNED_DEFAULTS = (
        ("extract", "pass_threshold", "agent_results", "pass_threshold"),
        ("extract", "reduce", "rule_results_multi", "reduce"),
        ("extract", "rule_reduce", "rule_results_multi", "reduce_samples"),
        ("extract", "min_score", "rule_results_multi", "min_score"),
        ("extract", "on_skip", "pytest_results", "on_skip"),
        ("split", "sel_ratio", "split_tasks", "sel_ratio"),
        ("split", "test_ratio", "split_tasks", "test_ratio"),
        ("split", "min_sel", "split_tasks", "min_sel"),
        ("budget", "max_edits", "edit_budget", "max_edits"),
        ("budget", "min_edits", "edit_budget", "min_edits"),
    )

    # The minimum argv each subcommand accepts. Built by hand because
    # argparse reports a mutually exclusive requirement on the group rather
    # than on its members, so walking `action.required` misses `--tasks`.
    # A wrong entry here fails loudly at parse time rather than passing
    # quietly, which is how the missing `--tasks` surfaced.
    _MINIMUM_ARGV = {
        "extract": ("--kind", "rule", "--input", "{path}"),
        "split": ("--seed", "s", "--tasks", "{path}", "--out", "{path}"),
        "budget": ("--step", "1", "--total", "2"),
    }

    def _parse(self, command, tmp_path):
        path = tmp_path / "x.json"
        path.write_text("[]", encoding="utf-8")
        argv = [a.format(path=path) for a in self._MINIMUM_ARGV[command]]
        return oa.build_parser().parse_args([command, *argv])

    @pytest.mark.parametrize(("command", "dest", "owner", "param"), _OWNED_DEFAULTS)
    def test_a_flag_default_equals_the_default_of_the_function_that_owns_it(
        self, tmp_path, command, dest, owner, param
    ):
        """The command must not carry its own copy of a value it does not own.

        Nine flags reach a function that already declares the same default.
        When the two drift, nothing fails: the command keeps answering with a
        value the owner never chose, and the README has two places to describe.

        Read from the owning module rather than through the module under test.
        Comparing what the command imported against what the command parsed is
        a tautology that survives the command hardcoding its own copy, which is
        exactly the defect this pins.
        """
        fn = getattr(adapters, owner, None) or getattr(core, owner)
        expected = inspect.signature(fn).parameters[param].default
        actual = getattr(self._parse(command, tmp_path), dest)
        assert _defaults_agree(expected, actual), f"{command} --{dest}"

    def test_the_pairs_above_name_a_parameter_each_owner_really_has(self):
        """A typo in the table above would silently test nothing.

        `getattr` on a missing owner raises, but a `dest` that no longer
        matches a parameter would make every case skip its real subject, so
        the table is checked against both signatures directly.
        """
        missing = [
            (param, owner)
            for _, _, owner, param in self._OWNED_DEFAULTS
            if param
            not in inspect.signature(
                getattr(adapters, owner, None) or getattr(core, owner)
            ).parameters
        ]
        assert missing == []

    def test_every_reducer_the_adapter_owns_survives_the_command(
        self, tmp_path, capsys
    ):
        report = _write(tmp_path, "r.json", [
            {"id": "S1", "negative_case": False, "mechanisms": {
                "full": {"scores": {
                    "activation_score": 5, "citation_score": 5,
                    "behavior_score": 5,
                }},
            }},
        ])
        refused = [
            name
            for name in adapters._REDUCERS
            if _run(
                capsys, "extract", "--kind", "rule", "--input", report,
                "--mechanism", "full", "--reduce", name,
            )[0] != EXIT_OK
        ]
        assert refused == []

    def test_a_reducer_the_adapter_does_not_own_is_refused(self, tmp_path):
        report = _write(tmp_path, "r.json", [])
        with pytest.raises(SystemExit) as exc:
            oa.main([
                "extract", "--kind", "rule", "--input", str(report),
                "--mechanism", "full", "--reduce", "sum",
            ])
        assert exc.value.code == EXIT_CONFIG


class TestMarkdownBlockStopsAtEveryBlockBoundary:
    """The README window has to end where a Markdown renderer ends the block.

    This is the fifth window this file has tried. The first four each widened
    quietly: a file-wide search, a fixed character count, the next heading,
    and a blank-line paragraph. Each passed an assertion on prose written for
    something else, which is the one failure a documentation test must not
    have, because it reports that a contract is documented when it is not.

    The blank-line window was the closest and still wrong. CommonMark lets a
    heading, a list, a blockquote, and a fence interrupt a paragraph with no
    blank line before them, so a README that grows one of those next to a
    marker silently hands the assertion its neighbour's words.
    """

    _INTERRUPTED = (
        "the contract sentence\n"
        "### Argument errors\n"
        "the neighbour sentence\n"
    )

    def test_a_heading_ends_the_block_without_a_blank_line(self):
        """The case the blank-line window could not see.

        No blank line anywhere, so the old window returned the whole file and
        an assertion for the contract sentence would have passed on the
        neighbour's words.
        """
        assert _markdown_block(self._INTERRUPTED, "contract") == "the contract sentence"

    def test_the_block_after_an_interrupter_is_also_bounded(self):
        """The window has to be right from both sides of the heading."""
        assert _markdown_block(self._INTERRUPTED, "neighbour") == "the neighbour sentence"

    def test_the_interrupting_heading_is_its_own_block(self):
        """A marker on the heading line selects the heading, not the prose."""
        assert _markdown_block(self._INTERRUPTED, "Argument") == "### Argument errors"

    @pytest.mark.parametrize(
        "interrupter",
        ["### Heading", "- a bullet", "1. an item", "> a quote", "```json"],
    )
    def test_every_construct_commonmark_lets_interrupt_a_paragraph_does(
        self, interrupter
    ):
        """One case each for the four block starts, plus a fence.

        Pinned by construct rather than by one representative because the
        previous windows were each correct for the example that motivated
        them and wrong for the next one.
        """
        text = f"the contract sentence\n{interrupter}\nsomething else\n"
        assert _markdown_block(text, "contract") == "the contract sentence"

    def test_a_blank_line_still_ends_a_block(self):
        """The property the previous window had is not lost by gaining this one."""
        text = "first paragraph\n\nsecond paragraph\n"
        assert _markdown_block(text, "first") == "first paragraph"

    def test_a_blank_line_carrying_a_space_still_ends_a_block(self):
        """Round 26's fix. A whitespace-only line renders as a break."""
        text = "first paragraph\n \nsecond paragraph\n"
        assert _markdown_block(text, "first") == "first paragraph"

    def test_a_soft_wrapped_paragraph_stays_whole(self):
        """The negative case. Over-splitting is as wrong as over-joining.

        Every README paragraph this file asserts on is soft-wrapped across
        several lines, so a window that stopped at every newline would make
        each of them assert on a fragment.
        """
        text = "one sentence\nwrapped across lines\nand a third\n\nnext\n"
        assert _markdown_block(text, "wrapped") == (
            "one sentence\nwrapped across lines\nand a third"
        )

    def test_a_hash_inside_a_fence_is_not_a_heading(self):
        """A shell comment in a `bash` block would otherwise split the fence.

        The README opens with exactly this shape, so a fence-blind rule would
        have reported the code sample as three separate blocks.
        """
        text = "```bash\n# a shell comment\nrun --flag\n```\n"
        assert _markdown_block(text, "shell comment") == text.rstrip("\n")

    def test_a_marker_that_appears_twice_is_refused(self):
        """A non-unique marker picks an arbitrary block, so it is not allowed."""
        with pytest.raises(AssertionError, match="2 times"):
            _markdown_block("a marker here\n\nand a marker there\n", "a marker")

    def test_a_marker_that_is_absent_is_refused(self):
        """An absent marker means the prose was rewritten, not that it passes."""
        with pytest.raises(AssertionError, match="0 times"):
            _markdown_block("nothing to see\n", "absent")

    def test_prose_after_a_closing_fence_is_not_inside_the_fence(self):
        """Round 45's window closed the fence and kept reading into it.

        The state machine suppressed block starts inside a fence and cleared
        the flag on the closing line, but nothing said the next line opens a
        block. Ordinary prose does not match any block-start pattern, so it
        was appended to the listing it follows and a code-sample assertion
        could pass on the sentence underneath.
        """
        text = "```bash\ncode contract\n```\nthe neighbour sentence\n"
        assert _markdown_block(text, "contract") == "```bash\ncode contract\n```"

    def test_an_indented_backtick_run_is_not_a_fence(self):
        """Four spaces makes it paragraph text, not a fence that swallows.

        The old rule matched a fence after any leading whitespace, so this
        opened a fence that then suppressed the heading below it and ran to
        the end of the file. CommonMark gives the run to the paragraph, and
        the heading still ends the block.
        """
        text = "the contract sentence\n    ```\nstill the same paragraph\n### Other\nprose\n"
        assert _markdown_block(text, "contract") == (
            "the contract sentence\n    ```\nstill the same paragraph"
        )

    @pytest.mark.parametrize("rule", ["***", "___", "* * *", "- - -"])
    def test_a_thematic_break_ends_the_block(self, rule):
        """A horizontal rule is a block boundary a reader plainly sees.

        The old rule had no pattern for one, so a README that separated two
        sections with a rule instead of a blank line handed the assertion
        the text on the far side of a visible line. `---` is absent here on
        purpose: after a paragraph it underlines rather than divides, which
        the next test pins.
        """
        text = f"the contract sentence\n{rule}\nthe neighbour sentence\n"
        assert _markdown_block(text, "contract") == "the contract sentence"

    def test_a_dash_run_under_a_paragraph_underlines_it(self):
        """`---` after prose is a setext heading, not a thematic break.

        The distinction is invisible to a pattern that only reads the line
        itself, which is the whole reason this window asks a parser. A rule
        would end the block above it; an underline joins it.
        """
        text = "the contract sentence\n---\nthe neighbour sentence\n"
        assert _markdown_block(text, "contract") == "the contract sentence\n---"

    def test_a_dash_run_after_a_blank_line_really_is_a_break(self):
        """The other half of the same line, to show the rule is contextual."""
        text = "the contract sentence\n\n---\n\nthe neighbour sentence\n"
        assert _markdown_block(text, "contract") == "the contract sentence"

    def test_a_setext_underline_makes_a_heading_of_what_came_before_it(self):
        """`===` under a line makes every line above it one heading.

        Not the split the old rule would have wanted, and the right one: a
        setext heading is announced by the line after it, so its content is
        the whole run of prose above the underline. The block that ends is
        the heading, and the sentence below is a separate paragraph, which
        is the part the old rule could not see at all.
        """
        text = "the contract sentence\nA Heading\n=========\nthe neighbour sentence\n"
        assert _markdown_block(text, "contract") == (
            "the contract sentence\nA Heading\n========="
        )

    def test_the_paragraph_after_a_setext_heading_is_its_own_block(self):
        """The half of the setext case an assertion would otherwise borrow."""
        text = "the contract sentence\nA Heading\n=========\nthe neighbour sentence\n"
        assert _markdown_block(text, "neighbour") == "the neighbour sentence"

    def test_a_blockquote_without_a_space_still_interrupts(self):
        """`>text` is a quote; the old pattern required `> ` with the space."""
        text = "the contract sentence\n>the neighbour sentence\n"
        assert _markdown_block(text, "contract") == "the contract sentence"

    def test_a_table_row_is_the_block_not_the_whole_table(self):
        """The dialect is the repo's, and the window is one row.

        `scripts/utils/markdown_parser` enables tables on CommonMark, so a
        README table renders as a table here too. The narrowest block holding
        the marker is its row, which is the unit that keeps an assertion from
        matching a neighbouring row's words, the same borrowing this window
        exists to stop between paragraphs.
        """
        text = "| head | cols |\n| --- | --- |\n| contract | cell |\n\nafter\n"
        assert _markdown_block(text, "contract") == "| contract | cell |"


    def test_a_marker_the_renderer_draws_no_block_for_is_refused_accurately(self):
        """A link reference definition is consumed, not drawn.

        The parser gives it no line range, so no window covers the marker.
        Round 46 still reported that as "landed on a blank line", which is a
        false statement about a reachable input and sends a reader looking
        for whitespace that is not there. The refusal names both reasons.
        """
        text = "[contract]: http://example.com\n\nafter\n"
        with pytest.raises(AssertionError, match="no block the renderer draws"):
            _markdown_block(text, "contract")

    def test_a_marker_on_a_blank_line_is_still_refused(self):
        """The other half of the same refusal, which must not regress."""
        with pytest.raises(AssertionError, match="no block the renderer draws"):
            _markdown_block("first\n  \nsecond\n", "  ")

    def test_a_marker_in_raw_html_is_refused_rather_than_given_a_wide_window(self):
        """One Markdown block can be several elements the reader sees.

        CommonMark ends a raw HTML block at a blank line, not at the end of an
        element, so a contiguous run of markup is one token however many
        siblings it renders. The window would hand back both, which is the
        borrowed-neighbour failure the parser was brought in to end, and the
        parser cannot tell one element from two without an HTML parser.

        Refusing is the honest half of that limit. Borrowing is silent; a
        refusal names the constraint and the remedy.
        """
        text = "<div>contract marker</div>\n<p>neighbour borrowed</p>\n"
        with pytest.raises(AssertionError, match="raw HTML"):
            _markdown_block(text, "contract")

    def test_the_refusal_covers_a_single_element_spanning_lines_too(self):
        """The limit is the construct, not the count of elements in it.

        `<details>` is one element over four lines and would be a correct
        window. The token is the same `html_block` either way, so accepting
        this case means accepting the borrowing one. The stricter half is
        chosen deliberately and pinned here so it is not read as an oversight.
        """
        text = "<details>\n<summary>contract marker</summary>\nbody\n</details>\n"
        with pytest.raises(AssertionError, match="raw HTML"):
            _markdown_block(text, "contract")

    def test_markdown_prose_beside_raw_html_still_gets_its_own_window(self):
        """The refusal is scoped to markup, not to documents containing it.

        A README may carry a badge or a details block and still assert on its
        prose. Only a marker the parser puts inside the markup is refused.
        """
        text = "<div>badge</div>\n\ncontract marker\n\n<p>neighbour</p>\n"
        assert _markdown_block(text, "contract") == "contract marker"


class TestDefaultsAgreeIsAsStrictAsTheFingerprint:
    """The bar the table above compares with needs its own coverage.

    A test whose comparison is looser than the system's own passes while the
    thing it pins is broken, which is how the previous spelling survived: it
    read `float(actual) == expected`, and `float` collapses every decimal
    string within one ULP of the default onto the default itself.

    Both directions are failures, so both are pinned here. Too loose accepts a
    drifted default that `split_fingerprint` would hash to a different split.
    Too tight reports drift for a respelling the fingerprint canonicalizes
    away, which sends a reader looking for a change nobody made.
    """

    @pytest.mark.parametrize(
        ("expected", "actual"),
        [
            (0.4, "0.4"),
            (0.0, "0.0"),
            (0.4, "0.40"),
            (0.0, "0.00"),
            (0.4, "0.4000"),
            (1.0, "1.0"),
        ],
    )
    def test_a_respelling_the_fingerprint_cannot_see_is_not_drift(
        self, expected, actual
    ):
        """Trailing zeros do not move the split, so they are not a mismatch.

        `_canonical_ratio` runs the value through `Fraction`, so `"0.40"` and
        `0.4` reach `split_fingerprint` as the same `2/5`. An exact-string bar
        would fail these, which is why the fix is not "compare the strings".
        """
        assert _defaults_agree(expected, actual)

    @pytest.mark.parametrize(
        ("expected", "actual"),
        [
            (0.4, "0.4000000000000000000000000001"),
            (0.4, "0.3999999999999999999999999999"),
            (0.0, "0.0000000000000000000000000001"),
            (0.4, "0.5"),
        ],
    )
    def test_a_default_that_moves_the_split_is_drift(self, expected, actual):
        """The first three are `float`-equal to the default and still drift.

        These are the cases the previous bar could not see. Each hashes to a
        different split, so a default that moved this far would have passed
        the audit while every stored fingerprint stopped matching.
        """
        assert not _defaults_agree(expected, actual)

    def test_the_drifting_values_really_do_move_the_fingerprint(self):
        """The negative cases above are only meaningful if this holds.

        Asserting the bar rejects them proves nothing on its own: the bar
        could be rejecting values the system treats as identical. Recompute
        the fingerprint to show the rejection tracks a real split change.
        """
        ids = ["a", "b", "c", "d", "e"]
        base = core.split_fingerprint(ids, seed="s", sel_ratio=0.4)
        moved = core.split_fingerprint(
            ids, seed="s", sel_ratio="0.4000000000000000000000000001"
        )
        same = core.split_fingerprint(ids, seed="s", sel_ratio="0.40")
        assert (moved != base, same == base) == (True, True)

    @pytest.mark.parametrize(
        ("expected", "actual"),
        [("mean", "mean"), ("fail", "fail"), (3, 3), (5, 5), (1, 1)],
    )
    def test_a_non_ratio_flag_compares_directly(self, expected, actual):
        """Six of the nine table entries are `str` or `int` on both sides.

        Those never reach the ratio branch, and routing them through it would
        make `3` and `"3"` agree, which for a count is a real mismatch.
        """
        assert _defaults_agree(expected, actual)

    @pytest.mark.parametrize(
        ("expected", "actual"),
        [("mean", "median"), (3, 4), (3, "3"), (0.4, 0.5)],
    )
    def test_a_non_ratio_mismatch_is_reported(self, expected, actual):
        """`(3, "3")` is the case that justifies not widening the branch."""
        assert not _defaults_agree(expected, actual)

    def test_a_ratio_default_that_is_not_a_decimal_fails_loudly(self):
        """A garbage default raises rather than quietly reading as drift.

        `"2/5"` is the value a reader most plausibly reaches for, and it is
        exactly what `_canonical_ratio` prints, so a silent `False` here would
        send them hunting for a numeric difference that does not exist. The
        error names the flag and the format instead.
        """
        with pytest.raises(ValueError, match="must be a decimal ratio"):
            _defaults_agree(0.4, "2/5")

    @pytest.mark.parametrize(
        ("expected", "actual"),
        [
            (0.0, False),
            (0, False),
            (1, True),
            (1.0, True),
            (False, 0),
            (True, 1),
            (False, 0.0),
        ],
    )
    def test_a_bool_never_agrees_with_a_number(self, expected, actual):
        """`bool` subclasses `int`, so `==` alone reads `False` as `0.0`.

        The audit exists to catch a default that moved, and turning a ratio
        flag into a `store_true` is one of the ways it moves. Every ratio the
        product validates rejects a bool by name: `_canonical_ratio(False)`
        raises "must be a decimal ratio". A bar that approves what the
        product refuses is not a bar, so the two kinds disagree here.
        """
        assert not _defaults_agree(expected, actual)

    @pytest.mark.parametrize(("expected", "actual"), [(True, True), (False, False)])
    def test_two_bools_still_compare_as_bools(self, expected, actual):
        """The guard rejects the mixed pair, not the flag kind itself.

        No table entry is a bool today, but a `store_true` flag is the most
        likely next one, and it has to keep reading as agreement.
        """
        assert _defaults_agree(expected, actual)

    def test_the_product_really_does_refuse_the_bool_this_bar_refuses(self):
        """Rejecting a bool is only right if the product rejects it too.

        Without this the guard is an unfounded opinion about types. The same
        `False` the bar now refuses reaches `split_fingerprint` as a hard
        error, so the bar and the product agree about the same input.
        """
        with pytest.raises(ValueError, match="must be a decimal ratio"):
            core.split_fingerprint(["a", "b"], seed="s", sel_ratio=False)

    @pytest.mark.parametrize(("expected", "actual"), [(5, 5.0), (5.0, 5), (1, 1.0)])
    def test_a_whole_number_never_agrees_across_kinds(self, expected, actual):
        """`bool` was one instance of a wider hole, not the hole itself.

        `==` compares numbers by value, so an `int` owner default and a
        `float` command default read as agreement while the two are different
        contracts. `edit_budget` is annotated `max_edits: int -> int`; hand it
        `5.0` and it answers `5.0`, which `json.dumps` writes as `5.0` where
        the published results carried `5`. A bar that approves a silent type
        change in the emitted schema is not a bar.

        Stated as one rule about kinds rather than a list of pairs. The
        previous spelling named `bool` and let every other pair through, which
        is the shape the block-boundary patterns failed in as well.
        """
        assert not _defaults_agree(expected, actual)

    def test_the_product_really_does_change_shape_for_the_pair_above(self):
        """The type bar is only right if the product notices the type.

        Without this the rule is a preference about spelling. `edit_budget`
        declares `-> int` and returns a `float` unchanged, so the same
        mismatch the bar now refuses reaches the results file as a different
        JSON number than the one the schema published.
        """
        assert json.dumps(core.edit_budget(0, 2, max_edits=5)) == "5"
        assert json.dumps(core.edit_budget(0, 2, max_edits=5.0)) == "5.0"

    @pytest.mark.parametrize(("expected", "actual"), [(3, 3), (1.0, 1.0), (5, 5)])
    def test_a_matching_kind_still_agrees(self, expected, actual):
        """The rule refuses the mixed pair, not the values themselves.

        Seven of the nine live table entries compare same-kind numbers. They
        have to keep passing or the bar reports drift nobody introduced.
        """
        assert _defaults_agree(expected, actual)


@_NEEDS_PERMISSION_BARRIER
class TestALockThatCannotBeTakenIsAConfigErrorNotATraceback:
    """Round 31's extraction lost the seam that made `_lock_held` safe.

    Every other filesystem call in this module turns `OSError` into
    `ConfigError`: `_read_buffer` reports "could not read", `_write_atomic`
    reports "could not write". `_lock_held` never did, and it did not have to,
    because its only caller ran inside `_digest_scrubbed`, whose whole job is
    to convert every `OSError` raised under the ledger. Giving the helper a
    second caller with no such wrapper left the one unconverted filesystem
    call in the program on the buffer path.

    The cost is the failure mode this branch exists to close. An uncaught
    `OSError` leaves `main`'s handler list, prints a traceback where the module
    docstring promises a JSON document, and exits 1, which is the code a loop
    reads as a decision it should branch on rather than a crash it should stop
    for.

    Measured against the commit before the extraction, `buffer-add` into an
    unwritable directory returned exit 2 and a JSON error document. After it,
    the same command returns exit 1 and a traceback.
    """

    def _fixture(self, tmp_path):
        unwritable = tmp_path / "ro"
        unwritable.mkdir()
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        unwritable.chmod(0o555)
        return unwritable / "b.json", patches

    def test_an_unwritable_directory_is_reported_as_a_config_error(self, tmp_path, capsys):
        buffer, patches = self._fixture(tmp_path)
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_message_names_the_lock_so_an_operator_can_act(self, tmp_path, capsys):
        buffer, patches = self._fixture(tmp_path)
        _, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert f"{buffer}.lock" in out["error"]

    def test_a_parent_that_cannot_be_created_is_reported_the_same_way(
        self, tmp_path, capsys
    ):
        buffer, patches = self._fixture(tmp_path)
        nested = buffer.parent / "deeper" / "b.json"
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            nested,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_a_write_that_fails_after_the_create_is_reported_the_same_way(
        self, tmp_path, capsys, monkeypatch
    ):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        monkeypatch.setattr(oa.os, "write", _boom)
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_a_failed_write_still_removes_the_lock_it_created(
        self, tmp_path, capsys, monkeypatch
    ):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        monkeypatch.setattr(oa.os, "write", _boom)
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert not Path(f"{buffer}.lock").exists()

    def test_contention_keeps_its_own_message_rather_than_the_generic_one(
        self, tmp_path, capsys
    ):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        Path(f"{buffer}.lock").write_text("999", encoding="utf-8")
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert "another buffer-add holds" in out["error"]

    def test_a_writable_directory_still_stores_the_rejection(self, tmp_path, capsys):
        buffer = tmp_path / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_OK
        assert out["added"] is True

    def test_the_gate_still_scrubs_the_digest_out_of_the_same_failure(
        self, tmp_path, capsys, monkeypatch
    ):
        """The ledger caller's cover must survive the helper learning to raise.

        `_digest_scrubbed` catches `ConfigError` as well as `OSError`, so
        converting inside the helper keeps the redaction. A conversion that
        forgot this would publish the digest, which is the held-out membership.
        """
        root = tmp_path / "ledger"
        root.mkdir()
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(root))
        tasks = tmp_path / "tasks.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(12)), encoding="utf-8")
        _, split = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "lock33")
        inc = _write(tmp_path, "i.json", {t: False for t in split["sel"]})
        cand = _write(tmp_path, "c.json", {t: True for t in split["sel"]})
        root.chmod(0o555)
        code, out = _run(
            capsys, "gate", "--split", tmp_path / "split.json",
            "--incumbent", inc, "--candidate", cand,
            "--max-consultations", "5",
            "--incumbent-fingerprint", split["fingerprint"],
        )
        assert code == EXIT_CONFIG
        assert oa._holdout_key(split) not in out["error"]


class TestACloseThatFailsIsAConfigErrorNotATraceback:
    """Round 33's fix converted four of the lock's five filesystem stages.

    The acquire, the parent create, and the pid write all became
    `ConfigError`; the unlink already warned. `os.close` was left raw, in a
    `finally` whose comment reasoned about whether the descriptor may be
    retried and never about which document the caller reads. It is the same
    defect the round-33 fix was written to close, one stage further down, and
    it survived because the fix was aimed at the two calls the reviewer named
    rather than at the class of call they belonged to.

    A close-only failure is not hypothetical: a write to a network or quota
    backed filesystem can be buffered past `os.write` and reported by `close`,
    which is why POSIX documents `EIO` and `ENOSPC` there. On the ledger path
    `_digest_scrubbed` masks it. On the buffer path nothing does, so it exits
    1 with a traceback where a JSON document is promised.

    Precedence is the second property. When the write fails and the close then
    fails too, the write is the actionable cause; a `finally` that raises would
    replace it with the incidental one.
    """

    def _fail_close_for_lock(self, monkeypatch, errno_, message):
        """Fail `close` only for descriptors this module opened.

        Patching `os.close` wholesale would break pytest's own capture
        plumbing, which closes descriptors while the test runs.
        """
        ours = set()
        real_open, real_close = oa.os.open, oa.os.close

        def spy_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            ours.add(fd)
            return fd

        def spy_close(fd):
            if fd in ours:
                ours.discard(fd)
                real_close(fd)
                raise OSError(errno_, message)
            real_close(fd)

        monkeypatch.setattr(oa.os, "open", spy_open)
        monkeypatch.setattr(oa.os, "close", spy_close)

    def _fixture(self, tmp_path):
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        return tmp_path / "b.json", patches

    def test_a_close_that_fails_is_reported_as_a_config_error(
        self, tmp_path, capsys, monkeypatch
    ):
        buffer, patches = self._fixture(tmp_path)
        self._fail_close_for_lock(monkeypatch, 5, "I/O error")
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_the_message_names_the_lock_so_an_operator_can_act(
        self, tmp_path, capsys, monkeypatch
    ):
        buffer, patches = self._fixture(tmp_path)
        self._fail_close_for_lock(monkeypatch, 5, "I/O error")
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert "I/O error" in out["error"]
        assert str(buffer.with_suffix(".json.lock")) in out["error"] or ".lock" in out["error"]

    def test_a_write_failure_outranks_a_close_failure_that_follows_it(
        self, tmp_path, capsys, monkeypatch
    ):
        buffer, patches = self._fixture(tmp_path)
        self._fail_close_for_lock(monkeypatch, 5, "I/O error")
        monkeypatch.setattr(
            oa.os, "write",
            lambda *a, **k: (_ for _ in ()).throw(OSError(28, "No space left")),
        )
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert "No space left" in out["error"]
        assert "I/O error" not in out["error"]

    def test_a_close_failure_still_removes_the_lock_it_created(
        self, tmp_path, capsys, monkeypatch
    ):
        buffer, patches = self._fixture(tmp_path)
        self._fail_close_for_lock(monkeypatch, 5, "I/O error")
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert not (tmp_path / "b.json.lock").exists()

    def test_the_gate_still_scrubs_the_digest_out_of_a_close_failure(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(tmp_path / "root"))
        self._fail_close_for_lock(monkeypatch, 5, "I/O error")
        digest = "c" * 64
        with pytest.raises(oa.ConfigError) as caught:
            with oa._ledger_held(digest):
                pass
        assert digest not in str(caught.value)

    def test_a_successful_close_still_stores_the_rejection(self, tmp_path, capsys):
        buffer, patches = self._fixture(tmp_path)
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_OK
        assert out["added"] is True


@_NEEDS_PERMISSION_BARRIER
class TestAnUnreadableRecordIsNotAnEmptyOne:
    """`Path.exists()` answers False to two different questions.

    It is False when the file is absent, and False when whether it is absent
    cannot be determined because `stat` was refused. Both readers here treated
    that False as "nothing recorded yet", which is right for the first and
    the worst available answer for the second.

    On the buffer the cost is a verdict flip, not a crash. Measured against
    the same patch and the same buffer: readable, `buffer-check` reports
    `seen: true` and exits 1, the code the loop reads as "already rejected,
    do not retry". With the buffer's directory unreadable it reports
    `seen: false` and exits 0. An unreadable buffer silently un-rejects every
    rejection in it, and nothing in the output says so.

    On the ledger the cost is the budget. An unreadable ledger reads as zero
    consultations spent, which is the one answer that lets a caller keep
    spending. The ledger exists because a budget the caller supplies is not a
    budget; a budget the caller can erase by making the file unreadable is
    not one either.

    The fix is to ask the question that was meant: only `FileNotFoundError`
    means absent, and every other `OSError` is a config error, which is what
    `_read_json` already does one call further in.
    """

    def _sealed(self, tmp_path, name):
        holder = tmp_path / name
        holder.mkdir()
        return holder

    def _buffer_with_a_rejection(self, tmp_path, capsys):
        holder = self._sealed(tmp_path, "held")
        buffer = holder / "b.json"
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        return holder, buffer, patches

    def test_a_readable_buffer_still_reports_the_rejection(self, tmp_path, capsys):
        _, buffer, patches = self._buffer_with_a_rejection(tmp_path, capsys)
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert (code, out["seen"]) == (EXIT_LOGIC, True)

    def test_an_unreadable_buffer_does_not_report_the_rejection_as_unseen(
        self, tmp_path, capsys
    ):
        holder, buffer, patches = self._buffer_with_a_rejection(tmp_path, capsys)
        holder.chmod(0o000)
        try:
            code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        finally:
            holder.chmod(0o755)
        assert (code, out.get("seen")) != (EXIT_OK, False)

    def test_an_unreadable_buffer_is_reported_as_a_config_error(self, tmp_path, capsys):
        holder, buffer, patches = self._buffer_with_a_rejection(tmp_path, capsys)
        holder.chmod(0o000)
        try:
            code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            buffer,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        finally:
            holder.chmod(0o755)
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_an_absent_buffer_still_reads_as_nothing_rejected_yet(self, tmp_path, capsys):
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            tmp_path / "missing.json",
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert (code, out["seen"]) == (EXIT_OK, False)

    def _gate_fixture(self, tmp_path, capsys, monkeypatch):
        root = tmp_path / "ledger"
        root.mkdir()
        monkeypatch.setenv("EVAL_LEDGER_DIR", str(root))
        tasks = tmp_path / "tasks.txt"
        tasks.write_text("\n".join(f"t{i}" for i in range(12)), encoding="utf-8")
        _, split = _split(capsys, tmp_path, "--tasks", tasks, "--seed", "unread34")
        universe = [t for group in ("opt", "sel", "test") for t in split[group]]
        inc = _write(tmp_path, "i.json", {t: False for t in universe})
        cand = _write(tmp_path, "c.json", {t: True for t in universe})
        return root, split, inc, cand

    def _run_the_gate(self, capsys, tmp_path, split, inc, cand):
        return _run(
            capsys, "gate", "--split", tmp_path / "split.json",
            "--incumbent", inc, "--candidate", cand,
            "--max-consultations", "5",
            "--incumbent-fingerprint", split["fingerprint"],
        )

    def test_an_unreadable_ledger_does_not_read_as_an_unspent_budget(self, tmp_path):
        """Unit level on purpose: through the CLI this site is latent.

        `cmd_gate` takes the ledger lock before it reads the ledger, and the
        lock is created in the same directory, so any barrier strong enough to
        refuse `stat` on the ledger also refuses the lock's `mkdir` and fails
        one stage earlier. That ordering is a fact about today's call site, not
        a property anyone stated, and it is the only thing standing between
        this guard and a budget that reads as unspent because it could not be
        read. Fixed as the general form rather than left to the ordering.
        """
        holder = tmp_path / "sealed"
        holder.mkdir()
        ledger = holder / "k.ledger"
        ledger.write_text('{"consultations": 4}', encoding="utf-8")
        holder.chmod(0o000)
        try:
            with pytest.raises(oa.ConfigError):
                oa._read_ledger(ledger, "k", 5, None)
        finally:
            holder.chmod(0o755)

    def test_an_absent_ledger_still_reads_as_an_unspent_budget(self, tmp_path):
        assert oa._read_ledger(tmp_path / "gone.ledger", "k", 5, None) == 0

    def test_a_ledger_whose_own_mode_refuses_reading_was_already_refused(
        self, tmp_path, capsys, monkeypatch
    ):
        """The reachable half, kept as a regression guard.

        A file whose own mode is 000 still answers `stat`, because only the
        parent's execute bit gates that. So `exists()` was right here and
        `_read_json` reported the failure. This is the case the guard handled
        correctly, and it must keep working after the guard changes.
        """
        root, split, inc, cand = self._gate_fixture(tmp_path, capsys, monkeypatch)
        self._run_the_gate(capsys, tmp_path, split, inc, cand)
        ledger = next(root.glob("*.ledger"))
        ledger.chmod(0o000)
        try:
            code, out = self._run_the_gate(capsys, tmp_path, split, inc, cand)
        finally:
            ledger.chmod(0o644)
        assert code == EXIT_CONFIG
        assert oa._holdout_key(split) not in out["error"]

    def test_a_working_gate_still_spends_from_an_absent_ledger(
        self, tmp_path, capsys, monkeypatch
    ):
        _, split, inc, cand = self._gate_fixture(tmp_path, capsys, monkeypatch)
        code, _ = self._run_the_gate(capsys, tmp_path, split, inc, cand)
        assert code in (EXIT_OK, EXIT_LOGIC)


class TestAWrongPathIsNotAnotherProcess:
    """`mkdir(exist_ok=True)` raises `FileExistsError` when the parent is a file.

    The acquire block runs two filesystem calls under one `try`, and reads
    `FileExistsError` as contention. That reading is right for the second
    call: `os.open` with `O_CREAT | O_EXCL` raises it when the lock file is
    already there, which is exactly what one holder looks like to another.

    It is wrong for the first. `Path.mkdir(exist_ok=True)` swallows
    `FileExistsError` only when the path it found is a directory, and
    re-raises otherwise, so a plain file sitting where the lock's parent
    should be produces errno 17 with nothing holding anything.

    The operator is then told to wait for a process that does not exist, or
    to clear a stale lock that was never taken. The path is wrong, and the
    one message that would say so is the one the other branch prints.

    Found while checking a review's proposed test remedy rather than adopting
    it. The remedy was to replace a read-only directory with a file at the
    parent path, since a permission barrier does not hold on Windows or under
    root. The substitution keeps every assertion in those tests green, because
    both branches raise `ConfigError` at exit 2 and both name the lock, while
    silently moving them onto the branch that is not under test.
    """

    def _patches(self, tmp_path):
        return _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])

    def _add(self, capsys, tmp_path, buffer):
        return _run(
            capsys,
            "buffer-add",
            "--buffer",
            buffer,
            "--patches",
            self._patches(tmp_path),
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )

    def test_a_file_where_the_parent_belongs_is_not_reported_as_contention(
        self, tmp_path, capsys
    ):
        """Negative: errno 17 from `mkdir` must not borrow the holder message."""
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        _, out = self._add(capsys, tmp_path, occupied / "b.json")
        assert "another buffer-add holds" not in out["error"]

    def test_a_file_where_the_parent_belongs_is_reported_as_a_refusal(
        self, tmp_path, capsys
    ):
        """Positive: the operator is told the lock could not be taken."""
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        _, out = self._add(capsys, tmp_path, occupied / "b.json")
        assert "could not take the lock" in out["error"]

    def test_the_refusal_says_the_write_was_not_attempted(self, tmp_path, capsys):
        """Positive: the caller learns nothing was half-done."""
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        _, out = self._add(capsys, tmp_path, occupied / "b.json")
        assert "was not attempted" in out["error"]

    def test_a_file_where_the_parent_belongs_still_exits_config(
        self, tmp_path, capsys
    ):
        """Positive: the exit code stays the one that means config, not verdict."""
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        code, out = self._add(capsys, tmp_path, occupied / "b.json")
        assert (code, out["type"]) == (EXIT_CONFIG, "ConfigError")

    def test_a_file_further_up_the_path_is_also_a_refusal(self, tmp_path, capsys):
        """Edge: `parents=True` walks up, so the collision can be a level higher."""
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        _, out = self._add(capsys, tmp_path, occupied / "deeper" / "b.json")
        assert "another buffer-add holds" not in out["error"]
        assert out["type"] == "ConfigError"

    def test_a_symlink_to_a_file_is_also_a_refusal(self, tmp_path, capsys):
        """Edge: `mkdir` resolves the link, so the collision is one hop away."""
        target = tmp_path / "target"
        target.write_text("a file, not a directory")
        link = tmp_path / "link"
        link.symlink_to(target)
        _, out = self._add(capsys, tmp_path, link / "b.json")
        assert "another buffer-add holds" not in out["error"]
        assert out["type"] == "ConfigError"

    def test_a_real_holder_is_still_reported_as_contention(self, tmp_path, capsys):
        """Positive control: the branch under test keeps its own cause.

        This is the assertion the fix must not break. A lock file already on
        disk is what one holder looks like to another, and `os.open` with
        `O_EXCL` raising `FileExistsError` is the only evidence of it there is.
        """
        buffer = tmp_path / "b.json"
        lock = tmp_path / "b.json.lock"
        lock.write_text("4242")
        _, out = self._add(capsys, tmp_path, buffer)
        assert "another buffer-add holds" in out["error"]
        assert out["type"] == "ConfigError"

    def test_a_real_holder_does_not_borrow_the_refusal_message(
        self, tmp_path, capsys
    ):
        """Negative control: contention must not report as a refused lock."""
        buffer = tmp_path / "b.json"
        (tmp_path / "b.json.lock").write_text("4242")
        _, out = self._add(capsys, tmp_path, buffer)
        assert "could not take the lock" not in out["error"]

    def test_an_ordinary_add_still_takes_the_lock(self, tmp_path, capsys):
        """Positive control: the ordinary path is untouched by the split."""
        code, out = self._add(capsys, tmp_path, tmp_path / "b.json")
        assert code == EXIT_OK
        assert (tmp_path / "b.json").exists()

    def test_the_gate_reports_a_wrong_ledger_path_as_a_refusal(
        self, tmp_path, monkeypatch, capsys
    ):
        """Negative: the ledger caller shares the acquire and the same defect.

        Reached at unit level rather than through `cmd_gate`, whose contention
        message is deliberately vague about the path it locks, so the CLI
        cannot show which cause it printed. The helper is the seam both
        callers share, so the split belongs there and is tested there.
        """
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._lock_held(
                occupied / "l.lock", "another gate holds a lock", lambda exc: "w"
            ):
                pass
        assert "another gate holds" not in str(caught.value)
        assert "could not take the lock" in str(caught.value)

    def test_the_helper_still_reports_a_real_holder_to_the_gate(self, tmp_path):
        """Positive control: the ledger caller keeps its contention message."""
        lock = tmp_path / "l.lock"
        lock.write_text("4242")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._lock_held(lock, "another gate holds a lock", lambda exc: "w"):
                pass
        assert "another gate holds" in str(caught.value)


class TestACrashOnAHugeNumberIsNotARejectVerdict:
    """`OverflowError` is not one of the three exceptions `main` catches.

    `_as_float` asked `math.isfinite` before it asked whether the value was in
    range, and `math.isfinite` converts to float first. An integer past
    1.8e308 raised `OverflowError` there, which reached the top uncaught. The
    command printed a traceback and exited 1, and exit 1 is the REJECT
    verdict a driver branches on, so a malformed scorer file read as a
    decision that the candidate lost.

    These assert at the command boundary rather than the adapter, because the
    exit code is the whole finding. The adapter tests prove the refusal is an
    `AdapterError`; only running the command proves `main` turns that into a
    config failure with a JSON error document instead of a traceback.
    """

    # A float cannot hold this.
    HUGE = 10**400

    def test_a_huge_agent_run_exits_config_not_reject(self, capsys, tmp_path):
        report = _write(
            tmp_path,
            "r.json",
            {"per_fixture_pass_rates": {"C1": {"agent": [self.HUGE]}}, "error_count": 0},
        )
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == 2
        assert out["type"] == "AdapterError"
        assert "between" in out["error"]

    def test_a_huge_rule_score_exits_config_not_reject(self, capsys, tmp_path):
        """The rule path is shadowed by the degradation guard, not the adapter.

        A score past the scale is also an incomplete score block, so
        `_refuse_degraded_rule_report` reaches this input before the adapter's
        own range check does and names it a `ConfigError`. Both halves of the
        finding survive that: the exit is 2 rather than the 1 a driver reads as
        REJECT, and the failure arrives as one JSON document rather than a
        traceback. The adapter's own `AdapterError` refusal is unchanged and is
        proven directly in `tests/test_eval_optimizer_adapters.py`; asserting
        it again here would only pin which of two correct guards fires first.
        """
        scenarios = _write(
            tmp_path,
            "s.json",
            [
                {
                    "id": "S1",
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": self.HUGE,
                                "behavior_score": 5,
                                "citation_score": 5,
                            }
                        }
                    },
                }
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", scenarios)
        assert code == 2
        assert out["type"] == "ConfigError"
        assert "S1" in out["error"]

    def test_the_failure_arrives_as_one_json_document(self, capsys, tmp_path):
        """A traceback on stderr is not something a driver can parse."""
        report = _write(
            tmp_path,
            "r.json",
            {"per_fixture_pass_rates": {"C1": {"agent": [self.HUGE]}}, "error_count": 0},
        )
        oa.main(["extract", "--kind", "agent", "--input", str(report)])
        captured = capsys.readouterr()
        assert captured.err == ""
        assert set(json.loads(captured.out)) == {"error", "type"}

    def test_an_ordinary_report_still_exits_zero(self, capsys, tmp_path):
        report = _write(
            tmp_path,
            "r.json",
            {"per_fixture_pass_rates": {"C1": {"agent": [1.0]}}, "error_count": 0},
        )
        code, out = _run(capsys, "extract", "--kind", "agent", "--input", report)
        assert code == 0
        assert out["results"] == {"C1": True}


class TestCleanupCannotSpeakOverTheFailureItCleansUpAfter:
    """The same defect the lock's close fix closed, at the two sites it missed.

    Round 33 gave the lock a `_close_quietly`, whose whole argument is that
    POSIX frees the descriptor even when close reports an error, so the news
    is unactionable and reporting it replaces a cause an operator can use.
    That argument is about `os.close` in cleanup, not about the lock, and two
    other calls in this module were doing the same thing:

    - `_write_atomic` closes the descriptor by hand when `os.fdopen` fails to
      take ownership of it. A close error there propagates from inside the
      handler and pre-empts the original failure, so a non-`OSError` cause
      arrives as a `ConfigError` naming the close.
    - `_fsync_dir` closes the directory descriptor in a `finally` wrapped by a
      single `except OSError`. When the fsync fails and the close then fails
      too, the warning names the close. Worse on the success path: the fsync
      already worked, the replace already happened, and an escaping close
      error reaches `_write_atomic`'s handler and reports a completed write as
      a failed one.

    Both are one word: call the helper that was written for this. The
    enumeration behind that claim is four `os.close` sites in the module. Two
    were already safe, one suppressed and one deliberately converted while no
    primary failure is pending. These are the other two.
    """

    def _fail_close_on_ours(self, monkeypatch, errno_=5, message="secondary close"):
        """Fail close for descriptors this module opened, and no others.

        Patching `os.close` wholesale takes pytest's capture plumbing with it.
        """
        ours = set()
        real_open, real_close = oa.os.open, oa.os.close

        def spy_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            ours.add(fd)
            return fd

        def spy_close(fd):
            if fd in ours:
                ours.discard(fd)
                real_close(fd)
                raise OSError(errno_, message)
            real_close(fd)

        monkeypatch.setattr(oa.os, "open", spy_open)
        monkeypatch.setattr(oa.os, "close", spy_close)

    # --- _write_atomic, the fdopen cleanup --------------------------------

    def test_a_non_oserror_primary_survives_a_failing_cleanup_close(
        self, tmp_path, monkeypatch
    ):
        """`fdopen` can fail for reasons that are not I/O at all.

        The primary must reach the caller as itself. Converting it into a
        `ConfigError` about the close reports the wrong layer and the wrong
        cause.
        """
        self._fail_close_on_ours(monkeypatch)
        monkeypatch.setattr(
            oa.os,
            "fdopen",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("primary")),
        )
        with pytest.raises(RuntimeError, match="primary"):
            oa._write_atomic(tmp_path / "out.json", "{}")

    def test_the_cleanup_error_is_not_the_one_reported(self, tmp_path, monkeypatch):
        self._fail_close_on_ours(monkeypatch, message="secondary close")
        monkeypatch.setattr(
            oa.os,
            "fdopen",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("primary")),
        )
        with pytest.raises(RuntimeError) as caught:
            oa._write_atomic(tmp_path / "out.json", "{}")
        assert "secondary close" not in str(caught.value)

    def test_an_oserror_primary_still_becomes_a_config_error(
        self, tmp_path, monkeypatch
    ):
        """Control: the conversion this module promises must still happen."""
        self._fail_close_on_ours(monkeypatch)
        monkeypatch.setattr(
            oa.os,
            "fdopen",
            lambda *a, **k: (_ for _ in ()).throw(OSError(28, "primary no space")),
        )
        with pytest.raises(oa.ConfigError, match="primary no space"):
            oa._write_atomic(tmp_path / "out.json", "{}")

    def test_the_descriptor_is_still_released(self, tmp_path, monkeypatch):
        """Quiet is not skipped. A leak would trade one defect for another."""
        closed = []
        real_close = oa.os.close
        monkeypatch.setattr(
            oa.os,
            "close",
            lambda fd: (closed.append(fd), real_close(fd), None)[-1],
        )
        monkeypatch.setattr(
            oa.os,
            "fdopen",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("primary")),
        )
        with pytest.raises(RuntimeError):
            oa._write_atomic(tmp_path / "out.json", "{}")
        assert closed, "cleanup must still close the descriptor it owns"

    # --- _fsync_dir, the directory descriptor -----------------------------

    def _fail_dir_fsync(self, monkeypatch, errno_=28, message="primary no space"):
        """Fail fsync for directory descriptors only.

        `_write_atomic` fsyncs the file too, and failing that one would test a
        different branch.
        """
        real_fsync = oa.os.fsync

        def spy(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(errno_, message)
            return real_fsync(fd)

        monkeypatch.setattr(oa.os, "fsync", spy)

    def test_the_warning_names_the_fsync_not_the_close(
        self, tmp_path, capsys, monkeypatch
    ):
        self._fail_dir_fsync(monkeypatch)
        self._fail_close_on_ours(monkeypatch, message="secondary close")
        oa._write_atomic(tmp_path / "out.json", "{}")
        err = capsys.readouterr().err
        assert "primary no space" in err
        assert "secondary close" not in err

    def test_a_directory_fsync_failure_is_still_only_a_warning(
        self, tmp_path, capsys, monkeypatch
    ):
        """Control: the write completed, so this must not become an error."""
        self._fail_dir_fsync(monkeypatch)
        self._fail_close_on_ours(monkeypatch)
        target = tmp_path / "out.json"
        oa._write_atomic(target, '{"a": 1}')
        assert target.read_text(encoding="utf-8") == '{"a": 1}'
        assert "could not fsync the directory" in capsys.readouterr().err

    def test_a_close_failure_alone_does_not_fail_a_completed_write(
        self, tmp_path, capsys, monkeypatch
    ):
        """The success path. Nothing is pending, so the close has no news.

        Before the fix this error escaped `_fsync_dir` into `_write_atomic`'s
        handler, which reported a write that had already been replaced onto
        disk as a write that failed.
        """
        self._fail_close_on_ours(monkeypatch, message="secondary close")
        target = tmp_path / "out.json"
        oa._write_atomic(target, '{"a": 1}')
        assert target.read_text(encoding="utf-8") == '{"a": 1}'
        assert "secondary close" not in capsys.readouterr().err

    def test_an_ordinary_write_is_unchanged(self, tmp_path, capsys):
        """Control: no injection at all."""
        target = tmp_path / "out.json"
        oa._write_atomic(target, '{"a": 1}')
        assert target.read_text(encoding="utf-8") == '{"a": 1}'
        assert capsys.readouterr().err == ""


class TestABarOutsideItsScaleIsRefusedLikeAScoreOutsideIts:
    """The measurements are bounded now. The bars they are compared against were not.

    `_as_float` refuses a score outside its scale, on the argument that a value
    outside the range does what infinity does, only quietly: it decides a
    verdict without measuring anything. The bar sits on the other side of the
    same comparison and had no check at all, so the same defect was reachable
    from the command line instead of from a scorer file. Measured before the
    fix, against a fixture whose pass rate is 0.0:

        --pass-threshold -0.1  ->  {"C1": true}   exit 0
        --pass-threshold nan   ->  {"C1": false}  exit 0
        --pass-threshold inf   ->  {"C1": false}  exit 0
        --pass-threshold 2.0   ->  {"C1": false}  exit 0

    The first is the fail-closed property inverted: a fixture that satisfied
    none of its assertions was reported as passing, because a negative floor
    admits every rate there is. The rest mark every measured task false, and
    an all-false side reads as a real regression rather than as a bad flag.
    None of them says anything on the way past.

    One range check covers all four, because every comparison against NaN is
    False and infinity leaves any bounded interval, so both fall out of the
    same test that catches -0.1 and 2.0. That is also what `--max-p` has done
    since it was added, so this reuses a rule the module already applies
    rather than inventing a second one.
    """

    def _report(self, tmp_path, rate=0.0):
        return _write(
            tmp_path,
            "r.json",
            {"per_fixture_pass_rates": {"C1": {"agent": [rate]}}, "error_count": 0},
        )

    def _scen(self, tmp_path, score=3.0):
        return _write(
            tmp_path,
            "s.json",
            [
                {
                    "id": "S1",
                    "mechanisms": {
                        "full": {
                            "scores": {
                                "activation_score": score,
                                "behavior_score": score,
                                "citation_score": score,
                            }
                        }
                    },
                }
            ],
        )

    @pytest.mark.parametrize("bad", ["-0.1", "nan", "inf", "-inf", "2.0", "1.0001"])
    def test_a_pass_threshold_off_its_scale_is_refused(self, capsys, tmp_path, bad):
        # Joined with `=` because argparse reads a leading `-` as an option
        # unless the token parses as a number, so `--pass-threshold -inf` is
        # rejected as a missing argument before any of this code runs.
        code, out = _run(
            capsys,
            "extract",
            "--kind",
            "agent",
            "--input",
            self._report(tmp_path),
            f"--pass-threshold={bad}",
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert "--pass-threshold" in out["error"]

    @pytest.mark.parametrize("bad", ["-0.1", "nan", "inf", "-inf", "5.1", "6"])
    def test_a_min_score_off_its_scale_is_refused(self, capsys, tmp_path, bad):
        code, out = _run(
            capsys,
            "extract",
            "--kind",
            "rule",
            "--input",
            self._scen(tmp_path),
            f"--min-score={bad}",
        )
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"
        assert "--min-score" in out["error"]

    def test_the_refusal_names_the_scale_so_the_caller_can_correct_it(
        self, capsys, tmp_path
    ):
        code, out = _run(
            capsys,
            "extract",
            "--kind",
            "rule",
            "--input",
            self._scen(tmp_path),
            "--min-score",
            "6",
        )
        assert "[0, 5]" in out["error"]
        assert "6" in out["error"]

    def test_a_negative_floor_no_longer_passes_a_fixture_that_measured_nothing(
        self, capsys, tmp_path
    ):
        """The specific inversion, asserted as itself.

        A range check is the mechanism; this is the behavior it protects.
        """
        code, out = _run(
            capsys,
            "extract",
            "--kind",
            "agent",
            "--input",
            self._report(tmp_path, rate=0.0),
            "--pass-threshold",
            "-0.1",
        )
        assert code == EXIT_CONFIG
        assert "results" not in out

    # --- the ends of each scale are legal ---------------------------------

    @pytest.mark.parametrize("good", ["0", "0.0", "1", "1.0", "0.5"])
    def test_every_point_on_the_pass_rate_scale_is_accepted(
        self, capsys, tmp_path, good
    ):
        code, _ = _run(
            capsys,
            "extract",
            "--kind",
            "agent",
            "--input",
            self._report(tmp_path),
            "--pass-threshold",
            good,
        )
        assert code == EXIT_OK

    @pytest.mark.parametrize("good", ["0", "3.5", "5", "5.0"])
    def test_every_point_on_the_rule_scale_is_accepted(self, capsys, tmp_path, good):
        code, _ = _run(
            capsys,
            "extract",
            "--kind",
            "rule",
            "--input",
            self._scen(tmp_path),
            "--min-score",
            good,
        )
        assert code == EXIT_OK

    def test_a_floor_of_zero_still_passes_a_fixture_that_measured_nothing(
        self, capsys, tmp_path
    ):
        """Zero is inside the scale, so it stays legal and keeps its meaning.

        The fix refuses bars off the scale, not permissive ones on it.
        """
        code, out = _run(
            capsys,
            "extract",
            "--kind",
            "agent",
            "--input",
            self._report(tmp_path, rate=0.0),
            "--pass-threshold",
            "0",
        )
        assert code == EXIT_OK
        assert out["results"] == {"C1": True}

    def test_the_defaults_are_inside_their_own_scales(self, capsys, tmp_path):
        """Control: neither default may be refused by the check guarding it."""
        for kind, path in (
            ("agent", self._report(tmp_path)),
            ("rule", self._scen(tmp_path)),
        ):
            code, _ = _run(capsys, "extract", "--kind", kind, "--input", path)
            assert code == EXIT_OK

    def test_max_p_still_reports_its_own_scale_unchanged(self, capsys, tmp_path):
        """Control: the flag whose rule this reuses must keep its message."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": False for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _write(tmp_path, "tasks.txt", "")
        (tmp_path / "tasks.txt").write_text(
            "\n".join(f"t{i}" for i in range(10)), encoding="utf-8"
        )
        split = _split(capsys, tmp_path, "--tasks", tmp_path / "tasks.txt", "--seed", "s1")[1]
        split_path = tmp_path / "split.json"
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent",
            inc,
            "--candidate",
            cand,
            "--split",
            split_path,
            "--incumbent-fingerprint",
            str(split.get("fingerprint", "unknown")),
            "--max-p",
            "1.5",
        )
        assert code == EXIT_CONFIG
        assert "--max-p must be in [0, 1], got 1.5" in out["error"]


class TestAnIncompleteScoreMappingIsRefusedBeforeItIsReduced:
    """The degraded scan caught an empty score mapping and no partial one.

    Rule scoring needs three keys, so a scenario's score mapping has eight
    presence combinations. The scan refused exactly one of them, the empty
    mapping, and let the six partial ones through to a reduction that filled
    the gaps with zeros. Two recorded maxima and one absent key reduce to
    3.33, which clears `--min-score 3.0`, so a verdict was reported on a
    measurement that was never taken.

    The scan is fixed here as well as the adapter because they answer
    different questions. The adapter refuses the first scenario it cannot
    reduce; the scan enumerates every degraded scenario and names them
    together, which is the difference between fixing a report in one pass and
    fixing it one scenario per run.
    """

    def _scen(self, scores, sid="S1"):
        return {
            "id": sid,
            "negative_case": False,
            "mechanisms": {"full": {"scores": scores}},
        }

    def test_two_maxima_cannot_cover_a_third_measurement_at_a_low_bar(
        self, tmp_path, capsys
    ):
        """The reviewer's fixture: this reported a pass at --min-score 3.0."""
        path = _write(
            tmp_path,
            "partial.json",
            [self._scen({"activation_score": 5, "citation_score": 5})],
        )
        code, out = _run(
            capsys, "extract", "--kind", "rule", "--input", path, "--min-score", "3.0"
        )
        assert code == EXIT_CONFIG
        assert out.get("results") is None

    def test_the_refusal_names_the_incomplete_scenario(self, tmp_path, capsys):
        path = _write(
            tmp_path, "partial.json", [self._scen({"activation_score": 5}, sid="S9")]
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "S9" in out["error"]

    def test_an_empty_mapping_is_still_refused(self, tmp_path, capsys):
        path = _write(tmp_path, "empty.json", [self._scen({})])
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG

    def test_a_complete_report_still_extracts(self, tmp_path, capsys):
        path = _write(
            tmp_path,
            "full.json",
            [
                self._scen(
                    {
                        "activation_score": 5,
                        "citation_score": 5,
                        "behavior_score": 5,
                    }
                )
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_OK
        assert out["results"] == {"S1": True}

    def test_every_incomplete_scenario_is_listed_not_just_the_first(
        self, tmp_path, capsys
    ):
        """The scan exists so one run names every scenario that needs fixing."""
        path = _write(
            tmp_path,
            "many.json",
            [
                self._scen({"activation_score": 5}, sid="S1"),
                self._scen({"citation_score": 5}, sid="S2"),
                self._scen({"behavior_score": 5}, sid="S3"),
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        for sid in ("S1", "S2", "S3"):
            assert sid in out["error"]

    def test_a_complete_scenario_is_not_listed_beside_an_incomplete_one(
        self, tmp_path, capsys
    ):
        path = _write(
            tmp_path,
            "mixed.json",
            [
                self._scen(
                    {
                        "activation_score": 5,
                        "citation_score": 5,
                        "behavior_score": 5,
                    },
                    sid="GOOD",
                ),
                self._scen({"activation_score": 5}, sid="BAD"),
            ],
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "BAD" in out["error"]
        assert "GOOD" not in out["error"]

    def test_the_multi_rule_envelope_namespaces_the_incomplete_scenario(
        self, tmp_path, capsys
    ):
        envelope = {
            "rules": {
                "refactoring": {
                    "summary": {"verdict": "PASS"},
                    "scenarios": [self._scen({"activation_score": 5}, sid="S1")],
                }
            }
        }
        path = _write(tmp_path, "envelope.json", envelope)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "refactoring::S1" in out["error"]

    def test_two_rules_are_both_named_not_just_the_one_scored_first(
        self, tmp_path, capsys
    ):
        """Scoring inside the collection loop truncated the list at rule one."""
        envelope = {
            "rules": {
                "alpha": {
                    "summary": {"verdict": "PASS"},
                    "scenarios": [self._scen({"activation_score": 5}, sid="S1")],
                },
                "beta": {
                    "summary": {"verdict": "PASS"},
                    "scenarios": [self._scen({"citation_score": 5}, sid="S1")],
                },
            }
        }
        path = _write(tmp_path, "two.json", envelope)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "alpha::S1" in out["error"]
        assert "beta::S1" in out["error"]

    def test_a_judge_failure_is_still_reported_as_a_judge_failure(
        self, tmp_path, capsys
    ):
        """Ordering control: a broken judge must not be renamed a bad shape."""
        path = _write(
            tmp_path, "judge.json", [self._scen({"judge_failed": True}, sid="S5")]
        )
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "S5" in out["error"]


class TestADanglingSymlinkIsNotAnAbsentFile:
    """Absence was asked with a call that follows the link, so a broken one lied.

    `_absent` used `Path.stat`, which resolves the symlink before answering.
    A link whose target is gone therefore raised `FileNotFoundError` and read
    as "the file is not there", even though the directory entry is right there
    and `ls` shows it.

    Both readers fail open on absence by design, and that design is only safe
    when absence is true. A missing buffer is an empty buffer, so a dangling
    buffer link un-rejects every patch recorded in it. A missing ledger is an
    unspent budget, so a dangling ledger link resets the consultation count,
    which is the one integrity property the ledger exists to hold.

    The realistic way to get here is not an attack. It is a symlinked state
    directory pointing into a volume that did not mount, which is an ops
    mistake that should stop the run rather than silently restore the budget.

    `lstat` asks about the directory entry instead of the target, so the entry
    exists and absence is false. The dangling case is then named on its own
    rather than left to the reader, which would report "no such file" about a
    path the operator can see.
    """

    def _dangling(self, tmp_path, name):
        link = tmp_path / name
        link.symlink_to(tmp_path / "gone-target")
        return link

    def _patches(self, tmp_path):
        return _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])

    def test_buffer_check_refuses_a_dangling_buffer(self, tmp_path, capsys):
        link = self._dangling(tmp_path, "b.json")
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            link,
            "--patches",
            self._patches(tmp_path),
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code == EXIT_CONFIG
        assert out.get("seen") is None

    def test_buffer_add_refuses_a_dangling_buffer(self, tmp_path, capsys):
        link = self._dangling(tmp_path, "b.json")
        code, out = _run(
            capsys,
            "buffer-add",
            "--buffer",
            link,
            "--patches",
            self._patches(tmp_path),
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_CONFIG
        assert out.get("added") is None

    def test_buffer_add_leaves_the_dangling_link_in_place(self, tmp_path, capsys):
        link = self._dangling(tmp_path, "b.json")
        _run(
            capsys,
            "buffer-add",
            "--buffer",
            link,
            "--patches",
            self._patches(tmp_path),
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert link.is_symlink()
        assert not link.exists()

    def test_the_refusal_names_the_missing_target(self, tmp_path, capsys):
        link = self._dangling(tmp_path, "b.json")
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            link,
            "--patches",
            self._patches(tmp_path),
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code == EXIT_CONFIG
        assert "gone-target" in out["error"]

    def test_a_truly_absent_buffer_is_still_absent(self, tmp_path, capsys):
        """Control: the fail-open path this protects must still work."""
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            tmp_path / "none.json",
            "--patches",
            self._patches(tmp_path),
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code == EXIT_OK
        assert out["seen"] is False

    def test_a_symlink_to_a_real_buffer_is_read_through(self, tmp_path, capsys):
        """Control: only the broken link is refused, not every link."""
        real = _write(tmp_path, "real.json", [])
        link = tmp_path / "b.json"
        link.symlink_to(real)
        code, out = _run(
            capsys,
            "buffer-check",
            "--buffer",
            link,
            "--patches",
            self._patches(tmp_path),
            "--artifact",
            _STATIC_ARTIFACT,
        )
        assert code == EXIT_OK
        assert out["seen"] is False

    def _gate_fixture(self, tmp_path, capsys):
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(
            capsys, "split", "--results", inc, "--seed", "s1",
            "--out", tmp_path / "split.json",
        )
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        split = tmp_path / "split.json"
        record = json.loads(split.read_text(encoding="utf-8"))
        return inc, cand, split, record["fingerprint"]

    def _dangling_ledger(self, split):
        ledger = oa._ledger_root() / f"{_key_of(split)}.ledger"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.symlink_to(ledger.parent / "unmounted-volume.ledger")
        return ledger

    def test_a_dangling_ledger_does_not_reset_the_budget(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._gate_fixture(tmp_path, capsys)
        self._dangling_ledger(split)
        code, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split, "--max-consultations", "3",
            "--incumbent-fingerprint", fingerprint,
        )
        assert code == EXIT_CONFIG
        assert out.get("decision") is None
        assert out.get("consultations") is None

    def test_a_dangling_ledger_is_left_in_place(self, tmp_path, capsys):
        inc, cand, split, fingerprint = self._gate_fixture(tmp_path, capsys)
        ledger = self._dangling_ledger(split)
        _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split, "--max-consultations", "3",
            "--incumbent-fingerprint", fingerprint,
        )
        assert ledger.is_symlink()
        assert not ledger.exists()

    def test_an_absent_ledger_still_means_an_unspent_budget(self, tmp_path, capsys):
        """Control: the gate must still run its first consultation."""
        inc, cand, split, fingerprint = self._gate_fixture(tmp_path, capsys)
        code, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split, "--max-consultations", "3",
            "--incumbent-fingerprint", fingerprint,
        )
        assert code in (EXIT_OK, EXIT_LOGIC)
        assert out["consultations"] == 1


class TestAbsenceAsksAboutTheEntryNotTheTarget:
    """Unit-level enumeration of what `_absent` must answer for each entry."""

    def test_a_missing_entry_is_absent(self, tmp_path):
        assert oa._absent(tmp_path / "nothing") is True

    def test_a_regular_file_is_present(self, tmp_path):
        path = tmp_path / "f"
        path.write_text("{}", encoding="utf-8")
        assert oa._absent(path) is False

    def test_a_symlink_to_a_regular_file_is_present(self, tmp_path):
        target = tmp_path / "t"
        target.write_text("{}", encoding="utf-8")
        link = tmp_path / "l"
        link.symlink_to(target)
        assert oa._absent(link) is False

    def test_a_dangling_symlink_is_neither_absent_nor_readable(self, tmp_path):
        link = tmp_path / "l"
        link.symlink_to(tmp_path / "missing")
        with pytest.raises(oa.ConfigError, match="missing"):
            oa._absent(link)

    def test_a_symlink_loop_is_refused_rather_than_read_as_absent(self, tmp_path):
        """ELOOP is an OSError that is not FileNotFoundError."""
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.symlink_to(b)
        b.symlink_to(a)
        with pytest.raises(oa.ConfigError):
            oa._absent(a)

    def test_a_directory_is_present(self, tmp_path):
        assert oa._absent(tmp_path) is False


class TestAtomicWriteReplacesALinkRatherThanWritingThroughIt:
    """Characterization, not a contract: `os.replace` swaps the entry.

    `_write_atomic` renames a temp file over the destination path. When the
    destination is a symlink, POSIX rename replaces the link itself, so the
    target keeps its old contents and the link is gone. Writing through the
    link instead would need the caller to resolve it first, and that is a
    behavior change with its own risks: it would follow a link out of the
    intended directory, which is the reason rename does not do it.

    This test exists so the next reader learns the behavior from the suite
    rather than from a surprise, and so a deliberate change to it fails here
    first. It asserts what the code does today. It does not claim that is the
    right answer for every caller.
    """

    def test_a_symlinked_buffer_is_replaced_and_its_target_is_untouched(
        self, tmp_path, capsys
    ):
        real = _write(tmp_path, "real.json", [])
        link = tmp_path / "b.json"
        link.symlink_to(real)
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        code, _ = _run(
            capsys,
            "buffer-add",
            "--buffer",
            link,
            "--patches",
            patches,
            "--artifact",
            _STATIC_ARTIFACT,
            "--reason",
            "r",
        )
        assert code == EXIT_OK
        assert not link.is_symlink()
        assert json.loads(real.read_text(encoding="utf-8")) == []
        assert json.loads(link.read_text(encoding="utf-8")) != []
class TestARefusedLockNamesTheAncestorThatRefusedIt:
    """`mkdir` fails on an ancestor, and the lock's name does not say which.

    `_lock_refused` built its parenthetical from `exc.strerror or exc.errno`,
    which is the errno's generic text and nothing else. A thirty-seventh
    review reported that this loses the offending path. Checking the claim
    rather than adopting it narrowed it: for the `mkdir` stage the offending
    path is always an *ancestor* of the lock, and the lock is already in the
    message, so the path is a prefix of what the operator was shown. Nothing
    was lost. The first draft of this class asserted `str(parent) in error`
    and passed before the fix, which is how the overclaim was caught.

    Two things are genuinely missing. `parents=True` walks up, so with a deep
    lock path the message names four candidate ancestors and does not say
    which one is the regular file. And the errno number never appears, so the
    operator has the sentence "File exists" and no code to search on. Both
    are what `str(exc)` already formats as `[Errno 17] File exists: 'path'`.

    "File exists" beside a lock also reads as contention, which is the one
    conclusion the round-35 split exists to prevent. Splitting the acquire
    without fixing the sentence left the operator at the same wrong answer by
    a different route.

    `str(exc)` rather than reassembling errno, strerror, and filename by hand:
    the interpreter already formats all three, and a second formatter is a
    second thing to keep in step with the first.
    """

    def _add(self, capsys, tmp_path, buffer):
        patches = _write(tmp_path, "p.json", [{"op": "append", "text": "x"}])
        return _run(
            capsys,
            "buffer-add",
            "--buffer",
            str(buffer),
            "--patches",
            str(patches),
            "--artifact",
            str(_STATIC_ARTIFACT),
            "--reason",
            "r",
        )

    def test_the_failing_ancestor_is_named_as_a_path_not_as_a_prefix(
        self, tmp_path, capsys
    ):
        """Positive: the finding, stated so a prefix cannot satisfy it.

        The lock sits four levels below the regular file, so every ancestor
        appears inside the lock's own name. Asserting the quoted form is what
        separates "the operator can see which one" from "the characters are
        somewhere on the line".
        """
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        _, out = self._add(capsys, tmp_path, occupied / "a" / "b" / "c" / "b.json")
        assert f"{occupied} exists and is not a directory" in out["error"]

    def test_the_deeper_ancestors_are_not_the_ones_blamed(self, tmp_path, capsys):
        """Negative: only the ancestor that actually failed is quoted."""
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        _, out = self._add(capsys, tmp_path, occupied / "a" / "b" / "c" / "b.json")
        assert f"{occupied / 'a'} exists and is not" not in out["error"]

    def test_the_errno_reaches_the_operator(self, tmp_path, capsys):
        """Positive: the numeric code survives, so a search finds the cause."""
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        _, out = self._add(capsys, tmp_path, occupied / "b.json")
        assert "Errno 17" in out["error"]

    def test_the_refusal_is_still_a_config_error(self, tmp_path, capsys):
        """Positive control: the exit contract does not move with the wording."""
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        code, out = self._add(capsys, tmp_path, occupied / "b.json")
        assert code == EXIT_CONFIG
        assert out["type"] == "ConfigError"

    def test_a_real_holder_still_reports_contention_and_no_errno(
        self, tmp_path, capsys
    ):
        """Negative control: the contention branch keeps its own sentence.

        Contention is not an errno the operator should chase. `O_EXCL` raising
        `FileExistsError` is the mechanism, not the news, so this branch must
        not grow the code that the refusal branch just gained.
        """
        buffer = tmp_path / "b.json"
        (tmp_path / "b.json.lock").write_text("4242")
        _, out = self._add(capsys, tmp_path, buffer)
        assert "another buffer-add holds" in out["error"]
        assert "Errno" not in out["error"]

    def test_an_ordinary_add_is_unaffected(self, tmp_path, capsys):
        """Negative control: no refusal, no message, on the ordinary path."""
        code, _ = self._add(capsys, tmp_path, tmp_path / "b.json")
        assert code == EXIT_OK

    def test_an_error_carrying_no_filename_still_reads(self, tmp_path):
        """Edge: `exc.filename` is optional, and `None` must not be printed.

        `os.write` and `os.close` raise with no filename, so the parenthetical
        has to stay readable when the path the fix exists to add is absent.
        """
        message = oa._lock_refused(tmp_path / "l.lock", OSError(28, "No space left"))
        assert "None" not in message
        assert "No space left" in message
        assert "Errno 28" in message

    def test_the_lock_is_still_named_as_the_lock(self, tmp_path):
        """Edge: adding the offending path must not drop the one already there.

        Two paths in one sentence is the point. The lock says which operation
        was refused; the quoted filename says what refused it. Reporting only
        the second would trade one missing fact for another.
        """
        occupied = tmp_path / "occupied"
        occupied.write_text("a file, not a directory")
        lock = occupied / "a" / "l.lock"
        with pytest.raises(oa.ConfigError) as caught:
            with oa._lock_held(lock, "another gate holds a lock", lambda exc: "w"):
                pass
        assert str(lock) in str(caught.value)
        assert f"{occupied} exists and is not a directory" in str(caught.value)

    def test_the_held_out_digest_is_still_scrubbed_from_the_fuller_message(
        self, tmp_path
    ):
        """Edge: a longer message must not outrun the redaction seam.

        The parenthetical now carries a quoted filesystem path, and under the
        ledger every such path ends in the digest of the held-out set. The
        scrub reads the whole message rather than a list of known call sites,
        so it covers this, and that is the property worth pinning rather than
        assuming.
        """
        key = "a" * 16
        lock = tmp_path / f"{key}.lock"
        lock.write_text("4242")
        with pytest.raises(oa.ConfigError) as caught:
            with oa._digest_scrubbed(key):
                with oa._lock_held(lock, f"another gate holds {lock}", lambda e: "w"):
                    pass
        assert key not in str(caught.value)


class TestTheBlockingAncestorWalkNeverRaises:
    """A diagnostic that raises replaces a verdict with a crash.

    `_blocking_ancestor` runs inside the handler that builds a lock refusal.
    `main` catches `ConfigError` and not `OSError`, so an exception here exits
    1, and exit 1 is the REJECT verdict a driver branches on. That is the same
    defect this branch opened with, one function away.

    The helper carries no `suppress`, because `os.path.lexists` returns False
    on any `OSError` and `Path.is_dir` returns False on `OSError` or
    `ValueError`. That is a claim about two standard-library functions, so it
    is pinned here against the four hostile inputs rather than asserted in a
    comment: a mode-000 ancestor, a name past `NAME_MAX`, an embedded null
    byte, and a symlink loop.
    """

    def test_an_unreadable_ancestor_does_not_raise(self, tmp_path):
        """Edge: a mode-000 directory on the path is walked, not tripped over."""
        secret = tmp_path / "secret"
        (secret / "inner").mkdir(parents=True)
        secret.chmod(0o000)
        try:
            assert oa._blocking_ancestor(secret / "inner" / "x.lock") is None
        finally:
            secret.chmod(0o755)

    def test_an_unreadable_ancestor_is_not_blamed(self, tmp_path):
        """Negative: unreadable is not the same as not-a-directory.

        Blaming it would send the operator to delete a directory that is fine.
        """
        secret = tmp_path / "secret"
        (secret / "inner").mkdir(parents=True)
        secret.chmod(0o000)
        try:
            message = oa._lock_refused(
                secret / "inner" / "x.lock", OSError(13, "Permission denied")
            )
            assert "exists and is not a directory" not in message
        finally:
            secret.chmod(0o755)

    def test_a_name_past_the_filesystem_limit_does_not_raise(self, tmp_path):
        """Edge: ENAMETOOLONG is swallowed by both predicates."""
        assert oa._blocking_ancestor(tmp_path / ("z" * 5000) / "x.lock") is None

    def test_an_embedded_null_byte_does_not_raise(self, tmp_path):
        """Edge: the null byte raises `ValueError`, not `OSError`, at the syscall.

        `suppress(OSError)` would not have covered it. Both predicates do.
        """
        assert oa._blocking_ancestor(tmp_path / "a\x00b" / "x.lock") is None

    def test_a_symlink_loop_is_named_rather_than_skipped(self, tmp_path):
        """Positive: `lexists` sees the loop, so the operator is told about it.

        `exists` would resolve and report absent, and the loop would go
        unmentioned while `mkdir` kept failing on it.
        """
        loop = tmp_path / "loop"
        loop.symlink_to(loop)
        assert oa._blocking_ancestor(loop / "x.lock") == loop

    def test_a_dangling_symlink_is_named_rather_than_skipped(self, tmp_path):
        """Positive: the same reason, for the ordinary broken link."""
        link = tmp_path / "link"
        link.symlink_to(tmp_path / "gone")
        assert oa._blocking_ancestor(link / "x.lock") == link

    def test_an_all_directory_path_blames_nothing(self, tmp_path):
        """Negative control: nothing in the way means no clause."""
        (tmp_path / "a" / "b").mkdir(parents=True)
        assert oa._blocking_ancestor(tmp_path / "a" / "b" / "x.lock") is None

    def test_only_one_ancestor_can_ever_block(self, tmp_path):
        """Edge: walk order is unobservable, and that is worth writing down.

        A mutation that reversed the walk to outermost-first survived the
        whole suite. That is not a coverage gap. Nothing can exist beneath a
        regular file: `mkdir`, `write_text`, and `symlink_to` under one all
        raise `ENOTDIR`, so a path has at most one non-directory ancestor and
        both orders return it. The mutant is equivalent.

        The test that produced the survivor claimed the nearest blocker wins
        when two are on the path, which cannot happen and so could not fail.
        This asserts the reachable fact instead: the blocker is found no
        matter how deep below it the lock sits.
        """
        blocker = tmp_path / "outer" / "inner"
        blocker.parent.mkdir()
        blocker.write_text("a file, not a directory")
        for depth in range(1, 5):
            lock = blocker.joinpath(*("d",) * depth) / "x.lock"
            assert oa._blocking_ancestor(lock) == blocker

    def test_nothing_can_be_created_beneath_a_regular_file(self, tmp_path):
        """Edge: the premise the equivalence rests on, pinned rather than assumed.

        If a future filesystem or Python version let an entry exist under a
        regular file, the walk order would become observable and the class
        above would silently stop covering it.
        """
        blocker = tmp_path / "f"
        blocker.write_text("a file, not a directory")
        for make in (
            lambda: (blocker / "sub").mkdir(),
            lambda: (blocker / "sub").write_text("x"),
            lambda: (blocker / "sub").symlink_to(tmp_path),
        ):
            with pytest.raises(NotADirectoryError):
                make()


class TestExtractingARulePathAcrossRepeatedRuns:
    """`--input` takes several reports so the rule path can reduce them.

    ADR-087 Open Requirement 6 measured that one LLM judge reading is not
    evidence about an edit: identical rule text scored twice moved 5 of 24
    tasks across the pass threshold. The adapter gained
    `rule_results_multi`; this is the command-line surface that reaches it.

    A run is a whole report because that is how the ADR's own paired
    measurement was gathered, so nothing about `eval-rule-activation.py`
    changes.
    """

    @staticmethod
    def _scen(sid, triple, mech="full"):
        return {
            "id": sid,
            "negative_case": False,
            "mechanisms": {
                mech: {
                    "scores": {
                        "activation_score": triple[0],
                        "citation_score": triple[1],
                        "behavior_score": triple[2],
                    }
                }
            },
        }

    def test_one_input_still_behaves_exactly_as_before(self, tmp_path, capsys):
        path = _write(tmp_path, "r1.json", [self._scen("S1", (4, 4, 4))])
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_OK
        assert out["results"] == {"S1": True}

    def test_two_runs_are_reduced_before_the_bar_is_applied(self, tmp_path, capsys):
        """3.0 and 4.0 reduce to 3.5, which clears the inclusive floor.

        Neither report passes this scenario on its own under the default bar,
        so a result of True can only have come from the reduction.
        """
        low = _write(tmp_path, "low.json", [self._scen("S1", (3, 3, 3))])
        high = _write(tmp_path, "high.json", [self._scen("S1", (4, 4, 4))])
        code, out = _run(
            capsys, "extract", "--kind", "rule", "--input", low, high
        )
        assert code == EXIT_OK
        assert out["results"] == {"S1": True}

    def test_the_reduce_flag_reaches_the_rule_path(self, tmp_path, capsys):
        low = _write(tmp_path, "low.json", [self._scen("S1", (3, 3, 3))])
        high = _write(tmp_path, "high.json", [self._scen("S1", (5, 5, 5))])
        code, out = _run(
            capsys, "extract", "--kind", "rule",
            "--input", low, high, "--reduce", "min",
        )
        assert code == EXIT_OK
        assert out["results"] == {"S1": False}

    @staticmethod
    def _sampled(sid, *triples, mech="full"):
        """A scenario carrying repeated judge samples, one per triple."""
        samples = [
            {
                "activation_score": t[0],
                "citation_score": t[1],
                "behavior_score": t[2],
            }
            for t in triples
        ]
        return {
            "id": sid,
            "negative_case": False,
            "mechanisms": {
                mech: {"scores": dict(samples[0]), "score_samples": samples}
            },
        }

    def test_the_rule_reduce_flag_reaches_the_sample_path(self, tmp_path, capsys):
        """The flag has to move a verdict, not merely parse.

        An outside review pointed out that the audit table only proved
        `--rule-reduce` declares the same default its owner does. A wrapper
        that accepted `reduce_samples` and dropped it left all 1355 tests in
        the primary suites green, because nothing asserted the value arrived.

        One outlier sample per run, so `median` ignores it and `mean` does
        not, and the two answers land on opposite sides of the bar.
        """
        one = _write(tmp_path, "s1.json", [self._sampled("S1", (5, 5, 5), (5, 5, 5), (0, 0, 0))])
        two = _write(tmp_path, "s2.json", [self._sampled("S1", (5, 5, 5), (5, 5, 5), (0, 0, 0))])

        code, out = _run(
            capsys, "extract", "--kind", "rule",
            "--input", one, two, "--rule-reduce", "median",
        )
        assert code == EXIT_OK
        assert out["results"] == {"S1": True}

        code, out = _run(
            capsys, "extract", "--kind", "rule",
            "--input", one, two, "--rule-reduce", "mean",
        )
        assert code == EXIT_OK
        assert out["results"] == {"S1": False}

    def test_the_rule_reduce_flag_reaches_the_single_input_path_too(
        self, tmp_path, capsys
    ):
        """`extract` has two rule paths and only one is the multi-run one.

        A single `--input` takes the plain branch, which forwards the flag
        separately. Pinning both stops a fix to one from leaving the other
        reading its own default.
        """
        one = _write(tmp_path, "s1.json", [self._sampled("S1", (5, 5, 5), (5, 5, 5), (0, 0, 0))])
        assert _run(
            capsys, "extract", "--kind", "rule", "--input", one,
            "--rule-reduce", "median",
        )[1]["results"] == {"S1": True}
        assert _run(
            capsys, "extract", "--kind", "rule", "--input", one,
            "--rule-reduce", "mean",
        )[1]["results"] == {"S1": False}

    def test_the_rule_reduce_flag_reaches_the_envelope_path(self, tmp_path, capsys):
        """`extract --kind rule` has a third rule path, and it forwards alone.

        The multi-rule envelope, `{"rules": {...}}`, produces `<rule>::<id>`
        task ids through its own `rule_results_multi` call. Hardcoding the
        reducer at that call left all 731 tests green even after the flat
        paths above were pinned, so the envelope needs its own assertion.
        """
        scen = self._sampled("S1", (5, 5, 5), (5, 5, 5), (0, 0, 0))
        one = _write(
            tmp_path, "env1.json", {"rules": {"alpha": {"scenarios": [scen]}}}
        )
        two = _write(
            tmp_path, "env2.json", {"rules": {"alpha": {"scenarios": [scen]}}}
        )
        assert _run(
            capsys, "extract", "--kind", "rule", "--input", one, two,
            "--rule-reduce", "median",
        )[1]["results"] == {"alpha::S1": True}
        assert _run(
            capsys, "extract", "--kind", "rule", "--input", one, two,
            "--rule-reduce", "mean",
        )[1]["results"] == {"alpha::S1": False}

    def test_a_report_without_samples_is_unmoved_by_the_flag(self, tmp_path, capsys):
        """The negative control, and the compatibility claim the README makes.

        Every report written before `score_samples` existed has to read the
        same under all four reducers, or this flag silently rescored history.
        """
        path = _write(tmp_path, "plain.json", [self._scen("S1", (4, 4, 4))])
        seen = {
            r: _run(
                capsys, "extract", "--kind", "rule", "--input", path,
                "--rule-reduce", r,
            )[1]["results"]["S1"]
            for r in ("mean", "min", "max", "median")
        }
        assert seen == {"mean": True, "min": True, "max": True, "median": True}

    def test_runs_that_score_different_scenarios_are_refused(self, tmp_path, capsys):
        first = _write(tmp_path, "a.json", [self._scen("S1", (4, 4, 4))])
        second = _write(tmp_path, "b.json", [self._scen("S2", (4, 4, 4))])
        code, _ = _run(
            capsys, "extract", "--kind", "rule", "--input", first, second
        )
        assert code == EXIT_CONFIG

    def test_the_multi_rule_envelope_reduces_per_rule(self, tmp_path, capsys):
        low = _write(
            tmp_path, "e-low.json",
            {"rules": {"alpha": {"scenarios": [self._scen("S1", (3, 3, 3))]}}},
        )
        high = _write(
            tmp_path, "e-high.json",
            {"rules": {"alpha": {"scenarios": [self._scen("S1", (4, 4, 4))]}}},
        )
        code, out = _run(
            capsys, "extract", "--kind", "rule", "--input", low, high
        )
        assert code == EXIT_OK
        assert out["results"] == {"alpha::S1": True}

    def test_envelopes_that_disagree_on_rule_names_are_refused(self, tmp_path, capsys):
        one = _write(
            tmp_path, "e1.json",
            {"rules": {"alpha": {"scenarios": [self._scen("S1", (4, 4, 4))]}}},
        )
        two = _write(
            tmp_path, "e2.json",
            {"rules": {"beta": {"scenarios": [self._scen("S1", (4, 4, 4))]}}},
        )
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", one, two)
        assert code == EXIT_CONFIG

    def test_mixing_an_envelope_with_a_bare_array_is_refused(self, tmp_path, capsys):
        """Two shapes cannot be reduced against each other.

        A bare array names scenarios; an envelope namespaces them under a rule.
        Reducing one against the other would compare `S1` with `alpha::S1`.
        """
        bare = _write(tmp_path, "bare.json", [self._scen("S1", (4, 4, 4))])
        env = _write(
            tmp_path, "env.json",
            {"rules": {"alpha": {"scenarios": [self._scen("S1", (4, 4, 4))]}}},
        )
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", bare, env)
        assert code == EXIT_CONFIG

    def test_a_degraded_scenario_in_a_later_run_is_still_refused(self, tmp_path, capsys):
        """The degraded scan must read every run, not just the first."""
        good = _write(tmp_path, "g.json", [self._scen("S1", (4, 4, 4))])
        bad = _write(
            tmp_path, "b.json",
            [{"id": "S1", "negative_case": False,
              "mechanisms": {"full": {"error": "judge timed out"}}}],
        )
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", good, bad)
        assert code == EXIT_CONFIG

    def test_the_agent_kind_refuses_more_than_one_report(self, tmp_path, capsys):
        """`agent_results` already averages runs inside one report.

        Reducing two agent reports would average an average, weighting the
        report with fewer runs equally. Refusing says so instead of guessing.
        """
        one = _write(tmp_path, "a1.json", {"per_fixture_pass_rates": {"F1": {"agent": [1.0]}}})
        two = _write(tmp_path, "a2.json", {"per_fixture_pass_rates": {"F1": {"agent": [1.0]}}})
        code, _ = _run(capsys, "extract", "--kind", "agent", "--input", one, two)
        assert code == EXIT_CONFIG

    def test_the_hook_kind_refuses_more_than_one_report(self, tmp_path, capsys):
        """pytest is deterministic, so repeated runs measure nothing new."""
        xml = '<testsuite><testcase classname="t" name="a"/></testsuite>'
        one = tmp_path / "j1.xml"
        one.write_text(xml, encoding="utf-8")
        two = tmp_path / "j2.xml"
        two.write_text(xml, encoding="utf-8")
        code, _ = _run(capsys, "extract", "--kind", "hook", "--input", one, two)
        assert code == EXIT_CONFIG

    def test_the_refusal_names_the_count_it_was_given(self, tmp_path, capsys):
        one = _write(tmp_path, "a1.json", {"per_fixture_pass_rates": {}})
        two = _write(tmp_path, "a2.json", {"per_fixture_pass_rates": {}})
        three = _write(tmp_path, "a3.json", {"per_fixture_pass_rates": {}})
        code, out = _run(
            capsys, "extract", "--kind", "agent", "--input", one, two, three
        )
        assert code == EXIT_CONFIG
        assert "3" in out["error"]

    def test_a_hook_run_still_reads_its_single_input(self, tmp_path, capsys):
        xml = '<testsuite><testcase classname="t" name="a"/></testsuite>'
        path = tmp_path / "j.xml"
        path.write_text(xml, encoding="utf-8")
        code, out = _run(capsys, "extract", "--kind", "hook", "--input", path)
        assert code == EXIT_OK
        assert out["results"] == {"t::a": True}


class TestTwoRulesCannotCollapseIntoOneTaskId:
    """`<rule>::<scenario>` is only a key if the join cannot be ambiguous.

    The envelope namespaces scenario ids under a rule name because ids
    restart at S1 inside every rule. That join is not injective: rule `a`
    with scenario `b::c` and rule `a::b` with scenario `c` both render as
    `a::b::c`, and a plain dict assignment keeps whichever is written last.

    Losing a task is not a cosmetic problem on this path. The held-out set is
    the gate's whole evidence, so a swallowed held-out failure shrinks the
    denominator and reads as a cleaner candidate than the one that ran. The
    single-rule adapter and the JUnit adapter both already refuse duplicate
    ids; this is the same refusal for the only producer that lacked it.
    """

    @staticmethod
    def _scen(sid, value):
        return {
            "id": sid,
            "negative_case": False,
            "mechanisms": {
                "full": {
                    "scores": {
                        "activation_score": value,
                        "citation_score": value,
                        "behavior_score": value,
                    }
                }
            },
        }

    def _envelope(self, pairs):
        return {
            "rules": {
                name: {"scenarios": [self._scen(sid, value)]}
                for name, sid, value in pairs
            }
        }

    def test_a_collision_is_refused_rather_than_silently_resolved(
        self, tmp_path, capsys
    ):
        """Without the guard this returns one task and reports ACCEPT-able data."""
        payload = self._envelope([("a", "b::c", 5), ("a::b", "c", 0)])
        path = _write(tmp_path, "e.json", payload)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG
        assert "a::b::c" in out["error"]

    def test_the_refusal_names_both_rules_that_produced_the_id(
        self, tmp_path, capsys
    ):
        """A reader has to know which two rules to rename, not just that two exist."""
        payload = self._envelope([("a", "b::c", 5), ("a::b", "c", 0)])
        path = _write(tmp_path, "e.json", payload)
        _, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert "'a'" in out["error"]
        assert "'a::b'" in out["error"]

    def test_distinct_rules_that_do_not_collide_are_still_scored(
        self, tmp_path, capsys
    ):
        """The guard fires on an actual collision, not on the separator."""
        payload = self._envelope([("alpha", "S1", 5), ("beta", "S1", 5)])
        path = _write(tmp_path, "e.json", payload)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_OK
        assert out["results"] == {"alpha::S1": True, "beta::S1": True}

    def test_a_rule_name_holding_the_separator_is_allowed_when_unambiguous(
        self, tmp_path, capsys
    ):
        """Refusing every `::` in a name would refuse measurable input.

        The gate refuses what it cannot measure, not what looks unusual. This
        envelope renders two distinct ids, so it is measurable.
        """
        payload = self._envelope([("a::b", "S1", 5), ("c", "S1", 5)])
        path = _write(tmp_path, "e.json", payload)
        code, out = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_OK
        assert out["results"] == {"a::b::S1": True, "c::S1": True}

    def test_the_collision_is_refused_even_when_both_sides_agree(
        self, tmp_path, capsys
    ):
        """Agreement is luck, not measurement.

        Two tasks that happen to share a verdict still shrink the denominator
        by one when they merge, so the count the gate reasons about is wrong
        whether or not the surviving value is.
        """
        payload = self._envelope([("a", "b::c", 5), ("a::b", "c", 5)])
        path = _write(tmp_path, "e.json", payload)
        code, _ = _run(capsys, "extract", "--kind", "rule", "--input", path)
        assert code == EXIT_CONFIG


class TestARepeatedJsonKeyIsRefusedNotSilentlyCollapsed:
    """`json.loads` keeps the last value for a repeated key.

    `{"t0": false, "t0": true}` parses to `{'t0': True}` with no error, so
    every validator downstream inspects a mapping the file does not actually
    contain. `_checked_verdicts` cannot see a regression that the decoder
    already discarded, and the gate divides by a denominator that never held
    the failing task.

    This is the same class of defect as the task-id collision: two facts
    entering one key. The gate refuses input it cannot measure rather than
    picking a winner, so the decoder refuses too.
    """

    def _raw(self, tmp_path, name, text):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_repeated_key_is_refused_by_the_reader(self, tmp_path):
        path = self._raw(tmp_path, "r.json", '{"t0": false, "t0": true}')
        with pytest.raises(oa.ConfigError, match="t0"):
            oa._read_json(path)

    def test_the_refusal_says_the_key_repeats(self, tmp_path):
        path = self._raw(tmp_path, "r.json", '{"t0": false, "t0": true}')
        with pytest.raises(oa.ConfigError, match="repeat"):
            oa._read_json(path)

    def test_an_ordinary_document_still_parses(self, tmp_path):
        path = self._raw(tmp_path, "r.json", '{"a": 1, "b": [1, 2], "c": {"d": 3}}')
        assert oa._read_json(path) == {"a": 1, "b": [1, 2], "c": {"d": 3}}

    def test_the_same_key_in_two_different_objects_is_not_a_repeat(self, tmp_path):
        """Scoping matters. Only keys repeating within one object collide."""
        path = self._raw(tmp_path, "r.json", '{"a": {"x": 1}, "b": {"x": 2}}')
        assert oa._read_json(path) == {"a": {"x": 1}, "b": {"x": 2}}

    def test_a_repeat_nested_inside_the_document_is_caught(self, tmp_path):
        """The hook runs at every object, so depth does not hide a collision."""
        path = self._raw(
            tmp_path, "r.json", '{"results": {"t0": false, "t0": true}}'
        )
        with pytest.raises(oa.ConfigError, match="t0"):
            oa._read_json(path)

    def test_every_repeated_key_is_named_not_just_the_first(self, tmp_path):
        path = self._raw(
            tmp_path, "r.json", '{"a": 1, "a": 2, "b": 3, "b": 4}'
        )
        with pytest.raises(oa.ConfigError) as excinfo:
            oa._read_json(path)
        assert "a" in str(excinfo.value) and "b" in str(excinfo.value)

    def test_an_empty_object_and_an_empty_array_are_unaffected(self, tmp_path):
        path = self._raw(tmp_path, "r.json", '{"a": {}, "b": []}')
        assert oa._read_json(path) == {"a": {}, "b": []}

    def test_the_gate_refuses_a_candidate_that_hides_a_regression(
        self, tmp_path, capsys
    ):
        """The impact, end to end.

        Without the guard the candidate reads as all-passing, the gate finds
        no held-out loss and can ACCEPT while the file on disk says one task
        regressed.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": True for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        record = json.loads((tmp_path / "split.json").read_text(encoding="utf-8"))
        pairs = ", ".join(f'"t{i}": true' for i in range(12))
        cand = self._raw(tmp_path, "cand.json", "{" + pairs + ', "t0": false, "t0": true}')
        code, out = _run(capsys, "gate", "--incumbent", inc, "--candidate", cand,
                         "--split", tmp_path / "split.json",
                         "--max-consultations", "10",
                         "--incumbent-fingerprint", record["fingerprint"])
        assert code == EXIT_CONFIG
        assert "t0" in out["error"]

    def test_the_corpus_preflight_reports_absence_rather_than_raising(
        self, tmp_path
    ):
        """That reader promises never to raise on content, only on open."""
        path = self._raw(
            tmp_path,
            "r.json",
            '{"schema": "optimizer-results/1", "corpus": "a", "corpus": "b"}',
        )
        assert oa._corpus_header(path) is oa._UNREADABLE

    def test_an_unreadable_header_is_not_the_same_fact_as_no_corpus(
        self, tmp_path
    ):
        """Both used to answer None, and the gate reads them differently.

        A file that declares no corpus conflicts with a pin on purpose: that
        is what closes the envelope strip. A file nobody could parse has not
        declared anything, so answering the same way sends a malformed input
        down the anti-strip path and turns it into a verdict.
        """
        stripped = self._raw(
            tmp_path, "s.json", '{"schema": "optimizer-results/1", "results": {}}'
        )
        assert oa._corpus_header(stripped) is None
        assert oa._corpus_header(stripped) is not oa._UNREADABLE

    def test_a_malformed_candidate_is_not_a_computed_reject(
        self, capsys, tmp_path
    ):
        """The F2 refusal leaked around itself through the preflight.

        With a corpus-pinned pair the preflight ran first, read the duplicate
        key as "declares no corpus", and answered `decision: REJECT` with a
        reason saying the files disagree on a corpus. They agree. The file is
        unreadable, which is exit 2, and the reason given was false besides.
        """
        corpus = "a" * 64
        inc = _write(tmp_path, "inc.json", _enveloped(corpus, {f"t{i}": i < 5 for i in range(10)}))
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "cp1")
        split_path = _write(tmp_path, "split.json", split)
        cand = self._raw(
            tmp_path,
            "cand.json",
            '{"schema": "optimizer-results/1", "corpus": "' + corpus + '", '
            '"results": {"t0": false, "t0": true}}',
        )
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG, out
        assert out.get("decision") != "REJECT"
        assert "t0" in out.get("error", "")

    @pytest.mark.parametrize(
        ("corpus", "label"),
        [
            ("not-a-hash", "a string that is not hex at all"),
            ("abc123", "a truncated digest"),
            ("A" * 64, "sixty-four upper-case hex characters"),
            (17, "a number where a string belongs"),
            ("", "an empty string"),
            ("g" * 64, "sixty-four characters that are not all hex"),
        ],
    )
    def test_a_corpus_nobody_can_compare_is_not_a_computed_reject(
        self, capsys, tmp_path, corpus, label
    ):
        """The unreadable answer covered the grammar, not the field.

        Round thirty-nine gave `_corpus_header` a third answer for a file that
        would not parse. A file that parses cleanly but carries a corpus the
        authoritative reader refuses was left collapsed into `None`, which is
        the envelope strip, so the preflight answered `decision: REJECT` with
        a reason saying the two files disagree on a corpus. Neither file
        declares one that can be compared, so there is nothing to disagree
        about, and `_checked_corpus` raises on every value here.
        """
        pin = "c" * 64
        inc = _write(tmp_path, "inc.json", _enveloped(pin, {f"t{i}": i < 5 for i in range(10)}))
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "cp3")
        split_path = _write(tmp_path, "split.json", split)
        cand = _write(
            tmp_path, "cand.json", _enveloped(corpus, {f"t{i}": True for i in range(10)})
        )
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG, (label, out)
        assert out.get("decision") != "REJECT", (label, out)
        assert "corpus" in out.get("error", ""), (label, out)

    def test_the_incumbent_side_refuses_the_same_way(self, capsys, tmp_path):
        """The guard reads both headers, so both sides must answer alike.

        The preflight calls `_corpus_header` twice and refuses if either answer
        is unreadable. Every other case here puts the bad corpus on the
        candidate, which would pass just as well if the guard only looked at
        one argument.
        """
        pin = "d" * 64
        clean = _write(tmp_path, "clean.json", _enveloped(pin, {f"t{i}": i < 5 for i in range(10)}))
        _, split = _split(capsys, tmp_path, "--results", clean, "--seed", "cp4")
        split_path = _write(tmp_path, "split.json", split)
        bad = _write(
            tmp_path, "bad.json", _enveloped("not-a-hash", {f"t{i}": i < 5 for i in range(10)})
        )
        cand = _write(tmp_path, "cand.json", _enveloped(pin, {f"t{i}": True for i in range(10)}))
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", bad, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_CONFIG, out
        assert out.get("decision") != "REJECT", out

    def test_only_an_absent_or_null_corpus_reads_as_declaring_none(self, tmp_path):
        """The two answers that must stay `None`, and the ones that must not.

        `None` is a domain fact the conflict rule acts on. It has to mean
        exactly "parsed, and declares no corpus", or the rule acts on a file
        that declared something unusable.
        """
        absent = _write(tmp_path, "absent.json", {"schema": "optimizer-results/1",
                                                  "results": {"t0": True}})
        explicit = _write(tmp_path, "null.json", _enveloped(None, {"t0": True}))
        assert oa._corpus_header(absent) is None
        assert oa._corpus_header(explicit) is None
        for bad in ("not-a-hash", "", "A" * 64, 17):
            path = _write(tmp_path, "bad.json", _enveloped(bad, {"t0": True}))
            assert oa._corpus_header(path) is oa._UNREADABLE, bad

    def test_a_stripped_candidate_is_still_a_corpus_conflict(
        self, capsys, tmp_path
    ):
        """Negative control: the anti-strip rule must survive the fix.

        A readable file that declares no corpus beside a pinned one is the
        case the preflight exists for. If the fix for the malformed case
        widened into this one, stripping the envelope would stop being caught.
        """
        corpus = "b" * 64
        inc = _write(tmp_path, "inc.json", _enveloped(corpus, {f"t{i}": i < 5 for i in range(10)}))
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "cp2")
        split_path = _write(tmp_path, "split.json", split)
        cand = _write(tmp_path, "cand.json", _enveloped(None, {f"t{i}": True for i in range(10)}))
        code, out = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", cand,
            "--split", split_path, cap=5,
        )
        assert code == EXIT_LOGIC, out
        assert out["decision"] == "REJECT"
        assert "corpus" in out["reason"]


class TestAStdoutThatCannotBeWrittenIsNotARejectVerdict:
    """A closed pipe must not answer the question the gate was asked.

    `_emit` calls `print` unguarded. When the reader is gone the write
    raises, and `BrokenPipeError` is an `OSError`, so it slips past the
    `(ConfigError, AdapterError, ValueError)` handler and leaves `main`
    entirely. The interpreter answers that with exit 1, which this CLI
    defines as REJECT: a verdict on a comparison that never finished.

    Measured on this branch before the fix, both in real subprocesses:
    `split` over 20000 tasks piped to a closed reader exited 1 with a
    traceback, and a small payload exited 120 because CPython overrides the
    status when it cannot flush stdout at shutdown. Neither is EXIT_CONFIG,
    and for `gate` the ledger write precedes the final emit, so a
    consultation was spent and the answer thrown away.

    The handler cannot report on the stream that just failed, so it stops
    trying. The exit code carries the whole message: no decision was
    produced.
    """

    class _Broken(io.TextIOBase):
        def write(self, s: str) -> int:
            raise BrokenPipeError(32, "broken pipe")

    def test_a_broken_stdout_answers_config_not_reject(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", self._Broken())
        assert oa.main(["budget", "--step", "1", "--total", "10"]) == EXIT_CONFIG

    def test_the_error_does_not_escape_main(self, monkeypatch):
        """Escaping is the defect. Returning any code at all is the fix."""
        monkeypatch.setattr(sys, "stdout", self._Broken())
        oa.main(["budget", "--step", "1", "--total", "10"])

    def test_a_broken_stdout_on_the_error_path_also_answers_config(
        self, tmp_path, monkeypatch
    ):
        """The old handler answered a failed write with a second write."""
        missing = tmp_path / "nope.json"
        monkeypatch.setattr(sys, "stdout", self._Broken())
        assert oa.main(["extract", "--kind", "rule", "--input", str(missing)]) == (
            EXIT_CONFIG
        )

    def test_a_gate_that_cannot_report_does_not_report_reject(
        self, tmp_path, capsys, monkeypatch
    ):
        """The impact. EXIT_LOGIC here would be a verdict nobody computed."""
        inc = _write(tmp_path, "inc.json", {f"t{i}": i % 3 != 0 for i in range(12)})
        _run(capsys, "split", "--results", inc, "--seed", "s1",
             "--out", tmp_path / "split.json")
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(12)})
        record = json.loads((tmp_path / "split.json").read_text(encoding="utf-8"))
        monkeypatch.setattr(sys, "stdout", self._Broken())
        code = oa.main(["gate", "--incumbent", str(inc), "--candidate", str(cand),
                        "--split", str(tmp_path / "split.json"),
                        "--max-consultations", "10",
                        "--incumbent-fingerprint", record["fingerprint"]])
        assert code == EXIT_CONFIG
        assert code != EXIT_LOGIC

    def test_a_broken_stderr_on_the_help_path_is_not_a_traceback(
        self, monkeypatch
    ):
        """`print_help` writes to stderr and sat outside the old guard."""
        monkeypatch.setattr(sys, "stderr", self._Broken())
        assert oa.main([]) == EXIT_CONFIG

    def test_an_ordinary_run_is_untouched(self, capsys):
        code, out = _run(capsys, "budget", "--step", "1", "--total", "10")
        assert code == EXIT_OK
        assert out

    def test_the_installed_script_exits_config_on_a_closed_reader(self, tmp_path):
        """End to end, on the process rather than the function.

        The read end is closed before the child runs, so the write raises
        rather than racing a shell reader that may or may not have exited.
        """
        big = tmp_path / "big.json"
        big.write_text(
            json.dumps({f"task-identifier-{i}": True for i in range(20000)}),
            encoding="utf-8",
        )
        proc = subprocess.Popen(
            [sys.executable, str(_SCRIPT), "split", "--results", str(big),
             "--seed", "s1", "--out", str(tmp_path / "s.json")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert proc.stdout is not None
        proc.stdout.close()
        stderr = proc.communicate()[1]
        assert proc.returncode == EXIT_CONFIG, stderr[:400]
        assert "Traceback" not in stderr

    def test_a_flush_that_fails_replaces_the_code_it_was_given(self, monkeypatch):
        """The 120 case, without racing a shell.

        CPython replaces the status when its own shutdown flush fails, so the
        flush happens here first and the failure becomes EXIT_CONFIG.
        """
        monkeypatch.setattr(sys, "stdout", _Unflushable())
        assert oa._final_exit_code(EXIT_OK) == EXIT_CONFIG

    def test_a_working_flush_keeps_the_code_it_was_given(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        assert oa._final_exit_code(EXIT_LOGIC) == EXIT_LOGIC

    def test_a_reject_survives_a_working_flush(self, monkeypatch):
        """A real REJECT must not be rewritten into a config failure."""
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        assert oa._final_exit_code(EXIT_LOGIC) != EXIT_CONFIG

    def test_a_failed_flush_says_why_the_code_changed(self, monkeypatch, capsys):
        """Exit 2 with an empty stderr tells the operator nothing.

        This path rewrites the status the command computed, so the reason has
        to reach someone. The write-time guard in `main` already reports, and
        a caller that hits the flush-time mode instead should not have to
        guess which of the two it got.
        """
        monkeypatch.setattr(sys, "stdout", _Unflushable())
        assert oa._final_exit_code(EXIT_OK) == EXIT_CONFIG
        assert "could not write" in capsys.readouterr().err

    def test_a_working_flush_stays_quiet(self, monkeypatch, capsys):
        """Negative control: the message belongs to the failure, not the path."""
        monkeypatch.setattr(sys, "stdout", io.StringIO())
        assert oa._final_exit_code(EXIT_OK) == EXIT_OK
        assert capsys.readouterr().err == ""

    def test_reporting_a_dead_stdout_does_not_need_a_live_stderr(self, monkeypatch):
        """Both streams close together often enough that this cannot assume one.

        `_warn` already suppresses its own failure. This holds that the exit
        path keeps relying on it rather than growing a second unguarded write.
        """
        monkeypatch.setattr(sys, "stdout", _Unflushable())
        monkeypatch.setattr(sys, "stderr", _Unflushable())
        assert oa._final_exit_code(EXIT_OK) == EXIT_CONFIG

    def test_a_small_payload_into_a_closed_reader_reports_on_stderr(self, tmp_path):
        """The end-to-end half of the two modes, measured rather than assumed.

        A payload under the pipe buffer is written successfully and fails at
        the shutdown flush, which is the mode that used to exit 120. The large
        payload above covers the write-time mode.
        """
        proc = subprocess.Popen(
            [sys.executable, str(_SCRIPT), "budget", "--step", "1", "--total", "5"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert proc.stdout is not None
        proc.stdout.close()
        stderr = proc.communicate()[1]
        assert proc.returncode == EXIT_CONFIG, stderr[:400]
        assert "could not write" in stderr
        assert "Traceback" not in stderr

    def test_a_closed_stream_is_refused_the_same_as_a_broken_one(self, tmp_path):
        """A closed file raises ValueError, not OSError, so the guard missed it.

        `sys.stdout.close()` then writing gives "I/O operation on closed
        file", a ValueError. The guard named only OSError, so an embedding
        harness with a closed stdout got exit 1, which is REJECT, plus a
        traceback. Measured at exit 1 before this.
        """
        proc = subprocess.run(
            [sys.executable, "-c", _CLOSED_STDOUT_DRIVER, str(_SCRIPT)],
            capture_output=True, text=True,
        )
        assert proc.returncode == EXIT_CONFIG, proc.stderr[:400]
        assert "Traceback" not in proc.stderr

    def test_the_status_survives_a_stream_the_redirect_cannot_reach(self):
        """The devnull fallback is what stops 120, and it can itself fail.

        `os.dup2` needs a descriptor. A stand-in stream has none, so the
        broken stream stayed installed and CPython flushed it again on the way
        out, replacing the status with 120 after this code had already decided
        on 2. Measured at 120 before this. The test runs in a subprocess
        because pytest restores stdout before interpreter shutdown, so an
        in-process assertion on the return value cannot see the override.
        """
        proc = subprocess.run(
            [sys.executable, "-c", _NO_FILENO_DRIVER, str(_SCRIPT)],
            capture_output=True, text=True,
        )
        assert proc.returncode == EXIT_CONFIG, proc.stderr[:400]
        assert "Exception ignored" not in proc.stderr

    def test_a_closed_stream_at_flush_time_is_also_a_config_failure(
        self, monkeypatch, tmp_path
    ):
        """The unit-level half of the ValueError gap, on the exit path.

        A real file object is the stand-in, not `io.StringIO`. A closed
        StringIO's flush returns quietly, so it cannot reach this branch; the
        stream this guards is a TextIOWrapper, whose flush raises after close.
        """
        stream = (tmp_path / "out").open("w", encoding="utf-8")
        stream.close()
        monkeypatch.setattr(sys, "stdout", stream)
        assert oa._final_exit_code(EXIT_OK) == EXIT_CONFIG

    def test_the_new_guard_does_not_leak_held_out_membership(
        self, tmp_path, capsys, monkeypatch
    ):
        """The guard reports the failure, so it could have reported the digest.

        `main` writes `str(exc)` through `_warn`, and every ledger and lock
        filename ends in an unsalted hash of the held-out set. The scrubber
        turns every OSError under the ledger into a ConfigError with the name
        replaced, so the guard never sees one carrying the digest. This holds
        that line, because a guard added to stop a wrong verdict must not buy
        it with a leak.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 5 for i in range(10)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "pe2")
        split_path = _write(tmp_path, "split.json", split)
        key = oa._holdout_key(split)
        monkeypatch.setattr(oa, "_corpus_header", lambda _p: (_ for _ in ()).throw(
            OSError(f"cannot open {key}")
        ))
        code, _ = _run_gate(
            capsys, tmp_path, "--incumbent", inc, "--candidate", inc,
            "--split", split_path, cap=5,
        )
        captured = capsys.readouterr()
        assert code == EXIT_CONFIG
        assert key not in captured.err
        assert key not in captured.out


class TestTheReadmeSpellsValuesTheCodeDeclares:
    """A value written into prose has a second author and nothing pins it.

    Rounds 40, 41 and 42 each declared the duplication class closed and each
    was reopened, because every audit searched for the shape of the previous
    fix rather than the shape of the defect. The defect is one value with two
    authors, wherever the first author keeps it: a module constant, a function
    signature, or a sentence.

    Prose is the author no mutation reaches. Renaming a constant turns its own
    tests red and leaves the paragraph describing the old value, unchanged and
    still the first thing an operator reads. An audit anchored on argparse
    found six duplications and missed these, which are the same defect one file
    over.

    These are not tautologies. One side is a Python constant, the other is a
    file on disk, and nothing moves them together.
    """

    def test_the_envelope_example_carries_the_schema_extract_writes(self):
        """The documented envelope is what a reader copies into a fixture.

        `_RESULTS_SCHEMA` is what `extract` stamps and what `gate` refuses a
        mismatch against, so a stale example teaches an operator to build a
        file the tool rejects, and the rejection names a schema they never
        typed.
        """
        block = _readme_paragraph('"schema":')
        assert f'"schema": "{oa._RESULTS_SCHEMA}"' in block

    def test_the_reject_sentence_names_the_reject_exit_code(self):
        """A shell loop branches on this number, so prose is its interface.

        Anchored on the full sentence opening rather than on `exit 1` alone.
        Both exit codes live in one paragraph, so a bare search for the number
        would pass on the argument-error sentence next to it and report
        agreement that is not there.
        """
        para = _readme_paragraph("A reject is exit")
        assert f"A reject is exit {oa.EXIT_LOGIC} " in para

    def test_the_argument_error_sentence_names_the_config_exit_code(self):
        """The other half of the same paragraph, anchored the same way."""
        para = _readme_paragraph("stderr, exit")
        assert f"stderr, exit {oa.EXIT_CONFIG}," in para


class TestEveryMissingFileReadsTheSameWay:
    """A typo in a path is the commonest operator mistake, so it gets one voice.

    `_read_json` turns a missing file into `no such file: <path>`, and every
    input reached that message except one. The gate peeks at the corpus header
    of `--incumbent` and `--candidate` before the full read, and that peek
    opened the file itself while catching only the decode failures. A missing
    file therefore escaped as a bare `OSError`, which `_digest_scrubbed`
    stringified into `[Errno 2] No such file or directory: 'nope.json'`.

    The same mistake reported two ways depending on which flag carried it. The
    peek stops being the layer that names the failure, which it was never
    meant to be, by reading through `_read_text` and letting the `ConfigError`
    that reader already raises travel past its own decode clause.

    The first attempt answered `_UNREADABLE` instead, on the argument that
    `_corpus_refused` declines to decide on an unreadable file so the full
    read would still raise. An outside review found the hole: the full read is
    not what runs next. `_guard` is, and an exhausted consultation budget
    turns a missing file into a REJECT at exit 1. A file that cannot be opened
    has to be refused before anything that can emit a decision, which is what
    the last test here pins.
    """

    def _split_for(self, tmp_path, capsys):
        inc = _write(tmp_path, "real.json", {f"t{i}": True for i in range(8)})
        _, split = _split(capsys, tmp_path, "--results", inc, "--seed", "s1")
        return _write(tmp_path, "split.json", split)

    def test_a_missing_incumbent_names_the_file_the_way_every_reader_does(
        self, tmp_path, capsys
    ):
        split_path = self._split_for(tmp_path, capsys)
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent", tmp_path / "nope.json",
            "--candidate", tmp_path / "real.json",
            "--split", split_path,
        )
        assert code == EXIT_CONFIG
        assert out["error"] == f"no such file: {tmp_path / 'nope.json'}"

    def test_a_missing_candidate_names_the_file_the_same_way(self, tmp_path, capsys):
        split_path = self._split_for(tmp_path, capsys)
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent", tmp_path / "real.json",
            "--candidate", tmp_path / "gone.json",
            "--split", split_path,
        )
        assert code == EXIT_CONFIG
        assert out["error"] == f"no such file: {tmp_path / 'gone.json'}"

    def test_a_missing_file_outranks_an_exhausted_budget(self, tmp_path, capsys):
        """The peek must refuse before anything that can emit a decision.

        `_gate_entry` runs the header peek, then takes the ledger lock, then
        runs `_guard`, and only then does the authoritative read. So a peek
        that answers instead of raising hands the next decision-producing
        guard a file nobody could open. With the budget already spent, the
        gate reported REJECT at exit 1 for a path that does not exist, telling
        the operator to re-split when the real fix was to fix the typo.

        This is the test the first version of the fix would have failed. It
        does not assert the message, only that a config error still outranks a
        verdict, which is the property the ordering has to preserve.
        """
        inc = _write(tmp_path, "inc.json", {f"t{i}": i < 2 for i in range(10)})
        cand = _write(tmp_path, "cand.json", {f"t{i}": True for i in range(10)})
        _, record = _split(capsys, tmp_path, "--results", inc, "--seed", "pin")
        split_path = _write(tmp_path, "split.json", record)
        fp = str(record["fingerprint"])

        code, out = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split_path, "--max-consultations", "1",
            "--incumbent-fingerprint", fp,
        )
        assert code == EXIT_OK, out

        spent, _ = _run(
            capsys, "gate", "--incumbent", inc, "--candidate", cand,
            "--split", split_path, "--max-consultations", "1",
            "--incumbent-fingerprint", fp,
        )
        assert spent == EXIT_LOGIC

        code, out = _run(
            capsys, "gate", "--incumbent", tmp_path / "typo.json", "--candidate", cand,
            "--split", split_path, "--max-consultations", "1",
            "--incumbent-fingerprint", fp,
        )
        assert code == EXIT_CONFIG, out
        assert "decision" not in out
        assert out["error"] == f"no such file: {tmp_path / 'typo.json'}"

    def test_no_errno_prefix_survives_on_any_input_flag(self, tmp_path, capsys):
        """One assertion over both peeked flags, so neither regresses alone."""
        split_path = self._split_for(tmp_path, capsys)
        real = tmp_path / "real.json"
        leaked = []
        for flag in ("--incumbent", "--candidate"):
            argv = {"--incumbent": real, "--candidate": real}
            argv[flag] = tmp_path / "absent.json"
            _, out = _run_gate(
                capsys,
                tmp_path,
                "--incumbent", argv["--incumbent"],
                "--candidate", argv["--candidate"],
                "--split", split_path,
            )
            if "Errno" in str(out.get("error", "")):
                leaked.append((flag, out["error"]))
        assert leaked == []

    def test_a_directory_in_place_of_a_report_is_still_named_by_the_full_read(
        self, tmp_path, capsys
    ):
        """`IsADirectoryError` is the other OSError the peek can meet.

        The guarantee is not that errno text disappears. `_read_text` keeps it
        for the unusual failures, where the OS detail is the only thing that
        says what went wrong, and it prefixes them with `could not read
        <path>` so the file is named first. The guarantee is that the peek
        stops being the layer that answers: whatever the operator sees comes
        from the authoritative reader, in that reader's shape.
        """
        split_path = self._split_for(tmp_path, capsys)
        adir = tmp_path / "a_dir"
        adir.mkdir()
        code, out = _run_gate(
            capsys,
            tmp_path,
            "--incumbent", adir,
            "--candidate", tmp_path / "real.json",
            "--split", split_path,
        )
        assert code == EXIT_CONFIG
        assert out["error"].startswith(f"could not read {adir}: ")


class TestDuplicateKeysAreRefusedBeforeAnythingReadsTheObject:
    """`_no_duplicate_keys` is the hook that makes a restated fact visible.

    `json.loads` keeps the last value for a repeated key and reports nothing,
    so a candidate stating `{"t0": false, "t0": true}` reaches the gate as a
    single passing task. The hook existed with one end-to-end test behind it,
    which pins that the gate refuses such a file but not what the hook itself
    does with the shapes the parser can hand it.
    """

    def test_a_document_without_repeats_builds_the_ordinary_object(self):
        assert oa._no_duplicate_keys([("a", 1), ("b", 2)]) == {"a": 1, "b": 2}

    def test_an_empty_object_is_not_a_duplicate(self):
        assert oa._no_duplicate_keys([]) == {}

    def test_a_repeated_key_raises_and_names_it(self):
        with pytest.raises(oa._DuplicateKeyError) as exc:
            oa._no_duplicate_keys([("t0", False), ("t0", True)])
        assert exc.value.keys == ["t0"]

    def test_a_key_repeated_with_the_same_value_is_still_a_repeat(self):
        """Equal values do not make the document state the fact once.

        The defect is a producer that emitted a key twice, and that is worth
        refusing whether or not the two copies happen to agree. Comparing
        values would also make the rule depend on `==`, which is a different
        question than how many times the document spoke.
        """
        with pytest.raises(oa._DuplicateKeyError) as exc:
            oa._no_duplicate_keys([("t0", True), ("t0", True)])
        assert exc.value.keys == ["t0"]

    def test_every_repeated_key_is_listed_once_and_sorted(self):
        with pytest.raises(oa._DuplicateKeyError) as exc:
            oa._no_duplicate_keys(
                [("b", 1), ("a", 1), ("b", 2), ("a", 2), ("b", 3), ("c", 1)]
            )
        assert exc.value.keys == ["a", "b"]

    def test_the_hook_runs_on_nested_objects_too(self):
        """The parser calls the hook per object, so nesting is not an escape."""
        with pytest.raises(oa._DuplicateKeyError) as exc:
            json.loads(
                '{"outer": {"t0": false, "t0": true}}',
                object_pairs_hook=oa._no_duplicate_keys,
            )
        assert exc.value.keys == ["t0"]

    def test_repeats_in_sibling_objects_are_reported_by_the_first_to_close(self):
        """Each object is its own document fragment and refuses on its own."""
        with pytest.raises(oa._DuplicateKeyError) as exc:
            json.loads(
                '{"a": {"x": 1, "x": 2}, "b": {"y": 1, "y": 2}}',
                object_pairs_hook=oa._no_duplicate_keys,
            )
        assert exc.value.keys == ["x"]

    def test_a_duplicate_error_is_a_value_error_so_peeks_can_catch_it(self):
        """`_corpus_header` promises `_UNREADABLE` for every content problem.

        It catches `ValueError`, and a duplicate key is a content problem, so
        the subclassing is what keeps that promise true.
        """
        assert issubclass(oa._DuplicateKeyError, ValueError)
