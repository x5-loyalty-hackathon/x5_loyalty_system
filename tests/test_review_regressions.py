from copy import deepcopy

import pytest

from tests.test_recipe_book_and_store_selection import recommendation_payload, post_recommendation
from tests.test_meal_flow import client, save_plan, receipt_for_plan


@pytest.mark.parametrize("radius", [20, 21, 25, 100])
def test_legacy_radius_remains_valid(radius):
    payload = recommendation_payload()
    payload.pop("shopping_context")
    payload["user"]["radius_km"] = radius
    result = post_recommendation(payload)
    assert result["recommendations"][0]["store_selection"]["radius_km"] == radius


def test_new_shopping_context_still_rejects_radius_over_20():
    payload = recommendation_payload()
    payload["shopping_context"]["radius_km"] = 21
    assert client.post("/api/v1/recommendations", json=payload).status_code == 422


def test_auto_store_skips_full_but_incompatible_basket():
    payload = recommendation_payload()
    near = payload["inventory_snapshot"][0]
    near["fulfillment_options"] = ["delivery"]
    tomato = deepcopy(payload["inventory_snapshot"][-1])
    tomato.update(sku_id="tomato-near", store_id="store_near", distance_km=0.2,
                  fulfillment_options=["next_visit"])
    payload["inventory_snapshot"].append(tomato)
    result = post_recommendation(payload)["recommendations"][0]
    assert result["store_selection"]["selected_store_id"] == "store_work"
    assert "store_near" not in [s["store_id"] for s in result["store_selection"]["options"]]
    payload["shopping_context"]["selected_store_id"] = "store_near"
    assert post_recommendation(payload)["recommendations"] == []


def test_optional_ingredient_does_not_limit_required_fulfillment_or_effort():
    payload = recommendation_payload()
    for product in payload["inventory_snapshot"]:
        product["fulfillment_options"] = ["delivery"]
    payload["recipe_catalog"][0]["ingredients"].append(
        {"ingredient_id": "salt", "name": "Соль", "category": "spice", "required": False}
    )
    payload["inventory_snapshot"].append({
        "sku_id": "salt", "name": "Соль", "category": "spice", "ingredient_ids": ["salt"],
        "store_id": "store_work", "distance_km": 0.6, "price": 10,
        "fulfillment_options": ["next_visit"],
    })
    result = post_recommendation(payload)["recommendations"][0]
    assert result["missing_count"] == 2
    assert result["fulfillment_options"] == ["delivery"]


def test_duplicate_receipt_recovers_only_original_owned_plan():
    save_plan(plan_id="retry-plan", route="cook", selected_product_ids=["egg"],
              selected_recipe_id="vegetable_omelette")
    event = receipt_for_plan(plan_id="retry-plan", sku_id="egg", is_prepared_food=False)
    first = client.post("/api/v1/events/receipts", json=event).json()
    retry = client.post("/api/v1/events/receipts", json=event).json()
    assert first["meal_plan"]["status"] == "collected"
    assert retry["status"] == "duplicate"
    assert retry["meal_plan"] == first["meal_plan"]
    assert retry["progress"] == first["progress"]
    save_plan(plan_id="unrelated", route="cook", selected_product_ids=["egg"],
              selected_recipe_id="vegetable_omelette")
    event["meal_plan_id"] = "unrelated"
    assert client.post("/api/v1/events/receipts", json=event).json()["meal_plan"] is None
    event["meal_plan_id"] = "retry-plan"
    event["user_id"] = "another-user"
    assert client.post("/api/v1/events/receipts", json=event).json()["meal_plan"] is None
