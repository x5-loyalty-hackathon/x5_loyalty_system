"""Reproducible synthetic safety flow through the actual FastAPI handlers.

Run from the checkout with ``python -m scripts.safety_demo [--json]``.
The CLI uses its own process-local repository; it never contacts a server.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.referral_codes import issue_invite_code


INVITER = "safety-demo-inviter"
INVITEE = "safety-demo-invitee"
COOK_PEER = "safety-demo-cook-peer"
READY_PEER = "safety-demo-ready-peer"
READY_FRIEND = "safety-demo-ready-friend"
REVIEW_INVITEE = "safety-demo-review-invitee"

RECEIPTS = "/api/v1/events/receipts"
REFERRALS = "/api/v1/referrals/evaluate"


def receipt_event(user_id: str, *, cohort: str = "cooking_households") -> dict:
    """Fixed synthetic inputs; the API computes verification and progress."""
    return {
        "user_id": user_id,
        "rank_cohort": cohort,
        "receipt": {
            "receipt_id": f"receipt-{user_id}",
            "purchased_at": "2026-09-03T12:00:00+03:00",
            "store_id": "safety-demo-store",
            "items": [{
                "sku_id": "safety-demo-milk",
                "name": "Молоко (синтетический пример)",
                "category": "dairy",
                "ingredient_ids": ["milk"],
                "quantity": 1,
                "unit_price": 50,
                "is_markdown": True,
                "original_unit_price": 100,
            }],
        },
        "now": "2026-09-03T12:05:00+03:00",
    }


def referral_request(inviter: str, invitee: str) -> dict:
    return {
        "inviter_user_id": inviter,
        "invitee_user_id": invitee,
        "invite_code": issue_invite_code(inviter),
    }


def run_demo(client: TestClient) -> dict[str, Any]:
    """Exercise a fresh test repository and return unmodified API responses.

    Callers in tests own repository reset/isolation. This function deliberately
    does not clear or replace an existing application repository.
    """
    events: list[dict[str, Any]] = []

    def call(
        name: str,
        path: str,
        payload: dict | None = None,
        *,
        setup: bool = False,
        expected_http: int = 200,
    ) -> dict:
        method = "GET" if payload is None else "POST"
        response = client.request(method, path, json=payload)
        if response.status_code != expected_http:
            raise RuntimeError(
                f"{name}: HTTP {response.status_code}: {response.text}"
            )
        body = response.json()
        events.append({
            "name": name,
            "phase": "setup" if setup else "demo",
            "method": method,
            "path": path,
            "request": deepcopy(payload),
            "http_status": response.status_code,
            "response": body,
        })
        return body

    # Establish comparison cohorts and XP using the same receipt/referral HTTP
    # paths as the demo. A ready-heavy peer has more XP than every cooking peer.
    for user_id, cohort in (
        (INVITER, "cooking_households"),
        (COOK_PEER, "cooking_households"),
        (READY_PEER, "ready_heavy"),
        (READY_FRIEND, "ready_heavy"),
    ):
        call(
            f"seed_receipt_{user_id}", RECEIPTS,
            receipt_event(user_id, cohort=cohort), setup=True,
        )
    call(
        "seed_cooking_peer_reward", REFERRALS,
        referral_request(COOK_PEER, READY_PEER), setup=True,
    )
    call(
        "seed_ready_peer_reward", REFERRALS,
        referral_request(READY_PEER, READY_FRIEND), setup=True,
    )

    referral = referral_request(INVITER, INVITEE)
    first_purchase = receipt_event(INVITEE)
    call("referral_before_purchase", REFERRALS, referral)
    call("first_purchase_no_passive_xp", RECEIPTS, first_purchase)
    call("private_rank_before_reward", f"/api/v1/progress/{INVITER}")
    call("referral_approved", REFERRALS, referral)
    call("private_rank_after_reward", f"/api/v1/progress/{INVITER}")
    call("separate_ready_cohort", f"/api/v1/progress/{READY_PEER}")
    call("referral_duplicate", REFERRALS, referral)
    call("receipt_duplicate", RECEIPTS, first_purchase)
    call("self_referral", REFERRALS, referral_request(INVITER, INVITER))

    replay = deepcopy(first_purchase)
    replay["user_id"] = INVITER
    call("cross_user_receipt_replay", RECEIPTS, replay)

    wrong_owner = referral_request(INVITER, INVITER)
    wrong_owner["inviter_user_id"] = COOK_PEER
    call("invite_code_owner_mismatch", REFERRALS, wrong_owner)

    call(
        "review_invitee_purchase", RECEIPTS,
        receipt_event(REVIEW_INVITEE, cohort="ready_heavy"),
    )
    for name, signals in (
        ("shared_device_review", {
            "inviter_device_hash": "synthetic-shared-device",
            "invitee_device_hash": "synthetic-shared-device",
        }),
        ("shared_payment_review", {
            "inviter_payment_hash": "synthetic-shared-payment",
            "invitee_payment_hash": "synthetic-shared-payment",
        }),
        ("shared_device_and_payment_review", {
            "inviter_device_hash": "synthetic-shared-device",
            "invitee_device_hash": "synthetic-shared-device",
            "inviter_payment_hash": "synthetic-shared-payment",
            "invitee_payment_hash": "synthetic-shared-payment",
        }),
    ):
        call(
            name, REFERRALS,
            referral_request(INVITER, REVIEW_INVITEE) | signals,
        )

    future_receipt = receipt_event(REVIEW_INVITEE, cohort="ready_heavy")
    future_receipt["receipt"]["receipt_id"] = "safety-demo-future-receipt"
    future_receipt["receipt"]["purchased_at"] = "2026-09-04T12:00:00+03:00"
    call("future_receipt_review", RECEIPTS, future_receipt)
    call("no_public_leaderboard", "/api/v1/leaderboard", expected_http=404)

    return {
        "synthetic": True,
        "transport": "FastAPI TestClient, isolated CLI process, no external server",
        "precision_measured": False,
        "limitations": [
            "Synthetic receipt JSON is not a real till integration or production authentication.",
            "Fraud scores are policy weights, not calibrated fraud probabilities.",
            "No labeled real-world sample: precision and false-positive rate are unmeasured.",
            "Cohorts are synthetic inputs; equal XP can share the same rank.",
        ],
        "events": events,
    }


def format_report(report: dict[str, Any]) -> str:
    """Compact rendering of response fields; no replacement result snapshots."""
    setup = [event for event in report["events"] if event["phase"] == "setup"]
    lines = [
        "Синтетическое safety-demo: реальные FastAPI HTTP handlers, локальный TestClient.",
        "Precision/FPR не измерены; fraud_score — вес правил, не вероятность.",
        f"Подготовка: {len(setup)} HTTP-событий; полные запросы и ответы доступны с --json.",
    ]
    for event in report["events"]:
        if event["phase"] == "setup":
            continue
        body = event["response"]
        line = f"{event['name']}: HTTP {event['http_status']}"
        if "status" in body:
            line += (
                f" status={body['status']} score={body['fraud_score']:g}"
                f" reasons={','.join(body['reason_codes'])}"
            )
        if "reward" in body:
            reward = body["reward"]
            line += (
                f"; reward XP={reward['inviter_xp']}+{reward['invitee_xp']}"
                f"; total XP={body['inviter_progress']['avatar_xp']}"
                f"/{body['invitee_progress']['avatar_xp']}"
                f"; invitee days={body['invitee_progress']['purchase_days']}"
            )
        else:
            progress = body.get("progress", body)
            if "avatar_xp" in progress:
                rank = progress["private_rank"]
                line += (
                    f"; XP={progress['avatar_xp']}"
                    f" receipts={progress['verified_receipts']}"
                    f" days={progress['purchase_days']}"
                    f"; rank={rank['cohort']}:{rank['position']}/{rank['cohort_size']}"
                    f" percentile={rank['percentile']:g}"
                )
            elif "detail" in body:
                line += f" {body['detail']}"
        lines.append(line)
    lines.append(
        "Равные XP делят место. private_rank содержит только личную позицию и агрегаты когорты."
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print complete API request/response evidence")
    args = parser.parse_args()
    with TestClient(app) as client:
        report = run_demo(client)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))


if __name__ == "__main__":
    main()
