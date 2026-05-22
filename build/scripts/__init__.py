"""Package marker for build/scripts/.

Created per TASK-008-04 (review-axes-convergence) so that downstream
modules can `from build.scripts import ...` without implicit-namespace
quirks. Empty by design; helpers live in sibling modules
(``generate_skills.py``, ``generate_hooks.py``, ``build_all.py``, etc.).
"""
