import json
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from app.main import app, state_repository
from scripts.safety_demo import (
    INVITEE,
    INVITER,
    RECEIPTS,
    format_report,
    receipt_event,
    run_demo,
)


@pytest.fixture
def report() -> dict:
    # tests/conftest.py resets the shared repository before and after each
    # test, including assertion failures. The scenario never resets user state.
    with TestClient(app) as client:
        return run_demo(client)


def responses(report: dict) -> dict:
    return {event["name"]: event["response"] for event in report["events"]}


def test_demo_purchase_qualification_and_rewards_are_api_13(report: dict) -> None:
    events = responses(report)
    initial = events["referral_before_purchase"]
    assert initial["status"] == "not_qualified"
    assert initial["reason_codes"] == ["invitee_has_no_verified_purchase_day"]
    assert initial["invitee_progress"]["purchase_days"] == 0
    assert initial["reward"]["inviter_xp"] == initial["reward"]["invitee_xp"] == 0

    purchase = events["first_purchase_no_passive_xp"]
    assert purchase["contract_version"] == "1.3"
    assert purchase["status"] == "verified"
    assert purchase["reason_codes"] == ["receipt_verified"]
    assert purchase["progress"]["purchase_days"] == 1
    assert purchase["progress"]["avatar_xp"] == 0
    assert purchase["progress"]["rewarded_meals"] == 0

    approved = events["referral_approved"]
    assert approved["status"] == "approved"
    assert approved["fraud_score"] == 0
    assert approved["reward"] == {
        "reward_type": "virtual_progress",
        "inviter_xp": 20,
        "invitee_xp": 20,
        "monetary_value": 0,
    }
    repeated = events["referral_duplicate"]
    assert repeated["status"] == "duplicate"
    assert repeated["reason_codes"] == ["referral_already_rewarded"]
    assert repeated["reward"]["inviter_xp"] == repeated["reward"]["invitee_xp"] == 0
    for role in ("inviter_progress", "invitee_progress"):
        assert repeated[role] == approved[role]
        assert approved[role]["avatar_xp"] == 20
        assert approved[role]["referral_rewards"] == 1
    receipt_repeat = events["receipt_duplicate"]
    assert receipt_repeat["status"] == "duplicate"
    assert receipt_repeat["reason_codes"] == ["receipt_already_processed"]
    assert receipt_repeat["progress"] == approved["invitee_progress"]


def test_demo_replay_and_identity_signals_preserve_progress(report: dict) -> None:
    events = responses(report)
    baseline = events["referral_approved"]["inviter_progress"]
    self_referral = events["self_referral"]
    assert self_referral["status"] == "rejected"
    assert self_referral["fraud_score"] == 1
    assert self_referral["reason_codes"] == ["self_referral"]
    assert self_referral["inviter_progress"] == self_referral["invitee_progress"] == baseline
    replay = events["cross_user_receipt_replay"]
    assert replay["status"] == "rejected"
    assert replay["fraud_score"] == 1
    assert replay["reason_codes"] == ["receipt_claimed_by_another_user"]
    assert replay["progress"] == baseline
    mismatch = events["invite_code_owner_mismatch"]
    assert mismatch["status"] == "rejected"
    assert mismatch["fraud_score"] == 1
    assert mismatch["reason_codes"] == ["invite_code_does_not_match_inviter"]
    assert mismatch["invitee_progress"] == baseline
    for rejected in (self_referral, mismatch):
        assert rejected["reward"]["inviter_xp"] == rejected["reward"]["invitee_xp"] == 0

    qualified = events["review_invitee_purchase"]["progress"]
    assert qualified["purchase_days"] == 1
    for name, score, reasons in (
        ("shared_device_review", 0.75, ["shared_device_hash"]),
        ("shared_payment_review", 0.8, ["shared_payment_hash"]),
        ("shared_device_and_payment_review", 0.8, ["shared_device_hash", "shared_payment_hash"]),
    ):
        review = events[name]
        assert review["status"] == "pending_review"
        assert review["fraud_score"] == score
        assert review["reason_codes"] == reasons
        assert review["reward"]["inviter_xp"] == review["reward"]["invitee_xp"] == 0
        assert review["inviter_progress"] == baseline
        assert review["invitee_progress"] == qualified
    future = events["future_receipt_review"]
    assert future["status"] == "pending_review"
    assert future["fraud_score"] == 0.8
    assert future["reason_codes"] == ["receipt_timestamp_in_future"]
    assert future["progress"] == qualified


def test_demo_private_rank_moves_and_excludes_other_cohort(report: dict) -> None:
    events = responses(report)
    before = events["private_rank_before_reward"]
    after = events["private_rank_after_reward"]
    ready = events["separate_ready_cohort"]
    assert before["avatar_xp"] == 0
    assert after["avatar_xp"] == 20
    assert before["private_rank"] == {
        "cohort": "cooking_households", "position": 2,
        "cohort_size": 3, "percentile": 66.67,
    }
    assert after["private_rank"] == {
        "cohort": "cooking_households", "position": 1,
        "cohort_size": 3, "percentile": 100,
    }
    assert ready["avatar_xp"] == 40
    assert ready["private_rank"] == {
        "cohort": "ready_heavy", "position": 1,
        "cohort_size": 2, "percentile": 100,
    }
    for event in report["events"]:
        body = event["response"]
        for progress in (body, body.get("progress", {}), body.get("inviter_progress", {}), body.get("invitee_progress", {})):
            if "private_rank" in progress:
                assert set(progress["private_rank"]) == {
                    "cohort", "position", "cohort_size", "percentile",
                }
    public = next(event for event in report["events"] if event["name"] == "no_public_leaderboard")
    assert public["http_status"] == 404


def test_demo_repeatable_after_repository_reset_and_output_is_labeled(report: dict) -> None:
    state_repository.reset()
    with TestClient(app) as client:
        assert run_demo(client) == report
    assert report["synthetic"] is True
    assert report["precision_measured"] is False
    text = format_report(report)
    assert "Синтетическое" in text
    assert "Precision/FPR не измерены" in text
    assert "status=not_qualified" in text
    assert "reward XP=20+20" in text
    assert "status=pending_review score=0.75 reasons=shared_device_hash" in text
    assert "rank=cooking_households:2/3" in text
    assert "rank=cooking_households:1/3" in text


def test_demo_cli_is_a_separate_process_and_preserves_existing_state() -> None:
    # A running backend's process-local state must not be replaced or reset by
    # the standalone demo, even when its synthetic IDs happen to overlap.
    with TestClient(app) as client:
        first = client.post(RECEIPTS, json=receipt_event(INVITEE))
        assert first.status_code == 200
        before = client.get(f"/api/v1/progress/{INVITEE}").json()
        output = subprocess.run(
            [sys.executable, "-m", "scripts.safety_demo", "--json"],
            cwd=Path(__file__).resolve().parents[1],
            check=True, capture_output=True, text=True, timeout=60,
        )
        evidence = json.loads(output.stdout)
        assert responses(evidence)["referral_before_purchase"]["status"] == "not_qualified"
        assert responses(evidence)["referral_approved"]["invitee_progress"]["avatar_xp"] == 20
        assert client.get(f"/api/v1/progress/{INVITEE}").json() == before
        assert client.get(f"/api/v1/progress/{INVITER}").json()["avatar_xp"] == 0
