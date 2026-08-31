"""Every bare repository the test suite creates is rooted in a temp directory.

Issue #4698 acceptance criterion 3: "Fixture-creating tests are shown to write
bare repositories only under a temporary path." ``tests/bare_repo_sites.py``
reads each module's tokens and ``tests/bare_repo_scan.py`` turns them into a
verdict; this module asserts the corpus result and pins the temp roots the scan
recognises. ``tests/test_bare_repo_scan_targets.py`` pins the three narrower
properties: what counts as a site, that a command's target must reach the root,
and that a module-level command is a violation on sight.

What the corpus assertion proves, exactly
-----------------------------------------
Every ``--bare`` and ``core.bare`` token under ``tests/`` that is being built
into a command sits inside a function whose paths are rooted in a temp
directory, **and** the command's own target traces back to that root. The root
is established one of four ways: a pytest temp fixture parameter, a ``tempfile``
factory call, the repository's own ``.pytest_tmp`` durable fixture root, or a
parameter naming a fixture that is itself temp-rooted. A helper taking its
target as a parameter, such as ``_init_git_repo`` in
``tests/gh_base_ref_test_helpers.py``, is admitted only when every caller
reached through the call graph is itself temp-rooted, and its parameters then
count as roots inside its body.

The target trace is what makes the claim about the command rather than about
the function. ``def test_x(tmp_path): subprocess.run(["git", "init", "--bare",
"/home/user/live.git"])`` roots the function and writes a bare repository into a
live checkout; it is a violation here.

What counts as a site
---------------------
A token is a site where it is being **built** into something a process could
receive: an element of a list or tuple, a value in a dict, an argument to a
call, or the right side of an assignment. A token being **compared** is not,
which keeps assertions and expected-message data out of the corpus. Measured at
``26911e9f0``: the old rule, any exact constant anywhere, counted 73 sites; the
construction rule counts 70. All three dropped are ``ast.Compare`` operands,
each an ``assert "core.bare" in <stream>`` in
``tests/test_lefthook_integration.py``,
``tests/validation/test_check_repo_health.py``, and
``tests/validation/test_check_repo_health_hostile_inputs.py``. Line numbers are
left off on purpose: the claim is about a shape those files contain, not about
a contract quoted at one line, which is the only thing
``check_citation_freshness.py`` can keep true.

Restricting further, to tokens lexically inside a ``subprocess`` argument list,
was rejected because it under-reports. ``tests/gh_base_ref_test_helpers.py``
builds ``args = ["git", "init"]``, appends ``--bare`` conditionally, and passes
``args`` to ``subprocess.run`` two statements later, so a lexical test sees no
site at a call that really does create a bare repository. The scanner follows
the carrier instead.

What it does not prove
----------------------
It reads argument-vector git calls only. A shell-form invocation, say
``subprocess.run("git init --bare x", shell=True)``, carries the token inside a
longer string and is not a site. That shape does not exist in the suite
(``shell=True`` appears under ``tests/`` only in prose and in assertions
forbidding it), and matching substrings instead would flag every assertion that
quotes the repair command, such as the expected-message table in
``tests/validation/test_check_repo_health_reporting.py``.

An environment site is graded on the function alone, not on a target. A token
written with ``monkeypatch.setenv`` or handed over as ``env=`` names no
repository: git applies ``GIT_CONFIG_KEY_0=core.bare`` wherever the child
process lands, so the only question is the one the call graph already answers.

The runtime complement is ``tests/test_git_isolation_blast_radius.py``, which
runs a real child pytest under a hook-shaped hostile environment and asserts a
decoy repository standing in for the developer's checkout never takes
``core.bare=true``. The two together cover the static shape and the inherited
environment; neither alone does.

Refs #4698, #4717, #4287.
"""

from __future__ import annotations

import ast

import pytest

from tests.bare_repo_scan import (
    PROJECT_ROOT,
    SCANNER_MODULES,
    ScanResult,
    scan,
    scan_test_suite,
    scannable_sources,
)


def _module(source: str, name: str = "probe") -> dict[str, str]:
    return {name: source}


class TestTheTestSuiteRootsEveryBareRepositoryInTemp:
    """The corpus assertion. Issue #4698 acceptance criterion 3."""

    @pytest.fixture(scope="class")
    def result(self) -> ScanResult:
        return scan_test_suite()

    def test_no_bare_repository_literal_escapes_a_temp_root(
        self, result: ScanResult
    ) -> None:
        assert not result.violations, (
            "a test creates a bare repository or sets core.bare outside a temp "
            "root. On a checkout with extensions.worktreeConfig enabled that "
            "writes core.bare into the shared .git/config and breaks every "
            "worktree at once (#4698). Root the fixture in tmp_path, a tempfile "
            "factory, or .pytest_tmp:\n  "
            + "\n  ".join(str(violation) for violation in result.violations)
        )

    def test_the_scan_examined_the_corpus_it_claims_to_cover(
        self, result: ScanResult
    ) -> None:
        """A zero-violation result means nothing without the examined count."""
        assert result.sites_examined >= 40, (
            f"the scan found only {result.sites_examined} bare-repository "
            "literals under tests/; the prefilter or the token list has drifted "
            "and the clean result above covers almost nothing"
        )
        assert result.modules_parsed >= 10, result.modules_parsed

    def test_acceptance_is_not_vacuous(self, result: ScanResult) -> None:
        """If every function were accepted, a clean scan would prove nothing."""
        assert result.functions_seen > 0
        rejected = result.functions_seen - result.functions_accepted
        assert rejected >= result.functions_seen // 10, (
            f"only {rejected} of {result.functions_seen} functions in the loaded "
            "modules were rejected as not temp-rooted; acceptance has widened far "
            "enough that a clean scan is close to unfalsifiable"
        )


class TestTheScannerRunsNoGitCommand:
    """What justifies excluding the scanner's own modules from the scan.

    Each holds ``--bare`` and ``core.bare`` as data: the token table in
    ``tests/bare_repo_sites.py`` and the negative controls below. The exclusion
    is safe only while none of them shells out, so assert the precondition
    rather than trusting the comment on ``SCANNER_MODULES``.
    """

    _PROCESS_SPAWNERS = frozenset(
        {"run", "Popen", "call", "check_call", "check_output", "system", "spawn"}
    )

    @pytest.mark.parametrize("module", sorted(SCANNER_MODULES))
    def test_the_excluded_module_spawns_no_process(self, module: str) -> None:
        path = PROJECT_ROOT.joinpath(*module.split(".")).with_suffix(".py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        spawns = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in self._PROCESS_SPAWNERS
        ]

        assert spawns == [], (
            f"{module} now spawns a process at line(s) {spawns}, so excluding it "
            "from the corpus scan would hide a real bare-repository call site. "
            "Either drop the call or stop excluding the module."
        )

    def test_every_excluded_module_exists_and_is_excluded(self) -> None:
        """A stale name in SCANNER_MODULES would silently exclude nothing."""
        sources = scannable_sources()
        for module in SCANNER_MODULES:
            path = PROJECT_ROOT.joinpath(*module.split(".")).with_suffix(".py")
            assert path.is_file(), f"{module} names no file; the exclusion is stale"
            assert module not in sources


class TestTheScanRejectsUnrootedFixtures:
    """Negative controls: inputs the corpus does not contain but must fail."""

    def test_a_bare_init_with_no_temp_root_is_rejected(self) -> None:
        source = (
            "import subprocess\n"
            "def test_thing():\n"
            "    subprocess.run(['git', 'init', '--bare', 'remote.git'])\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert len(result.violations) == 1
        assert result.violations[0].token == "--bare"
        assert result.violations[0].scope == "test_thing()"

    def test_setting_core_bare_with_no_temp_root_is_rejected(self) -> None:
        source = (
            "import subprocess\n"
            "def test_thing(repo):\n"
            "    subprocess.run(['git', 'config', 'core.bare', 'true'], cwd=repo)\n"
        )

        result = scan(_module(source))

        assert [violation.token for violation in result.violations] == ["core.bare"]

    def test_a_helper_with_one_unrooted_caller_is_rejected(self) -> None:
        """One caller without a temp root is the one handing over an ambient path."""
        source = (
            "import subprocess\n"
            "def _init_bare(path):\n"
            "    subprocess.run(['git', 'init', '--bare', str(path)])\n"
            "def test_rooted(tmp_path):\n"
            "    _init_bare(tmp_path / 'remote.git')\n"
            "def test_unrooted():\n"
            "    _init_bare('remote.git')\n"
        )

        result = scan(_module(source))

        assert len(result.violations) == 1
        assert result.violations[0].scope == "_init_bare()"

    def test_an_unreferenced_helper_is_rejected(self) -> None:
        """No caller is not the same as every caller being temp-rooted."""
        source = (
            "import subprocess\n"
            "def _init_bare(path):\n"
            "    subprocess.run(['git', 'init', '--bare', str(path)])\n"
        )

        result = scan(_module(source))

        assert len(result.violations) == 1

    def test_a_module_constant_read_by_an_unrooted_function_is_rejected(self) -> None:
        source = (
            "import subprocess\n"
            "HOSTILE = {'GIT_CONFIG_KEY_0': 'core.bare'}\n"
            "def test_thing():\n"
            "    subprocess.run(['git', 'status'], env=HOSTILE)\n"
        )

        result = scan(_module(source))

        assert len(result.violations) == 1
        assert "module constant HOSTILE" in result.violations[0].scope

    def test_a_plain_parameter_name_does_not_root_the_body(self) -> None:
        """The fixture rung requires a @pytest.fixture decorator, not a name match."""
        source = (
            "def decoy(tmp_path):\n"
            "    return tmp_path\n"
            "def test_thing(decoy):\n"
            "    run(str(decoy), '--bare')\n"
        )

        result = scan(_module(source))

        assert len(result.violations) == 1


class TestTheScanAcceptsTheEstablishedIsolationPatterns:
    """Positive controls: each temp root the suite actually uses."""

    @pytest.mark.parametrize(
        ("label", "body"),
        [
            ("tmp_path", "def test_thing(tmp_path):\n    run(str(tmp_path), '--bare')\n"),
            (
                "tempfile",
                "import tempfile\n"
                "def test_thing():\n"
                "    with tempfile.TemporaryDirectory() as directory:\n"
                "        run(directory, '--bare')\n",
            ),
            (
                "pytest_tmp",
                "def test_thing():\n"
                "    root = PROJECT_ROOT / '.pytest_tmp' / 'x'\n"
                "    run(str(root), '--bare')\n",
            ),
            (
                "tmp_path_factory",
                "def test_thing(tmp_path_factory):\n"
                "    run(str(tmp_path_factory.mktemp('x')), '--bare')\n",
            ),
        ],
    )
    def test_an_established_temp_root_is_accepted(self, label: str, body: str) -> None:
        result = scan(_module(body))

        assert result.sites_examined == 1, label
        assert result.violations == [], (label, result.violations)

    def test_a_fixture_parameter_roots_the_test_that_requests_it(self) -> None:
        """The live shape of `decoy_repo` and `git_sandbox`."""
        source = (
            "import pytest\n"
            "@pytest.fixture\n"
            "def decoy(tmp_path_factory):\n"
            "    return tmp_path_factory.mktemp('decoy')\n"
            "def test_thing(decoy):\n"
            "    run(str(decoy), '--bare')\n"
        )

        result = scan(_module(source))

        assert result.violations == []

    def test_a_module_constant_read_only_by_a_rooted_function_is_accepted(self) -> None:
        """The live shape of `_HOSTILE_CONFIG` in test_git_isolation_blast_radius."""
        source = (
            "import subprocess\n"
            "HOSTILE = {'GIT_CONFIG_KEY_0': 'core.bare'}\n"
            "def test_thing(tmp_path):\n"
            "    subprocess.run(['git', 'status'], cwd=tmp_path, env=HOSTILE)\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert result.violations == []

    def test_a_module_constant_nothing_reads_runs_no_git_command(self) -> None:
        source = "UNUSED = {'GIT_CONFIG_KEY_0': 'core.bare'}\n"

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert result.violations == []


class TestTheScanReachesAcrossModules:
    """The `resolve_more` rung: a helper's callers live in another file."""

    _HELPERS = (
        "import subprocess\n"
        "def _init_bare(path):\n"
        "    subprocess.run(['git', 'init', '--bare', str(path)])\n"
    )

    def _scan_with(self, caller: str) -> ScanResult:
        return scan(
            {"tests.helpers": self._HELPERS},
            resolve_more=lambda name: (
                {"tests.caller": caller} if name == "_init_bare" else {}
            ),
        )

    def test_a_helper_is_admitted_by_callers_in_another_module(self) -> None:
        result = self._scan_with(
            "from tests.helpers import _init_bare\n"
            "def test_thing(tmp_path):\n"
            "    _init_bare(tmp_path / 'remote.git')\n"
        )

        assert result.modules_parsed == 2
        assert result.violations == []

    def test_a_helper_whose_other_module_caller_is_unrooted_is_rejected(self) -> None:
        """The discriminating control for the test above.

        Same seed, same loader shape, one caller without a temp root. If this
        passed, the test above would prove only that the loader ran.
        """
        result = self._scan_with(
            "from tests.helpers import _init_bare\n"
            "def test_thing():\n"
            "    _init_bare('remote.git')\n"
        )

        assert result.modules_parsed == 2
        assert len(result.violations) == 1
