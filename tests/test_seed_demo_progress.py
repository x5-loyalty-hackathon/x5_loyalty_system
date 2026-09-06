"""Demo preparation uses real API contracts; no direct XP/state seeding."""
from copy import deepcopy
from datetime import datetime, timedelta
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app, state_repository
from scripts import seed_demo_progress as seed


@pytest.fixture
def setup_seed(monkeypatch, tmp_path):
    client = TestClient(app)
    calls = []

    def post(base, path, payload):
        response = client.post(path, json=payload)
        assert response.status_code == 200, response.text
        body = response.json()
        calls.append((path, deepcopy(payload), body))
        return body

    monkeypatch.setattr(seed, "post", post)
    fixture = json.loads(seed.FIXTURE.read_text(encoding="utf-8"))
    start = datetime.fromisoformat(fixture["now"])
    journal = seed.SeedJournal(tmp_path / "journal.json", "http://testserver")
    return client, calls, fixture, start, journal


def test_fifty_days_and_fresh_process_retry_have_exact_plans_and_no_extra_xp(setup_seed):
    client, calls, fixture, start, journal = setup_seed
    for attempt in range(2):
        # A new object reads the on-disk journal, like a second CLI process.
        journal = seed.SeedJournal(journal.path, "http://testserver")
        for offset in range(50, 0, -1):
            status = seed.seed_day("http://testserver", fixture, start - timedelta(days=offset), journal)
            assert status == ("verified" if attempt == 0 else "duplicate")
        progress = client.get(f"/api/v1/progress/{seed.VETERAN_USER_ID}").json()
        assert progress["avatar_xp"] == 1000
        assert progress["avatar_level"] == 21
        assert progress["rewarded_meals"] == progress["verified_receipts"] == progress["purchase_days"] == 50
    plans = [(request, response) for path, request, response in calls if path.endswith("/meal-plans")]
    assert [request for request, _ in plans[:50]] == [request for request, _ in plans[50:]]
    assert {response["status"] for _, response in plans[:50]} == {"created"}
    assert {response["status"] for _, response in plans[50:]} == {"duplicate"}
    assert len([path for path, _, _ in calls if path.endswith("/meal-recommendations")]) == 50


def test_journal_survives_backend_restart_without_bypassing_offer_validation(setup_seed):
    client, calls, fixture, start, journal = setup_seed
    day = start - timedelta(days=1)
    assert seed.seed_day("http://testserver", fixture, day, journal) == "verified"
    state_repository.reset()
    assert seed.seed_day("http://testserver", fixture, day, journal) == "verified"
    assert client.get(f"/api/v1/progress/{seed.VETERAN_USER_ID}").json()["avatar_xp"] == 20
    assert [result["status"] for path, _, result in calls if path.endswith("/meal-plans")] == ["created", "rejected", "created"]


@pytest.mark.parametrize("lost_path", ["/api/v1/meal-plans", "/api/v1/events/receipts"])
def test_lost_response_replays_exact_request_after_new_process(setup_seed, monkeypatch, lost_path):
    client, calls, fixture, start, journal = setup_seed
    post = seed.post
    lost = False

    def lose_once(base, path, payload):
        nonlocal lost
        result = post(base, path, payload)
        if path == lost_path and not lost:
            lost = True
            raise OSError("Response lost after server accepted the request")
        return result

    monkeypatch.setattr(seed, "post", lose_once)
    day = start - timedelta(days=1)
    with pytest.raises(OSError):
        seed.seed_day("http://testserver", fixture, day, journal)
    journal = seed.SeedJournal(journal.path, "http://testserver")
    assert seed.seed_day("http://testserver", fixture, day, journal) in {"verified", "duplicate"}
    sent = [payload for path, payload, _ in calls if path == lost_path]
    assert len(sent) == 2 and sent[0] == sent[1]
    assert client.get(f"/api/v1/progress/{seed.VETERAN_USER_ID}").json()["avatar_xp"] == 20


@pytest.mark.parametrize("reason", ["meal_plan_payload_mismatch", "meal_offer_expired"])
def test_rejected_plan_stops_before_receipt_and_does_not_discard_journal(setup_seed, monkeypatch, reason):
    _, calls, fixture, start, journal = setup_seed
    post = seed.post

    def reject(base, path, payload):
        if path.endswith("/meal-plans"):
            return {"status": "rejected", "reason_codes": [reason]}
        return post(base, path, payload)

    monkeypatch.setattr(seed, "post", reject)
    with pytest.raises(RuntimeError, match="План"):
        seed.seed_day("http://testserver", fixture, start - timedelta(days=1), journal)
    assert journal.path.exists()
    assert not any(path.endswith("/receipts") for path, _, _ in calls)


@pytest.mark.parametrize("status", ["rejected", "pending_review"])
def test_nonverified_receipt_is_not_reported_as_success(setup_seed, monkeypatch, status):
    _, _, fixture, start, journal = setup_seed
    post = seed.post

    def reject(base, path, payload):
        if path.endswith("/receipts"):
            return {"status": status, "reason_codes": ["test_failure"]}
        return post(base, path, payload)

    monkeypatch.setattr(seed, "post", reject)
    with pytest.raises(RuntimeError, match="Чек"):
        seed.seed_day("http://testserver", fixture, start - timedelta(days=1), journal)


def test_journal_cannot_be_replayed_to_another_server(setup_seed):
    _, _, fixture, start, journal = setup_seed
    seed.seed_day("http://testserver", fixture, start - timedelta(days=1), journal)
    with pytest.raises(RuntimeError, match="другому серверу"):
        seed.SeedJournal(journal.path, "http://another-server")
