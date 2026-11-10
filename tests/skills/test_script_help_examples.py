"""Keep every skill script's ``--help`` examples runnable against its own parser.

The agentskills.io guide "Using scripts in skills" makes ``--help`` the agent's
main way to learn a script. A script with an ``epilog`` must show real examples
and its exit codes. Each example is parsed with the script's own
``ArgumentParser``, so an example cannot name a flag the code no longer has.

Discovery is static: a script is covered when it defines an entry point (an
``if __name__ == "__main__"`` guard) and its source holds the ``%(prog)s``
placeholder plus a line reading ``exit codes:``, the two marks of the shape
below. A script not yet converted to this shape is out of scope here, so adding
this test does not fail on a script that has not been reached yet.

Epilog shape this test enforces::

    examples:
      %(prog)s --flag VALUE
      %(prog)s --other-flag

    exit codes:
      0  success
      2  usage or config error

ADR-035 owns the exit codes: 0 ok, 1 logic, 2 config or usage, 3 external, 4 auth, and
100-255 for a script-specific code.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("script_help_probe.py")
SKILL_ROOTS = (REPO_ROOT / "src" / "claude" / "skills", REPO_ROOT / ".claude" / "skills")
MAIN_GUARD = re.compile(r"""__name__\s*==\s*['"]__main__['"]""")
EXIT_CODES_HEADING = re.compile(r"^exit codes:$", re.MULTILINE)
EXIT_CODE_LINE = re.compile(r"^  (?P<code>\d+)  \S", re.MULTILINE)
ADR_035_CODES = frozenset({0, 1, 2, 3, 4}) | frozenset(range(100, 256))
PROBE_TIMEOUT_SECONDS = 60
# Codes 5 to 99 that a script returns on purpose, though ADR-035 reserves that
# range. Each entry documents what the script does today; a rename belongs to
# the script's owner, not to this test.
SCRIPT_SPECIFIC_CODES: dict[str, frozenset[int]] = {
    "assess.py": frozenset({10, 11}),
    "check_style.py": frozenset({10}),
    "doc_accuracy.py": frozenset({10}),
    "pre-mortem.py": frozenset({10}),
    "scan_principles.py": frozenset({10}),
    "scan_vulnerabilities.py": frozenset({10}),
    "taste_lints.py": frozenset({10}),
    "validate-cva-matrix.py": frozenset({10}),
    "validate_experiment.py": frozenset({10}),
    "validate_threat_model.py": frozenset({10}),
}


def is_epilog_shaped(source: str) -> bool:
    return "%(prog)s" in source and EXIT_CODES_HEADING.search(source) is not None


def discover_scripts() -> list[Path]:
    """Return entry-point scripts, outside symlinks, written in the epilog shape."""
    found: list[Path] = []
    for root in SKILL_ROOTS:
        for directory, subdirs, files in os.walk(root, followlinks=False):
            subdirs[:] = [d for d in subdirs if d not in {"tests", "__pycache__", "assets"}]
            for name in files:
                path = Path(directory) / name
                if not name.endswith(".py") or name.startswith("_") or path.is_symlink():
                    continue
                source = path.read_text(encoding="utf-8")
                if MAIN_GUARD.search(source) and is_epilog_shaped(source):
                    found.append(path)
    return sorted(found)


def run_probe(script: Path, scratch: Path) -> dict:
    """Run the probe on ``script`` from an empty directory and return its JSON report."""
    env = {**os.environ, "HOME": str(scratch), "NO_COLOR": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, str(PROBE), str(script)],
        cwd=scratch,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=PROBE_TIMEOUT_SECONDS,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode == 0, f"probe crashed on {script}: {result.stderr[-500:]}"
    return json.loads(result.stdout.splitlines()[-1])


def exit_codes(epilog: str) -> list[int]:
    """Return the codes listed under the ``exit codes:`` heading."""
    _, _, tail = epilog.partition("exit codes:")
    return [int(m.group("code")) for m in EXIT_CODE_LINE.finditer(tail)]


SCRIPTS = discover_scripts()


def script_id(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


@pytest.mark.parametrize("script", SCRIPTS, ids=script_id)
def test_script_help_examples_parse_with_the_scripts_own_parser(script: Path, tmp_path: Path):
    report = run_probe(script, tmp_path)

    assert "probe_error" not in report, report.get("probe_error")
    assert report["help_error"] is None, f"--help formatting fails: {report['help_error']}"
    assert report["examples"], "epilog needs an 'examples:' heading with %(prog)s lines"
    failures = [e["error"] for e in report["examples"] if not e["ok"]]
    assert not failures, f"examples rejected by the script's parser: {failures}"


@pytest.mark.parametrize("script", SCRIPTS, ids=script_id)
def test_script_help_lists_adr_035_exit_codes(script: Path, tmp_path: Path):
    report = run_probe(script, tmp_path)

    assert "probe_error" not in report, report.get("probe_error")
    codes = exit_codes(report["epilog"])
    assert codes, "epilog needs an 'exit codes:' heading with '  N  meaning' lines"
    assert len(codes) == len(set(codes)), f"duplicate exit codes: {codes}"
    allowed = ADR_035_CODES | SCRIPT_SPECIFIC_CODES.get(script.name, frozenset())
    outside = sorted(set(codes) - allowed)
    assert not outside, f"codes outside ADR-035: {outside}"


PARSER_TEMPLATE = '''\
import argparse
import sys

EPILOG = """\\
{epilog}"""


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="fixture",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--name", required=True)
    parser.parse_args(argv)
    open("side-effect.txt", "w").write("ran")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def write_fixture(tmp_path: Path, epilog: str) -> Path:
    script = tmp_path / "fixture_tool.py"
    script.write_text(PARSER_TEMPLATE.format(epilog=epilog), encoding="utf-8")
    return script


def test_probe_accepts_an_example_that_matches_the_parser(tmp_path: Path):
    script = write_fixture(tmp_path, "examples:\n  %(prog)s --name widget\n")

    report = run_probe(script, tmp_path)

    assert report["help_error"] is None
    assert [e["ok"] for e in report["examples"]] == [True]


def test_probe_rejects_an_example_with_a_flag_the_parser_lacks(tmp_path: Path):
    script = write_fixture(tmp_path, "examples:\n  %(prog)s --name widget --bogus 1\n")

    report = run_probe(script, tmp_path)

    assert [e["ok"] for e in report["examples"]] == [False]
    assert "--bogus" in report["examples"][0]["error"]


def test_probe_rejects_an_example_that_omits_a_required_flag(tmp_path: Path):
    script = write_fixture(tmp_path, "examples:\n  %(prog)s\n")

    report = run_probe(script, tmp_path)

    assert [e["ok"] for e in report["examples"]] == [False]
    assert "--name" in report["examples"][0]["error"]


def test_probe_reports_a_bare_percent_that_breaks_help(tmp_path: Path):
    script = write_fixture(tmp_path, "examples:\n  %(prog)s --name 99.9%\n")

    report = run_probe(script, tmp_path)

    assert report["help_error"] is not None


def test_probe_stops_before_the_script_acts(tmp_path: Path):
    script = write_fixture(tmp_path, "examples:\n  %(prog)s --name widget\n")

    run_probe(script, tmp_path)

    assert not (tmp_path / "side-effect.txt").exists()


def test_probe_reports_a_script_that_never_builds_a_parser(tmp_path: Path):
    script = tmp_path / "no_parser.py"
    script.write_text("def main():\n    return 0\n", encoding="utf-8")

    report = run_probe(script, tmp_path)

    assert "no entry function" in report["probe_error"]


def test_exit_codes_reads_each_listed_code():
    epilog = "examples:\n  %(prog)s\n\nexit codes:\n  0  ok\n  3  gh failed\n"

    assert exit_codes(epilog) == [0, 3]


def test_exit_codes_returns_nothing_without_a_heading():
    assert exit_codes("examples:\n  %(prog)s\n") == []


def test_exit_codes_ignores_numbers_inside_a_meaning():
    epilog = "exit codes:\n  1  5 files failed\n"

    assert exit_codes(epilog) == [1]


def test_is_epilog_shaped_needs_the_prog_placeholder_and_the_exit_codes_heading():
    shaped = 'E = """\\\nexamples:\n  %(prog)s --x\n\nexit codes:\n  0  ok\n"""\n'

    assert is_epilog_shaped(shaped)
    assert not is_epilog_shaped(shaped.replace("exit codes:", "exit status:"))
    assert not is_epilog_shaped(shaped.replace("%(prog)s", "tool.py"))


def test_discovery_skips_symlinked_and_library_modules():
    discovered = {script.name for script in SCRIPTS}

    assert not any(name.startswith("_") for name in discovered)
    assert all(not script.is_symlink() for script in SCRIPTS)


def test_probe_parses_the_arguments_of_a_piped_example(tmp_path: Path):
    script = write_fixture(tmp_path, "examples:\n  echo hi | %(prog)s --name widget --bogus\n")

    report = run_probe(script, tmp_path)

    assert [e["argv"] for e in report["examples"]] == [["--name", "widget", "--bogus"]]
    assert [e["ok"] for e in report["examples"]] == [False]
