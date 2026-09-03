import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
client = TestClient(app)


def load_example(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_published_examples_form_one_end_to_end_demo() -> None:
    recommendation = client.post(
        "/api/v1/recommendations",
        json=load_example("recommendation_request.json"),
    )
    assert recommendation.status_code == 200, recommendation.text
    assert recommendation.json()["user_id"] == "user_demo_001"
    assert recommendation.json()["recommendations"]

    receipt = client.post(
        "/api/v1/events/receipts",
        json=load_example("receipt_event.json"),
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["status"] == "verified"
    assert receipt.json()["progress"]["avatar_xp"] == 30

    progress = client.get("/api/v1/progress/user_demo_001")
    assert progress.status_code == 200, progress.text
    assert progress.json()["recipes_completed"] == 1
    assert progress.json()["markdown_savings"] == 100.0

    referral = client.post(
        "/api/v1/referrals/evaluate",
        json=load_example("referral_request.json"),
    )
    assert referral.status_code == 200, referral.text
    assert referral.json()["status"] == "approved"
    assert referral.json()["reward"]["monetary_value"] == 0
    assert referral.json()["invitee_progress"]["avatar_xp"] == 40
