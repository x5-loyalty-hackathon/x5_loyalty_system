import json
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient

from app.contracts import ModelRecommendation, RecommendationMode, RecommendationRequest
from app.main import app
from app.safety import SafetyPolicy
from app.service import RecommendationService


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_REQUEST = json.loads(
    (ROOT / "examples" / "recommendation_request.json").read_text(
        encoding="utf-8"
    )
)
client = TestClient(app)


def load_example(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def meal_recommendation_payload(*, prefer_ready: bool = False) -> dict:
    payload = deepcopy(EXAMPLE_REQUEST)
    if prefer_ready:
        payload["user"]["preferred_meal_route"] = "ready"
    recipe = next(
        item
        for item in payload["recipe_catalog"]
        if item["recipe_id"] == "vegetable_omelette"
    )
    recipe["meal_intent_id"] = "omelette"
    payload["inventory_snapshot"].append(
        {
            "sku_id": "ready_omelette_01",
            "name": "Омлет с овощами готовый",
            "category": "prepared_food",
            "ingredient_ids": ["egg", "milk", "tomato"],
            "store_id": "store_17",
            "distance_km": 0.7,
            "price": 249.9,
            "original_price": 249.9,
            "is_markdown": False,
            "is_prepared_food": True,
            "meal_intent_ids": ["omelette"],
            "contained_categories": ["dairy", "egg", "vegetable"],
            "safety_eligible": True,
            "expires_at": "2026-09-04T20:00:00+03:00",
            "available_quantity": 3,
            "fulfillment_options": ["delivery", "next_visit"],
        }
    )
    return payload


def recommendation_by_id(body: dict, meal_id: str) -> dict:
    return next(item for item in body["recommendations"] if item["meal_id"] == meal_id)


def save_plan(
    *,
    plan_id: str,
    route: str,
    selected_product_ids: list[str],
    selected_recipe_id: str | None = None,
    user_id: str = "user_demo_001",
) -> dict:
    payload = meal_recommendation_payload()
    payload["user"]["user_id"] = user_id
    payload["now"] = "2026-09-04T12:00:00+03:00"
    payload["recipe_catalog"] = [{
        "recipe_id": "vegetable_omelette", "title": "Омлет", "meal_intent_id": "omelette",
        "ingredients": [{"ingredient_id": "egg", "name": "Яйцо", "category": "egg"}],
    }]
    payload["current_receipt"]["items"] = [{
        "sku_id": "milk", "name": "Молоко", "category": "dairy",
        "ingredient_ids": ["milk"], "unit_price": 90,
    }]
    payload["user"]["home_ingredient_ids"] = ["egg"] if not selected_product_ids else []
    payload["inventory_snapshot"] = [{
        "sku_id": sku, "name": "Товар", "category": "egg" if route == "cook" else "prepared_food",
        "ingredient_ids": ["egg"], "store_id": "store_17", "distance_km": 0.5,
        "price": 100, "is_prepared_food": route == "ready",
        "meal_intent_ids": ["omelette"] if route == "ready" else [],
        "contained_categories": ["egg"] if route == "ready" else [],
    } for sku in selected_product_ids]
    payload["requested_mode"] = "explore"
    offers = client.post("/api/v1/meal-recommendations", json=payload)
    assert offers.status_code == 200, offers.text
    offer = recommendation_by_id(offers.json(), "vegetable_omelette")
    response = client.post(
        "/api/v1/meal-plans",
        json={
            "offer_id": offer["offer_id"],
            "plan_id": plan_id,
            "user_id": user_id,
            "meal_id": "vegetable_omelette",
            "selected_route": route,
            "selected_recipe_id": selected_recipe_id,
            "selected_product_ids": selected_product_ids,
            "fulfillment": "next_visit",
            "created_at": "2026-09-04T12:00:00+03:00",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def receipt_for_plan(
    *,
    plan_id: str,
    sku_id: str,
    is_prepared_food: bool,
    receipt_id: str = "meal-receipt-1",
) -> dict:
    return {
        "user_id": "user_demo_001",
        "meal_plan_id": plan_id,
        "receipt": {
            "receipt_id": receipt_id,
            "purchased_at": "2026-09-04T13:00:00+03:00",
            "store_id": "store_17",
            "items": [
                {
                    "sku_id": sku_id,
                    "name": "Товар из плана",
                    "category": "prepared_food" if is_prepared_food else "egg",
                    "ingredient_ids": ["egg"],
                    "quantity": 1,
                    "unit_price": 249.9,
                    "is_prepared_food": is_prepared_food,
                }
            ],
        },
        "now": "2026-09-04T13:05:00+03:00",
    }


def test_meal_endpoint_adds_ready_variant_without_changing_recipe_endpoint() -> None:
    payload = meal_recommendation_payload(prefer_ready=True)

    meal_response = client.post("/api/v1/meal-recommendations", json=payload)
    recipe_response = client.post("/api/v1/recommendations", json=payload)

    assert meal_response.status_code == 200, meal_response.text
    assert recipe_response.status_code == 200, recipe_response.text
    meal = recommendation_by_id(meal_response.json(), "vegetable_omelette")
    assert (
        meal_response.json()["challenge_selection"]
        == recipe_response.json()["challenge_selection"]
    )
    assert meal["default_route"] == "ready"
    assert set(meal["available_routes"]) == {"cook", "ready"}
    assert meal["route_reason_codes"] == ["explicit_ready_preference"]
    assert meal["ready_variant"]["meal_intent_id"] == "omelette"
    assert meal["ready_variant"]["product_options"][0]["sku_id"] == "ready_omelette_01"
    assert "default_route" not in recipe_response.json()["recommendations"][0]


def test_ready_route_is_selected_from_observed_history() -> None:
    payload = meal_recommendation_payload()
    payload["purchase_history"] = [
        {
            "receipt_id": "ready-history",
            "purchased_at": "2026-09-02T12:00:00+03:00",
            "store_id": "store_17",
            "items": [
                {
                    "sku_id": f"ready-history-{index}",
                    "name": "Готовое блюдо",
                    "category": "prepared_food",
                    "quantity": 1,
                    "unit_price": 200,
                    "is_prepared_food": True,
                }
                for index in range(4)
            ],
        }
    ]

    response = client.post("/api/v1/meal-recommendations", json=payload)

    assert response.status_code == 200, response.text
    meal = recommendation_by_id(response.json(), "vegetable_omelette")
    assert meal["default_route"] == "ready"
    assert meal["route_reason_codes"] == ["prepared_food_share_supports_ready"]


def test_unsafe_ready_product_is_removed_without_losing_cook_route() -> None:
    payload = meal_recommendation_payload(prefer_ready=True)
    payload["inventory_snapshot"][-1]["safety_eligible"] = False

    response = client.post("/api/v1/meal-recommendations", json=payload)

    assert response.status_code == 200, response.text
    meal = recommendation_by_id(response.json(), "vegetable_omelette")
    assert meal["available_routes"] == ["cook"]
    assert meal["default_route"] == "cook"
    assert meal["ready_variant"] is None
    assert meal["route_reason_codes"] == [
        "ready_route_unavailable",
        "cook_route_fallback",
    ]


def test_safe_ready_route_survives_unavailable_cook() -> None:
    payload = meal_recommendation_payload(prefer_ready=True)
    payload["inventory_snapshot"] = [payload["inventory_snapshot"][-1]]

    response = client.post("/api/v1/meal-recommendations", json=payload)

    assert response.status_code == 200, response.text
    meal = recommendation_by_id(response.json(), "vegetable_omelette")
    assert meal["available_routes"] == ["ready"]
    assert meal["default_route"] == "ready"
    assert meal["cook_variant"] is None
    assert meal["ready_variant"] is not None
    assert meal["route_reason_codes"] == ["explicit_ready_preference"]
    assert meal["reason_codes"] == ["safe_ready_option_available"]
    assert meal["mode"] == "explore"
    assert "current" not in response.json()["challenge_selection"]["available_modes"]

    payload["user"].pop("preferred_meal_route")
    response_without_preference = client.post(
        "/api/v1/meal-recommendations", json=payload
    )
    assert response_without_preference.status_code == 200
    meal_without_preference = recommendation_by_id(
        response_without_preference.json(), "vegetable_omelette"
    )
    assert meal_without_preference["default_route"] == "ready"
    assert meal_without_preference["route_reason_codes"] == [
        "only_ready_route_available"
    ]

    payload["current_receipt"]["items"] = [
        {
            "sku_id": "other-ready-meal",
            "name": "Другое готовое блюдо",
            "category": "prepared_food",
            "quantity": 1,
            "unit_price": 200,
            "is_prepared_food": True,
        }
    ]
    novel_ready = client.post("/api/v1/meal-recommendations", json=payload)
    assert novel_ready.status_code == 200
    assert novel_ready.json()["challenge_selection"]["default_mode"] == "explore"
    assert novel_ready.json()["challenge_selection"][
        "explicit_choice_required"
    ] == []

    payload["user"]["preferred_meal_route"] = "cook"
    cook_fallback = client.post("/api/v1/meal-recommendations", json=payload)
    assert cook_fallback.status_code == 200
    fallback_meal = recommendation_by_id(
        cook_fallback.json(), "vegetable_omelette"
    )
    assert fallback_meal["default_route"] == "ready"
    assert fallback_meal["route_reason_codes"] == [
        "cook_route_unavailable",
        "ready_route_fallback",
    ]


def test_cookable_explore_recipe_is_not_crowded_out_by_a_ready_only_one() -> None:
    """A ready-only candidate consumes no raw products, so it always reads as
    "not a full basket" and used to win the EXPLORE slot outright against any
    recipe that needs buying more than one item — even when a real,
    buyable-today recipe existed. "Nothing to cook" must not beat "cook this,
    confirm the fresh basket"."""
    payload = deepcopy(EXAMPLE_REQUEST)
    payload["user"]["saved_recipe_ids"] = []
    payload["user"]["home_ingredient_ids"] = []
    payload["current_receipt"]["items"] = [
        {
            "sku_id": "bread_01", "name": "Хлеб", "category": "grain",
            "ingredient_ids": ["bread"], "unit_price": 55,
        }
    ]
    payload["purchase_history"] = []
    payload["recipe_catalog"] = [
        {
            "recipe_id": "ready_only_dish", "title": "Только готовое блюдо",
            "verified": True, "meal_intent_id": "ready_only_dish",
            "ingredients": [
                {"ingredient_id": "rare_cut", "name": "Редкий отруб", "category": "meat", "required": True},
            ],
        },
        {
            "recipe_id": "two_item_dish", "title": "Блюдо из двух покупок",
            "verified": True,
            "ingredients": [
                {"ingredient_id": "onion", "name": "Лук", "category": "vegetable", "required": True},
                {"ingredient_id": "carrot", "name": "Морковь", "category": "vegetable", "required": True},
            ],
        },
    ]
    payload["inventory_snapshot"] = [
        {
            "sku_id": "ready_only_dish_01", "name": "Готовое блюдо",
            "category": "prepared_food", "ingredient_ids": [], "store_id": "store_17",
            "distance_km": 0.5, "price": 259.9, "is_markdown": False,
            "is_prepared_food": True, "meal_intent_ids": ["ready_only_dish"],
            "contained_categories": ["meat"], "safety_eligible": True,
            "available_quantity": 3, "fulfillment_options": ["delivery", "next_visit"],
        },
        {
            "sku_id": "onion_01", "name": "Лук", "category": "vegetable",
            "ingredient_ids": ["onion"], "store_id": "store_17", "distance_km": 0.5,
            "price": 39.9, "safety_eligible": True, "available_quantity": 10,
            "fulfillment_options": ["delivery", "next_visit"],
        },
        {
            "sku_id": "carrot_01", "name": "Морковь", "category": "vegetable",
            "ingredient_ids": ["carrot"], "store_id": "store_17", "distance_km": 0.5,
            "price": 45.9, "safety_eligible": True, "available_quantity": 10,
            "fulfillment_options": ["delivery", "next_visit"],
        },
    ]

    response = client.post("/api/v1/meal-recommendations", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    # Both candidates are EXPLORE-mode (neither overlaps the receipt, neither
    # is saved), so exactly one wins the single EXPLORE slot. Before the fix
    # it was ready_only_dish, purely because a ready-only candidate is never
    # "a full basket" — regardless of whether a real recipe was buyable today.
    assert len(body["recommendations"]) == 1
    explore = body["recommendations"][0]
    assert explore["mode"] == "explore"
    assert explore["meal_id"] == "two_item_dish"
    assert explore["cook_variant"] is not None
    assert explore["cook_variant"]["missing_count"] == 2
    assert "explore" in body["challenge_selection"]["explicit_choice_required"]


def test_explicit_store_choice_applies_to_cook_and_ready_routes() -> None:
    payload = meal_recommendation_payload(prefer_ready=True)
    payload["shopping_context"]["selected_store_id"] = "store_work"
    ready = next(
        item
        for item in payload["inventory_snapshot"]
        if item["sku_id"] == "ready_omelette_01"
    )
    ready["store_id"] = "store_work"
    ready["distance_km"] = 0.4

    response = client.post("/api/v1/meal-recommendations", json=payload)

    assert response.status_code == 200, response.text
    meal = recommendation_by_id(response.json(), "vegetable_omelette")
    assert meal["available_routes"] == ["ready"]
    assert meal["cook_variant"] is None
    assert {
        option["store_id"] for option in meal["ready_variant"]["product_options"]
    } == {"store_work"}


def test_unverified_recipe_cannot_survive_through_ready_only_route(
    monkeypatch,
) -> None:
    payload = meal_recommendation_payload(prefer_ready=True)
    payload["recipe_catalog"] = [payload["recipe_catalog"][0]]
    payload["recipe_catalog"][0]["verified"] = False
    payload["inventory_snapshot"] = [payload["inventory_snapshot"][-1]]

    class NonCompliantEngine:
        def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
            return [
                ModelRecommendation(
                    recipe_id=request.recipe_catalog[0].recipe_id,
                    mode=RecommendationMode.EXPLORE,
                    score=0.99,
                    reason_codes=["untrusted_adapter_reason"],
                )
            ]

    service = RecommendationService(
        engine=NonCompliantEngine(),
        safety_policy=SafetyPolicy(),
    )
    import app.main as main_module

    monkeypatch.setattr(main_module, "recommendation_service", service)

    recipe_response = client.post("/api/v1/recommendations", json=payload)
    meal_response = client.post("/api/v1/meal-recommendations", json=payload)

    assert recipe_response.status_code == meal_response.status_code == 200
    assert recipe_response.json()["recommendations"] == []
    assert meal_response.json()["recommendations"] == []
    assert recipe_response.json()["filtered_candidates"] == 1
    assert meal_response.json()["filtered_candidates"] == 1


def test_ready_product_respects_explicit_content_category_exclusion() -> None:
    payload = meal_recommendation_payload(prefer_ready=True)
    payload["user"]["excluded_categories"] = ["meat"]
    payload["inventory_snapshot"][-1]["contained_categories"].append("meat")

    response = client.post("/api/v1/meal-recommendations", json=payload)

    assert response.status_code == 200, response.text
    meal = recommendation_by_id(response.json(), "vegetable_omelette")
    assert meal["available_routes"] == ["cook"]
    assert meal["ready_variant"] is None


def test_prepared_product_is_not_reused_as_a_raw_recipe_product() -> None:
    payload = meal_recommendation_payload()
    prepared = payload["inventory_snapshot"][-1]
    prepared["ingredient_ids"] = ["zucchini"]
    payload["inventory_snapshot"] = [prepared]
    payload["recipe_catalog"] = [
        recipe
        for recipe in payload["recipe_catalog"]
        if recipe["recipe_id"] == "chicken_and_vegetables"
    ]

    response = client.post("/api/v1/recommendations", json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["recommendations"] == []


def test_ready_plan_completes_only_with_matching_verified_receipt() -> None:
    saved = save_plan(
        plan_id="ready-plan-1",
        route="ready",
        selected_product_ids=["ready_omelette_01"],
    )
    assert saved["status"] == "created"
    assert saved["plan"]["status"] == "saved"

    unmatched = client.post(
        "/api/v1/events/receipts",
        json=receipt_for_plan(
            plan_id="ready-plan-1",
            sku_id="another-ready-meal",
            is_prepared_food=True,
        ),
    )
    assert unmatched.status_code == 200, unmatched.text
    assert unmatched.json()["meal_plan"]["status"] == "saved"
    assert "ready_meal_not_matched" in unmatched.json()["reason_codes"]
    assert unmatched.json()["progress"]["meals_completed"] == 0

    matched = client.post(
        "/api/v1/events/receipts",
        json=receipt_for_plan(
            plan_id="ready-plan-1",
            sku_id="ready_omelette_01",
            is_prepared_food=True,
            receipt_id="meal-receipt-2",
        ),
    )
    assert matched.status_code == 200, matched.text
    body = matched.json()
    assert body["meal_plan"]["status"] == "completed"
    assert body["meal_plan"]["completion_evidence"] == (
        "verified_receipt:meal-receipt-2"
    )
    assert "ready_meal_plan_completed" in body["reason_codes"]
    assert body["progress"]["meals_completed"] == 1
    assert body["progress"]["ready_meals_completed"] == 1
    assert body["progress"]["recipes_completed"] == 0
    assert body["progress"]["avatar_xp"] == 20

    repeated_purchase = client.post(
        "/api/v1/events/receipts",
        json=receipt_for_plan(
            plan_id="ready-plan-1",
            sku_id="ready_omelette_01",
            is_prepared_food=True,
            receipt_id="meal-receipt-3",
        ),
    )
    assert repeated_purchase.status_code == 200, repeated_purchase.text
    assert "meal_plan_already_completed" in repeated_purchase.json()["reason_codes"]
    assert repeated_purchase.json()["progress"]["meals_completed"] == 1


def test_another_user_cannot_complete_ready_plan() -> None:
    save_plan(
        plan_id="owned-ready-plan",
        route="ready",
        selected_product_ids=["ready_omelette_01"],
        user_id="owner",
    )
    payload = receipt_for_plan(
        plan_id="owned-ready-plan",
        sku_id="ready_omelette_01",
        is_prepared_food=True,
    )
    payload["user_id"] = "another-user"

    response = client.post("/api/v1/events/receipts", json=payload)

    assert response.status_code == 200, response.text
    assert "meal_plan_owner_mismatch" in response.json()["reason_codes"]
    assert response.json()["meal_plan"] is None
    assert response.json()["progress"]["meals_completed"] == 0


def test_cook_plan_requires_collection_then_explicit_confirmation() -> None:
    save_plan(
        plan_id="cook-plan-1",
        route="cook",
        selected_product_ids=["egg_01"],
        selected_recipe_id="vegetable_omelette",
    )
    early_confirmation = client.post(
        "/api/v1/meal-plans/cook-plan-1/complete-cook",
        json={
            "user_id": "user_demo_001",
            "now": "2026-09-04T12:30:00+03:00",
        },
    )
    assert early_confirmation.status_code == 200, early_confirmation.text
    assert early_confirmation.json()["status"] == "not_ready"

    receipt = client.post(
        "/api/v1/events/receipts",
        json=receipt_for_plan(
            plan_id="cook-plan-1",
            sku_id="egg_01",
            is_prepared_food=False,
        ),
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["meal_plan"]["status"] == "collected"
    assert receipt.json()["progress"]["meals_completed"] == 0

    completed = client.post(
        "/api/v1/meal-plans/cook-plan-1/complete-cook",
        json={
            "user_id": "user_demo_001",
            "now": "2026-09-04T14:00:00+03:00",
        },
    )
    duplicate = client.post(
        "/api/v1/meal-plans/cook-plan-1/complete-cook",
        json={
            "user_id": "user_demo_001",
            "now": "2026-09-04T14:01:00+03:00",
        },
    )

    assert completed.status_code == duplicate.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["plan"]["completion_evidence"] == (
        "user_cooking_confirmation"
    )
    assert completed.json()["progress"]["meals_completed"] == 1
    assert completed.json()["progress"]["recipes_completed"] == 1
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["progress"]["meals_completed"] == 1


def test_receipt_before_plan_creation_cannot_complete_plan() -> None:
    save_plan(
        plan_id="future-ready-plan",
        route="ready",
        selected_product_ids=["ready_omelette_01"],
    )
    payload = receipt_for_plan(
        plan_id="future-ready-plan",
        sku_id="ready_omelette_01",
        is_prepared_food=True,
        receipt_id="past-receipt",
    )
    payload["receipt"]["purchased_at"] = "2026-09-04T11:59:00+03:00"
    payload["now"] = "2026-09-04T12:05:00+03:00"

    response = client.post("/api/v1/events/receipts", json=payload)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "verified"
    assert body["meal_plan"]["status"] == "saved"
    assert "receipt_predates_meal_plan" in body["reason_codes"]
    assert body["progress"]["verified_receipts"] == 1
    assert body["progress"]["meals_completed"] == 0


def test_cooking_confirmation_before_plan_creation_is_rejected() -> None:
    save_plan(
        plan_id="future-cook-plan",
        route="cook",
        selected_product_ids=[],
        selected_recipe_id="vegetable_omelette",
    )

    response = client.post(
        "/api/v1/meal-plans/future-cook-plan/complete-cook",
        json={
            "user_id": "user_demo_001",
            "now": "2026-09-04T11:59:00+03:00",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"
    assert response.json()["reason_codes"] == [
        "cooking_confirmation_predates_plan"
    ]
    assert response.json()["progress"]["meals_completed"] == 0


def test_duplicate_markdown_warning_is_returned_once() -> None:
    payload = meal_recommendation_payload()
    payload["current_receipt"]["items"] = [
        item
        for item in payload["current_receipt"]["items"]
        if item["sku_id"] != "milk_01"
    ]
    payload["inventory_snapshot"].append(
        {
            "sku_id": "milk_markdown",
            "name": "Молоко по уценке",
            "category": "dairy",
            "ingredient_ids": ["milk"],
            "store_id": "store_17",
            "distance_km": 0.6,
            "price": 70,
            "original_price": 120,
            "is_markdown": True,
            "expires_at": "2026-09-04T20:00:00+03:00",
            "available_quantity": 2,
            "fulfillment_options": ["delivery", "next_visit"],
        }
    )
    payload["inventory_snapshot"][-2]["is_markdown"] = True
    payload["inventory_snapshot"][-2]["original_price"] = 300
    payload["inventory_snapshot"][-2]["category"] = "dairy"

    response = client.post("/api/v1/meal-recommendations", json=payload)

    assert response.status_code == 200, response.text
    meal = recommendation_by_id(response.json(), "vegetable_omelette")
    assert meal["warnings"].count(
        "Markdown availability is best-effort: the item is not reserved."
    ) == 1


def test_ready_plan_requires_at_least_one_selected_product() -> None:
    response = client.post(
        "/api/v1/meal-plans",
        json={
            "plan_id": "invalid-ready-plan",
            "user_id": "user_demo_001",
            "meal_id": "vegetable_omelette",
            "selected_route": "ready",
            "selected_product_ids": [],
            "fulfillment": "next_visit",
            "created_at": "2026-09-04T12:00:00+03:00",
        },
    )

    assert response.status_code == 422


def test_published_ready_examples_form_one_end_to_end_flow() -> None:
    recommendation = client.post(
        "/api/v1/meal-recommendations",
        json=load_example("meal_recommendation_request.json"),
    )
    assert recommendation.status_code == 200, recommendation.text
    meal = recommendation.json()["recommendations"][0]
    assert meal["default_route"] == "ready"
    assert meal["ready_variant"]["product_options"][0]["sku_id"] == "ready_omelette_01"

    plan_payload = load_example("meal_plan_request.json")
    plan_payload["offer_id"] = meal["offer_id"]
    plan = client.post(
        "/api/v1/meal-plans",
        json=plan_payload,
    )
    assert plan.status_code == 200, plan.text
    assert plan.json()["status"] == "created"

    receipt = client.post(
        "/api/v1/events/receipts",
        json=load_example("ready_receipt_event.json"),
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["meal_plan"]["status"] == "completed"
    assert receipt.json()["progress"]["ready_meals_completed"] == 1
