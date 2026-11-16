"""Tests for the unguarded-symlink rule in scripts/validation/check_io_portability.py.

Split from test_check_io_portability.py to keep each file under the size ratchet.
"""

from __future__ import annotations

import pytest

from scripts.validation import check_io_portability as checker

TEST_PATH = "tests/test_sample.py"
CODE_PATH = "scripts/sample.py"


def rules(source: str, path: str = TEST_PATH) -> list[str]:
    return [v.rule for v in checker.scan_source(path, source)]


class TestUnguardedSymlink:
    def test_bare_symlink_in_test_is_flagged(self) -> None:
        source = "def test_x(tmp_path):\n    (tmp_path / 'l').symlink_to(tmp_path)\n"

        assert rules(source) == ["unguarded-symlink"]

    def test_os_symlink_in_test_is_flagged(self) -> None:
        source = "import os\ndef test_x():\n    os.symlink('a', 'b')\n"

        assert rules(source) == ["unguarded-symlink"]

    def test_try_catching_oserror_guards(self) -> None:
        source = (
            "def test_x(p):\n    try:\n        p.symlink_to('t')\n"
            "    except (OSError, NotImplementedError):\n        pytest.skip('no links')\n"
        )

        assert rules(source) == []

    def test_try_catching_only_valueerror_does_not_guard(self) -> None:
        source = (
            "def test_x(p):\n    try:\n        p.symlink_to('t')\n"
            "    except ValueError:\n        pass\n"
        )

        assert rules(source) == ["unguarded-symlink"]

    def test_symlink_in_except_handler_is_not_guarded_by_its_own_try(self) -> None:
        source = (
            "def test_x(p):\n    try:\n        pass\n    except OSError:\n"
            "        p.symlink_to('t')\n"
        )

        assert rules(source) == ["unguarded-symlink"]

    @pytest.mark.parametrize("name", ["test_skips_existing_link", "TestSkipExisting"])
    def test_a_test_named_for_skipping_is_not_a_guard(self, name: str) -> None:
        keyword = "class" if name.startswith("Test") else "def"
        body = "    def test_x(self, p):\n        p.symlink_to('t')\n"
        source = (
            f"class {name}:\n{body}"
            if keyword == "class"
            else f"def {name}(p):\n    p.symlink_to('t')\n"
        )

        assert rules(source) == ["unguarded-symlink"]

    @pytest.mark.parametrize(
        "mark",
        [
            "pytest.mark.skipif(False, reason='never')",
            "pytest.mark.skipif(condition=0, reason='never')",
            "unittest.skipIf(False, 'never')",
            "pytest.mark.skip_cache",
            "pytest.mark.skip_slow('x')",
        ],
    )
    def test_a_mark_that_never_skips_does_not_guard(self, mark: str) -> None:
        source = f"@{mark}\ndef test_x(p):\n    p.symlink_to('t')\n"

        assert rules(source) == ["unguarded-symlink"]

    @pytest.mark.parametrize(
        "mark", ["pytest.mark.skip(reason='x')", "pytest.mark.skip", "unittest.skipIf(WIN, 'x')"]
    )
    def test_a_real_skip_mark_guards(self, mark: str) -> None:
        source = f"@{mark}\ndef test_x(p):\n    p.symlink_to('t')\n"

        assert rules(source) == []

    def test_class_level_pytestmark_skip_guards_its_methods(self) -> None:
        source = (
            "class TestLinks:\n"
            "    pytestmark = pytest.mark.skipif(os.name == 'nt', reason='links')\n"
            "    def test_x(self, p):\n        p.symlink_to('t')\n"
        )

        assert rules(source) == []

    def test_class_level_pytestmark_without_a_skip_does_not_guard(self) -> None:
        source = (
            "class TestLinks:\n"
            "    pytestmark = pytest.mark.usefixtures('skip_cache')\n"
            "    def test_x(self, p):\n        p.symlink_to('t')\n"
        )

        assert rules(source) == ["unguarded-symlink"]

    def test_a_try_around_a_def_does_not_guard_its_body(self) -> None:
        source = (
            "try:\n    def make_link(p):\n        p.symlink_to('t')\nexcept OSError:\n    pass\n"
        )

        assert rules(source) == ["unguarded-symlink"]

    def test_a_module_skip_does_not_cover_import_time_calls(self) -> None:
        source = "pytestmark = pytest.mark.skip(reason='x')\np.symlink_to('t')\n"

        assert rules(source) == ["unguarded-symlink"]

    def test_a_class_body_call_under_a_class_skip_runs_at_import(self) -> None:
        source = (
            "class TestLinks:\n"
            "    pytestmark = pytest.mark.skipif(os.name == 'nt', reason='links')\n"
            "    LINK = p.symlink_to('t')\n"
        )

        assert rules(source) == ["unguarded-symlink"]

    def test_a_skip_named_helper_still_guards_its_own_body(self) -> None:
        source = "def link_or_skip(p):\n    p.symlink_to('t')\n"

        assert rules(source) == []

    def test_skip_named_helper_guards(self) -> None:
        source = "def symlink_or_skip(p, t):\n    p.symlink_to(t)\n"

        assert rules(source) == []

    def test_skipif_decorator_on_function_guards(self) -> None:
        source = (
            "@pytest.mark.skipif(sys.platform == 'win32', reason='posix')\n"
            "def test_x(p):\n    p.symlink_to('t')\n"
        )

        assert rules(source) == []

    def test_skipif_decorator_on_class_guards(self) -> None:
        source = (
            "@pytest.mark.skipif(True, reason='posix')\nclass TestX:\n"
            "    def test_x(self, p):\n        p.symlink_to('t')\n"
        )

        assert rules(source) == []

    def test_module_pytestmark_guards(self) -> None:
        source = (
            "pytestmark = pytest.mark.skipif(True, reason='posix')\n"
            "def test_x(p):\n    p.symlink_to('t')\n"
        )

        assert rules(source) == []

    def test_named_skip_mark_on_a_class_guards(self) -> None:
        source = (
            "POSIX_ONLY = pytest.mark.skipif(os.name != 'posix', reason='links')\n"
            "@POSIX_ONLY\nclass TestX:\n    def test_x(self, p):\n        p.symlink_to('t')\n"
        )

        assert rules(source) == []

    def test_named_mark_that_does_not_skip_does_not_guard(self) -> None:
        source = "SLOW = pytest.mark.slow\n@SLOW\ndef test_x(p):\n    p.symlink_to('t')\n"

        assert rules(source) == ["unguarded-symlink"]

    @pytest.mark.parametrize(
        "value", ["POSIX_ONLY", "[POSIX_ONLY]", "(pytest.mark.slow, POSIX_ONLY)"]
    )
    def test_module_pytestmark_naming_a_skip_alias_guards(self, value: str) -> None:
        source = (
            "POSIX_ONLY = pytest.mark.skipif(os.name != 'posix', reason='links')\n"
            f"pytestmark = {value}\ndef test_x(p):\n    p.symlink_to('t')\n"
        )

        assert rules(source) == []

    @pytest.mark.parametrize(
        "mark",
        [
            "pytest.mark.usefixtures('skip_cache')",
            "[pytest.mark.usefixtures('skip_cache')]",
            "pytest.mark.parametrize('mode', ['skip'])",
        ],
    )
    def test_a_skip_word_inside_mark_arguments_does_not_guard(self, mark: str) -> None:
        module = f"pytestmark = {mark}\ndef test_x(p):\n    p.symlink_to('t')\n"
        decorated = f"@{mark}\ndef test_x(p):\n    p.symlink_to('t')\n"

        assert (rules(module), rules(decorated)) == (["unguarded-symlink"], ["unguarded-symlink"])

    def test_an_alias_of_a_non_skip_mark_with_skip_in_its_arguments_does_not_guard(self) -> None:
        source = (
            "CACHE = pytest.mark.usefixtures('skip_cache')\n"
            "@CACHE\ndef test_x(p):\n    p.symlink_to('t')\n"
        )

        assert rules(source) == ["unguarded-symlink"]

    def test_module_pytestmark_without_a_skip_does_not_guard(self) -> None:
        source = (
            "pytestmark = pytest.mark.usefixtures('repo')\ndef test_x(p):\n    p.symlink_to('t')\n"
        )

        assert rules(source) == ["unguarded-symlink"]

    def test_symlink_outside_test_paths_is_ignored(self) -> None:
        source = "def make(p):\n    p.symlink_to('t')\n"

        assert rules(source, CODE_PATH) == []

    @pytest.mark.parametrize("path", ["tests/a/b.py", "x/test_y.py", "pkg/conftest.py"])
    def test_test_path_detection(self, path: str) -> None:
        assert checker.is_test_path(path)
