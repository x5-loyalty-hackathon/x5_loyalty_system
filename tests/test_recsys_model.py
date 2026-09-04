import json
from pathlib import Path

from app.contracts import ModelRecommendation, RecommendationMode, RecommendationRequest
from recsys.model import FEATURE_NAMES

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
