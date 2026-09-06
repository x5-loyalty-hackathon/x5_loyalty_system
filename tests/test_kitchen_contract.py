from fastapi.testclient import TestClient

from app.main import app, state_repository


client = TestClient(app)


def setup_function() -> None:
    state_repository.reset()


def _receipt() -> dict:
    return {
        "user_id": "cook-1",
        "receipt": {
            "receipt_id": "receipt-kitchen-1",
            "purchased_at": "2026-09-06T12:00:00+03:00",
            "store_id": "store-17",
            "items": [
                {
                    "sku_id": "curd-1", "name": "Творог", "category": "dairy",
                    "ingredient_ids": ["cottage_cheese"], "quantity": 1,
                    "unit_price": 120,
                },
                {
                    "sku_id": "egg-1", "name": "Яйца", "category": "egg",
                    "ingredient_ids": ["egg"], "quantity": 10,
                    "unit_price": 100,
                },
            ],
        },
        "now": "2026-09-06T12:05:00+03:00",
    }


def test_verified_receipt_populates_synthetic_kitchen() -> None:
    assert client.post("/api/v1/events/receipts", json=_receipt()).status_code == 200
    response = client.get("/api/v1/kitchen/cook-1")
    assert response.status_code == 200
    assert response.json() == {
        "contract_version": "1.0",
        "user_id": "cook-1",
        "data_source": "synthetic_from_verified_receipts",
        "items": [
            {"ingredient_id": "cottage_cheese", "name": "Творог", "quantity": 1.0, "unit": "шт."},
            {"ingredient_id": "egg", "name": "Яйца", "quantity": 10.0, "unit": "шт."},
        ],
    }


def test_recipe_completion_is_separate_from_receipt_and_idempotent() -> None:
    client.post("/api/v1/events/receipts", json=_receipt())
    payload = {
        "completion_id": "cook-1/syrniki/1", "user_id": "cook-1",
        "recipe_id": "syrniki", "ingredient_ids": ["cottage_cheese", "egg"],
        "completed_at": "2026-09-06T12:30:00+03:00",
    }
    first = client.post("/api/v1/events/recipes/completed", json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "completed"
    assert first.json()["kitchen"]["items"] == []
    assert first.json()["progress"]["recipes_completed"] == 1

    second = client.post("/api/v1/events/recipes/completed", json=payload)
    assert second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert second.json()["progress"]["recipes_completed"] == 1


def test_completion_cannot_claim_a_different_synthetic_recipe() -> None:
    payload = {
        "completion_id": "cook-1/forged/1", "user_id": "cook-1",
        "recipe_id": "syrniki", "ingredient_ids": ["milk"],
        "completed_at": "2026-09-06T12:30:00+03:00",
    }
    response = client.post("/api/v1/events/recipes/completed", json=payload)
    assert response.status_code == 422


def test_recipe_details_are_explicitly_synthetic_and_unknown_recipes_404() -> None:
    response = client.get("/api/v1/recipes/syrniki")
    assert response.status_code == 200
    assert set(response.json()["ingredient_ids"]) == {"cottage_cheese", "egg"}
    assert client.get("/api/v1/recipes/not-real").status_code == 404
