"""The bench harness, and the properties that keep its comparisons honest."""

from __future__ import annotations

import pytest

from recsys.experimental.recommender import DeterministicMockEngine
from recsys.experimental.service import BLENDED, EFFORT_FIRST, RELEVANCE_FIRST
from recsys.benchmark import (
    PRIMARY_METRIC,
    Arm,
    CellDelta,
    Comparison,
    RandomEngine,
    default_arms,
    run_benchmark,
    stable_seed,
    verdict,
)
from recsys.regimes import REGIMES
from recsys.experimental.catalog_freeze import baseline_catalog, recipe_content_hash
from recsys.experimental.recipes import RECIPES
from recsys.response_models import (
    EconomicResponder,
    RuleBasedResponder,
    UserAction,
)

SMALL_REGIMES = REGIMES[:3]
RESPONDERS = (RuleBasedResponder(), EconomicResponder())


@pytest.mark.parametrize("recipes", [None, baseline_catalog()[:5]])
def test_benchmark_records_the_actual_catalog_without_changing_default(recipes) -> None:
    result = run_benchmark(
        (Arm(name="mock", engine=DeterministicMockEngine()),),
        regimes=SMALL_REGIMES[:1],
        responders=RESPONDERS[:1],
        users_per_regime=2,
        recipes=recipes,
    )
    expected = list(RECIPES) if recipes is None else recipes
    assert result.recipe_catalog_hash == recipe_content_hash(expected)
    if recipes is None:
        assert result.recipe_catalog_hash != recipe_content_hash(baseline_catalog())


def _run(arms, **kwargs):
    return run_benchmark(
        arms,
        regimes=SMALL_REGIMES,
        responders=RESPONDERS,
        users_per_regime=kwargs.pop("users_per_regime", 6),
        **kwargs,
    )


# --- the property the whole comparison rests on -------------------------


def test_arms_are_paired_on_identical_users_and_inventory() -> None:
    """Two arms wrapping the same engine must produce byte-identical cells.

    This is the load-bearing guarantee: if inventory or profiles were drawn per
    arm, supply noise would show up as a ranking effect and every delta in the
    report would be partly luck. Duplicating one engine is the cleanest probe —
    any difference at all can only come from the harness.
    """
    engine = DeterministicMockEngine()
    result = _run(
        (
            Arm(name="twin_a", engine=engine, ranking_policy=EFFORT_FIRST),
            Arm(name="twin_b", engine=engine, ranking_policy=EFFORT_FIRST),
        )
    )
    for regime in SMALL_REGIMES:
        for responder in RESPONDERS:
            left = result.cell("twin_a", regime.name, responder.name)
            right = result.cell("twin_b", regime.name, responder.name)
            assert left is not None and right is not None
            assert left.counts == right.counts
            assert left.n_cards == right.n_cards

    comparison = result.compare("twin_a", "twin_b")
    assert all(delta.delta == 0.0 for delta in comparison.deltas)
    assert comparison.independent_win_rate == 0.0


def test_the_ranking_policy_alone_changes_the_outcome() -> None:
    """Same engine, different policy: the harness must register the difference."""
    engine = DeterministicMockEngine()
    result = _run(
        (
            Arm(name="effort", engine=engine, ranking_policy=EFFORT_FIRST),
            Arm(name="relevance", engine=engine, ranking_policy=RELEVANCE_FIRST),
        )
    )
    comparison = result.compare("effort", "relevance")
    assert any(delta.delta != 0.0 for delta in comparison.deltas)


def test_seeds_are_stable_across_processes() -> None:
    """``hash()`` on strings is randomised per process; seeds must not be.

    Two sweeps with identical arguments once disagreed because the responder
    RNG was seeded from ``hash((seed, responder.name))``. Pinning the value
    catches any return to a process-local hash — a same-process determinism
    test cannot see that bug at all.
    """
    assert stable_seed("seed", "rule_based") == 2334935858
    assert stable_seed(1, 2, 3) == stable_seed(1, 2, 3)
    assert stable_seed("a", "b") != stable_seed("b", "a")


def test_run_is_deterministic_given_a_seed() -> None:
    arms = (Arm(name="a", engine=DeterministicMockEngine()),)
    first = _run(arms, seed=7)
    second = _run(arms, seed=7)
    assert [c.counts for c in first.cells] == [c.counts for c in second.cells]

    different = _run(arms, seed=8)
    assert [c.counts for c in first.cells] != [c.counts for c in different.cells]


def test_every_arm_regime_responder_cell_exists() -> None:
    arms = (
        Arm(name="a", engine=DeterministicMockEngine()),
        Arm(name="b", engine=RandomEngine(), is_control=True),
    )
    result = _run(arms)
    assert len(result.cells) == len(arms) * len(SMALL_REGIMES) * len(RESPONDERS)
    assert result.n_regimes == len(SMALL_REGIMES)
    for cell in result.cells:
        assert cell.n_cards > 0
        assert sum(cell.counts.values()) == cell.n_cards


# --- metric semantics ----------------------------------------------------


def test_cook_conversion_excludes_substitutions() -> None:
    """The bug this metric exists to avoid: substitutions rewarding bad advice."""
    result = _run((Arm(name="a", engine=DeterministicMockEngine()),))
    for cell in result.cells:
        buys = cell.counts.get(UserAction.BUY.value, 0)
        subs = cell.counts.get(UserAction.SUBSTITUTE.value, 0)
        assert cell.cook_conversion_rate == pytest.approx(buys / cell.n_cards)
        assert cell.substitute_rate == pytest.approx(subs / cell.n_cards)
        assert cell.retail_conversion_rate == pytest.approx(
            (buys + subs) / cell.n_cards
        )
        if subs:
            assert cell.retail_conversion_rate > cell.cook_conversion_rate


def test_primary_metric_is_the_cook_rate() -> None:
    assert PRIMARY_METRIC == "cook_conversion_rate"
    result = _run((Arm(name="a", engine=DeterministicMockEngine()),))
    assert set(result.arm_means()) == {"a"}


def test_rates_are_bounded() -> None:
    result = _run(default_arms()[:2], users_per_regime=4)
    for cell in result.cells:
        for value in (
            cell.cook_conversion_rate,
            cell.substitute_rate,
            cell.retail_conversion_rate,
            cell.engagement_rate,
        ):
            assert 0.0 <= value <= 1.0
        assert cell.cards_per_user <= 3.0


# --- comparison arithmetic ----------------------------------------------


def _comparison(pairs: list[tuple[str, str, float, float]]) -> Comparison:
    return Comparison(
        baseline="A",
        challenger="B",
        metric=PRIMARY_METRIC,
        deltas=tuple(
            CellDelta(regime=r, responder=s, baseline_value=b, challenger_value=c)
            for r, s, b, c in pairs
        ),
    )


def test_win_rate_and_unanimity() -> None:
    comparison = _comparison(
        [
            ("w1", "rule_based", 0.1, 0.2),
            ("w2", "rule_based", 0.1, 0.2),
            ("w3", "rule_based", 0.1, 0.2),
            ("w1", "probabilistic", 0.1, 0.2),
            ("w2", "probabilistic", 0.1, 0.2),
            ("w3", "probabilistic", 0.1, 0.05),
            ("w1", "economic", 0.1, 0.2),
            ("w2", "economic", 0.1, 0.2),
            ("w3", "economic", 0.1, 0.2),
        ]
    )
    assert comparison.independent_win_rate == pytest.approx(8 / 9)
    assert comparison.is_unanimous_across_responders is True
    assert len(comparison.losing_cells()) == 1


def test_a_simulator_split_down_the_middle_is_not_a_win() -> None:
    """Exactly half the worlds is no evidence, so unanimity needs a strict majority."""
    comparison = _comparison(
        [
            ("w1", "rule_based", 0.1, 0.2),
            ("w2", "rule_based", 0.1, 0.2),
            ("w1", "probabilistic", 0.1, 0.2),
            ("w2", "probabilistic", 0.1, 0.05),
            ("w1", "economic", 0.1, 0.2),
            ("w2", "economic", 0.1, 0.2),
        ]
    )
    assert comparison.win_rate_by_responder()["probabilistic"] == 0.5
    assert comparison.is_unanimous_across_responders is False


def test_one_enthusiastic_simulator_cannot_carry_a_verdict() -> None:
    """Majority overall, but two of three simulators disagree."""
    comparison = _comparison(
        [
            ("w1", "rule_based", 0.1, 0.9),
            ("w2", "rule_based", 0.1, 0.9),
            ("w3", "rule_based", 0.1, 0.9),
            ("w1", "probabilistic", 0.1, 0.05),
            ("w2", "probabilistic", 0.1, 0.05),
            ("w1", "economic", 0.1, 0.05),
        ]
    )
    assert comparison.independent_win_rate == 0.5
    assert comparison.is_unanimous_across_responders is False


def test_oracle_cells_are_excluded_from_the_independent_rate() -> None:
    comparison = _comparison(
        [
            ("w1", "rule_based", 0.1, 0.05),
            ("w1", "oracle_selfref", 0.1, 0.9),
        ]
    )
    assert comparison.independent_win_rate == 0.0
    assert comparison.win_rate() == 0.5


# --- bench validity ------------------------------------------------------


def test_discrimination_is_measured_over_the_best_candidate() -> None:
    """Bench blindness and a weak arm are opposite conclusions, not one number."""
    result = _run(
        (
            Arm(name="good", engine=DeterministicMockEngine(), ranking_policy=BLENDED),
            Arm(
                name="noise",
                engine=RandomEngine(),
                ranking_policy=RELEVANCE_FIRST,
                is_control=True,
            ),
        )
    )
    checks = result.discrimination_check()
    assert set(checks) == {"noise"}
    assert result.candidate_arms() == ("good",)
    assert result.control_arms() == ("noise",)


def test_verdict_states_its_own_limits() -> None:
    result = _run(default_arms()[:3] + (default_arms()[-1],), users_per_regime=4)
    text = verdict(result, result.compare("heuristic/effort", "ml/effort"))
    assert "not a forecast" in text
    assert "not a p-value" in text
    assert "per simulator" in text
