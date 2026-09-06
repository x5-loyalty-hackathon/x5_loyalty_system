"""Dashboard contracts use real accepted business events, not test-only counters."""
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app, state_repository
from tests import test_game_rewards as rewards
from tests.test_progress_and_referral import (
    post_receipt, post_referral, receipt_event, referral_request,
)


client = TestClient(app)
WINDOW = {"start_date": "2026-09-03", "end_date": "2026-09-06"}


def summary(**params):
    response = client.get("/api/v1/metrics/summary", params={**WINDOW, **params})
    assert response.status_code == 200, response.text
    return response.json()


def daily(**params):
    response = client.get("/api/v1/metrics/daily", params={**WINDOW, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_empty_metrics_are_read_only_and_have_null_ratios():
    before = deepcopy(state_repository._users)
    result = summary()
    assert result["counts"]["observed_event_users"] == 0
    assert result["counts"]["verified_receipts"] == 0
    for key in ("receipts_per_observed_user", "purchase_days_per_observed_user",
                "share_at_least_n_receipts", "share_at_least_n_purchase_days"):
        assert result["purchase_frequency"][key] is None
    assert len(daily()["days"]) == 4
    assert all(day["counts"]["observed_event_users"] == 0 for day in daily()["days"])
    assert summary() == result
    assert state_repository._users == before


def test_unique_accepted_receipts_and_observed_nonbuyers_define_denominator():
    one = receipt_event(user_id="buyer", receipt_id="one")
    assert post_receipt(one)["status"] == "verified"
    assert post_receipt(one)["status"] == "duplicate"
    assert post_receipt({**one, "user_id": "attacker"})["status"] == "rejected"
    post_receipt(receipt_event(user_id="buyer", receipt_id="two"))
    post_receipt(receipt_event(
        user_id="buyer", receipt_id="three", purchased_at="2026-09-04T10:00:00+03:00",
        now="2026-09-04T10:05:00+03:00",
    ))
    post_receipt(receipt_event(user_id="other-buyer", receipt_id="four"))
    assert post_receipt(receipt_event(
        user_id="future", receipt_id="held", purchased_at="2026-09-07T10:00:00+03:00",
    ))["status"] == "pending_review"
    # Recommendation input/history isn't a verified receipt; this user is still
    # in the observed population because an offer was actually issued.
    rewards.issue(rewards.payload())
    client.get("/api/v1/progress/read-only-visitor")
    result = summary()
    counts = result["counts"]
    assert counts["observed_event_users"] == 3
    assert counts["unclassified_event_users"] == 1
    assert counts["purchasing_users"] == 2
    assert counts["verified_receipts"] == 4
    assert counts["purchase_user_days"] == 3
    assert counts["receipt_amount_rub"] == 400
    assert counts["markdown_savings_rub"] == 400
    assert counts["meal_xp_earned"] == 0
    frequency = result["purchase_frequency"]
    assert frequency["receipts_per_observed_user"] == pytest.approx(4 / 3)
    assert frequency["purchase_days_per_observed_user"] == 1
    assert frequency["users_at_least_n_receipts"] == 1
    assert frequency["users_at_least_n_purchase_days"] == 1
    assert frequency["share_at_least_n_purchase_days"] == pytest.approx(1 / 3)
    assert summary(purchase_threshold=3)["purchase_frequency"]["users_at_least_n_purchase_days"] == 0


def test_daily_moscow_boundaries_and_zero_filled_days():
    for index, timestamp in enumerate([
        "2026-09-03T20:59:59Z",  # September 3 Moscow, outside selected window.
        "2026-09-03T21:00:00Z",  # September 4 starts exactly here.
        "2026-09-04T20:59:59Z",  # Same Moscow purchase day, another receipt.
        "2026-09-04T21:00:00Z",  # September 5 starts.
    ]):
        post_receipt(receipt_event(
            receipt_id=f"boundary-{index}", purchased_at=timestamp,
            now="2026-09-06T12:00:00+03:00",
        ))
    result = daily(start_date="2026-09-04")
    assert [day["date"] for day in result["days"]] == ["2026-09-04", "2026-09-05", "2026-09-06"]
    assert [day["counts"]["verified_receipts"] for day in result["days"]] == [2, 1, 0]
    assert [day["counts"]["purchase_user_days"] for day in result["days"]] == [1, 1, 0]
    whole = summary(start_date="2026-09-04")["counts"]
    assert whole["verified_receipts"] == 3
    assert whole["purchase_user_days"] == 2
    assert whole["observed_event_users"] == 1  # Daily uniques aren't additive.
    assert summary(start_date="2026-09-04", end_date="2026-09-04")["counts"]["verified_receipts"] == 2


def test_cohorts_do_not_guess_segment_for_offer_only_users():
    post_receipt(receipt_event(user_id="cook", receipt_id="cook-r"))
    post_receipt({**receipt_event(user_id="ready", receipt_id="ready-r"), "rank_cohort": "ready_heavy"})
    rewards.issue(rewards.payload(home=True))
    assert summary()["counts"]["observed_event_users"] == 3
    assert summary(cohort="cooking_households")["counts"]["observed_event_users"] == 1
    assert summary(cohort="ready_heavy")["counts"]["observed_event_users"] == 1
    assert summary(cohort="ready_heavy")["counts"]["unclassified_event_users"] == 0


def test_empty_feeds_are_not_recorded_and_repeated_feeds_are_new_offers():
    request = rewards.payload()
    request["user"]["excluded_categories"] = ["dairy"]
    empty = rewards.post("/api/v1/meal-recommendations", request)
    assert empty["recommendations"] == []
    assert summary()["counts"]["observed_event_users"] == 0
    first = rewards.post("/api/v1/meal-recommendations", rewards.payload())
    second = rewards.post("/api/v1/meal-recommendations", rewards.payload())
    counts = summary()["counts"]
    assert counts["observed_event_users"] == 1
    assert counts["meal_offers_issued"] == len(first["recommendations"]) + len(second["recommendations"])
    assert counts["verified_receipts"] == 0


def test_completions_not_plan_creation_or_receipts_define_xp_date():
    request = rewards.payload()
    rewards.emit(request["current_receipt"])
    meal = rewards.issue(request)
    plan = rewards.plan_request(meal)
    rewards.post("/api/v1/meal-plans", plan)
    assert rewards.post("/api/v1/meal-plans", plan)["status"] == "duplicate"
    assert rewards.post("/api/v1/meal-plans", {**plan, "plan_id": "bad", "offer_id": "invalid"})["status"] == "rejected"
    assert summary(end_date="2026-09-04")["counts"]["meal_xp_earned"] == 0
    rewards.complete(now="2026-09-05T00:00:00+03:00")
    assert rewards.complete()["status"] == "duplicate"
    counts = summary(start_date="2026-09-05")["counts"]
    assert counts["cook_plans_created"] == 0
    assert counts["cook_plans_completed"] == 1
    assert counts["rewarded_completed_plans"] == 1
    assert counts["meal_xp_earned"] == 20
    assert counts["verified_receipts"] == 0
    assert summary(end_date="2026-09-04")["counts"]["meal_xp_earned"] == 0
    # The reward's purchase-day cap is September 4, but earned XP is on completion.
    assert summary()["counts"]["cook_plans_created"] == 1


def test_ready_completion_and_same_purchase_day_cap_are_separate_from_cook():
    meal = rewards.issue(rewards.payload())
    for plan_id in ("ready-one", "ready-two"):
        rewards.save(meal, plan_id, route="ready")
        receipt = rewards.purchase(sku="ready", receipt_id=plan_id, ready=True)
        assert rewards.emit(receipt, plan_id)["status"] == "verified"
        assert rewards.emit(receipt, plan_id)["status"] == "duplicate"
    counts = summary()["counts"]
    assert counts["ready_plans_created"] == 2
    assert counts["ready_plans_completed"] == 2
    assert counts["cook_plans_completed"] == 0
    assert counts["rewarded_completed_plans"] == 1
    assert counts["meal_xp_earned"] == 20
    assert counts["purchase_user_days"] == 1


def test_home_only_completion_counts_activity_without_minting_purchases_or_xp():
    rewards.save(rewards.issue(rewards.payload(home=True)))
    rewards.complete()
    counts = summary()["counts"]
    assert counts["cook_plans_completed"] == 1
    assert counts["verified_receipts"] == 0
    assert counts["meal_xp_earned"] == 0
    assert counts["observed_event_users"] == 1
    assert counts["unclassified_event_users"] == 1


def test_referral_xp_is_not_fabricated_as_a_dated_meal_reward():
    post_receipt(receipt_event(user_id="invitee-1"))
    assert post_referral(referral_request())["status"] == "approved"
    result = summary()
    assert result["counts"]["meal_xp_earned"] == 0
    assert result["counts"]["observed_event_users"] == 1  # Undated inviter isn't a window event.
    assert "period_referral_xp" in result["metadata"]["unavailable"]
    assert "margin_per_participant_and_roi" in result["metadata"]["unavailable"]


def test_metrics_snapshot_is_detached_and_api_leaks_no_identifiers():
    post_receipt(receipt_event(user_id="private-user-id", receipt_id="private-receipt-id"))
    before = state_repository.metrics_snapshot()
    detached = state_repository.metrics_snapshot()
    detached.receipts[0][1].items[0].unit_price = 999
    detached.receipt_cohorts.clear()
    assert state_repository.metrics_snapshot() == before
    for endpoint in ("summary", "daily"):
        response = client.get(f"/api/v1/metrics/{endpoint}", params=WINDOW)
        assert response.status_code == 200
        assert "private-user-id" not in response.text
        assert "private-receipt-id" not in response.text
        assert "store-17" not in response.text
    assert state_repository.metrics_snapshot() == before


@pytest.mark.parametrize("endpoint,params", [
    ("summary", {}),
    ("summary", {"start_date": "bad", "end_date": "2026-09-06"}),
    ("summary", {"start_date": "2026-09-06", "end_date": "2026-09-05"}),
    ("daily", {"start_date": "2025-01-01", "end_date": "2026-01-02"}),
    ("summary", {**WINDOW, "purchase_threshold": 0}),
    ("summary", {**WINDOW, "purchase_threshold": 1001}),
    ("summary", {**WINDOW, "cohort": "unknown"}),
])
def test_invalid_or_unbounded_requests_are_422(endpoint, params):
    assert client.get(f"/api/v1/metrics/{endpoint}", params=params).status_code == 422


def test_largest_inclusive_window_is_366_days():
    response = client.get("/api/v1/metrics/daily", params={
        "start_date": "2025-01-01", "end_date": "2026-01-01",
    })
    assert response.status_code == 200
    assert len(response.json()["days"]) == 366


def test_openapi_exposes_metrics_contracts():
    paths = client.get("/openapi.json").json()["paths"]
    for endpoint in ("summary", "daily"):
        path = paths[f"/api/v1/metrics/{endpoint}"]
        assert set(path) == {"get"}
        assert "200" in path["get"]["responses"]
