"""Reproduce PoC system invariants through HTTP without changing a live server.

Run: .venv/bin/python -m scripts.poc_system_safety_audit --output artifacts/safety-audit-2026-09-07/directed.json
Failures are preserved as evidence; --check also makes them fail the process.
All inputs are synthetic. No network, checkout or persistent application state.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from itertools import product
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app import main as api
from app.contracts import ModelRecommendation
from app.recommender import DeterministicMockEngine
from app.safety import SafetyPolicy
from app.service import RecommendationService
from recsys.model import MLRecommendationEngine


NOW = "2026-09-07T12:00:00+03:00"
ENDPOINT = "/api/v1/meal-recommendations"


def fixture() -> dict:
    def sku(ingredient: str) -> dict:
        return dict(sku_id=ingredient, name=ingredient, category="vegetable",
                    ingredient_ids=[ingredient], store_id="audit-store",
                    distance_km=0.5, price=100, fulfillment_options=["delivery"])

    return dict(
        user=dict(user_id="audit-user", radius_km=0.75),
        current_receipt=dict(receipt_id="audit-context", purchased_at=NOW,
                             store_id="audit-store", items=[dict(
                                 sku_id="bread", name="Хлеб", category="bakery",
                                 ingredient_ids=["bread"], unit_price=50)]),
        recipe_catalog=[dict(recipe_id="vegetable_stew", title="Овощное рагу",
                             verified=True, ingredients=[
                                 dict(ingredient_id=i, name=i, category="vegetable")
                                 for i in ["zucchini", "tomato"]])],
        inventory_snapshot=[sku("zucchini"), sku("tomato"), dict(
            sku_id="ready-stew", name="Рагу из кабачков и томатов",
            category="prepared_food", ingredient_ids=["zucchini", "tomato"],
            composition_complete=True, composition_source="synthetic_fixture",
            contained_categories=["vegetable"], is_prepared_food=True,
            meal_intent_ids=["vegetable_stew"], store_id="audit-store",
            distance_km=0.5, price=150, fulfillment_options=["delivery"])],
        now=NOW, limit=1, requested_mode="explore")


class MaxScoreEngine:
    """Every candidate gets max score, including unverified/duplicate/unknown IDs."""
    def rank(self, request):
        ids = ["absent-from-catalog"] + [r.recipe_id for r in request.recipe_catalog] * 2
        return [ModelRecommendation(recipe_id=i, mode="explore", score=1,
                                    reason_codes=["personalized_discovery"]) for i in ids]


def cases():
    def case(name, mutate, routes=("cook", "ready"), status=200):
        p = fixture()
        mutate(p)
        return name, p, set(routes), status

    yield case("safe_control", lambda p: None)
    yield case("unverified_recipe", lambda p: p["recipe_catalog"][0].update(verified=False), ())
    for mode in ("current", "repeat", "explore"):
        def exclude(p):
            p["requested_mode"] = mode
            p["user"].update(excluded_ingredient_ids=["tomato"],
                             saved_recipe_ids=["vegetable_stew"], home_ingredient_ids=["tomato"])
            p["current_receipt"]["items"][0]["ingredient_ids"] = ["tomato"]
        yield case(f"excluded_recipe_even_if_available_{mode}", exclude, ())
    yield case("excluded_optional_recipe_ingredient", lambda p: (
        p["user"].update(excluded_ingredient_ids=["tomato"]),
        p["recipe_catalog"][0]["ingredients"][1].update(required=False)), ())
    yield case("excluded_known_ready_component", lambda p: (
        p["user"].update(excluded_ingredient_ids=["milk"]),
        p["inventory_snapshot"][2]["ingredient_ids"].append("milk")), ("cook",))
    yield case("excluded_known_ready_category", lambda p: (
        p["user"].update(excluded_categories=["dairy"]),
        p["inventory_snapshot"][2]["contained_categories"].append("dairy")), ("cook",))
    yield case("excluded_known_raw_component", lambda p: (
        p["user"].update(excluded_ingredient_ids=["milk"]),
        p["inventory_snapshot"][0].update(name="Кабачки со сливками", ingredient_ids=["zucchini", "milk"])), ("ready",))
    yield case("excluded_known_raw_category", lambda p: (
        p["user"].update(excluded_categories=["dairy"]),
        p["inventory_snapshot"][0].update(name="Кабачки со сливками", contained_categories=["vegetable", "dairy"])), ("ready",))
    yield case("excluded_known_receipt_component", lambda p: (
        p["user"].update(excluded_ingredient_ids=["milk"]),
        p["current_receipt"]["items"][0].update(name="Кабачки со сливками", category="vegetable",
                                               ingredient_ids=["zucchini", "milk"])))
    # The excluded receipt pack must not cover zucchini, but this fixture has
    # a safe zucchini SKU to purchase instead. Regression tests inspect source
    # and selected SKU, not just the surviving routes.
    yield case("unknown_ready_composition_with_hard_exclusion", lambda p: (
        p["user"].update(excluded_ingredient_ids=["tomato"]),
        p["inventory_snapshot"][2].update(ingredient_ids=[])), ())
    yield case("unknown_ready_composition_without_exclusions", lambda p:
               p["inventory_snapshot"][2].update(ingredient_ids=[]))
    yield case("wrong_ready_meal_intent", lambda p:
               p["inventory_snapshot"][2].update(meal_intent_ids=["soup"]), ("cook",))
    yield case("raw_does_not_match_ingredient", lambda p:
               p["inventory_snapshot"][0].update(ingredient_ids=["onion"]), ("ready",))
    yield case("ready_not_used_as_raw", lambda p: p["inventory_snapshot"].pop(0), ("ready",))
    yield case("no_inventory", lambda p: p.update(inventory_snapshot=[]), ())
    yield case("one_store_cannot_supply_basket", lambda p:
               p["inventory_snapshot"][0].update(store_id="other-store"), ("ready",))
    yield case("no_common_fulfillment", lambda p:
               p["inventory_snapshot"][0].update(fulfillment_options=["next_visit"]), ("ready",))
    yield case("selected_store_unavailable", lambda p: p.update(shopping_context=dict(
        anchor_type="home", radius_km=0.75, selected_store_id="absent-store")), ())
    yield case("empty_mapping_false_complete_basket", lambda p: (
        p["inventory_snapshot"][0].update(name="Томаты", ingredient_ids=[]),
        p.update(inventory_snapshot=p["inventory_snapshot"][:1])), ())
    yield case("same_sku_for_two_ingredients_false_complete_basket", lambda p: (
        p["inventory_snapshot"][0].update(ingredient_ids=["zucchini", "tomato"]),
        p.update(inventory_snapshot=p["inventory_snapshot"][:1])), ())
    for idx, route in [(0, "cook"), (2, "ready")]:
        for name, patch in [
            ("expired", dict(expires_at="2026-09-07T11:59:59+03:00")),
            ("expiry_equals_now_utc", dict(expires_at="2026-09-07T09:00:00Z")),
            ("out_of_stock", dict(available_quantity=0)),
            ("ineligible", dict(safety_eligible=False)),
            ("outside_radius", dict(distance_km=0.75001)),
            ("no_fulfillment", dict(fulfillment_options=[])),
            ("forbidden_markdown_category", dict(is_markdown=True, category="bakery", original_price=200)),
        ]:
            yield case(f"{route}_{name}", lambda p: p["inventory_snapshot"][idx].update(patch),
                       ({"cook", "ready"} - {route}))
        yield case(f"{route}_exact_radius_allowed", lambda p: p["inventory_snapshot"][idx].update(distance_km=0.75))
    for name, mutate in [
        ("duplicate_sku", lambda p: p["inventory_snapshot"].append(deepcopy(p["inventory_snapshot"][0]))),
        ("duplicate_recipe", lambda p: p["recipe_catalog"].append(deepcopy(p["recipe_catalog"][0]))),
        ("negative_price", lambda p: p["inventory_snapshot"][0].update(price=-1)),
        ("negative_stock", lambda p: p["inventory_snapshot"][0].update(available_quantity=-1)),
        ("unknown_enum", lambda p: p.update(requested_mode="invented")),
        ("unknown_request_field", lambda p: p.update(force_safe=True)),
        ("naive_time", lambda p: p.update(now="2026-09-07T12:00:00")),
        ("empty_catalog", lambda p: p.update(recipe_catalog=[])),
        ("empty_receipt", lambda p: p["current_receipt"].update(items=[])),
    ]:
        yield case(name, mutate, (), 422)
    # Exhaustive 2^6 combinations independently on both routes (128 per engine).
    for idx, route in [(0, "cook"), (2, "ready")]:
        for flags in product((False, True), repeat=6):
            p = fixture()
            p["inventory_snapshot"][idx].update(
                safety_eligible=not flags[0], available_quantity=0 if flags[1] else 1,
                expires_at=NOW if flags[2] else None, distance_km=1 if flags[3] else 0.5,
                fulfillment_options=[] if flags[4] else ["delivery"],
                is_markdown=flags[5], category="bakery" if flags[5] else ("vegetable" if idx == 0 else "prepared_food"),
                original_price=200)
            yield (f"combo_{route}_{''.join(str(int(f)) for f in flags)}", p,
                   {"cook", "ready"} - ({route} if any(flags) else set()), 200)


def selected_plan(client, p, meal):
    """Check whether a supposedly complete cook basket can actually be saved."""
    ids = sorted({i["product_options"][0]["sku_id"]
                  for i in meal["cook_variant"]["ingredients"] if i["product_options"]})
    request = dict(offer_id=meal["offer_id"], plan_id="audit-plan", user_id=p["user"]["user_id"],
                   meal_id=meal["meal_id"], selected_route="cook",
                   selected_recipe_id=meal["cook_variant"]["recipe_id"],
                   selected_product_ids=ids, fulfillment="delivery", created_at=NOW)
    response = client.post("/api/v1/meal-plans", json=request)
    return dict(request=request, http_status=response.status_code, response=response.json())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="exit nonzero on invariant failures")
    args = parser.parse_args()
    results, engines = [], {}
    for name, engine in [("mock", DeterministicMockEngine()), ("model", MLRecommendationEngine()),
                         ("max_score_with_unknown_and_duplicates", MaxScoreEngine())]:
        engines[name] = dict(type=f"{type(engine).__module__}.{type(engine).__name__}",
                             training_catalog_hash=getattr(engine, "training_catalog_hash", None))
        api.recommendation_service = RecommendationService(engine=engine, safety_policy=SafetyPolicy(),
                                                           saved_recipe_provider=api.state_repository)
        with TestClient(api.app, raise_server_exceptions=False) as client:
            for case_name, payload, expected, expected_status in cases():
                api.state_repository.reset()
                response = client.post(ENDPOINT, json=payload)
                body = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
                meals = body.get("recommendations", []) if isinstance(body, dict) else []
                routes = {r for meal in meals for r in meal["available_routes"]}
                consistent = all(meal["default_route"] in meal["available_routes"] and
                                 bool(meal["cook_variant"]) == ("cook" in meal["available_routes"]) and
                                 bool(meal["ready_variant"]) == ("ready" in meal["available_routes"])
                                 for meal in meals)
                passed = response.status_code == expected_status and routes == expected and consistent
                row = dict(engine=name, case=case_name, passed=passed, http_status=response.status_code,
                           expected_http_status=expected_status, expected_routes=sorted(expected),
                           actual_routes=sorted(routes), consistent_variants=consistent)
                if not passed:
                    row.update(request=payload, response=body)
                    if "false_complete_basket" in case_name and meals:
                        row["save_plan_attempt"] = selected_plan(client, payload, meals[0])
                results.append(row)
    report = dict(synthetic=True, transport="FastAPI TestClient, isolated process", engines=engines,
                  total=len(results), passed=sum(r["passed"] for r in results),
                  failures_by_case=dict(Counter(r["case"] for r in results if not r["passed"])), results=results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    if args.check and report["failures_by_case"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
