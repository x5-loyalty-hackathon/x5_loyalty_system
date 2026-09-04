from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app.contracts import ReceiptProgressRequest, ReferralEvaluationRequest
from app.main import app, progress_service, referral_service


client = TestClient(app)


def receipt_event(
    *,
    receipt_id: str = "receipt-1",
    user_id: str = "user-1",
    purchased_at: str = "2026-09-03T12:00:00+03:00",
    now: str = "2026-09-03T12:05:00+03:00",
    recipe_completed: bool = False,
) -> dict:
    return {
        "user_id": user_id,
        "receipt": {
            "receipt_id": receipt_id,
            "purchased_at": purchased_at,
            "store_id": "store-17",
            "items": [
                {
                    "sku_id": "milk-markdown",
                    "name": "Молоко",
                    "category": "dairy",
                    "ingredient_ids": ["milk"],
                    "quantity": 2,
                    "unit_price": 50,
                    "is_markdown": True,
                    "original_unit_price": 100,
                }
            ],
        },
        "recipe_id": "porridge" if recipe_completed else None,
        "recipe_completed": recipe_completed,
        "now": now,
    }


def post_receipt(payload: dict) -> dict:
    response = client.post("/api/v1/events/receipts", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def referral_request(
    *,
    inviter: str = "inviter-1",
    invitee: str = "invitee-1",
) -> dict:
    return {
        "inviter_user_id": inviter,
        "invitee_user_id": invitee,
        "invite_code": "INVITE-123",
    }


def post_referral(payload: dict) -> dict:
    response = client.post("/api/v1/referrals/evaluate", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def qualify_invitee(user_id: str = "invitee-1") -> None:
    post_receipt(receipt_event(user_id=user_id, receipt_id=f"receipt-{user_id}"))


def test_verified_receipt_updates_bounded_progress_and_savings() -> None:
    body = post_receipt(receipt_event(recipe_completed=True))

    assert body["contract_version"] == "1.2"
    assert body["status"] == "verified"
    assert body["reason_codes"] == ["receipt_verified"]
    assert body["fraud_score"] == 0
    assert body["progress"] == {
        "user_id": "user-1",
        "verified_receipts": 1,
        "purchase_days": 1,
        "meals_completed": 1,
        "recipes_completed": 1,
        "ready_meals_completed": 0,
        "markdown_savings": 100.0,
        "rescue_items": 2.0,
        "referral_rewards": 0,
        "avatar_xp": 30,
        "avatar_level": 1,
        "xp_to_next_level": 20,
        "private_rank": {
            "cohort": "cooking_households",
            "position": 1,
            "cohort_size": 1,
            "percentile": 100.0,
        },
    }


def test_duplicate_receipt_is_idempotent() -> None:
    payload = receipt_event(recipe_completed=True)
    first = post_receipt(payload)
    second = post_receipt(payload)

    assert second["status"] == "duplicate"
    assert second["reason_codes"] == ["receipt_already_processed"]
    assert second["progress"] == first["progress"]


def test_concurrent_duplicate_receipt_is_recorded_once() -> None:
    request = ReceiptProgressRequest.model_validate(receipt_event())

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(lambda _: progress_service.process_receipt(request), range(8))
        )

    statuses = [response.status.value for response in responses]
    assert statuses.count("verified") == 1
    assert statuses.count("duplicate") == 7
    assert progress_service.get_progress("user-1").verified_receipts == 1
    assert progress_service.get_progress("user-1").avatar_xp == 10


def test_extra_receipt_same_day_does_not_add_purchase_day_xp() -> None:
    first = post_receipt(receipt_event())
    second = post_receipt(
        receipt_event(receipt_id="receipt-2", purchased_at="2026-09-03T18:00:00+03:00", now="2026-09-03T18:05:00+03:00")
    )

    assert first["progress"]["avatar_xp"] == 10
    assert second["status"] == "verified"
    assert "same_day_receipt_collapsed" in second["reason_codes"]
    assert second["progress"]["verified_receipts"] == 2
    assert second["progress"]["purchase_days"] == 1
    assert second["progress"]["avatar_xp"] == 10


def test_same_moscow_day_with_different_offsets_is_collapsed() -> None:
    first = post_receipt(
        receipt_event(
            receipt_id="offset-1",
            purchased_at="2026-09-04T00:30:00+03:00",
            now="2026-09-04T00:35:00+03:00",
        )
    )
    second = post_receipt(
        receipt_event(
            receipt_id="offset-2",
            purchased_at="2026-09-03T22:00:00Z",
            now="2026-09-03T22:05:00Z",
        )
    )

    assert first["progress"]["purchase_days"] == 1
    assert second["progress"]["purchase_days"] == 1
    assert second["progress"]["avatar_xp"] == 10
    assert "same_day_receipt_collapsed" in second["reason_codes"]


def test_naive_receipt_timestamps_are_rejected_instead_of_crashing() -> None:
    payload = receipt_event(
        purchased_at="2026-09-03T12:00:00",
        now="2026-09-03T12:05:00",
    )

    response = client.post("/api/v1/events/receipts", json=payload)

    assert response.status_code == 422


def test_cross_user_receipt_replay_is_rejected() -> None:
    post_receipt(receipt_event(user_id="owner"))
    replay = post_receipt(receipt_event(user_id="attacker"))

    assert replay["status"] == "rejected"
    assert replay["fraud_score"] == 1
    assert replay["reason_codes"] == ["receipt_claimed_by_another_user"]
    assert replay["progress"]["verified_receipts"] == 0


def test_future_receipt_is_held_for_review_without_progress() -> None:
    body = post_receipt(
        receipt_event(
            purchased_at="2026-09-04T12:00:00+03:00",
            now="2026-09-03T12:00:00+03:00",
        )
    )

    assert body["status"] == "pending_review"
    assert body["fraud_score"] == 0.8
    assert body["progress"]["verified_receipts"] == 0


def test_private_rank_is_returned_without_public_leaderboard() -> None:
    post_receipt(receipt_event(user_id="low", receipt_id="receipt-low"))
    post_receipt(
        receipt_event(
            user_id="high",
            receipt_id="receipt-high",
            recipe_completed=True,
        )
    )

    low = client.get("/api/v1/progress/low")
    high = client.get("/api/v1/progress/high")
    leaderboard = client.get("/api/v1/leaderboard")

    assert low.status_code == high.status_code == 200
    assert low.json()["private_rank"] == {
        "cohort": "cooking_households",
        "position": 2,
        "cohort_size": 2,
        "percentile": 50.0,
    }
    assert high.json()["private_rank"]["position"] == 1
    assert leaderboard.status_code == 404


def test_private_rank_never_compares_cooking_and_ready_heavy_users() -> None:
    post_receipt(receipt_event(user_id="cook", receipt_id="receipt-cook"))
    ready_payload = receipt_event(
        user_id="ready",
        receipt_id="receipt-ready",
        recipe_completed=True,
    )
    ready_payload["rank_cohort"] = "ready_heavy"
    post_receipt(ready_payload)

    cook_rank = client.get("/api/v1/progress/cook").json()["private_rank"]
    ready_rank = client.get("/api/v1/progress/ready").json()["private_rank"]

    assert cook_rank == {
        "cohort": "cooking_households",
        "position": 1,
        "cohort_size": 1,
        "percentile": 100.0,
    }
    assert ready_rank == {
        "cohort": "ready_heavy",
        "position": 1,
        "cohort_size": 1,
        "percentile": 100.0,
    }


def test_later_receipt_cannot_switch_an_established_rank_cohort() -> None:
    first = receipt_event(user_id="stable", receipt_id="stable-first")
    first["rank_cohort"] = "ready_heavy"
    post_receipt(first)
    second = receipt_event(user_id="stable", receipt_id="stable-second")
    second["rank_cohort"] = "cooking_households"
    post_receipt(second)

    rank = client.get("/api/v1/progress/stable").json()["private_rank"]

    assert rank["cohort"] == "ready_heavy"


def test_referral_waits_for_verified_invitee_purchase() -> None:
    body = post_referral(referral_request())

    assert body["status"] == "not_qualified"
    assert body["reason_codes"] == ["invitee_has_no_verified_purchase_day"]
    assert body["reward"]["inviter_xp"] == 0
    assert body["reward"]["invitee_xp"] == 0
    assert body["reward"]["monetary_value"] == 0


def test_qualified_referral_awards_virtual_progress_once() -> None:
    qualify_invitee()
    first = post_referral(referral_request())
    duplicate = post_referral(referral_request())

    assert first["status"] == "approved"
    assert first["reward"] == {
        "reward_type": "virtual_progress",
        "inviter_xp": 20,
        "invitee_xp": 20,
        "monetary_value": 0.0,
    }
    assert first["inviter_progress"]["avatar_xp"] == 20
    assert first["invitee_progress"]["avatar_xp"] == 30

    assert duplicate["status"] == "duplicate"
    assert duplicate["reward"]["inviter_xp"] == 0
    assert duplicate["reward"]["invitee_xp"] == 0
    assert duplicate["inviter_progress"]["avatar_xp"] == 20
    assert duplicate["invitee_progress"]["avatar_xp"] == 30


def test_concurrent_referral_awards_progress_once() -> None:
    qualify_invitee()
    request = ReferralEvaluationRequest.model_validate(referral_request())

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(
            pool.map(lambda _: referral_service.evaluate(request), range(8))
        )

    statuses = [response.status.value for response in responses]
    assert statuses.count("approved") == 1
    assert statuses.count("duplicate") == 7
    assert client.get("/api/v1/progress/inviter-1").json()["avatar_xp"] == 20
    assert client.get("/api/v1/progress/invitee-1").json()["avatar_xp"] == 30


def test_second_inviter_cannot_claim_an_attributed_invitee() -> None:
    qualify_invitee()
    post_referral(referral_request(inviter="first"))
    body = post_referral(referral_request(inviter="second"))

    assert body["status"] == "rejected"
    assert body["fraud_score"] == 1
    assert body["reason_codes"] == ["invitee_already_attributed"]
    assert body["inviter_progress"]["avatar_xp"] == 0


def test_self_referral_is_hard_rejected() -> None:
    body = post_referral(referral_request(inviter="same", invitee="same"))

    assert body["status"] == "rejected"
    assert body["fraud_score"] == 1
    assert body["reason_codes"] == ["self_referral"]


def test_identity_collisions_go_to_review_instead_of_automatic_block() -> None:
    qualify_invitee()
    payload = referral_request()
    payload.update(
        {
            "inviter_device_hash": "same-device",
            "invitee_device_hash": "same-device",
            "inviter_payment_hash": "same-payment",
            "invitee_payment_hash": "same-payment",
        }
    )

    body = post_referral(payload)

    assert body["status"] == "pending_review"
    assert body["fraud_score"] == 0.8
    assert set(body["reason_codes"]) == {
        "shared_device_hash",
        "shared_payment_hash",
    }
    assert body["reward"]["inviter_xp"] == 0
    assert body["invitee_progress"]["avatar_xp"] == 10


def test_progress_contract_rejects_unknown_fields() -> None:
    payload = deepcopy(receipt_event())
    payload["unexpected"] = True

    response = client.post("/api/v1/events/receipts", json=payload)

    assert response.status_code == 422
