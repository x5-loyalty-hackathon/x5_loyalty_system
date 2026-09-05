"""Mobile fixtures and browser origin are part of the backend regression gate."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.contracts import RecommendationRequest
from app.main import app


def test_mobile_fixture_matches_contract_and_has_no_fabricated_pantry_expiry():
    fixture = json.loads(
        (Path(__file__).resolve().parents[1] / "mobile/src/fixtures/mealRequest.json")
        .read_text(encoding="utf-8")
    )
    request = RecommendationRequest.model_validate(fixture)
    assert request.current_receipt.purchased_at < request.now
    assert request.shopping_context.radius_km == 0.75
    assert request.user.saved_recipe_ids == set()
    assert all("expires_at" not in item for item in fixture["current_receipt"]["items"])
    response = TestClient(app).post("/api/v1/meal-recommendations", json=fixture)
    assert response.status_code == 200
    assert response.json()["contract_version"] == "1.2"


@pytest.mark.parametrize("origin,expected", [
    ("http://localhost:8081", 200),
    ("http://127.0.0.1:8081", 200),
    ("https://untrusted.example", 400),
])
def test_mobile_web_cors_is_explicit_not_wildcard(origin, expected):
    response = TestClient(app).options("/api/v1/meal-recommendations", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == expected
    if expected == 200:
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert "access-control-allow-origin" not in response.headers
