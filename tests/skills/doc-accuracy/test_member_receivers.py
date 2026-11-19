"""Phase 3 skips a member name only when its receiver is proven not repo API.

A receiver is proven when its chain starts at a type the example declares,
a framework type, a variable declared or constructed with one of those, or
``this`` inside an example that declares a type. A free variable, or one
assigned from an unresolved call, proves nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from example_scope_helpers import mod, run_cli, unresolved

# --- Positive: proven receivers -------------------------------------------------


@pytest.mark.parametrize(
    ("code", "lang"),
    [
        ("class Order { }\nvoid Run(Order order) { order.Validate(); }\n", "csharp"),
        ("class Order { }\nvar order = new Order();\nvar n = order.Items.Count;\n", "csharp"),
        ("class Order { }\nvar total = new Order().Lines.Sum();\n", "csharp"),
        ('Console.WriteLine("x");\nvar now = DateTime.Now.ToString();\n', "csharp"),
        ("void Run(IEnumerable<int> input) {\n    var any = input.Any();\n}\n", "csharp"),
        ('string name = "x";\nvar size = name.Length;\n', "csharp"),
        ('var sb = new StringBuilder();\nsb.Append("x").AppendLine();\n', "csharp"),
        ("class Greeter {\n    void Hi() { this.Say(); }\n}\n", "csharp"),
        (
            "interface User { id: string }\nconst u: User = load();\nconst p = u.Profile;\n",
            "typescript",
        ),
        ("enum Level { High }\nconst l = Level.High;\n", "typescript"),
        ("const d = new Date();\nconst t = d.Ticks;\n", "javascript"),
    ],
)
def test_members_of_proven_receivers_are_not_flagged(code: str, lang: str) -> None:
    assert unresolved(code, lang) == set()


# --- Negative: unproven receivers keep their members checkable ------------------


@pytest.mark.parametrize(
    ("code", "lang", "expected"),
    [
        (
            "var builder = DistributedApplication.CreateBuilder(args);\n"
            'var redis = builder.AddRedis("cache");\n'
            'builder.AddProject<Projects.Api>("api").WithReference(redis);\n',
            "csharp",
            {"AddProject", "AddRedis", "CreateBuilder", "DistributedApplication", "Projects"},
        ),
        ("var total = order.Items.Count;\nvar text = order.ToString();\n", "csharp", {"Items"}),
        ('if (input.Any(c => c > 0)) { Console.WriteLine("y"); }\n', "csharp", {"Any"}),
        ("var user = await _db.Users.FindAsync(userId);\n", "csharp", {"Users", "FindAsync"}),
        ('log.Warn("failed", credentials.UserId);\n', "csharp", {"UserId", "Warn"}),
        ("var w = GhostFactory.Create().Widget;\n", "csharp", {"GhostFactory", "Create"}),
        ("const v = client.GetValue();\n", "typescript", {"GetValue"}),
        ("class Local { }\nvar g = ghost.Run();\n", "csharp", {"Run"}),
    ],
)
def test_members_of_unproven_receivers_stay_flagged(
    code: str, lang: str, expected: set[str]
) -> None:
    assert expected <= unresolved(code, lang)


def test_member_of_a_known_repo_type_is_not_proven_by_the_type() -> None:
    assert unresolved("var w = new ExistingWidget();\nw.Explode();\n", "csharp") == {"Explode"}


def test_this_without_a_declared_type_proves_nothing() -> None:
    assert unresolved("this.Render();\n", "typescript") == {"Render"}


def test_receiver_root_walks_calls_generics_and_indexers() -> None:
    view = 'builder.AddProject<Projects.Api>("api")[0].WithReference(redis)'
    assert mod._receiver_root(view, view.index(".WithReference")) == ("builder", False)
    view = "new Order().Lines"
    assert mod._receiver_root(view, view.index(".Lines")) == ("Order", True)
    view = "(a + b).Total"
    assert mod._receiver_root(view, view.index(".Total"))[0] == ""


# --- Real CLI -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "exit_code", "expected"),
    [
        ("class Order { }\nvoid Run(Order order) { order.Validate(); }", 0, set()),
        (
            'var redis = builder.AddRedis("cache");',
            10,
            {("unresolved_symbol", "AddRedis")},
        ),
    ],
)
def test_cli_member_receivers(
    tmp_path: Path, code: str, exit_code: int, expected: set[tuple[str, str]]
) -> None:
    assert run_cli(tmp_path, "csharp", code) == (exit_code, expected)
