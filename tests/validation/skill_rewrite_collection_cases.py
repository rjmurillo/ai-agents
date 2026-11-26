"""Source cases for the pytest collection tests in ``test_skill_rewrite_collection.py``."""

from __future__ import annotations

# Full sources pytest does not collect, beyond rebinds of the name itself.
HIDDEN = [
    ("import pytest\n@pytest.fixture\ndef test_t():\n    pass\n", [], "test_t"),
    ("@(lambda f: None)\ndef test_t():\n    pass\n", [], "test_t"),
    ("def drop(f):\n    return None\n@drop\ndef test_t():\n    pass\n", [], "test_t"),
    ("class TestR:\n    @property\n    def test_r(self):\n        pass\n", ["TestR"], "test_r"),
    (
        "from dataclasses import dataclass\n@dataclass\nclass TestR:\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class Base:\n    __test__ = False\nclass TestR(Base):\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class Base:\n    def __init__(self):\n        pass\nclass TestR(Base):\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("def test_t():\n    pass\nif True:\n    __test__ = False\n", [], "test_t"),
    ("def test_t():\n    pass\n__test__ = ()\n", [], "test_t"),
    ("def test_t():\n    pass\n(__test__ := False)\n", [], "test_t"),
    ("def test_t():\n    pass\n__test__, x = False, 1\n", [], "test_t"),
    (
        "class TestR:\n    def test_r(self):\n        pass\nTestR.test_r.__test__ = False\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class TestR:\n    __init__ = lambda self: None\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class TestR:\n    if True:\n        def __init__(self):\n"
        "            pass\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "def test_t():\n    pass\nclass Helper:\n    global test_t\n    test_t = None\n",
        [],
        "test_t",
    ),
    (
        "class TestR:\n    def test_r(self):\n        pass\nTestR.test_r = None\n",
        ["TestR"],
        "test_r",
    ),
    ("class TestR:\n    def test_r(self):\n        pass\ndel TestR.test_r\n", ["TestR"], "test_r"),
    (
        "def test_t():\n    pass\ntry:\n    raise ValueError\n"
        "except (test_t := ValueError):\n    pass\n",
        [],
        "test_t",
    ),
    # Import-time code, compile errors and hooks that hide the test.
    (
        "import pytest\npytest.skip('x', allow_module_level=True)\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\npytest.importorskip('no_such_module_zz')\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\nclass TestR:\n    pytest.skip('x', allow_module_level=True)\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("def test_t():\n    pass\nraise RuntimeError('x')\n", [], "test_t"),
    ("def test_t():\n    pass\nreturn\n", [], "test_t"),
    ("def test_t(x, x):\n    pass\n", [], "test_t"),
    ("# coding: nonexistent_zz\ndef test_t():\n    pass\n", [], "test_t"),
    (
        "class TestR:\n    from os import EX_OK as __test__\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "class TestR:\n    match 0:\n        case __test__:\n            pass\n"
        "    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "import pytest\ndef kill(f):\n    return None\n@pytest.mark.foo(kill)\n"
        "def test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "class mark:\n    foo = staticmethod(lambda f: None)\n@mark.foo\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\npytest.mark.kill = lambda f: None\n"
        "@pytest.mark.kill\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    ("@mark.foo\ndef test_t():\n    pass\n", [], "test_t"),
    ("import pytest\n@pytest.mark.foo.mark\ndef test_t():\n    pass\n", [], "test_t"),
    ("@pytest.mark.foo\ndef test_t():\n    pass\nimport pytest\n", [], "test_t"),
    ("from pytest import fixture as mark\n@mark.foo\ndef test_t():\n    pass\n", [], "test_t"),
    ("def __getattr__(n):\n    return None\ndef test_t():\n    pass\n", [], "test_t"),
    ("pytest_plugins = ['test_x']\ndef test_t():\n    pass\n", [], "test_t"),
    ("def test_t():\n    yield\n", [], "test_t"),
    ("def test_t():\n    pass\ntest_t.__dict__['__test__'] = False\n", [], "test_t"),
    (
        "import pytest\ndef k(f):\n    return None\nA = [k]\n"
        "@pytest.mark.foo(*A)\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\ndef k(f):\n    return None\n"
        "@pytest.mark.foo(k, **{})\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    ("import pytest\npytestmark = 1\ndef test_t():\n    pass\n", [], "test_t"),
    ("pytestmark = 'x'\ndef test_t():\n    pass\n", [], "test_t"),
    ("pytestmark = [1]\ndef test_t():\n    pass\n", [], "test_t"),
    (
        "import pytest\ndef k(f):\n    return None\npytestmark = pytest.mark.foo(k)\n"
        "def test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "class TestR:\n    pytestmark = 1\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("def test_t():\n    pass\ntest_t.pytestmark = 1\n", [], "test_t"),
    (
        "import pytest\nif True:\n    pytestmark = 1\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    ("pytestmark = pytest.mark.slow\nimport pytest\ndef test_t():\n    pass\n", [], "test_t"),
]
# Full sources pytest collects, with decorators and switches the checker allows.
COLLECTED = [
    (
        "import pytest\n@pytest.mark.usefixtures('tmp_path')\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "import pytest\n@pytest.mark.skip(reason='later')\n"
        "class TestR:\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("import pytest\ndef test_t():\n    pytest.skip('inside the test is fine')\n", [], "test_t"),
    (
        "import pytest\n@pytest.mark.skipif(1 > 2, reason='no')\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    ("import pytest\n@pytest.mark.parametrize('a', [1])\ndef test_t(a):\n    pass\n", [], "test_t"),
    ("from pytest import mark\n@mark.slow\ndef test_t():\n    pass\n", [], "test_t"),
    (
        "import pytest\n@pytest.mark.slow\nclass TestR:\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    (
        "other = type('O', (), {})\nother.__test__ = False\n"
        "flag = False\ndef test_t():\n    pass\n",
        [],
        "test_t",
    ),
    (
        "class TestR:\n    __test__ = True\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
    ("import pytest\npytestmark = pytest.mark.slow\ndef test_t():\n    pass\n", [], "test_t"),
    (
        "import pytest\npytestmark = [pytest.mark.a, pytest.mark.b]\n"
        "class TestR:\n    pytestmark = [pytest.mark.c]\n    def test_r(self):\n        pass\n",
        ["TestR"],
        "test_r",
    ),
]
REBINDS = [
    ("test_t = None", [], "test_t"),
    ("del test_t", [], "test_t"),
    ("from os import path as test_t", [], "test_t"),
    ("test_t: object = None", [], "test_t"),
    ("type test_t = int", [], "test_t"),
    ("for test_t in [None]:\n    pass", [], "test_t"),
    ("with open(__file__) as test_t:\n    pass", [], "test_t"),
    ("(test_t := None)", [], "test_t"),
    ("print(test_t := None)", [], "test_t"),
    ("x = (test_t := None)", [], "test_t"),
    ("if (test_t := None):\n    pass", [], "test_t"),
    ("[test_t := 1 for _ in range(1)]", [], "test_t"),
    ("while (test_t := None):\n    pass", [], "test_t"),
    ("match (test_t := 1):\n    case _:\n        pass", [], "test_t"),
    ("@(test_t := lambda f: f)\ndef helper():\n    pass", [], "test_t"),
    ("def helper(a=(test_t := None)):\n    pass", [], "test_t"),
    ("def helper(*, a=(test_t := None)):\n    pass", [], "test_t"),
    ("class Helper((test_t := object)):\n    pass", [], "test_t"),
    ("@(TestR := lambda c: c)\nclass Helper:\n    pass", ["TestR"], "test_r"),
    ("class Helper(metaclass=(test_t := type)):\n    pass", [], "test_t"),
    ("f = lambda a=(test_t := None): a", [], "test_t"),
    ("from os import *", [], "test_t"),
    ("test_t = staticmethod(test_t)", [], "test_t"),
    ("TestR = None", ["TestR"], "test_r"),
    # A block body runs in module scope, so its bindings count at any depth.
    ("try:\n    test_t = None\nexcept Exception:\n    pass", [], "test_t"),
    ("try:\n    1 / 0\nexcept Exception:\n    test_t = None", [], "test_t"),
    ("try:\n    1 / 0\nexcept Exception as test_t:\n    pass", [], "test_t"),
    ("try:\n    pass\nexcept Exception:\n    pass\nelse:\n    test_t = None", [], "test_t"),
    ("try:\n    pass\nfinally:\n    test_t = None", [], "test_t"),
    ("try:\n    from os import path as test_t\nexcept ImportError:\n    pass", [], "test_t"),
    ("if True:\n    test_t = None", [], "test_t"),
    ("if False:\n    pass\nelif True:\n    test_t = None", [], "test_t"),
    ("if False:\n    pass\nelse:\n    test_t = None", [], "test_t"),
    ("if True:\n    print(test_t := None)", [], "test_t"),
    ("for _ in [1]:\n    test_t = None", [], "test_t"),
    ("for _ in []:\n    pass\nelse:\n    test_t = None", [], "test_t"),
    ("while True:\n    test_t = None\n    break", [], "test_t"),
    ("with open(__file__):\n    test_t = None", [], "test_t"),
    ("match 1:\n    case _:\n        test_t = None", [], "test_t"),
    ("match 1:\n    case test_t:\n        pass", [], "test_t"),
    ("match [1]:\n    case [*test_t]:\n        pass", [], "test_t"),
    ("match {}:\n    case {**test_t}:\n        pass", [], "test_t"),
    ("match 1:\n    case _ if (test_t := None) is None:\n        pass", [], "test_t"),
    (
        "if True:\n    for _ in [1]:\n        match 1:\n            case _:\n"
        "                try:\n                    test_t = None\n"
        "                except Exception:\n                    pass",
        [],
        "test_t",
    ),
    ("try:\n    TestR = None\nexcept Exception:\n    pass", ["TestR"], "test_r"),
]
# pytest collects these, because the rebind leaves a function under the name,
# but the checker cannot prove that statically, so it fails closed.
FAIL_CLOSED = frozenset(
    {
        "@(test_t := lambda f: f)\ndef helper():\n    pass",
        "from os import *",
        "test_t = staticmethod(test_t)",
    }
)
KEPT = [
    "test_t = None\n\ndef test_t():\n    pass\n",
    "from os import *\n\ndef test_t():\n    pass\n",
    "d = {}\nd[test_t] = 1\n",
    "x: test_t\n",
    "f = lambda: (test_t := None)\n",
    "def helper():\n    test_t = None\n",
    "class Helper:\n    test_t = None\n",
    "[test_t for test_t in range(1)]\n",
    "try:\n    x = 1\nexcept Exception:\n    y = 2\n",
    "if True:\n    def helper():\n        test_t = None\n",
]
