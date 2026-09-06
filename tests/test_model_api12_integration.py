"""Compatibility of c28b613 scorer/catalog with our API 1.2, not an uplift eval."""

import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys

from app.contracts import Recipe, RecommendationMode, RecommendationRequest
from recsys.model import FEATURE_NAMES, compute_features, compute_user_stats
from recsys.pantry import available_ingredient_ids
from recsys.profiles import generate_population
from recsys.recipe_metadata import RECIPE_METADATA
from recsys.recipes import RECIPES

ROOT = Path(__file__).resolve().parents[1]


def mobile_request() -> RecommendationRequest:
    return RecommendationRequest.model_validate_json(
        (ROOT / "mobile/src/fixtures/mealRequest.json").read_text()
    )


def test_expanded_catalog_keeps_metadata_without_changing_api_schema() -> None:
    assert len(RECIPES) == len(RECIPE_METADATA) == 47
    for recipe in RECIPES:
        payload = recipe.model_dump(mode="json")
        assert Recipe.model_validate(payload) == recipe
        assert not {"servings", "dish_type", "cuisine"} & payload.keys()
        metadata = RECIPE_METADATA[recipe.recipe_id]
        assert metadata.servings > 0 and metadata.dish_type and metadata.cuisine
        assert recipe.meal_intent_id == recipe.recipe_id


def test_explicit_home_reduces_required_missing_but_does_not_create_current(ml_engine) -> None:
    request = mobile_request()
    recipe = next(r for r in request.recipe_catalog if r.recipe_id == "chicken_soup")
    before = compute_features(request, recipe)
    request.user.home_ingredient_ids.update(i.ingredient_id for i in recipe.ingredients)
    after = compute_features(request, recipe)
    assert before["_missing_count"] > 0
    assert after["_missing_count"] == 0
    assert after["coverage"] == before["coverage"] == 0
    ranked = {r.recipe_id: r for r in ml_engine.rank(request)}
    assert ranked[recipe.recipe_id].mode == RecommendationMode.EXPLORE


def test_optional_ingredient_is_not_a_required_purchase() -> None:
    request = mobile_request()
    pasta = next(r for r in request.recipe_catalog if r.recipe_id == "pasta_tomatoes")
    assert any(not i.required for i in pasta.ingredients)
    features = compute_features(request, pasta)
    assert features["_missing_count"] == features["_missing_cost"] == 0


def test_history_is_not_an_automatic_pantry_and_prepared_food_is_not_raw(ml_engine) -> None:
    request = mobile_request()
    request.user.home_ingredient_ids = {"unknown_home_ingredient"}
    request.purchase_history = [request.current_receipt.model_copy(deep=True)]
    for item in request.current_receipt.items:
        item.is_prepared_food = True
    assert request.purchase_history
    assert available_ingredient_ids(request) == {"unknown_home_ingredient"}
    assert ml_engine._pantry_policy.enabled is False
    for recipe in request.recipe_catalog:
        assert compute_features(request, recipe)["coverage"] == 0


def profile_request(profile, history=None) -> RecommendationRequest:
    return RecommendationRequest(
        user=profile.user, current_receipt=profile.current_receipt,
        purchase_history=profile.purchase_history if history is None else history,
        recipe_catalog=list(RECIPES), now=profile.now,
    )


def test_cold_start_is_explicit_and_features_stay_finite(ml_engine) -> None:
    profile = generate_population(1, seed=5)[0]
    assert compute_user_stats(profile_request(profile)).has_history
    for history in ([], profile.purchase_history[:1]):
        request = profile_request(profile, history)
        assert not compute_user_stats(request).has_history
        for recipe in RECIPES:
            features = compute_features(request, recipe)
            assert features["history_is_known"] == 0
            assert all(math.isfinite(features[name]) for name in FEATURE_NAMES)
        ranked = ml_engine.rank(request)
        assert len(ranked) == len(RECIPES)
        assert all(0 <= r.score <= 1 for r in ranked)


def test_history_feature_varies_by_user_not_only_by_recipe() -> None:
    # Adapted from c28b613 test_model_features, without its benchmark/API 1.0
    # request builder. Variation is a wiring guard, not proof of relevance.
    requests = [profile_request(p) for p in generate_population(25, seed=11)]
    by_recipe = [
        [compute_features(request, recipe)["history_affinity"] for request in requests]
        for recipe in RECIPES
    ]
    within = statistics.mean(statistics.pvariance(values) for values in by_recipe)
    between = statistics.pvariance(statistics.mean(values) for values in by_recipe)
    assert within / (within + between) > 0.3


def test_model_scores_reproduce_across_python_hash_seeds() -> None:
    source = """
from pathlib import Path
from app.contracts import RecommendationRequest
from recsys.model import MLRecommendationEngine
import json
request = RecommendationRequest.model_validate_json(Path('mobile/src/fixtures/mealRequest.json').read_text())
print(json.dumps([r.model_dump(mode='json') for r in MLRecommendationEngine().rank(request)], sort_keys=True))
"""
    outputs = [
        subprocess.run(
            [sys.executable, "-c", source], cwd=ROOT, check=True, capture_output=True,
            text=True, timeout=30, env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "42")
    ]
    assert json.loads(outputs[0]) == json.loads(outputs[1])
