"""Feature-space guarantees, including one defect that turned out not to be one."""

from __future__ import annotations

import random
import statistics
from datetime import datetime, timezone

import pytest

from app.contracts import RecommendationRequest
from recsys.benchmark import _build_request
from recsys.inventory import generate_inventory
from recsys.model import (
    FEATURE_NAMES,
    MLRecommendationEngine,
    compute_features,
    compute_user_stats,
)
from recsys.profiles import generate_population
from recsys.recipes import RECIPES

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
RECIPE_LIST = list(RECIPES)


@pytest.fixture(scope="module")
def sampled_features():
    """(feature -> recipe_id -> [value per user]) over a small population."""
    rng = random.Random(3)
    data = {name: {r.recipe_id: [] for r in RECIPE_LIST} for name in FEATURE_NAMES}
    for profile in generate_population(25, seed=11):
        inventory = generate_inventory(
            rng,
            now=profile.now,
            home_store_id=profile.current_receipt.store_id,
            user_radius_km=profile.user.radius_km,
        )
        request = _build_request(profile, RECIPE_LIST, inventory, [])
        for recipe in RECIPE_LIST:
            features = compute_features(request, recipe)
            for name in FEATURE_NAMES:
                data[name][recipe.recipe_id].append(features[name])
    return data


def _user_variance_share(by_recipe: dict[str, list[float]]) -> float:
    """Share of variance that is between users on the same recipe.

    Zero means the feature cannot personalise at all: every user sees the same
    number for a given recipe. That is how ``history_affinity`` was caught —
    it was named for personalisation and delivered none.
    """
    means = [statistics.mean(v) for v in by_recipe.values() if v]
    between = statistics.pvariance(means) if len(means) > 1 else 0.0
    within = statistics.mean(
        [statistics.pvariance(v) for v in by_recipe.values() if len(v) > 1]
    )
    total = between + within
    return within / total if total else 0.0


def test_history_affinity_actually_varies_between_users(sampled_features) -> None:
    """The regression guard for the defect that started the label repair.

    It used to divide a count of recipe categories by a count of recipe
    ingredients, and every user's history covered all seven categories, so the
    result was a recipe-shape constant.
    """
    share = _user_variance_share(sampled_features["history_affinity"])
    assert share > 0.3, f"history_affinity personalises only {share:.2f} of its variance"


def test_user_state_proxies_are_pure_user_signal(sampled_features) -> None:
    """They describe the shopper, so they must not vary with the recipe."""
    for name in (
        "markdown_share_history",
        "basket_size_norm",
        "visit_cadence_norm",
        "brand_concentration",
    ):
        assert _user_variance_share(sampled_features[name]) > 0.9, name


def test_time_fit_is_deliberately_an_item_feature(sampled_features) -> None:
    """Not a defect, despite looking like one — see the note in compute_features.

    Personalising it was tried twice and reverted: within-effort AUC did not
    move, because ``prep_vs_cadence`` already carries the user half. This test
    pins the decision so the "fix" is not reattempted blind.
    """
    time_fit_share = _user_variance_share(sampled_features["time_fit"])
    interaction_share = _user_variance_share(sampled_features["prep_vs_cadence"])
    assert time_fit_share < 0.05
    assert interaction_share > time_fit_share, (
        "the interaction must carry more user signal than the item term"
    )


# --- cold start -----------------------------------------------------------


def _request(history) -> RecommendationRequest:
    profile = generate_population(1, seed=5)[0]
    return RecommendationRequest(
        user=profile.user,
        current_receipt=profile.current_receipt,
        purchase_history=history,
        recipe_catalog=RECIPE_LIST,
        now=profile.now,
        limit=3,
    )


def test_a_user_without_history_is_flagged_not_faked() -> None:
    """A fabricated cadence must not look like a measurement.

    With no history the proxies fall back to a single receipt and a constant
    cadence. That constant is indistinguishable from a real rare shopper unless
    something says so, which is what ``history_is_known`` is for.
    """
    profile = generate_population(1, seed=5)[0]
    warm = _build_request(profile, RECIPE_LIST, [], [])
    assert compute_features(warm, RECIPE_LIST[0])["history_is_known"] == 1.0

    for history in ([], profile.purchase_history[:1]):
        cold = _request(history)
        assert compute_user_stats(cold).has_history is False
        assert compute_features(cold, RECIPE_LIST[0])["history_is_known"] == 0.0


def test_ranking_still_works_without_any_history() -> None:
    engine = MLRecommendationEngine()
    ranked = engine.rank(_request([]))
    assert len(ranked) == len(RECIPE_LIST)
    assert all(0.0 <= r.score <= 1.0 for r in ranked)


def test_features_are_finite_and_bounded_in_degenerate_cases() -> None:
    import math

    for history in ([], generate_population(1, seed=5)[0].purchase_history[:1]):
        request = _request(history)
        for recipe in RECIPE_LIST[:5]:
            for name, value in compute_features(request, recipe).items():
                assert math.isfinite(value), f"{name} is not finite"
                if not name.startswith("_"):
                    assert -10.0 <= value <= 10.0, f"{name} = {value}"
