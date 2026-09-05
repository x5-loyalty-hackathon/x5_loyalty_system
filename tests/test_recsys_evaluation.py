import statistics

from recsys.evaluation import run_evaluation
from recsys.profiles import generate_population
from recsys.recipes import RECIPES

ADR_001_HIT_RATE_BAR = 0.70

#: ADR-001 allows 30-50 profiles. Use the top of that range: at 30 profiles one
#: profile is worth 0.033, so a single population lands within noise of the bar
#: and the test becomes a coin flip as the recipe catalog grows (hit_rate_own is
#: a top-3 metric, so it falls mechanically with catalog size).
ADR_001_PROFILES = 50

#: Seeds the bar is checked over, so a lucky or unlucky population cannot on its
#: own decide whether the target is met.
ADR_001_SEEDS = (321, 7, 42, 55, 91, 100, 2024, 13, 777, 8)

#: No single population may collapse, even where the mean clears the bar.
ADR_001_PER_SEED_FLOOR = 0.60


def test_hit_rate_own_meets_the_adr_001_bar(ml_engine) -> None:
    profiles = generate_population(ADR_001_PROFILES, seed=321)
    result = run_evaluation(ml_engine, profiles, list(RECIPES))
    assert 0.0 <= result.hit_rate_own <= 1.0
    assert 0.0 <= result.hit_rate_shuffled <= 1.0
    assert result.hit_rate_own >= ADR_001_HIT_RATE_BAR, (
        "ADR-001 target: own-history hit rate >= 70% on 30-50 profiles"
    )


def test_hit_rate_own_holds_across_seeds(ml_engine) -> None:
    """The bar is a property of the recommender, not of one population."""
    rates = [
        run_evaluation(
            ml_engine, generate_population(ADR_001_PROFILES, seed=seed), list(RECIPES)
        ).hit_rate_own
        for seed in ADR_001_SEEDS
    ]
    assert statistics.mean(rates) >= ADR_001_HIT_RATE_BAR
    assert min(rates) >= ADR_001_PER_SEED_FLOOR, f"a population collapsed: {rates}"


def test_coverage_and_diversity_are_reported(ml_engine) -> None:
    profiles = generate_population(20, seed=8)
    result = run_evaluation(ml_engine, profiles, list(RECIPES))
    assert result.coverage > 0.0
    assert result.unique_recipes_recommended > 0
    assert result.unique_recipes_recommended <= result.total_recipes_available
    assert sum(result.mode_distribution.values()) > 0


def test_evaluation_is_deterministic_given_a_seed(ml_engine) -> None:
    profiles = generate_population(15, seed=55)
    a = run_evaluation(ml_engine, profiles, list(RECIPES), seed=11)
    b = run_evaluation(ml_engine, profiles, list(RECIPES), seed=11)
    assert a.hit_rate_own == b.hit_rate_own
    assert a.hit_rate_shuffled == b.hit_rate_shuffled
    assert a.mode_distribution == b.mode_distribution


def test_history_dependent_slice_is_reported_or_explicitly_absent(ml_engine) -> None:
    profiles = generate_population(60, seed=91)
    result = run_evaluation(ml_engine, profiles, list(RECIPES))
    if result.history_dependent_n == 0:
        assert result.hit_rate_own_history_dependent is None
    else:
        assert 0.0 <= result.hit_rate_own_history_dependent <= 1.0
        assert 0.0 <= result.hit_rate_shuffled_history_dependent <= 1.0
