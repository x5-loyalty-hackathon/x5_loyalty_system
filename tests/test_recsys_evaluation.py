import statistics

from recsys.benchmark import RandomEngine
from recsys.evaluation import run_evaluation
from recsys.profiles import generate_population
from recsys.recipes import RECIPES

ADR_001_HIT_RATE_BAR = 0.70

#: Precision@k must beat the share of the catalog that is relevant anyway by at
#: least this much. ``hit_rate_own`` is kept as a reported number but is no
#: longer asserted on: once the relevance label stopped gating on
#: ``missing_count``, base relevance rose to ~43%, at which point "at least one
#: of three is relevant" is 1-(1-0.43)^3 = 82% for a *random* ranker and the
#: 70% bar stopped being a bar. See ``EvalResult.precision_at_k_own``.
ADR_001_PRECISION_LIFT_BAR = 0.25

#: ADR-001 allows 30-50 profiles. Use the top of that range: at 30 profiles one
#: profile is worth 0.033, so a single population lands within noise of the bar
#: and the test becomes a coin flip as the recipe catalog grows (hit_rate_own is
#: a top-3 metric, so it falls mechanically with catalog size).
ADR_001_PROFILES = 50

#: Seeds the bar is checked over, so a lucky or unlucky population cannot on its
#: own decide whether the target is met.
ADR_001_SEEDS = (321, 7, 42, 55, 91, 100, 2024, 13, 777, 8)

#: No single population may collapse, even where the mean clears the bar.
ADR_001_PER_SEED_FLOOR_LIFT = 0.15


def test_ranking_beats_the_base_relevance_rate(ml_engine) -> None:
    """ADR-001's intent — the ranker earns its place — on a metric that can fail."""
    profiles = generate_population(ADR_001_PROFILES, seed=321)
    result = run_evaluation(ml_engine, profiles, list(RECIPES))
    assert 0.0 <= result.hit_rate_own <= 1.0
    assert 0.0 <= result.hit_rate_shuffled <= 1.0
    assert 0.0 < result.base_relevance_rate < 1.0
    assert result.precision_lift >= ADR_001_PRECISION_LIFT_BAR, (
        f"precision@{result.top_k} {result.precision_at_k_own:.2f} is only "
        f"{result.precision_lift:+.2f} over the {result.base_relevance_rate:.2f} "
        f"base relevance rate"
    )


def test_the_precision_bar_is_one_a_random_ranker_fails(ml_engine) -> None:
    """A bar noise can clear measures nothing — the flaw that hid in hit_rate.

    This is the evaluation-side twin of the benchmark's discrimination check.
    """
    profiles = generate_population(ADR_001_PROFILES, seed=321)
    noise = run_evaluation(RandomEngine(), profiles, list(RECIPES))
    assert noise.precision_lift < ADR_001_PRECISION_LIFT_BAR, (
        "a random ranker clears the bar; the metric is not measuring ranking"
    )

    trained = run_evaluation(ml_engine, profiles, list(RECIPES))
    assert trained.precision_at_k_own > noise.precision_at_k_own


def test_hit_rate_flatters_a_random_ranker_but_precision_does_not(ml_engine) -> None:
    """Why the ADR-001 assertion moved off ``hit_rate_own``.

    Both metrics are computed on the same random ranker. ``hit_rate_own`` puts
    it within a few points of the 70% target — respectable-looking, and it
    would clear the bar outright on a slightly easier population. Precision
    reports the truth: no lift over simply drawing recipes at random.
    """
    profiles = generate_population(ADR_001_PROFILES, seed=321)
    noise = run_evaluation(RandomEngine(), profiles, list(RECIPES))

    assert noise.hit_rate_own > ADR_001_HIT_RATE_BAR - 0.10
    assert noise.precision_lift < 0.05
    assert abs(noise.precision_at_k_own - noise.base_relevance_rate) < 0.05

    trained = run_evaluation(ml_engine, profiles, list(RECIPES))
    # The metric that still separates the two.
    assert trained.precision_lift - noise.precision_lift > 0.25


def test_precision_lift_holds_across_seeds(ml_engine) -> None:
    """The bar is a property of the recommender, not of one population."""
    lifts = [
        run_evaluation(
            ml_engine, generate_population(ADR_001_PROFILES, seed=seed), list(RECIPES)
        ).precision_lift
        for seed in ADR_001_SEEDS
    ]
    assert statistics.mean(lifts) >= ADR_001_PRECISION_LIFT_BAR
    assert min(lifts) >= ADR_001_PER_SEED_FLOOR_LIFT, f"a population collapsed: {lifts}"


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
