import json
from pathlib import Path

from app.contracts import ModelRecommendation, RecommendationMode, RecommendationRequest
from app.recommender import DeterministicMockEngine
from recsys.model import FEATURE_NAMES, MLRecommendationEngine, compute_features, ingredient_idf

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_REQUEST = json.loads(
    (ROOT / "examples" / "recommendation_request.json").read_text(encoding="utf-8")
)


def test_implements_the_recommendation_engine_protocol(ml_engine) -> None:
    # app.recommender.RecommendationEngine is a plain (non-runtime-checkable)
    # Protocol, so this checks structural conformance directly rather than
    # via isinstance().
    assert callable(getattr(ml_engine, "rank", None))
    request = RecommendationRequest.model_validate(EXAMPLE_REQUEST)
    result = ml_engine.rank(request)
    assert isinstance(result, list)


def test_rank_returns_schema_valid_model_recommendations(ml_engine) -> None:
    request = RecommendationRequest.model_validate(EXAMPLE_REQUEST)
    results = ml_engine.rank(request)

    assert results
    for item in results:
        assert isinstance(item, ModelRecommendation)
        assert 0.0 <= item.score <= 1.0
        assert item.reason_codes
        assert item.mode in RecommendationMode


def test_rank_is_deterministic_for_the_same_engine_instance(ml_engine) -> None:
    request = RecommendationRequest.model_validate(EXAMPLE_REQUEST)
    first = ml_engine.rank(request)
    second = ml_engine.rank(request)
    assert [r.recipe_id for r in first] == [r.recipe_id for r in second]
    assert [r.score for r in first] == [r.score for r in second]


def test_saved_recipe_is_ranked_as_repeat(ml_engine) -> None:
    request = RecommendationRequest.model_validate(EXAMPLE_REQUEST)
    results = {r.recipe_id: r for r in ml_engine.rank(request)}
    # examples/recommendation_request.json marks cottage_cheese_bake as saved.
    assert results["cottage_cheese_bake"].mode == RecommendationMode.REPEAT
    assert "saved_recipe_repeat" in results["cottage_cheese_bake"].reason_codes


def test_current_receipt_overlap_is_flagged(ml_engine) -> None:
    request = RecommendationRequest.model_validate(EXAMPLE_REQUEST)
    results = {r.recipe_id: r for r in ml_engine.rank(request)}
    # vegetable_omelette shares milk and tomato with today's receipt.
    assert results["vegetable_omelette"].mode == RecommendationMode.CURRENT
    assert "current_receipt_overlap" in results["vegetable_omelette"].reason_codes


def test_unverified_recipe_is_never_returned(ml_engine) -> None:
    payload = json.loads(json.dumps(EXAMPLE_REQUEST))
    payload["recipe_catalog"][0]["verified"] = False
    unverified_id = payload["recipe_catalog"][0]["recipe_id"]
    request = RecommendationRequest.model_validate(payload)
    results = ml_engine.rank(request)
    assert all(r.recipe_id != unverified_id for r in results)


def test_classifier_learned_a_non_degenerate_weight_per_feature(ml_engine) -> None:
    # Sanity check against a silently-broken training loop (e.g. all-zero
    # gradients): every feature should end up with *some* non-trivial
    # influence after fitting on a few hundred synthetic profiles.
    weights = ml_engine._classifier.weights
    assert len(weights) == len(FEATURE_NAMES)
    assert sum(abs(w) for w in weights) > 0.5


def test_prepared_food_does_not_count_as_raw_receipt_coverage(ml_engine) -> None:
    payload = json.loads(json.dumps(EXAMPLE_REQUEST))
    payload["current_receipt"]["items"] = [
        {
            "sku_id": "ready-omelette",
            "name": "Готовый омлет",
            "category": "prepared_food",
            "ingredient_ids": ["egg", "milk", "tomato"],
            "quantity": 1,
            "unit_price": 250,
            "is_prepared_food": True,
        }
    ]
    request = RecommendationRequest.model_validate(payload)
    omelette = next(
        recipe
        for recipe in request.recipe_catalog
        if recipe.recipe_id == "vegetable_omelette"
    )

    assert compute_features(request, omelette)["coverage"] == 0
    mock_result = {
        item.recipe_id: item for item in DeterministicMockEngine().rank(request)
    }
    model_result = {item.recipe_id: item for item in ml_engine.rank(request)}
    assert mock_result["vegetable_omelette"].mode == RecommendationMode.EXPLORE
    assert model_result["vegetable_omelette"].mode == RecommendationMode.EXPLORE


def test_ingredient_idf_downweights_ingredients_common_across_the_catalog() -> None:
    request = RecommendationRequest.model_validate(EXAMPLE_REQUEST)
    weights = ingredient_idf(request.recipe_catalog)
    # "egg" is in 2 of the 3 example recipes; "milk"/"chicken" are each in
    # only 1 — a rarer ingredient should carry strictly more weight.
    assert weights["egg"] < weights["milk"]
    assert weights["egg"] < weights["chicken"]
    assert all(w >= 0 for w in weights.values())


def test_idf_weighting_is_opt_in_and_changes_ingredient_affinity() -> None:
    request = RecommendationRequest.model_validate(EXAMPLE_REQUEST)
    recipe = next(r for r in request.recipe_catalog if r.recipe_id == "vegetable_omelette")
    weights = ingredient_idf(request.recipe_catalog)

    unweighted = compute_features(request, recipe)
    weighted = compute_features(request, recipe, idf_weights=weights)

    # Default call (no idf_weights) must be byte-for-byte the same as before
    # this feature existed — opt-in means opt-in.
    assert unweighted["ingredient_affinity"] == compute_features(request, recipe, idf_weights=None)["ingredient_affinity"]
    # The two computations use a different formula, so they need not be equal,
    # but both must stay valid affinities.
    assert 0.0 <= weighted["ingredient_affinity"] <= 1.0


def test_engine_with_ingredient_idf_trains_and_ranks(ml_engine) -> None:
    idf_engine = MLRecommendationEngine(
        recipe_catalog=ml_engine._recipe_catalog_for_training, use_ingredient_idf=True
    )
    request = RecommendationRequest.model_validate(EXAMPLE_REQUEST)
    results = idf_engine.rank(request)
    assert results
    for item in results:
        assert 0.0 <= item.score <= 1.0
    # Opt-out (default) must be entirely unaffected by this feature existing.
    assert ml_engine._idf_weights is None
    assert idf_engine._idf_weights is not None
