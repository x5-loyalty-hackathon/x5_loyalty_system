"""Pantry inference, and the consequence that keeps it honest."""

from __future__ import annotations

from datetime import timedelta

import pytest

from recsys.experimental.contracts import IngredientSource, RecommendationRequest
from recsys.experimental.recommender import DeterministicMockEngine
from recsys.experimental.safety import SafetyPolicy
from recsys.experimental.service import EFFORT_FIRST, RecommendationService
from recsys.benchmark import Arm, run_benchmark
from recsys.experimental.pantry import (
    CATEGORY_HALF_LIFE_DAYS,
    DISABLED_PANTRY,
    PantryPolicy,
    available_ingredient_ids,
    estimate_pantry,
    survival_probability,
)
from recsys.experimental.profiles import generate_population
from recsys.experimental.recipes import RECIPES
from recsys.regimes import REGIMES
from recsys.response_models import RuleBasedResponder, UserAction
from recsys.true_pantry import TRUE_HALF_LIFE_DAYS, household_speed, true_pantry

RECIPE_LIST = list(RECIPES)


def _request(profile, **overrides) -> RecommendationRequest:
    defaults = dict(
        user=profile.user,
        current_receipt=profile.current_receipt,
        purchase_history=profile.purchase_history,
        recipe_catalog=RECIPE_LIST,
        now=profile.now,
        limit=3,
    )
    defaults.update(overrides)
    return RecommendationRequest(**defaults)


# --- the estimator --------------------------------------------------------


def test_survival_decays_and_respects_category_shelf_life() -> None:
    """Flour outlives milk; both decay; neither survives forever."""
    policy = PantryPolicy.confident()
    for days in (1, 7, 30):
        assert survival_probability(days, "flour", policy) > survival_probability(
            days, "milk", policy
        )
    assert survival_probability(0, "milk", policy) == 1.0
    assert survival_probability(1, "milk", policy) > survival_probability(30, "milk", policy)
    assert 0.0 < survival_probability(365, "flour", policy) < 0.05


def test_disabled_policy_sees_only_todays_basket() -> None:
    """The shipped default must not change behaviour."""
    profile = generate_population(1, seed=5)[0]
    request = _request(profile)
    receipt_ids = {
        ingredient_id
        for item in profile.current_receipt.items
        for ingredient_id in item.ingredient_ids
    }
    assert available_ingredient_ids(request, policy=DISABLED_PANTRY) == receipt_ids

    enabled = available_ingredient_ids(request, policy=PantryPolicy.confident())
    assert enabled >= receipt_ids
    assert len(enabled) > len(receipt_ids), "history should add something"


def test_todays_basket_is_certainty_not_inference() -> None:
    profile = generate_population(1, seed=5)[0]
    pantry = estimate_pantry(_request(profile), policy=PantryPolicy.confident())
    for item in profile.current_receipt.items:
        for ingredient_id in item.ingredient_ids:
            estimate = pantry[ingredient_id]
            assert estimate.probability == 1.0
            assert estimate.is_observed
            assert estimate.reason == "in_basket"


def test_an_ingredient_never_bought_is_never_assumed() -> None:
    """Assuming unseen staples is the error that strands people."""
    profile = generate_population(1, seed=5)[0]
    pantry = estimate_pantry(_request(profile), policy=PantryPolicy.optimistic())
    seen = {
        ingredient_id
        for receipt in [profile.current_receipt, *profile.purchase_history]
        for item in receipt.items
        for ingredient_id in item.ingredient_ids
    }
    assert set(pantry) <= seen


def test_a_stricter_threshold_credits_less() -> None:
    profile = generate_population(1, seed=5)[0]
    request = _request(profile)
    strict = available_ingredient_ids(request, policy=PantryPolicy.confident())
    loose = available_ingredient_ids(request, policy=PantryPolicy.optimistic())
    assert strict <= loose


# --- the world ------------------------------------------------------------


def test_ground_truth_uses_a_different_model_than_the_estimator() -> None:
    """Otherwise the estimator would be calibrated by construction.

    The world consumes faster than the estimator assumes, so the estimator is
    systematically optimistic — the realistic failure direction.
    """
    for category, true_half_life in TRUE_HALF_LIFE_DAYS.items():
        assert true_half_life < CATEGORY_HALF_LIFE_DAYS[category], category


def test_household_speed_varies_between_users_and_is_stable() -> None:
    speeds = {household_speed(f"user_{i}") for i in range(20)}
    assert len(speeds) > 1
    assert household_speed("user_1") == household_speed("user_1")
    assert all(0.6 <= s <= 1.4 for s in speeds)


def test_truth_is_deterministic_and_includes_todays_basket() -> None:
    profile = generate_population(1, seed=5)[0]
    request = _request(profile)
    first, second = true_pantry(request), true_pantry(request)
    assert first.present == second.present

    for item in profile.current_receipt.items:
        for ingredient_id in item.ingredient_ids:
            assert first.has(ingredient_id)


def test_older_purchases_survive_less_often() -> None:
    profile = generate_population(1, seed=5)[0]
    fresh = true_pantry(_request(profile))
    stale = true_pantry(_request(profile), now=profile.now + timedelta(days=120))
    assert len(stale.present) <= len(fresh.present)


# --- the consequence ------------------------------------------------------


def test_service_marks_inferred_stock_as_inferred() -> None:
    """A guess must never be presented as an observation."""
    profile = generate_population(1, seed=5)[0]
    service = RecommendationService(
        engine=DeterministicMockEngine(),
        safety_policy=SafetyPolicy(),
        ranking_policy=EFFORT_FIRST,
        pantry_policy=PantryPolicy.confident(),
    )
    response = service.recommend(_request(profile))
    inferred = [
        ingredient
        for card in response.recommendations
        for ingredient in card.ingredients
        if ingredient.source == IngredientSource.PANTRY_LIKELY
    ]
    for ingredient in inferred:
        assert ingredient.pantry_probability is not None
        assert 0.0 < ingredient.pantry_probability <= 1.0

    observed = [
        ingredient
        for card in response.recommendations
        for ingredient in card.ingredients
        if ingredient.source == IngredientSource.RECEIPT
    ]
    assert all(i.pantry_probability is None for i in observed)


def test_an_arm_without_pantry_can_never_fail_a_cook() -> None:
    """No claim, no way to be wrong — the baseline the others are judged against."""
    result = run_benchmark(
        (Arm(name="plain", engine=DeterministicMockEngine()),),
        regimes=REGIMES[:2],
        responders=(RuleBasedResponder(),),
        users_per_regime=10,
    )
    assert all(cell.failed_cooks == 0 for cell in result.cells)


def test_overconfident_pantry_strands_users_more_often() -> None:
    """The guard against the metric this whole mechanism exists to fix.

    Before failures were counted, the optimistic policy scored best precisely
    because it assumed most. With consequences it buys a smaller gain for a
    much larger failure rate.
    """
    arms = (
        Arm(
            name="careful",
            engine=DeterministicMockEngine(),
            pantry_policy=PantryPolicy.confident(),
        ),
        Arm(
            name="reckless",
            engine=DeterministicMockEngine(),
            pantry_policy=PantryPolicy.optimistic(),
        ),
    )
    result = run_benchmark(
        arms, regimes=REGIMES[:3], responders=(RuleBasedResponder(),), users_per_regime=25
    )
    careful = [c for c in result.cells if c.arm == "careful"]
    reckless = [c for c in result.cells if c.arm == "reckless"]
    assert sum(c.failed_cooks for c in reckless) > sum(c.failed_cooks for c in careful)


def test_failed_cooks_are_subtracted_from_the_primary_metric() -> None:
    result = run_benchmark(
        (
            Arm(
                name="p",
                engine=DeterministicMockEngine(),
                pantry_policy=PantryPolicy.optimistic(),
            ),
        ),
        regimes=REGIMES[:2],
        responders=(RuleBasedResponder(),),
        users_per_regime=20,
    )
    assert sum(c.failed_cooks for c in result.cells) > 0
    for cell in result.cells:
        buys = cell.counts.get(UserAction.BUY.value, 0)
        assert cell.cook_conversion_rate == pytest.approx(
            max(buys - cell.failed_cooks, 0) / cell.n_cards
        )
        assert cell.failed_cook_rate == pytest.approx(cell.failed_cooks / cell.n_cards)
