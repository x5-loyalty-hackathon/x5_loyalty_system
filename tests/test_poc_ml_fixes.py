"""Selective ML fixes keep the serving contract and ranking behavior intact."""

import importlib
import json
from pathlib import Path

import pytest

from app.contracts import RecommendationRequest
from app.safety import SafetyPolicy
from app.service import RecommendationService
from recsys import model


ROOT = Path(__file__).resolve().parents[1]
OLD_EFFORT_REGISTRY = frozenset({"missing_ratio", "missing_cost_norm"})


@pytest.mark.parametrize("module_name", ["recsys.model", "recsys.experimental.model"])
def test_preference_only_vectors_suppress_missing_count_scaled_by_basket(module_name):
    scorer = importlib.import_module(module_name)
    features = {name: 0.3 for name in scorer.FEATURE_NAMES}
    changed = {**features, "missing_vs_basket": 0.9}

    assert scorer._feature_vector(features, include_effort=False) == (
        scorer._feature_vector(changed, include_effort=False)
    )
    assert scorer._feature_vector(features) != scorer._feature_vector(changed)


def test_effort_registry_fix_preserves_default_training_and_final_serving(monkeypatch):
    # Fit with both registries: matching weights also checks that the fix does
    # not change the default training path before final safety/selector output.
    fixed = model.MLRecommendationEngine(training_profiles=30)
    with monkeypatch.context() as before:
        before.setattr(model, "EFFORT_FEATURE_NAMES", OLD_EFFORT_REGISTRY)
        original = model.MLRecommendationEngine(training_profiles=30)

    assert fixed._include_effort is original._include_effort is True
    assert fixed.training_catalog_hash == original.training_catalog_hash
    assert fixed._classifier.weights == original._classifier.weights
    assert fixed._classifier.bias == original._classifier.bias

    fixed_service = RecommendationService(engine=fixed, safety_policy=SafetyPolicy())
    original_service = RecommendationService(engine=original, safety_policy=SafetyPolicy())
    for filename in (
        "examples/recommendation_request.json",
        "mobile/src/fixtures/mealRequest.json",
    ):
        request = RecommendationRequest.model_validate_json((ROOT / filename).read_text())
        actual = fixed_service.recommend_meals(request)
        with monkeypatch.context() as before:
            before.setattr(model, "EFFORT_FEATURE_NAMES", OLD_EFFORT_REGISTRY)
            expected = original_service.recommend_meals(request)
        assert actual == expected
        assert actual.contract_version == "1.3"


def test_static_referral_example_matches_the_default_demo_secret(monkeypatch):
    from app.referral_codes import issue_invite_code

    monkeypatch.delenv("REFERRAL_CODE_SECRET", raising=False)
    example = json.loads((ROOT / "examples/referral_request.json").read_text())
    assert example["invite_code"] == issue_invite_code(example["inviter_user_id"])
