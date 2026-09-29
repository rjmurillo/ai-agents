"""Dynamic-load handling in the completion gate's verifier closure.

ADR-101 Application B, issue #5245. The static import pass cannot see a load by
computed name, so a verifier reached through one was dispatched unverified. The
decision under test: a load whose target is a literal, or a path built only from
``__file__`` and string literals, joins the closure and is byte-verified; any
other load fails closed as untrusted. ``new_pr.py`` loading ``pr_validations.py``
through a computed path is the concrete case the decision was made against.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_GATE_PATH = (
    _REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "run_completion_gate.py"
)
_NEW_PR = _REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr" / "new_pr.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("run_completion_gate_dynamic", _GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_completion_gate_dynamic"] = module
    spec.loader.exec_module(module)
    return module


gate = _load_gate()


def _write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _loads(tmp_path: Path, body: str, name: str = "verify.py"):
    script = _write(tmp_path, name, body)
    return gate._dynamic_loads(script.read_bytes(), script)


def _closure(tmp_path: Path, *named: str) -> list[str]:
    return gate._expand_import_closure(list(named), tmp_path)


class TestResolvableLoads:
    def test_import_module_with_a_literal_name_joins_the_closure(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "import importlib\nimportlib.import_module('sibling')\n")
        _write(tmp_path, "sibling.py", "X = 1\n")

        assert _closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_dunder_import_with_a_literal_name_joins_the_closure(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "__import__('sibling')\n")
        _write(tmp_path, "sibling.py", "X = 1\n")

        assert "sibling.py" in _closure(tmp_path, "verify.py")

    @pytest.mark.parametrize(
        "expression",
        [
            "Path(__file__).resolve().parent / 'sibling.py'",
            "Path(__file__).resolve().with_name('sibling.py')",
            "Path(__file__).parent.joinpath('sibling.py')",
            "pathlib.Path(__file__).absolute().parent / 'sibling.py'",
            "os.path.join(os.path.dirname(__file__), 'sibling.py')",
            "os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sibling.py')",
            "Path(__file__).resolve().parents[0] / 'sibling.py'",
        ],
    )
    def test_a_path_built_from_file_and_literals_joins_the_closure(
        self, tmp_path: Path, expression: str
    ) -> None:
        _write(
            tmp_path,
            "verify.py",
            f"""\
            import importlib.util, os, pathlib
            from pathlib import Path
            spec = importlib.util.spec_from_file_location("sibling", {expression})
            """,
        )
        _write(tmp_path, "sibling.py", "X = 1\n")

        assert _closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_a_path_held_in_a_single_assignment_is_followed(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util
            from pathlib import Path
            target = Path(__file__).resolve().parent / "sibling.py"
            spec = importlib.util.spec_from_file_location("sibling", target)
            """,
        )
        _write(tmp_path, "sibling.py", "X = 1\n")

        assert _closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_the_loaded_files_own_imports_are_followed(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('s', Path(__file__).parent / 'sibling.py')\n",
        )
        _write(tmp_path, "sibling.py", "import deep\n")
        _write(tmp_path, "deep.py", "X = 1\n")

        assert _closure(tmp_path, "verify.py") == ["verify.py", "sibling.py", "deep.py"]

    def test_an_already_listed_target_is_not_added_twice(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "import sibling\n__import__('sibling')\n")
        _write(tmp_path, "sibling.py", "X = 1\n")

        assert _closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_a_literal_stdlib_module_resolves_to_nothing_and_is_not_reported(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path, "verify.py", "import importlib\nimportlib.import_module('json')\n")

        assert _closure(tmp_path, "verify.py") == ["verify.py"]
        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []


class TestUnresolvableLoads:
    @pytest.mark.parametrize(
        ("body", "kind"),
        [
            ("import importlib\nimportlib.import_module(name)\n", "import_module"),
            ("import importlib\nimportlib.import_module('.rel')\n", "import_module"),
            ("__import__(name)\n", "__import__"),
            ("import runpy\nrunpy.run_module(name)\n", "run_module"),
            ("import runpy\nrunpy.run_path(path)\n", "run_path"),
            ("exec(source)\n", "exec"),
            ("eval(build())\n", "eval"),
            (
                "import importlib.util\nimportlib.util.spec_from_file_location('x', path)\n",
                "spec_from_file_location",
            ),
            (
                "import importlib.machinery\nimportlib.machinery.SourceFileLoader('x', path)\n",
                "SourceFileLoader",
            ),
            (
                "import importlib.util\nimportlib.util.spec_from_file_location('x')\n",
                "spec_from_file_location",
            ),
        ],
    )
    def test_a_computed_target_fails_closed(self, tmp_path: Path, body: str, kind: str) -> None:
        _write(tmp_path, "verify.py", body)

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert len(sites) == 1
        assert re.match(r"verify\.py:\d+: unresolvable dynamic load \(", sites[0])
        assert kind in sites[0]

    @pytest.mark.parametrize(
        "expression",
        [
            "Path(__file__).resolve().parent / name",
            "Path(__file__).resolve().with_name(f'{name}.py')",
            "Path(__file__).parent / 'missing.py'",
            "Path(__file__).parents[9] / 'x.py'",
            "Path(__file__).parents[-1] / 'x.py'",
            "Path(f'{name}')",
            "Path(__file__, 'extra')",
            "Path(__file__).parent.joinpath(name)",
            "Path(__file__).parent.with_name('a', 'b')",
            "os.path.join(name, 'x.py')",
            "os.path.join(os.path.dirname(__file__))",
            "Path(__file__).parent.somewhere('x')",
        ],
    )
    def test_a_path_not_built_from_file_and_literals_fails_closed(
        self, tmp_path: Path, expression: str
    ) -> None:
        _write(
            tmp_path,
            "verify.py",
            f"""\
            import importlib.util, os
            from pathlib import Path
            spec = importlib.util.spec_from_file_location("x", {expression})
            """,
        )

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert len(sites) == 1

    def test_a_name_assigned_twice_is_ambiguous_and_fails_closed(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util
            from pathlib import Path
            target = Path(__file__).parent / "a.py"
            target = Path(__file__).parent / "b.py"
            importlib.util.spec_from_file_location("x", target)
            """,
        )
        _write(tmp_path, "a.py", "")
        _write(tmp_path, "b.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_an_augmented_assignment_makes_a_name_ambiguous(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util
            from pathlib import Path
            target = Path(__file__).parent
            target /= "a.py"
            importlib.util.spec_from_file_location("x", target)
            """,
        )
        _write(tmp_path, "a.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_target_that_does_not_exist_fails_closed(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('x', Path(__file__).parent / 'gone.py')\n",
        )

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_target_outside_the_work_tree_fails_closed(
        self, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        outside = tmp_path_factory.mktemp("outside")
        (outside / "evil.py").write_text("", encoding="utf-8")
        tree = tmp_path / "tree"
        depth = len(tree.resolve().parts)
        climbs = "/".join([".."] * (depth - 1))
        _write(
            tree,
            "verify.py",
            "import importlib.util\nimport os\n"
            "importlib.util.spec_from_file_location('x', os.path.join("
            f"os.path.dirname(__file__), '{climbs}', '{outside.resolve().as_posix().lstrip('/')}',"
            " 'evil.py'))\n",
        )

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tree)

        assert len(sites) == 1

    def test_a_symlinked_target_fails_closed(
        self, tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        outside = tmp_path_factory.mktemp("outside")
        real = outside / "real.py"
        real.write_text("", encoding="utf-8")
        (tmp_path / "link.py").symlink_to(real)
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('x', Path(__file__).parent / 'link.py')\n",
        )

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_string_constant_exec_is_not_a_dynamic_load(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "exec('x = 1')\neval('1 + 1')\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_method_named_exec_is_not_the_builtin(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "conn.exec(query)\ncursor.eval(expr)\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_only_python_files_are_scanned(self, tmp_path: Path) -> None:
        _write(tmp_path, "data.json", "exec(source)\n")

        assert gate._unresolvable_dynamic_sites(["data.json"], tmp_path) == []

    def test_an_unreadable_file_is_skipped_without_crashing(self, tmp_path: Path) -> None:
        assert gate._unresolvable_dynamic_sites(["absent.py"], tmp_path) == []

    def test_an_unparseable_file_yields_no_sites(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "def broken(:\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []
        assert _loads(tmp_path, "def broken(:\n", "other.py") == []

    def test_sites_are_reported_in_line_order(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "\n\n__import__(b)\n\nexec(a)\n")

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert [site.split(": ")[0] for site in sites] == ["verify.py:3", "verify.py:5"]


class TestPathDerivationEdges:
    """Direct cases for the evaluator behind the resolvable side of the decision."""

    @staticmethod
    def _derive(expression: str, script: Path, names: dict | None = None):
        import ast

        node = ast.parse(expression, mode="eval").body
        return gate._derive_file_path(node, script, names or {})

    def test_with_suffix_on_a_derived_path(self, tmp_path: Path) -> None:
        script = tmp_path / "verify.py"

        assert self._derive("Path(__file__).with_suffix('.txt')", script) == (
            tmp_path / "verify.txt"
        )

    def test_a_bad_suffix_is_unresolvable_not_a_crash(self, tmp_path: Path) -> None:
        assert self._derive("Path(__file__).with_suffix('txt')", tmp_path / "v.py") is None

    def test_parents_with_a_literal_index(self, tmp_path: Path) -> None:
        script = tmp_path / "a" / "b" / "verify.py"

        assert self._derive("Path(__file__).parents[1]", script) == tmp_path / "a"

    @pytest.mark.parametrize(
        "expression",
        [
            "Path(__file__).ancestors[0]",
            "Path(name).parents[0]",
            "Path(__file__).parents[name]",
            "Path(__file__).parents[-1]",
            "Path(__file__).parents[99]",
            "Path(__file__) + 'x'",
            "Path(__file__).name",
            "name",
            "Path(__file__).parent / other",
        ],
    )
    def test_unmodelled_shapes_derive_nothing(self, tmp_path: Path, expression: str) -> None:
        assert self._derive(expression, tmp_path / "verify.py") is None

    def test_a_reference_chain_longer_than_the_depth_limit_derives_nothing(
        self, tmp_path: Path
    ) -> None:
        import ast

        script = tmp_path / "verify.py"
        names = {f"a{i}": ast.parse(f"a{i - 1}", mode="eval").body for i in range(1, 16)}
        names["a0"] = ast.parse("Path(__file__)", mode="eval").body

        assert self._derive("a3", script, names) == script
        assert self._derive("a15", script, names) is None

    def test_keyword_arguments_are_read(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location(\n"
            "    name='s', location=Path(__file__).parent / 'sibling.py')\n",
        )
        _write(tmp_path, "sibling.py", "X = 1\n")

        assert _closure(tmp_path, "verify.py") == ["verify.py", "sibling.py"]

    def test_a_call_on_a_call_result_is_not_named(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "factory()()\n(lambda: 1)()\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_missing_path_argument_is_unresolvable(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "import runpy\nrunpy.run_path()\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1


class TestSecurityReviewFindings:
    """Cases the security review of this change raised, each with its fix."""

    def test_constant_code_that_imports_is_not_inert(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "exec('import sibling')\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    @pytest.mark.parametrize(
        "code",
        [
            "__import__('os')",
            "import_module('os')",
            "exec('1')",
            "def f(:",
            "x = (",
        ],
    )
    def test_constant_code_that_loads_or_does_not_parse_is_not_inert(
        self, tmp_path: Path, code: str
    ) -> None:
        _write(tmp_path, "verify.py", f"exec({code!r})\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_constant_code_with_no_import_or_load_stays_inert(self, tmp_path: Path) -> None:
        _write(tmp_path, "verify.py", "exec('total = 1 + 1')\neval('[1, 2][0]')\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_dotdot_segment_in_a_derived_path_is_unresolvable(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location(\n"
            "    'x', Path(__file__).parent / 'a' / '..' / 'b.py')\n",
        )
        _write(tmp_path, "b.py", "")
        (tmp_path / "a").mkdir()

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_non_python_target_is_unresolvable(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            "from importlib.machinery import SourceFileLoader\nfrom pathlib import Path\n"
            "SourceFileLoader('x', str(Path(__file__).parent / 'data.txt'))\n",
        )
        _write(tmp_path, "data.txt", "print(1)\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    @pytest.mark.parametrize(
        "preamble",
        [
            "class Path:\n    pass\n",
            "def Path(x):\n    return x\n",
            "os = fake\n",
            "__file__ = '/elsewhere/x.py'\n",
            "from mypkg import Path\n",
            "import mypkg as os\n",
            "def f(os):\n    pass\n",
        ],
    )
    def test_a_file_that_rebinds_path_os_or_file_is_never_resolved(
        self, tmp_path: Path, preamble: str
    ) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path as _P\n"
            + preamble
            + "importlib.util.spec_from_file_location('x', Path(__file__).parent / 'sibling.py')\n",
        )
        _write(tmp_path, "sibling.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_trusted_pathlib_import_does_not_count_as_shadowing(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nimport os\nimport pathlib\n"
            "from pathlib import Path, PurePath\n"
            "importlib.util.spec_from_file_location('x', Path(__file__).parent / 'sibling.py')\n",
        )
        _write(tmp_path, "sibling.py", "")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    @pytest.mark.parametrize(
        "binding",
        [
            "def f(target):\n    load(target)\n",
            "for target in items:\n    load(target)\n",
            "a, target = pair\n",
            "with open(p) as target:\n    load(target)\n",
            "[load(target) for target in items]\n",
            "(target := compute())\n",
            "[target, other] = pair\n",
        ],
    )
    def test_a_name_bound_in_another_way_is_ambiguous(self, tmp_path: Path, binding: str) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target = Path(__file__).parent / 'sibling.py'\n"
            + binding
            + "importlib.util.spec_from_file_location('x', target)\n",
        )
        _write(tmp_path, "sibling.py", "")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_an_annotated_single_assignment_still_resolves(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target: Path = Path(__file__).parent / 'sibling.py'\n"
            "importlib.util.spec_from_file_location('x', target)\n",
        )
        _write(tmp_path, "sibling.py", "")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []

    def test_a_declaration_without_a_value_is_not_an_assignment(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "target: Path\n"
            "importlib.util.spec_from_file_location('x', target)\n",
        )

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1

    def test_a_file_the_parser_gives_up_on_is_reported_not_read_as_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(tmp_path, "verify.py", "x = 1\n")

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RecursionError("too deep")

        monkeypatch.setattr(gate.ast, "parse", _boom)

        sites = gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)

        assert sites == ["verify.py:1: unresolvable dynamic load (unparseable)"]

    def test_line_breaks_in_a_listed_name_are_escaped(self) -> None:
        forged = "a.py\n  b.py\r\u2028c.py\u2029"

        rendered = gate._one_line(forged)

        assert "\n" not in rendered
        assert "\r" not in rendered
        assert "\u2028" not in rendered
        assert "\u2029" not in rendered
        assert rendered == "a.py\\n  b.py\\r\\u2028c.py\\u2029"

    def test_the_halt_message_names_the_dynamic_load_route(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        script = _write(repo, "verify.py", "import sys\n__import__(sys.argv[1])\n")
        config = repo / "pr-review-config.yaml"
        config.write_text(json.dumps({"completion_criteria": _criteria(script)}), encoding="utf-8")
        _trust(repo)

        rc = gate.main(["--config", str(config), "--pull-request", "1"])

        err = capsys.readouterr().err
        assert rc == 2
        assert "unresolvable dynamic load" in err
        assert "verify.py:2:" in err


class TestTheConcreteCaseTheAdrNames:
    """``new_pr.py`` loads ``pr_validations.py`` through a computed path."""

    def test_new_pr_falls_on_the_fail_closed_side(self) -> None:
        loads = gate._dynamic_loads(_NEW_PR.read_bytes(), _NEW_PR)

        kinds = [load.kind for load in loads]
        assert "spec_from_file_location" in kinds
        target = next(load for load in loads if load.kind == "spec_from_file_location")
        assert target.path is None

    def test_the_computed_path_shape_from_new_pr_is_unresolvable(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util, sys
            from pathlib import Path

            def _load_sibling(name):
                path = Path(__file__).resolve().with_name(f"{name}.py")
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                return module

            _pr_val = _load_sibling("pr_validations")
            """,
        )
        _write(tmp_path, "pr_validations.py", "X = 1\n")

        assert len(gate._unresolvable_dynamic_sites(["verify.py"], tmp_path)) == 1
        assert _closure(tmp_path, "verify.py") == ["verify.py"]

    def test_the_same_load_with_a_literal_name_resolves_and_is_verified(
        self, tmp_path: Path
    ) -> None:
        """The refactor that keeps python3 -I isolation and gains verification."""
        _write(
            tmp_path,
            "verify.py",
            """\
            import importlib.util
            from pathlib import Path

            path = Path(__file__).resolve().with_name("pr_validations.py")
            spec = importlib.util.spec_from_file_location("pr_validations", path)
            """,
        )
        _write(tmp_path, "pr_validations.py", "X = 1\n")

        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []
        assert _closure(tmp_path, "verify.py") == ["verify.py", "pr_validations.py"]

    def test_no_shipped_verifier_reaches_a_dynamic_load_today(self) -> None:
        """Measured 2026-09-29: the closure of the configured verifiers has none."""
        import yaml

        config = yaml.safe_load(
            (_REPO_ROOT / ".claude/skills/pr-review/pr-review-config.yaml").read_text(
                encoding="utf-8"
            )
        )
        named: set[str] = set()

        def collect(value: object) -> None:
            if isinstance(value, str):
                for token in value.replace('"', " ").replace("'", " ").split():
                    marker = token.find(".claude/skills/")
                    if marker != -1 and token.endswith(".py"):
                        named.add(token[marker:])
            elif isinstance(value, dict):
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(config)
        present = sorted(path for path in named if (_REPO_ROOT / path).is_file())
        assert present, "the config names no verifier script; the scan proves nothing"

        closure = gate._expand_import_closure(present, _REPO_ROOT)

        assert len(closure) > len(present)
        assert gate._unresolvable_dynamic_sites(closure, _REPO_ROOT) == []


def _git(cwd: Path, *args: str) -> None:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(cwd),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    proc = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(gate, "_PROJECT_ROOT", tmp_path)
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _trust(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "trusted")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")


def _criteria(script: Path) -> list[dict]:
    return [
        {
            "name": "Dynamic",
            "verification": "command",
            "command": f"{sys.executable} {script}",
            "pass_when": "stdout-json.ok == true",
        }
    ]


class TestCommandTrustIntegration:
    """Real git, real closure: a dynamic edge is verified or it halts."""

    def test_a_resolvable_dynamic_target_that_diverged_from_the_trusted_ref_halts(
        self, repo: Path
    ) -> None:
        script = _write(
            repo,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('s', Path(__file__).parent / 'sibling.py')\n",
        )
        sibling = _write(repo, "sibling.py", "X = 1\n")
        _trust(repo)
        sibling.write_text("X = 2  # the pull request rewrote this\n", encoding="utf-8")

        result = gate._verify_command_trust(_criteria(script), 1, "origin/main")

        assert result.status == gate.COMMAND_TRUST_UNTRUSTED
        assert "sibling.py" in result.untrusted_files

    def test_a_resolvable_dynamic_target_identical_to_the_trusted_ref_is_trusted(
        self, repo: Path
    ) -> None:
        script = _write(
            repo,
            "verify.py",
            "import importlib.util\nfrom pathlib import Path\n"
            "importlib.util.spec_from_file_location('s', Path(__file__).parent / 'sibling.py')\n",
        )
        _write(repo, "sibling.py", "X = 1\n")
        _trust(repo)

        result = gate._verify_command_trust(_criteria(script), 1, "origin/main")

        assert result.status == gate.COMMAND_TRUST_TRUSTED
        assert "sibling.py" in result.checked_files

    def test_an_unresolvable_dynamic_load_halts_as_untrusted_and_names_the_line(
        self, repo: Path
    ) -> None:
        script = _write(repo, "verify.py", "import sys\n__import__(sys.argv[1])\n")
        _trust(repo)

        result = gate._verify_command_trust(_criteria(script), 1, "origin/main")

        assert result.status == gate.COMMAND_TRUST_UNTRUSTED
        assert result.untrusted_files == ["verify.py:2: unresolvable dynamic load (__import__)"]

    def test_main_halts_before_running_any_command(self, repo: Path) -> None:
        marker = repo / "ran.txt"
        script = _write(
            repo,
            "verify.py",
            f"""\
            import json, pathlib, sys
            pathlib.Path({str(marker)!r}).write_text("ran")
            __import__(sys.argv[1])
            print(json.dumps({{"ok": True}}))
            """,
        )
        config = _write(repo, "pr-review-config.yaml", "placeholder: 1\n")
        config.write_text(
            json.dumps({"completion_criteria": _criteria(script)}),
            encoding="utf-8",
        )
        _trust(repo)

        rc = gate.main(["--config", str(config), "--pull-request", "1"])

        assert rc == 2
        assert not marker.exists()

    def test_approval_lets_an_unresolvable_load_proceed(self, repo: Path) -> None:
        marker = repo / "ran.txt"
        script = _write(
            repo,
            "verify.py",
            f"""\
            import json, pathlib
            pathlib.Path({str(marker)!r}).write_text("ran")
            exec(open(__file__).read().splitlines()[0])
            print(json.dumps({{"ok": True}}))
            """,
        )
        config = repo / "pr-review-config.yaml"
        config.write_text(
            json.dumps({"completion_criteria": _criteria(script)}),
            encoding="utf-8",
        )
        _trust(repo)

        rc = gate.main(
            ["--config", str(config), "--pull-request", "1", "--approve-untrusted-config"]
        )

        assert rc == 0
        assert marker.exists()
