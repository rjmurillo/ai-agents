"""Make sibling helper modules (round_cap_harness) importable by the tests here."""

import sys
from pathlib import Path

_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
