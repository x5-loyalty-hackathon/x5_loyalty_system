import json
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from app.contracts import ChallengeSelection, ModelRecommendation, RecommendationMode
from app.main import _build_recommendation_engine, app
from app.safety import SafetyPolicy
from app.service import RecommendationService


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_REQUEST = json.loads(
    (ROOT / "examples" / "recommendation_request.json").read_text(
        encoding="utf-8"
    )
)
client = TestClient(app)


def post_recommendation(payload: dict) -> dict:
    response = client.post("/api/v1/recommendations", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def recommendation_by_id(body: dict, recipe_id: str) -> dict:
    return next(
        item for item in body["recommendations"] if item["recipe_id"] == recipe_id
    )


def ingredient_by_id(recommendation: dict, ingredient_id: str) -> dict:
    return next(
        item
        for item in recommendation["ingredients"]
        if item["ingredient_id"] == ingredient_id
    )


def test_health_exposes_contract_version() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "contract_version": "1.2",
        "recommendation_engine": "mock",
        "model_fallback": False,
    }


def test_example_returns_current_repeat_and_explore_modes() -> None:
    body = post_recommendation(deepcopy(EXAMPLE_REQUEST))

    assert body["contract_version"] == "1.2"
    assert [item["missing_count"] for item in body["recommendations"]] == [1, 1, 2]
    assert {item["mode"] for item in body["recommendations"]} == {
        "current",
        "repeat",
        "explore",
    }

    explore = recommendation_by_id(body, "chicken_and_vegetables")
    chicken = ingredient_by_id(explore, "chicken")
    assert chicken["source"] == "markdown"
    assert chicken["product_options"][0]["source"] == "markdown"
    assert "Markdown availability is best-effort" in explore["warnings"][0]


def test_initial_challenge_feed_has_one_unique_representative_per_mode() -> None:
    body = post_recommendation(deepcopy(EXAMPLE_REQUEST))

    selection = body["challenge_selection"]
    recommendations = body["recommendations"]
    modes = [item["mode"] for item in recommendations]
    recipe_ids = [item["recipe_id"] for item in recommendations]

    assert selection["default_mode"] == modes[0]
    assert set(selection["available_modes"]) == set(modes)
    assert set(selection["mode_reason_codes"]) == set(modes)
    assert len(modes) == len(set(modes))
    assert len(recipe_ids) == len(set(recipe_ids))
    if "explore" in selection["explicit_choice_required"]:
        explore = next(item for item in recommendations if item["mode"] == "explore")
        assert not any(
            ingredient["source"] in {"receipt", "home"}
            for ingredient in explore["ingredients"]
        )


def test_explore_is_novelty_and_can_reuse_the_current_receipt() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["requested_mode"] = "explore"

    body = post_recommendation(payload)
    omelette = recommendation_by_id(body, "vegetable_omelette")

    assert body["challenge_selection"] == {
        "default_mode": "explore",
        "available_modes": ["explore"],
        "mode_reason_codes": {
            "explore": ["novel_recipe_strategy", "explicit_mode_request"]
        },
        "explicit_choice_required": [],
    }
    assert omelette["mode"] == "explore"
    assert "current_receipt_overlap" in omelette["reason_codes"]
    assert "novel_recipe_strategy" in (
        body["challenge_selection"]["mode_reason_codes"]["explore"]
    )


def test_full_basket_explore_never_becomes_an_implicit_default() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["user"]["saved_recipe_ids"] = []
    payload["user"]["home_ingredient_ids"] = []
    payload["recipe_catalog"] = [
        recipe
        for recipe in payload["recipe_catalog"]
        if recipe["recipe_id"] == "chicken_and_vegetables"
    ]

    implicit = post_recommendation(payload)

    assert implicit["challenge_selection"]["default_mode"] is None
    assert implicit["challenge_selection"]["available_modes"] == ["explore"]
    assert implicit["challenge_selection"]["explicit_choice_required"] == [
        "explore"
    ]
    assert "full_basket_requires_explicit_choice" in (
        implicit["challenge_selection"]["mode_reason_codes"]["explore"]
    )

    payload["requested_mode"] = "explore"
    explicit = post_recommendation(payload)

    assert explicit["challenge_selection"]["default_mode"] == "explore"
    assert explicit["challenge_selection"]["explicit_choice_required"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {
            "default_mode": "repeat",
            "available_modes": ["current"],
            "mode_reason_codes": {"current": ["current_basket_strategy"]},
        },
        {
            "default_mode": "current",
            "available_modes": ["current"],
            "mode_reason_codes": {},
        },
        {
            "default_mode": "current",
            "available_modes": ["current"],
            "mode_reason_codes": {"current": ["current_basket_strategy"]},
            "explicit_choice_required": ["explore"],
        },
        {
            "default_mode": "explore",
            "available_modes": ["explore"],
            "mode_reason_codes": {"explore": ["novel_recipe_strategy"]},
            "explicit_choice_required": ["explore"],
        },
    ],
)
def test_challenge_selection_rejects_inconsistent_state(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ChallengeSelection.model_validate(payload)


def test_full_price_is_used_when_markdown_is_expired() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["inventory_snapshot"][1]["expires_at"] = "2026-09-03T17:00:00+03:00"
    payload["inventory_snapshot"].append(
        {
            "sku_id": "chicken_full_price",
            "name": "Филе куриное",
            "category": "meat",
            "ingredient_ids": ["chicken"],
            "store_id": "store_21",
            "distance_km": 0.6,
            "price": 399.9,
            "original_price": 399.9,
            "is_markdown": False,
            "safety_eligible": True,
            "available_quantity": 4,
            "fulfillment_options": ["delivery", "next_visit"],
        }
    )

    body = post_recommendation(payload)
    explore = recommendation_by_id(body, "chicken_and_vegetables")
    chicken = ingredient_by_id(explore, "chicken")

    assert chicken["source"] == "full_price"
    assert chicken["product_options"][0]["sku_id"] == "chicken_full_price"


def test_recipe_is_filtered_when_required_product_is_outside_radius() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["shopping_context"]["radius_km"] = 0.5

    body = post_recommendation(payload)

    assert "chicken_and_vegetables" not in {
        item["recipe_id"] for item in body["recommendations"]
    }
    assert body["filtered_candidates"] == 1
    assert body["warnings"] == []


def test_all_safety_filtered_candidates_return_only_a_generic_warning() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["shopping_context"]["radius_km"] = 0.5
    payload["recipe_catalog"] = [
        recipe
        for recipe in payload["recipe_catalog"]
        if recipe["recipe_id"] == "chicken_and_vegetables"
    ]

    body = post_recommendation(payload)

    assert body["recommendations"] == []
    assert body["filtered_candidates"] == 1
    assert body["warnings"] == [
        "No safe recommendations are currently available."
    ]
    assert not any("chicken" in warning for warning in body["warnings"])


def test_explicit_category_exclusion_filters_recipe() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["user"]["excluded_categories"] = ["meat"]

    body = post_recommendation(payload)

    assert "chicken_and_vegetables" not in {
        item["recipe_id"] for item in body["recommendations"]
    }


def test_unverified_recipe_never_reaches_response() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["recipe_catalog"][0]["verified"] = False

    body = post_recommendation(payload)

    assert "vegetable_omelette" not in {
        item["recipe_id"] for item in body["recommendations"]
    }


def test_same_category_does_not_override_explicit_ingredient_tags() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["inventory_snapshot"][2]["ingredient_ids"] = ["carrot"]

    body = post_recommendation(payload)

    assert "chicken_and_vegetables" not in {
        item["recipe_id"] for item in body["recommendations"]
    }


def test_unknown_request_field_is_rejected() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["unexpected"] = True

    response = client.post("/api/v1/recommendations", json=payload)

    assert response.status_code == 422


def test_naive_recommendation_timestamp_is_rejected() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["now"] = "2026-09-04T12:00:00"

    response = client.post("/api/v1/recommendations", json=payload)

    assert response.status_code == 422


def test_duplicate_recipe_and_inventory_ids_are_rejected() -> None:
    duplicate_recipe = deepcopy(EXAMPLE_REQUEST)
    duplicate_recipe["recipe_catalog"].append(
        deepcopy(duplicate_recipe["recipe_catalog"][0])
    )
    duplicate_sku = deepcopy(EXAMPLE_REQUEST)
    duplicate_sku["inventory_snapshot"].append(
        deepcopy(duplicate_sku["inventory_snapshot"][0])
    )

    assert client.post("/api/v1/recommendations", json=duplicate_recipe).status_code == 422
    assert client.post("/api/v1/recommendations", json=duplicate_sku).status_code == 422


def test_prepared_receipt_item_is_not_reused_as_raw_ingredients() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["requested_mode"] = "current"
    payload["current_receipt"]["items"] = [
        {
            "sku_id": "ready_omelette",
            "name": "Готовый омлет",
            "category": "prepared_food",
            "ingredient_ids": ["egg", "milk", "tomato"],
            "quantity": 1,
            "unit_price": 250,
            "is_prepared_food": True,
        }
    ]

    body = post_recommendation(payload)

    assert body["recommendations"] == []
    assert body["challenge_selection"]["available_modes"] == []


def test_saved_current_recipe_always_has_a_public_recipe_reason() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["user"]["saved_recipe_ids"].append("vegetable_omelette")
    payload["requested_mode"] = "current"

    body = post_recommendation(payload)

    assert recommendation_by_id(body, "vegetable_omelette")["reason_codes"]


def test_default_mode_tie_uses_mode_priority_before_recipe_id() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["user"]["saved_recipe_ids"] = ["a_repeat"]
    payload["recipe_catalog"] = [
        {
            "recipe_id": "z_current",
            "title": "Current",
            "ingredients": [
                {"ingredient_id": "milk", "name": "Молоко", "category": "dairy"},
                {"ingredient_id": "egg", "name": "Яйца", "category": "egg"},
            ],
        },
        {
            "recipe_id": "a_repeat",
            "title": "Repeat",
            "ingredients": [
                {"ingredient_id": "egg", "name": "Яйца", "category": "egg"}
            ],
        },
    ]

    class EqualScoreEngine:
        def rank(self, request):
            return [
                ModelRecommendation(
                    recipe_id=recipe.recipe_id,
                    mode=RecommendationMode.EXPLORE,
                    score=0.5,
                    reason_codes=["internal_feature"],
                )
                for recipe in request.recipe_catalog
            ]

    service = RecommendationService(
        engine=EqualScoreEngine(), safety_policy=SafetyPolicy()
    )
    from app.contracts import RecommendationRequest

    response = service.recommend(RecommendationRequest.model_validate(payload))

    assert response.challenge_selection.default_mode == RecommendationMode.CURRENT
    assert response.recommendations[0].mode == RecommendationMode.CURRENT


def test_optional_owned_garnish_does_not_make_explore_a_partial_basket() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["user"]["saved_recipe_ids"] = []
    payload["user"]["home_ingredient_ids"] = []
    payload["recipe_catalog"] = [
        {
            "recipe_id": "new_egg",
            "title": "Новое блюдо",
            "ingredients": [
                {"ingredient_id": "egg", "name": "Яйца", "category": "egg"},
                {
                    "ingredient_id": "milk",
                    "name": "Молоко для подачи",
                    "category": "dairy",
                    "required": False,
                },
            ],
        }
    ]
    payload["current_receipt"]["items"] = [
        item for item in payload["current_receipt"]["items"] if item["sku_id"] == "milk_01"
    ]

    body = post_recommendation(payload)

    assert body["challenge_selection"]["default_mode"] is None
    assert body["challenge_selection"]["explicit_choice_required"] == ["explore"]


def test_unknown_engine_setting_is_visible_as_health_fallback(monkeypatch) -> None:
    monkeypatch.setenv("RECOMMENDATION_ENGINE", "typo")

    _, engine_name, fallback = _build_recommendation_engine()

    assert engine_name == "mock"
    assert fallback is True


def test_receipt_brand_alone_does_not_claim_an_available_brand_option() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["requested_mode"] = "current"
    for product in payload["inventory_snapshot"]:
        product["brand"] = None

    body = post_recommendation(payload)

    omelette = recommendation_by_id(body, "vegetable_omelette")
    assert "preferred_brand_option_available" not in omelette["reason_codes"]


def test_recipe_quantity_does_not_produce_unverifiable_actual_cost_claim() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["requested_mode"] = "current"
    payload["recipe_catalog"][0]["ingredients"][-1]["quantity"] = 10
    payload["purchase_history"] = [deepcopy(payload["current_receipt"])]
    payload["purchase_history"][0]["receipt_id"] = "history-receipt"

    body = post_recommendation(payload)

    omelette = recommendation_by_id(body, "vegetable_omelette")
    assert "actual_cost_within_usual_receipt" not in omelette["reason_codes"]
