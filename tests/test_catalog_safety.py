"""S1–S3: safety survives ranking, receipt decomposition and plan creation."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app import main as api
from app.recommender import DeterministicMockEngine
from app.safety import SafetyPolicy
from app.service import RecommendationService
from scripts.poc_system_safety_audit import (
    ENDPOINT, MaxScoreEngine, cases, fixture, selected_plan,
)


@pytest.fixture(params=["mock", "model", "max_score"])
def catalog_client(request, monkeypatch, ml_engine):
    engine = {"mock": DeterministicMockEngine(), "model": ml_engine,
              "max_score": MaxScoreEngine()}[request.param]
    monkeypatch.setattr(api, "recommendation_service", RecommendationService(
        engine=engine, safety_policy=SafetyPolicy(), saved_recipe_provider=api.state_repository,
    ))
    with TestClient(api.app) as client:
        yield client


def meals(client, payload):
    response = client.post(ENDPOINT, json=payload)
    assert response.status_code == 200, response.text
    return response.json()["recommendations"]


@pytest.mark.parametrize("name,payload,routes,status", [
    pytest.param(*case, id=case[0]) for case in cases()
])
def test_directed_safety_invariants(catalog_client, name, payload, routes, status):
    response = catalog_client.post(ENDPOINT, json=deepcopy(payload))
    assert response.status_code == status, (name, response.text)
    if status != 200:
        return
    result = response.json()["recommendations"]
    assert {r for meal in result for r in meal["available_routes"]} == routes, name
    for meal in result:
        assert meal["default_route"] in meal["available_routes"]
        assert bool(meal["cook_variant"]) == ("cook" in meal["available_routes"])
        assert bool(meal["ready_variant"]) == ("ready" in meal["available_routes"])
        if meal["cook_variant"]:
            saved = selected_plan(catalog_client, payload, meal)
            assert saved["http_status"] == 200, saved
            assert saved["response"]["status"] == "created", saved


@pytest.mark.parametrize("exclusion", ["ingredient", "category"])
@pytest.mark.parametrize("replacement", [True, False])
def test_excluded_receipt_pack_is_never_home_coverage(catalog_client, exclusion, replacement):
    payload = fixture()
    payload["user"].update(excluded_ingredient_ids=["milk"] if exclusion == "ingredient" else [],
                           excluded_categories=["dairy"] if exclusion == "category" else [])
    payload["current_receipt"]["items"][0].update(
        ingredient_ids=["zucchini", "milk"], contained_categories=["vegetable", "dairy"],
    )
    if not replacement:
        payload["inventory_snapshot"].pop(0)
    meal = meals(catalog_client, payload)[0]
    # API routes are a set; JSON array order is not the default-route contract.
    assert set(meal["available_routes"]) == ({"cook", "ready"} if replacement else {"ready"})
    if replacement:
        ingredient = meal["cook_variant"]["ingredients"][0]
        assert ingredient["source"] == "full_price"
        assert [p["sku_id"] for p in ingredient["product_options"]] == ["zucchini"]
        assert meal["cook_variant"]["missing_count"] == 2


@pytest.mark.parametrize("exclusion", ["ingredient", "category", "none"])
@pytest.mark.parametrize("source,complete,known,confirmed", [
    ("unknown", False, False, False), ("unknown", True, True, False),
    ("recipe_proxy", True, True, False), ("manufacturer", False, True, False),
    ("manufacturer", True, False, False), ("manufacturer", True, True, True),
    ("synthetic_fixture", True, True, True),
])
def test_ready_composition_provenance(catalog_client, exclusion, source, complete, known, confirmed):
    payload = fixture()
    payload["user"].update(excluded_ingredient_ids=["milk"] if exclusion == "ingredient" else [],
                           excluded_categories=["dairy"] if exclusion == "category" else [])
    payload["inventory_snapshot"][-1].update(
        composition_source=source, composition_complete=complete,
        ingredient_ids=["zucchini", "tomato"] if known else [],
    )
    meal = meals(catalog_client, payload)[0]
    assert ("ready" in meal["available_routes"]) == (confirmed or exclusion == "none")
    assert "cook" in meal["available_routes"]


def test_shared_pack_is_removed_but_single_ingredient_alternatives_save(catalog_client):
    payload = fixture()
    shared = deepcopy(payload["inventory_snapshot"][0])
    shared.update(sku_id="shared", ingredient_ids=["zucchini", "tomato"], price=1)
    payload["inventory_snapshot"].insert(0, shared)
    meal = meals(catalog_client, payload)[0]
    assert meal["cook_variant"]["store_selection"]["options"][0]["complete"]
    assert all(p["sku_id"] != "shared" for i in meal["cook_variant"]["ingredients"] for p in i["product_options"])
    saved = selected_plan(catalog_client, payload, meal)
    assert saved["response"]["status"] == "created", saved


def test_feasible_store_survives_ambiguous_nearer_store(catalog_client):
    payload = fixture()
    for product in payload["inventory_snapshot"][:2]:
        product.update(store_id="safe-farther", distance_km=0.7)
    shared = deepcopy(payload["inventory_snapshot"][0])
    shared.update(sku_id="shared", store_id="bad-nearer", distance_km=0.1,
                  ingredient_ids=["zucchini", "tomato"])
    payload["inventory_snapshot"].append(shared)
    meal = meals(catalog_client, payload)[0]
    assert meal["cook_variant"]["store_selection"]["selected_store_id"] == "safe-farther"
    assert selected_plan(catalog_client, payload, meal)["response"]["status"] == "created"
