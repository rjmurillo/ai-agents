"""Spec<->Code drift detection for the /sync command (issue #1997).

The package exposes :mod:`scripts.sync.detect_spec_drift`, which scans the
specification tier (REQ/DESIGN/TASK) for references to code paths and
artifacts that no longer exist in the working tree. A stale reference is
evidence the spec drifted from the code.
"""
