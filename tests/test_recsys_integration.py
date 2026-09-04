"""End-to-end: recsys profiles/recipes/inventory through the real,
unmodified app.service.RecommendationService + app.safety.SafetyPolicy —
the actual "profiles with different recommendations" deliverable, exercised
as a test rather than only as a one-off script."""

import json
from pathlib import Path

from app.contracts import RecommendationRequest, RecommendationResponse
from app.safety import SafetyPolicy
from app.service import RecommendationService
from recsys.generate_examples import generate_examples
from recsys.inventory import generate_inventory
from recsys.recipes import RECIPES


ROOT = Path(__file__).resolve().parents[1]


def test_generate_examples_produces_ten_profiles_with_real_service_output() -> None:
    records = generate_examples()
    assert len(records) == 10
    assert {r["archetype"] for r in records} == {"routine", "explorer", "value", "time_limited"}
    for record in records:
        response = RecommendationResponse.model_validate(record["response"])
        assert response.user_id == record["user_id"]


def test_committed_sample_artifact_matches_current_response_contract() -> None:
    records = json.loads(
        (ROOT / "recsys/examples/sample_recommendations.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(records) == 10
    assert records == generate_examples()
    for record in records:
        RecommendationResponse.model_validate(record["response"])


def test_recommendations_genuinely_differ_across_profiles() -> None:
    records = generate_examples()
    recipe_sets = [
        tuple(sorted(r["recipe_id"] for r in record["response"]["recommendations"])) for record in records
    ]
    # Not every profile should get the identical top-3 recipe set — that
    # would indicate the engine ignores the receipt/history it was given.
    assert len(set(recipe_sets)) > 1

    modes_seen = {rec["mode"] for record in records for rec in record["response"]["recommendations"]}
    assert len(modes_seen) >= 2


def test_full_pipeline_via_recommendation_service_directly(ml_engine) -> None:
    import random

    from recsys.profiles import generate_profile

    rng = random.Random(1)
    profile = generate_profile(rng, 0)
    inventory = generate_inventory(
        rng, now=profile.now, home_store_id=profile.current_receipt.store_id, user_radius_km=profile.user.radius_km
    )
    request = RecommendationRequest(
        user=profile.user,
        current_receipt=profile.current_receipt,
        purchase_history=profile.purchase_history,
        recipe_catalog=list(RECIPES),
        inventory_snapshot=inventory,
        now=profile.now,
        limit=3,
    )
    service = RecommendationService(engine=ml_engine, safety_policy=SafetyPolicy())
    response = service.recommend(request)

    assert isinstance(response, RecommendationResponse)
    assert response.contract_version == "1.1"
    assert len(response.recommendations) <= 3
    for rec in response.recommendations:
        assert rec.missing_count >= 0
        assert rec.reason_codes
