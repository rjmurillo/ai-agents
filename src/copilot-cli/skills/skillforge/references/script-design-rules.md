# Script design rules

Owner of the rules for scripts bundled in a skill's script directory. Read
it before you add or change a script, and when you review one. An agent runs
these scripts without a person at the keyboard, so every rule below removes a
way for a run to hang, guess, or lose information.

Source: the agentskills.io guide "Using scripts in skills", adjusted to the
runtime contract this repository ships.

## Rules every script follows

- **Never wait for a person.** No `input()`, no `getpass`, no confirmation
  prompt. Take every value from a flag, an environment variable, or stdin. When
  a script reads stdin by default and stdin is a terminal, stop with exit 2 and
  say how to pass the input:

  ```python
  if args.file is None and sys.stdin.isatty():
      print("tool: no input. Pass FILE or pipe text on stdin.", file=sys.stderr)
      return 2
  ```

- **Make `--help` the interface.** Use `argparse`, never hand-parsed `argv`, so
  `--help` prints usage and exits 0 and never runs the action. Give the parser a
  one-line `description`, a `help=` on every flag, and an `epilog` with one or
  two example commands and the exit codes. Use `RawDescriptionHelpFormatter` so
  the epilog keeps its line breaks.
- **Split the streams.** Put the result on stdout, in a form the next step can
  parse. Put progress, warnings, and errors on stderr. A caller that captures
  stdout must get only the result.
- **Write errors an agent can act on.** Say what failed, what the script
  expected, and what to try next. "unknown command: bogus; expected one of
  path, check, restore, cleanup" beats "bad input".
- **Use the shared exit codes (ADR-035).** One code per failure type:

  | Code | Meaning | Use for |
  |---|---|---|
  | 0 | Success | Every success path, including an idempotent no-op |
  | 1 | Logic error | A failed check, a validation finding, a broken invariant |
  | 2 | Usage or configuration error | A bad flag, a missing argument or input file, a missing dependency |
  | 3 | External error | A failed API call, network error, timeout, or subprocess |
  | 4 | Authentication or authorization error | An expired token, a denied permission, a rate limit |
  | 5-99 | Reserved | Never use |
  | 100+ | Script-specific | Only when a caller must tell outcomes apart, such as "already merged" |

  List every code the script can return in the module docstring's
  `Exit codes:` block and in the `--help` epilog, including any code of 100 or
  more. The `SKILL.md` row for the script names the same codes.
- **Bound the output.** A script that can print an unbounded list takes a
  `--limit`, a `--max-lines`, or an `--output FILE` flag, and says in `--help`
  what the default is. Agent harnesses truncate large output, and a truncated
  result looks like a complete one.

## Rules for scripts that change state

A script that writes a file, calls a mutating API, or deletes anything also:

- **Takes `--dry-run`.** It runs every read and every validation, then reports
  what it would do and skips only the write. Name the planned action in the
  result (`would_reopen`, `would_assign`) and set `dryRun: true`, so a caller
  can tell a plan from a change. `dryRun` is the key the shipped GitHub scripts
  use (`close_pr.py`, `merge_pr.py`, `post_pr_comment_reply.py`); a script that
  already shipped `DryRun` or `dry_run` keeps its key, so a caller does not break.
- **Keeps the same exit codes under `--dry-run`.** Invalid input, a missing
  target, or a refused precondition fails the same way. A dry run that passes
  where the real run fails is worse than none.
- **Stays idempotent.** A second run on the same target reports "already done"
  and changes nothing.
- **Defaults to the safe action.** A destructive mode needs its own flag. The
  default never overwrites or deletes.

## Dependencies and invocation

- **Ship stdlib-only scripts and run them with `python3`.** The plugin consumer
  has no guaranteed `uv`, so a shipped script's import closure is the standard
  library plus the plugin's own modules (`plugin-self-containment` rule, MUST
  4; the repository's python3 entry-point check governs entry points).
  A PEP 723 `# /// script` block with `uv run` would change that runtime
  contract, so a shipped script does not carry one.
  *Deliberate deviation from upstream:* agentskills.io recommends PEP 723
  inline dependencies for self-contained scripts. This repository bans them
  for the runtime-contract reason above.
- **Guard an optional third-party import.** Import it inside the function that
  needs it, catch `ImportError`, print the package name and the install command
  on stderr, and exit non-zero. Never let a bare traceback be the message.
- **Resolve paths from the plugin root.** `SKILL.md` invokes a script through
  the plugin-root locator (ADR-121), which runs `lib/ptk_run.py` from the first
  plugin root that holds it. This one runs skillforge's `conformance.py`; swap
  in your skill and script:

  ```bash
  ( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/skillforge/scripts/conformance.py --help; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
  ```

  Do not write a bare relative path; it resolves only when the working
  directory happens to match.
  *Deliberate deviation from upstream:* agentskills.io writes script paths
  relative to the skill root. This repository uses the plugin-root locator
  because the agent's working directory is not the skill root.

## Writing the Python

The repository's `python` rule covers general idioms, typing, and tooling.
These additions apply to a script a skill ships.

- **Write to python3 and the standard library.** Never name a minimum Python
  version in `SKILL.md` or `compatibility`. Keep the syntax parseable by
  Python 3.10, the hook-portability floor: no `def f[T]()` generics and no
  unparenthesized `except A, B:`.
- **Return the exit code from `main`.** Define `main(argv: list[str] | None =
  None) -> int`, parse with `build_parser().parse_args(argv)`, and `return` each
  code. The only `sys.exit` is `sys.exit(main())` under
  `if __name__ == "__main__":`. A test then calls `main([...])` and asserts the
  integer, with no `SystemExit` to catch.
- **Do nothing at import time.** No argument parsing, file reads, network
  calls, or `sys.path` changes in the module body beyond imports and constants.
  A test imports the module once and calls it many times.
- **Map failures to codes in one place.** Lower functions raise or return
  results; `main` turns them into exit codes and stderr messages. Catch the
  narrowest exception you can act on, never a bare `except:`, and never use
  `assert` to validate input, because `python -O` strips it.
- **Read and write text with `pathlib` and `encoding="utf-8"`.** Never rely on
  the platform default encoding.
- **Run subprocesses with an argument list, a timeout, and `check=False`.**
  Never `shell=True`. A missing tool exits 2; a failed or timed-out tool
  exits 3.
- **Keep helpers out of the entry-point list.** A module other scripts import
  starts with `_` and has no `__main__` block. Keep every file under 500
  lines; split a large script into an entry point and `_` helpers.
- **Type every public signature** and keep `ruff check`, `ruff format
  --check`, and `mypy` clean when the project runs them.

Start a new script from `assets/templates/script-template.py`. It already
follows these rules.

## One-off commands

agentskills.io lets a skill run an existing package through `uvx`, `npx`,
`bunx`, `deno run`, or `go run` instead of a bundled script.
*Deliberate deviation from upstream:* a shipped skill here does not. The
consumer has python3 and the standard library, and no guaranteed runner,
package index, or network. Write a bundled stdlib script instead, or name the
external tool as an optional step the user runs.

## Listing the scripts

`SKILL.md` lists every entry-point script with its purpose, key flags, and exit
codes, and tells the agent when to run it. A script the body does not name is a
script the agent never finds. When the table would push `SKILL.md` past its size
cap, put the full table in `references/` and keep one line in `SKILL.md` that
names each script and the file that holds its parameters.

## Testing a script

The repository's `testing` rule covers test structure, isolation, and
coverage. These additions apply to a script a skill ships.

- **Put tests in the repository's test tree,** such as
  `tests/skills/<skill>/test_<script>.py`. Never put them in the shipped skill
  directory; they would ship to every consumer.
- **Drive `main(argv)` in-process** for each behavior, and assert the returned
  code plus both streams through `capsys`. Run the real process with
  `sys.executable` only for what needs one: `--help`, a bad flag, and stdin.
  Pass a timeout and `encoding="utf-8"` with `errors="replace"`, and drop
  `CI` and `GITHUB_` variables from its environment.
- **Test every exit code the script can return.** Each test asserts the code,
  that stdout holds only the result, and that the error is on stderr. A failure
  path also asserts stdout is empty.
- **Cover the interface:** `--help` exits 0 and creates nothing; an unknown
  flag exits 2 with empty stdout; a terminal stdin exits 2 without reading;
  `--dry-run` writes nothing and keeps the real run's exit code; a second run
  on the same target changes nothing.
- **Parse structured output.** Load JSON with `json.loads` and assert on the
  object, never on a substring.
- **Fake only the boundary.** Replace the HTTP call, the subprocess, or the
  clock, never the function under test. A subprocess fake answers by its
  argument list, not by call order. Tests make no network calls.
- **Isolate the filesystem.** Write inputs under `tmp_path`, and assert an
  output is absent before the act that creates it.
- **Import the script by path without leaking modules.** Register the module
  in `sys.modules` before `exec_module`, because dataclasses look it up there.
  If you add the script directory to `sys.path`, restore it afterward and drop
  only the modules loaded from that directory. Evicting a third-party module
  such as `yaml` gives later importers a second copy and breaks class identity
  in unrelated tests.
- **Prove each regression test.** Break the behavior on purpose, watch the
  test fail, then restore it.

### Test template

Copy this into the test tree, point `SCRIPT` at the script, and replace the
example behaviors with the script's own. It pairs with
`assets/templates/script-template.py`.

<!-- test-template:start -->
```python
"""Tests for the <skill> skill's <script>.py."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "skills" / "<skill>" / "scripts" / "<script>.py"


def _load(path: Path) -> ModuleType:
    """Import the script by path; register it so dataclasses resolve."""
    name = f"_under_test_{path.stem.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def tool() -> ModuleType:
    return _load(SCRIPT)


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CI", "GITHUB_"))}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )


def test_success_returns_0_and_prints_json(tool, tmp_path, capsys) -> None:
    source = tmp_path / "in.json"
    source.write_text("{}", encoding="utf-8")

    code = tool.main([str(source), "--json"])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["success"] is True


def test_missing_input_returns_2_with_the_error_on_stderr(tool, tmp_path, capsys) -> None:
    code = tool.main([str(tmp_path / "missing.json")])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "missing.json" in captured.err


def test_failed_check_returns_1(tool, tmp_path, monkeypatch, capsys) -> None:
    source = tmp_path / "in.json"
    source.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(tool, "fast_fail_check", lambda result: (False, "no rows"))

    code = tool.main([str(source)])

    assert code == 1
    assert "no rows" in capsys.readouterr().err


def test_help_exits_0_and_creates_nothing(tmp_path) -> None:
    proc = _run("--help", cwd=tmp_path)

    assert proc.returncode == 0
    assert "usage:" in proc.stdout
    assert list(tmp_path.iterdir()) == []


def test_unknown_flag_exits_2_with_empty_stdout(tmp_path) -> None:
    proc = _run("in.json", "--no-such-flag", cwd=tmp_path)

    assert proc.returncode == 2
    assert proc.stdout == ""
    assert "--no-such-flag" in proc.stderr


def test_dry_run_writes_nothing_and_keeps_the_exit_code(tool, tmp_path) -> None:
    source = tmp_path / "in.json"
    source.write_text("{}", encoding="utf-8")
    target = tmp_path / "out.json"
    assert not target.exists()

    code = tool.main([str(source), "--output", str(target), "--dry-run"])

    assert code == 0
    assert not target.exists()


def test_real_run_writes_the_output(tool, tmp_path) -> None:
    source = tmp_path / "in.json"
    source.write_text("{}", encoding="utf-8")
    target = tmp_path / "out.json"
    assert not target.exists()

    code = tool.main([str(source), "--output", str(target)])

    assert code == 0
    assert json.loads(target.read_text(encoding="utf-8")) == {"processed": True}
```
<!-- test-template:end -->
