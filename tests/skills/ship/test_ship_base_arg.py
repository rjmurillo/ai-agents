"""``base_arg_error``: the one home of the ``--base`` acceptance rule."""

from __future__ import annotations

import pytest


class TestBaseArgError:
    """``base_arg_error`` is the one home of the ``--base`` rule: strict, or any valid branch."""

    REFUSED = "--base is not a plain ref"

    @pytest.mark.parametrize("strict", [False, True])
    def test_no_base_and_a_plain_ref_pass_in_both_stages(self, scripts, strict):
        error = scripts[1].base_arg_error
        assert error(None, strict=strict) is None
        assert error("release/2", strict=strict) is None

    def test_a_valid_branch_outside_the_plain_ref_rule_passes_only_the_first_stage(self, scripts):
        error = scripts[1].base_arg_error
        assert error("release/2026+hotfix") is None
        assert error("release/2026+hotfix", strict=True) == self.REFUSED

    @pytest.mark.parametrize("strict", [False, True])
    @pytest.mark.parametrize("bad", ["", "-x", "a..b", "a b", "a:b"])
    def test_an_invalid_branch_is_refused_in_both_stages(self, scripts, strict, bad):
        assert scripts[1].base_arg_error(bad, strict=strict) == self.REFUSED
