import json
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


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
    assert response.json() == {"status": "ok", "contract_version": "1.0"}


def test_example_returns_current_repeat_and_explore_modes() -> None:
    body = post_recommendation(deepcopy(EXAMPLE_REQUEST))

    assert body["contract_version"] == "1.0"
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


def test_full_price_is_used_when_markdown_is_expired() -> None:
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["inventory_snapshot"][1]["expires_at"] = "2026-09-03T17:00:00+03:00"
    payload["inventory_snapshot"].append(
        {
            "sku_id": "chicken_full_price",
            "name": "Филе куриное",
            "category": "meat",
            "ingredient_ids": ["chicken"],
            "store_id": "store_17",
            "distance_km": 0.8,
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
    payload["user"]["radius_km"] = 1.0

    body = post_recommendation(payload)

    assert "chicken_and_vegetables" not in {
        item["recipe_id"] for item in body["recommendations"]
    }
    assert body["filtered_candidates"] == 1
    assert any(
        "no_safe_product:chicken" in warning for warning in body["warnings"]
    )


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
