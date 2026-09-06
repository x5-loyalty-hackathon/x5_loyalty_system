"""ADR-005 through real HTTP handlers, not fabricated client reward responses."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
USER = "reward-user"
NOW = "2026-09-04T12:00:00+03:00"


def payload(*, home=False, topup=False):
    return {
        "user": {"user_id": USER, "home_ingredient_ids": ["milk"] if home else []},
        "current_receipt": {
            "receipt_id": "original-purchase", "purchased_at": "2026-09-04T11:00:00+03:00",
            "store_id": "store", "items": [{
                "sku_id": "water" if home else "milk", "name": "Продукт", "category": "dairy",
                "ingredient_ids": ["water"] if home else ["milk"], "unit_price": 90,
            }],
        },
        "recipe_catalog": [{
            "recipe_id": "porridge", "title": "Каша", "meal_intent_id": "porridge",
            "ingredients": [{"ingredient_id": "milk", "name": "Молоко", "category": "dairy"}]
            + ([{"ingredient_id": "oats", "name": "Хлопья", "category": "grain"}] if topup else []),
        }],
        "inventory_snapshot": [{
            "sku_id": "oats", "name": "Хлопья", "category": "grain", "ingredient_ids": ["oats"],
            "store_id": "store", "distance_km": 0.2, "price": 50,
        }, {
            "sku_id": "ready", "name": "Готовая каша", "category": "prepared_food",
            "store_id": "store", "distance_km": 0.2, "price": 150,
            "is_prepared_food": True, "meal_intent_ids": ["porridge"], "contained_categories": ["dairy"],
        }], "requested_mode": "explore", "now": NOW,
    }


def post(path, body):
    response = client.post(path, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def issue(request):
    return post("/api/v1/meal-recommendations", request)["recommendations"][0]


def plan_request(meal, plan_id="plan", route="cook", now=NOW):
    return {
        "offer_id": meal["offer_id"], "user_id": USER, "plan_id": plan_id,
        "meal_id": meal["meal_id"], "selected_route": route,
        "selected_recipe_id": meal["cook_variant"]["recipe_id"] if route == "cook" else None,
        "selected_product_ids": ([item["product_options"][0]["sku_id"]
            for item in meal["cook_variant"]["ingredients"]
            if item["required"] and item["source"] not in {"home", "receipt"}]
            if route == "cook" else [meal["ready_variant"]["product_options"][0]["sku_id"]]),
        "fulfillment": "next_visit", "created_at": now,
    }


def save(meal, plan_id="plan", route="cook", now=NOW):
    result = post("/api/v1/meal-plans", plan_request(meal, plan_id, route, now))
    assert result["status"] == "created", result
    return result


def emit(receipt, plan_id=None, **changes):
    return post("/api/v1/events/receipts", {
        "user_id": USER, "receipt": receipt, "meal_plan_id": plan_id,
        "now": "2026-09-06T12:00:00+03:00", **changes,
    })


def purchase(sku="oats", receipt_id="new-purchase", day="04", *, ready=False):
    return {
        "receipt_id": receipt_id, "store_id": "store",
        "purchased_at": f"2026-09-{day}T13:00:00+03:00",
        "items": [{"sku_id": sku, "name": "Продукт", "category": "dairy",
                   "unit_price": 100, "ingredient_ids": [sku], "is_prepared_food": ready}],
    }


def complete(plan_id="plan", now="2026-09-05T14:00:00+03:00"):
    return post(f"/api/v1/meal-plans/{plan_id}/complete-cook", {"user_id": USER, "now": now})


def test_passive_purchase_and_legacy_completion_never_award_xp():
    result = emit(purchase(), recipe_id="made-up", recipe_completed=True)
    assert result["progress"]["avatar_xp"] == 0
    assert result["progress"]["meals_completed"] == 0
    assert result["progress"]["purchase_days"] == 1
    assert "legacy_completion_ignored" in result["reason_codes"]


def test_home_cooking_can_repeat_without_receipts_but_never_farm_xp():
    meal = issue(payload(home=True))
    for index in range(4):
        saved = save(meal, str(index))
        assert saved["plan"]["reward"]["status"] == "no_purchase_evidence"
        result = complete(str(index))
        assert result["status"] == "completed"
        assert result["progress"]["avatar_xp"] == 0
        assert result["progress"]["meals_completed"] == index + 1
    assert result["progress"]["purchase_days"] == 0


@pytest.mark.parametrize("changes", [
    {"offer_id": "invented"}, {"user_id": "other"}, {"meal_id": "invented"},
    {"selected_recipe_id": "invented"}, {"selected_product_ids": []},
    {"selected_product_ids": ["wrong"]}, {"selected_product_ids": ["oats", "extra"]},
    {"created_at": "2026-09-03T12:00:00+03:00"},
])
def test_offer_owner_recipe_products_and_time_are_not_client_authority(changes):
    request = plan_request(issue(payload(topup=True)))
    request.update(changes)
    result = post("/api/v1/meal-plans", request)
    assert result["status"] == "rejected"
    assert result["plan"] is None
    assert result["progress"]["avatar_xp"] == 0


def test_existing_plan_cannot_be_rewritten_on_retry():
    request = plan_request(issue(payload(topup=True)))
    first = post("/api/v1/meal-plans", request)
    assert post("/api/v1/meal-plans", request)["plan"] == first["plan"]
    request["selected_product_ids"] = []
    assert post("/api/v1/meal-plans", request)["reason_codes"] == ["meal_plan_payload_mismatch"]


def test_current_receipt_is_evidence_only_after_verification_and_exact_binding():
    request = payload()
    emit(request["current_receipt"])
    meal = issue(request)
    assert save(meal)["plan"]["reward"]["status"] == "available"
    result = complete()
    assert result["progress"]["avatar_xp"] == 20
    assert result["plan"]["reward"] == {"status": "awarded", "xp": 20, "purchase_day": "2026-09-04"}
    assert complete()["progress"] == result["progress"]
    assert save(meal, "second")["plan"]["reward"]["status"] == "purchase_day_reward_used"
    assert complete("second")["progress"]["avatar_xp"] == 20


@pytest.mark.parametrize("mutated,owner", [(False, USER), (True, USER), (False, "other")])
def test_unverified_or_substituted_current_receipt_does_not_mint_reward(mutated, owner):
    request = payload()
    if mutated or owner != USER:
        emit(request["current_receipt"], user_id=owner)
    if mutated:
        request["current_receipt"]["items"][0]["unit_price"] += 1
    save(issue(request))
    assert complete()["progress"]["avatar_xp"] == 0


def test_topup_has_no_passive_xp_and_completion_is_capped_by_purchase_day():
    meal = issue(payload(topup=True))
    for index, day, expected in [(1, "04", 20), (2, "04", 20), (3, "05", 40)]:
        plan_id = str(index)
        save(meal, plan_id)
        bought = emit(purchase(receipt_id=plan_id, day=day), plan_id)
        before = 0 if index == 1 else 20
        assert bought["progress"]["avatar_xp"] == before
        result = complete(plan_id)
        assert result["progress"]["avatar_xp"] == expected
    assert result["progress"]["purchase_days"] == 2
    assert result["progress"]["rewarded_meals"] == 2


def test_simultaneous_completions_use_one_atomic_day_reward():
    request = payload()
    emit(request["current_receipt"])
    meal = issue(request)
    for index in range(8):
        save(meal, str(index))
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda index: complete(str(index)), range(8)))
    assert sum(r["plan"]["reward"]["status"] == "awarded" for r in results) == 1
    progress = client.get(f"/api/v1/progress/{USER}").json()
    assert progress["avatar_xp"] == 20 and progress["rewarded_meals"] == 1


@pytest.mark.parametrize("mutation", ["store", "prepared", "sku", "old", "future"])
def test_nonmatching_or_invalid_purchase_cannot_collect_or_award(mutation):
    save(issue(payload(topup=True)))
    receipt = purchase()
    if mutation == "store": receipt["store_id"] = "another-store"
    if mutation == "prepared": receipt["items"][0]["is_prepared_food"] = True
    if mutation == "sku": receipt["items"][0]["sku_id"] = "other"
    if mutation == "old": receipt["purchased_at"] = "2026-09-04T11:59:00+03:00"
    if mutation == "future": receipt["purchased_at"] = "2026-09-07T13:00:00+03:00"
    emit(receipt, "plan")
    assert complete()["status"] == "not_ready"
    assert client.get(f"/api/v1/progress/{USER}").json()["avatar_xp"] == 0


@pytest.mark.parametrize("after_purchase", [False, True])
def test_ready_reward_requires_explicit_task_for_both_entry_orders(after_purchase):
    request = payload()
    receipt = purchase("ready", ready=True)
    if after_purchase:
        receipt["purchased_at"] = "2026-09-04T11:00:00+03:00"
        request["current_receipt"] = deepcopy(receipt)
        assert emit(receipt)["progress"]["avatar_xp"] == 0
    meal = issue(request)
    result = save(meal, route="ready")
    if not after_purchase:
        assert result["progress"]["avatar_xp"] == 0
        result = emit(receipt, "plan")
    assert result["progress"]["avatar_xp"] == 20
    assert result["progress"]["ready_meals_completed"] == 1
    assert complete()["status"] == "rejected"


def test_moscow_day_is_used_even_when_cooking_next_day():
    meal = issue(payload(topup=True))
    save(meal, "one")
    first = purchase(receipt_id="one")
    first["purchased_at"] = "2026-09-04T21:05:00Z"  # Sep 5 in Moscow
    emit(first, "one")
    assert complete("one")["plan"]["reward"]["purchase_day"] == "2026-09-05"
    save(meal, "two")
    second = purchase(receipt_id="two", day="05")
    second["purchased_at"] = "2026-09-05T00:10:00+03:00"
    emit(second, "two")
    result = complete("two", "2026-09-06T14:00:00+03:00")
    assert result["plan"]["reward"]["status"] == "purchase_day_reward_used"
    assert result["progress"]["avatar_xp"] == 20


def test_multiple_receipts_use_latest_contributing_purchase_not_arrival_order():
    request = payload(topup=True)
    request["recipe_catalog"][0]["ingredients"].append(
        {"ingredient_id": "egg", "name": "Яйцо", "category": "egg"}
    )
    egg = deepcopy(request["inventory_snapshot"][0])
    egg.update(sku_id="egg", ingredient_ids=["egg"], name="Яйцо", category="egg")
    request["inventory_snapshot"].append(egg)
    save(issue(request))
    later = emit(purchase(receipt_id="later", day="05"), "plan")
    assert later["meal_plan"]["status"] == "saved"
    assert complete()["status"] == "not_ready"
    earlier = emit(purchase("egg", "earlier", day="04"), "plan")
    assert earlier["meal_plan"]["status"] == "collected"
    assert earlier["meal_plan"]["reward"]["purchase_day"] == "2026-09-05"
    result = complete()
    assert result["progress"]["avatar_xp"] == 20
    assert result["progress"]["purchase_days"] == 2
    assert emit(purchase("egg", "earlier", day="04"), "plan")["meal_plan"]["reward"]["purchase_day"] == "2026-09-05"
