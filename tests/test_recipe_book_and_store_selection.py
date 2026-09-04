from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def recommendation_payload() -> dict:
    return {
        "user": {
            "user_id": "user-store-demo",
            "saved_recipe_ids": [],
        },
        "shopping_context": {
            "anchor_type": "work",
            "anchor_id": "office-place-opaque-id",
            "radius_km": 0.75,
            "preferred_store_ids": [],
        },
        "current_receipt": {
            "receipt_id": "receipt-store-demo",
            "purchased_at": "2026-09-04T12:00:00+03:00",
            "store_id": "store_previous",
            "items": [
                {
                    "sku_id": "receipt-milk",
                    "name": "Молоко",
                    "category": "dairy",
                    "ingredient_ids": ["milk"],
                    "unit_price": 90,
                }
            ],
        },
        "recipe_catalog": [
            {
                "recipe_id": "vegetable_stew",
                "title": "Овощное рагу",
                "preparation_minutes": 30,
                "ingredients": [
                    {
                        "ingredient_id": "zucchini",
                        "name": "Кабачок",
                        "category": "vegetable",
                    },
                    {
                        "ingredient_id": "tomato",
                        "name": "Томаты",
                        "category": "vegetable",
                    },
                ],
            }
        ],
        "inventory_snapshot": [
            {
                "sku_id": "zucchini-near",
                "name": "Кабачок",
                "category": "vegetable",
                "ingredient_ids": ["zucchini"],
                "store_id": "store_near",
                "distance_km": 0.2,
                "price": 100,
            },
            {
                "sku_id": "zucchini-work",
                "name": "Кабачок",
                "category": "vegetable",
                "ingredient_ids": ["zucchini"],
                "store_id": "store_work",
                "distance_km": 0.6,
                "price": 110,
            },
            {
                "sku_id": "tomato-work",
                "name": "Томаты",
                "category": "vegetable",
                "ingredient_ids": ["tomato"],
                "store_id": "store_work",
                "distance_km": 0.6,
                "price": 120,
            },
        ],
        "requested_mode": "explore",
        "now": "2026-09-04T12:05:00+03:00",
        "limit": 1,
    }


def post_recommendation(payload: dict) -> dict:
    response = client.post("/api/v1/recommendations", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_store_selector_prefers_complete_basket_over_nearest_partial_store() -> None:
    body = post_recommendation(recommendation_payload())

    recommendation = body["recommendations"][0]
    selection = recommendation["store_selection"]
    assert selection["anchor_type"] == "work"
    assert selection["anchor_id"] == "office-place-opaque-id"
    assert selection["radius_km"] == 0.75
    assert selection["selected_store_id"] == "store_work"
    assert selection["reason_codes"] == ["maximum_ingredient_coverage"]
    assert [(item["store_id"], item["complete"]) for item in selection["options"]] == [
        ("store_work", True),
        ("store_near", False),
    ]
    product_store_ids = {
        option["store_id"]
        for ingredient in recommendation["ingredients"]
        for option in ingredient["product_options"]
    }
    assert product_store_ids == {"store_work"}


def test_preferred_store_is_anchor_specific_tiebreak() -> None:
    payload = recommendation_payload()
    payload["inventory_snapshot"].append(
        {
            "sku_id": "tomato-near",
            "name": "Томаты",
            "category": "vegetable",
            "ingredient_ids": ["tomato"],
            "store_id": "store_near",
            "distance_km": 0.2,
            "price": 130,
        }
    )
    payload["shopping_context"]["preferred_store_ids"] = ["store_work"]

    body = post_recommendation(payload)

    selection = body["recommendations"][0]["store_selection"]
    assert selection["selected_store_id"] == "store_work"
    assert selection["reason_codes"] == [
        "maximum_ingredient_coverage",
        "preferred_store_for_anchor",
    ]


def test_nearest_store_wins_equal_coverage_without_anchor_preference() -> None:
    payload = recommendation_payload()
    payload["inventory_snapshot"].append(
        {
            "sku_id": "tomato-near",
            "name": "Томаты",
            "category": "vegetable",
            "ingredient_ids": ["tomato"],
            "store_id": "store_near",
            "distance_km": 0.2,
            "price": 130,
        }
    )

    body = post_recommendation(payload)

    selection = body["recommendations"][0]["store_selection"]
    assert selection["selected_store_id"] == "store_near"
    assert selection["reason_codes"] == [
        "maximum_ingredient_coverage",
        "nearest_store_tiebreak",
    ]


def test_explicit_store_choice_overrides_automatic_store_order() -> None:
    payload = recommendation_payload()
    payload["inventory_snapshot"].append(
        {
            "sku_id": "tomato-near",
            "name": "Томаты",
            "category": "vegetable",
            "ingredient_ids": ["tomato"],
            "store_id": "store_near",
            "distance_km": 0.2,
            "price": 130,
        }
    )
    payload["shopping_context"]["selected_store_id"] = "store_near"

    body = post_recommendation(payload)

    selection = body["recommendations"][0]["store_selection"]
    assert selection["selected_store_id"] == "store_near"
    assert selection["reason_codes"] == ["explicit_store_choice"]


def test_explicit_incomplete_store_does_not_create_split_store_basket() -> None:
    payload = recommendation_payload()
    payload["shopping_context"]["selected_store_id"] = "store_near"

    body = post_recommendation(payload)

    assert body["recommendations"] == []
    assert body["filtered_candidates"] == 1


def test_anchor_radius_filters_products_even_if_legacy_radius_is_larger() -> None:
    payload = recommendation_payload()
    payload["user"]["radius_km"] = 3.0
    for product in payload["inventory_snapshot"]:
        if product["store_id"] == "store_work":
            product["distance_km"] = 0.8

    body = post_recommendation(payload)

    assert body["recommendations"] == []


def test_recipe_book_is_idempotent_and_drives_repeat_without_client_echo() -> None:
    initial = recommendation_payload()
    initial["user"]["user_id"] = "recipe-book-user"
    initial["current_receipt"]["receipt_id"] = "recipe-book-receipt"
    initial["requested_mode"] = "repeat"
    assert post_recommendation(deepcopy(initial))["recommendations"] == []

    first = client.post(
        "/api/v1/saved-recipes",
        json={"user_id": "recipe-book-user", "recipe_id": "vegetable_stew"},
    )
    duplicate = client.post(
        "/api/v1/saved-recipes",
        json={"user_id": "recipe-book-user", "recipe_id": "vegetable_stew"},
    )

    assert first.status_code == duplicate.status_code == 200
    assert first.json()["status"] == "created"
    assert duplicate.json()["status"] == "duplicate"
    assert first.json()["saved_recipe_ids"] == ["vegetable_stew"]
    assert client.get("/api/v1/progress/recipe-book-user").json()["avatar_xp"] == 0

    repeated = post_recommendation(initial)
    assert repeated["recommendations"][0]["recipe_id"] == "vegetable_stew"
    assert repeated["recommendations"][0]["mode"] == "repeat"


def test_saved_recipe_state_is_isolated_by_user() -> None:
    client.post(
        "/api/v1/saved-recipes",
        json={"user_id": "first-user", "recipe_id": "vegetable_stew"},
    )

    assert client.get("/api/v1/saved-recipes/first-user").json()[
        "saved_recipe_ids"
    ] == ["vegetable_stew"]
    assert client.get("/api/v1/saved-recipes/second-user").json()[
        "saved_recipe_ids"
    ] == []
