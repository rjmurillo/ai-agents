"""Import-graph test selection.

Maps a set of changed Python source files to the pytest files that transitively
import them, so a Python-only diff runs a targeted subset instead of the whole
878s suite. Every uncertain case falls back to the full suite; the subset is
always a superset of the truly-affected tests.
"""
