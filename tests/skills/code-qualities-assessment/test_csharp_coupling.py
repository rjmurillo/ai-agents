"""C# directive and resource classification regressions for issue #7406."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "code-qualities-assessment"
    / "scripts"
    / "assess.py"
)
_spec = importlib.util.spec_from_file_location("assess", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
assess_content = _mod.assess_content


@pytest.mark.parametrize(
    "directive",
    [
        "using System.IO;",
        "    using System . IO ; // namespace import",
        "using global::System.IO;",
        "using @namespace.IO;",
        "using IO = System.IO;",
        "using @var = System.IO.MemoryStream;",
        "using Streams = System.Collections.Generic.List<System.IO.Stream>;",
        "using unsafe Pointer = int*;",
        "using static System.Math;",
        "using static Example.Factory<System.IO.Stream>;",
        "global using System.IO;",
        "global using IO = global::System.IO;",
        "global using unsafe Pointer = int*;",
        "global using static System.Math;",
    ],
)
def test_csharp_directives_count_as_dependencies(directive: str) -> None:
    """AC2: Namespace, alias, static, and global directives remain dependencies."""
    coupling = assess_content(Path("Imports.cs"), directive).coupling

    assert coupling.reasons[0] == "1 import/dependency statements"
    assert coupling.value < 10
    assert coupling.confidence == 0.6


@pytest.mark.parametrize(
    "resource",
    [
        "using var stream = new MemoryStream();",
        "    using Stream stream = new MemoryStream();",
        "using System.IO.Stream stream = new MemoryStream();",
        "using global::System.IO.Stream stream = new MemoryStream();",
        "using Resource<Stream> resource = Open();",
        "using @var resource = Open();",
        "using (var stream = new MemoryStream()) { }",
        "using (Stream stream = new MemoryStream()) { }",
        "using (stream) { }",
        "await using var stream = new MemoryStream();",
        "await using Stream stream = new MemoryStream();",
        "await using (var stream = new MemoryStream()) { }",
        "await using (stream) { }",
    ],
)
def test_csharp_resources_are_not_dependencies(resource: str) -> None:
    """AC1: Resource declarations and statements add no dependency imports."""
    baseline = assess_content(Path("Resources.cs"), "using System.IO;\n").coupling
    with_resource = assess_content(Path("Resources.cs"), f"using System.IO;\n{resource}\n").coupling

    assert with_resource == baseline


def test_csharp_resource_cleanup_preserves_coupling() -> None:
    """AC1: The issue's eight resource declarations leave one dependency."""
    imports = "using System.IO;\n"
    resources = "".join(f"using var resource{i} = new MemoryStream();\n" for i in range(8))

    baseline = assess_content(Path("Resources.cs"), imports).coupling
    with_cleanup = assess_content(Path("Resources.cs"), imports + resources).coupling

    assert baseline.reasons[0] == "1 import/dependency statements"
    assert with_cleanup == baseline
