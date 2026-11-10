"""The report shows per-harness sampling counts and the cap notice (issue #7187)."""

from render_report import render_page


def _sampling_report(**sampling):
    return {
        "scores": {"overall": 0.8},
        "sampling": {
            "notice": None,
            "per_harness": {
                "claude": {"scoreable": 3, "skill_candidates": 2, "sampled": 1, "overall": 0.75},
                "copilot": {"scoreable": 1, "skill_candidates": 0, "sampled": 0},
            },
            **sampling,
        },
    }


def test_report_lists_per_harness_counts_and_scores():
    page = render_page(_sampling_report())

    assert "<h2>Sampling</h2>" in page
    assert "<td>claude</td><td>3</td><td>2</td><td>1</td><td>75</td>" in page
    assert "<td>copilot</td><td>1</td><td>0</td><td>0</td><td>-</td>" in page
    assert "skill-first within each harness" in page
    assert 'class="notice"' not in page


def test_report_states_when_the_cap_prevented_full_harness_coverage():
    page = render_page(_sampling_report(notice="Cap 1 omits copilot <b>(1 scoreable)</b>."))

    assert 'class="notice">Cap 1 omits copilot &lt;b&gt;(1 scoreable)&lt;/b&gt;.' in page


def test_report_without_sampling_block_has_no_sampling_section():
    assert "<h2>Sampling</h2>" not in render_page({"scores": {"overall": 0.8}})
    assert "<h2>Sampling</h2>" not in render_page({"scores": {"overall": 0.8}, "sampling": {}})
