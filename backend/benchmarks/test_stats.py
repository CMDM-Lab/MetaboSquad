"""Tests for the scoring functions in figure_bench.

These are the only fully-implemented parts of the harness (both reviewer entry
points are still stubs), so they are the parts that can silently produce
plausible-but-wrong numbers. The McNemar case uses the counts actually reported
in the thesis — 24 cases rescued, 4 lost, across 150 predictions — so a
regression shows up against a number someone can check.

    venv/bin/python -m pytest benchmarks/test_stats.py -q
"""

from __future__ import annotations

import math

from benchmarks.figure_bench import BinaryScore, continuous_metrics, friedman, mcnemar


def test_mcnemar_matches_thesis_reported_counts():
    a = [True] * 24 + [False] * 4 + [True] * 122     # MetaboSquad correct
    b = [False] * 24 + [True] * 4 + [True] * 122     # baseline correct
    m = mcnemar(a, b)
    assert (m["b"], m["c"]) == (24, 4)
    assert m["p_value"] < 0.001


def test_mcnemar_uses_exact_test_when_discordant_pairs_are_few():
    # b=5, c=2, n=7 -> 2 * P(X <= 2) = 2 * (1 + 7 + 21) / 128
    m = mcnemar([True] * 5 + [False] * 2 + [True] * 20,
                [False] * 5 + [True] * 2 + [True] * 20)
    assert m["method"] == "exact binomial"
    assert math.isclose(m["p_value"], 58 / 128)


def test_mcnemar_no_discordant_pairs_is_not_significant():
    assert mcnemar([True] * 10, [True] * 10)["p_value"] == 1.0


def test_binary_score_f1():
    s = BinaryScore("t")
    for pred, actual in [(1, 1), (1, 1), (1, 0), (0, 1), (0, 0)]:
        s.add(bool(pred), bool(actual))
    assert (s.tp, s.fp, s.fn, s.tn) == (2, 1, 1, 1)
    assert math.isclose(s.f1, 2 / 3)


def test_continuous_metrics_perfect_prediction():
    m = continuous_metrics([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert m["mae"] == 0
    assert math.isclose(m["pearson_r"], 1.0)


def test_continuous_metrics_constant_offset():
    m = continuous_metrics([2.0, 3.0, 4.0], [1.0, 2.0, 3.0])
    assert math.isclose(m["mae"], 1.0)
    assert math.isclose(m["mape"], (1 + 1 / 2 + 1 / 3) / 3 * 100)
    assert math.isclose(m["pearson_r"], 1.0)


def test_continuous_metrics_survives_missing_values():
    assert continuous_metrics([1.0, None, 3.0], [1.0, 2.0, None])["n"] == 1


def test_friedman_maximal_when_every_block_ranks_identically():
    # statistic reaches n * (k - 1) when the ordering repeats in every block
    f = friedman({"a": [1, 1, 1, 1], "b": [2, 2, 2, 2], "c": [3, 3, 3, 3]})
    assert math.isclose(f["statistic"], 8.0)
    assert f["df"] == 2


def test_friedman_zero_when_all_values_tie():
    f = friedman({"a": [5, 5, 5], "b": [5, 5, 5], "c": [5, 5, 5]})
    assert math.isclose(f["statistic"], 0.0, abs_tol=1e-9)
    assert f["rank_sums"] == [6.0, 6.0, 6.0]
