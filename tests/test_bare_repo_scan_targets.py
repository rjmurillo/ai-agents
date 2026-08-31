"""The scan is a claim about each git command, not about its enclosing function.

Split from ``tests/test_bare_repo_fixtures_are_temp_rooted.py``, which asserts
the corpus result, to keep both files under the 500-line taste ceiling. That
file pins the four temp roots the suite uses and the call-graph walk that
carries them across modules. This one pins the three narrower properties review
found missing, each of which let a real bare-repository write pass the gate.

**Only command construction counts as a site.** The scan used to record every
exact ``--bare`` or ``core.bare`` constant anywhere in a file, which meant
assertions and expected-message data inflated ``sites_examined`` and could
raise a violation for a string nobody runs. A token is a site where it is being
built into something a process could receive; a token being compared is not.
Measured at ``26911e9f0``, the old rule counted 73 sites against 70, and all
three dropped are ``ast.Compare`` operands.

**The command's target must reach the temp root.** Temp-rooting the enclosing
function proves nothing about the path handed to git.
``def test_x(tmp_path): subprocess.run(["git", "init", "--bare",
"/home/user/live.git"])`` passed the old gate, and it writes a bare repository
into a live checkout, which is the exact damage issue #4698 records.

**A module-level command is a violation on sight.** It binds no name, so
following bindings to their readers found nothing and reported it clean. It
executes at import, during pytest collection, against whatever directory
collection happens to be running in.

Every case here is paired with a discriminating control that must come out the
other way, so an exit-clean result cannot be the scan having stopped looking.

Refs #4698.
"""

from __future__ import annotations

from tests.bare_repo_scan import scan


def _module(source: str, name: str = "probe") -> dict[str, str]:
    return {name: source}


class TestOnlyCommandConstructionCountsAsASite:
    """A token being compared is not a token being run."""

    def test_an_assertion_quoting_the_token_is_not_a_site(self) -> None:
        """`assert "core.bare" in stderr` inflated the count and could violate."""
        source = (
            "def test_thing(result):\n"
            "    assert 'core.bare' in result.stderr\n"
            "    assert result.args == '--bare'\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 0
        assert result.violations == []

    def test_the_same_token_in_an_argument_vector_is_a_site(self) -> None:
        """The discriminating control: identical spelling, construction position."""
        source = (
            "import subprocess\n"
            "def test_thing():\n"
            "    subprocess.run(['git', 'config', 'core.bare', 'true'])\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert len(result.violations) == 1

    def test_a_token_appended_to_a_command_vector_is_a_site(self) -> None:
        """The live `_init_git_repo` shape a subprocess-only rule would miss."""
        source = (
            "import subprocess\n"
            "def test_thing():\n"
            "    args = ['git', 'init']\n"
            "    args.append('--bare')\n"
            "    subprocess.run(args, cwd='/home/user/live')\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert len(result.violations) == 1

    def test_a_token_read_back_out_of_a_vector_is_not_a_site(self) -> None:
        """Branching on what a command said is not building a command."""
        source = "def test_thing(argv):\n    if argv[2] == '--bare':\n        return 1\n"

        result = scan(_module(source))

        assert result.sites_examined == 0
        assert result.violations == []


class TestTheCommandsTargetMustReachTheTempRoot:
    """A temp-rooted function is not evidence about the path it hands to git."""

    def test_an_absolute_target_inside_a_tmp_path_test_is_rejected(self) -> None:
        """The exact shape `tests/bare_repo_scan.py` used to admit."""
        source = (
            "import subprocess\n"
            "def test_x(tmp_path):\n"
            "    subprocess.run(['git', 'init', '--bare', '/home/user/live.git'])\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert len(result.violations) == 1
        assert "target is not" in result.violations[0].reason

    def test_the_same_call_using_the_fixture_path_is_accepted(self) -> None:
        """The discriminating control: one argument differs."""
        source = (
            "import subprocess\n"
            "def test_x(tmp_path):\n"
            "    subprocess.run(['git', 'init', '--bare', str(tmp_path / 'live.git')])\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert result.violations == []

    def test_a_derived_name_carries_the_root(self) -> None:
        """`bare = tmp_path / name` is the live `_bare_remote` shape."""
        source = (
            "import subprocess\n"
            "def test_x(tmp_path):\n"
            "    bare = tmp_path / 'remote.git'\n"
            "    subprocess.run(['git', 'init', '--bare', str(bare)])\n"
        )

        result = scan(_module(source))

        assert result.violations == []

    def test_tuple_unpacking_carries_the_root(self) -> None:
        """`bare, linked = _make(tmp_path)` binds two names the walk must follow."""
        source = (
            "import subprocess\n"
            "def _make(root):\n"
            "    return root / 'a', root / 'b'\n"
            "def test_x(tmp_path):\n"
            "    bare, linked = _make(tmp_path)\n"
            "    subprocess.run(['git', 'config', 'core.bare', 'true'], cwd=linked)\n"
        )

        result = scan(_module(source))

        assert result.violations == []

    def test_a_cwd_pointing_at_the_root_is_enough(self) -> None:
        """A relative target is safe when the command runs inside the temp root."""
        source = (
            "import subprocess\n"
            "def test_x(tmp_path):\n"
            "    subprocess.run(['git', 'init', '--bare', 'remote.git'], cwd=tmp_path)\n"
        )

        result = scan(_module(source))

        assert result.violations == []

    def test_a_command_vector_is_traced_to_the_call_that_runs_it(self) -> None:
        """The token is appended here and the target travels two statements later."""
        source = (
            "import subprocess\n"
            "def test_x(tmp_path):\n"
            "    args = ['git', 'init']\n"
            "    args.append('--bare')\n"
            "    subprocess.run(args, cwd=tmp_path)\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert result.violations == []

    def test_a_command_vector_run_outside_the_root_is_rejected(self) -> None:
        """The discriminating control for the case above: only `cwd=` differs."""
        source = (
            "import subprocess\n"
            "def test_x(tmp_path):\n"
            "    args = ['git', 'init']\n"
            "    args.append('--bare')\n"
            "    subprocess.run(args, cwd='/home/user/live')\n"
        )

        result = scan(_module(source))

        assert len(result.violations) == 1

    def test_a_helper_receives_its_root_from_its_callers(self) -> None:
        """A parameter is a root only where callers vouch for it."""
        source = (
            "import subprocess\n"
            "def _init_bare(path):\n"
            "    subprocess.run(['git', 'init', '--bare', str(path)])\n"
            "def test_rooted(tmp_path):\n"
            "    _init_bare(tmp_path / 'remote.git')\n"
        )

        result = scan(_module(source))

        assert result.violations == []

    def test_an_environment_write_is_graded_on_the_function(self) -> None:
        """`GIT_CONFIG_KEY_0=core.bare` names no repository, so there is no target."""
        source = (
            "import subprocess\n"
            "def test_x(tmp_path, monkeypatch):\n"
            "    monkeypatch.setenv('GIT_CONFIG_KEY_0', 'core.bare')\n"
            "    subprocess.run(['git', 'status'], cwd=tmp_path)\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert result.violations == []

    def test_an_environment_write_in_an_unrooted_function_is_still_rejected(self) -> None:
        """The discriminating control: skipping the target trace is not a pass."""
        source = (
            "import subprocess\n"
            "def test_x(monkeypatch):\n"
            "    monkeypatch.setenv('GIT_CONFIG_KEY_0', 'core.bare')\n"
            "    subprocess.run(['git', 'status'])\n"
        )

        result = scan(_module(source))

        assert len(result.violations) == 1
        assert "no temp root" in result.violations[0].reason


class TestAModuleLevelCommandIsAViolationOnSight:
    """It runs at import, during collection, against the ambient directory."""

    def test_an_unbound_module_level_call_is_reported(self) -> None:
        """It binds no name, so following bindings to readers found nothing."""
        source = (
            "import subprocess\n"
            "subprocess.run(['git', 'init', '--bare', 'remote.git'])\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert len(result.violations) == 1
        assert result.violations[0].scope == "module scope"
        assert "module scope" in result.violations[0].reason

    def test_the_same_call_inside_a_rooted_function_is_accepted(self) -> None:
        """The discriminating control: identical call, bound to a rooted scope."""
        source = (
            "import subprocess\n"
            "def test_thing(tmp_path):\n"
            "    subprocess.run(['git', 'init', '--bare', str(tmp_path / 'remote.git')])\n"
        )

        result = scan(_module(source))

        assert result.sites_examined == 1
        assert result.violations == []

    def test_a_module_constant_is_still_graded_by_its_readers(self) -> None:
        """Binding a name is what separates data from a command."""
        source = (
            "import subprocess\n"
            "HOSTILE = {'GIT_CONFIG_KEY_0': 'core.bare'}\n"
            "def test_thing(tmp_path):\n"
            "    subprocess.run(['git', 'status'], cwd=tmp_path, env=HOSTILE)\n"
        )

        result = scan(_module(source))

        assert result.violations == []
