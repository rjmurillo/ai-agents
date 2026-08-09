"""Entry point for python -m memory_sync."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.memory_sync.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
