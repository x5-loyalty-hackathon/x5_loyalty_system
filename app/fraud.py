from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.contracts import (
    ReceiptEventStatus,
    ReceiptProgressRequest,
    ReferralEvaluationRequest,
    ReferralStatus,
)
from app.referral_codes import verify_invite_code


RECEIPT_FUTURE_TOLERANCE = timedelta(minutes=5)
REFERRAL_REVIEW_THRESHOLD = 0.7
REFERRAL_BLOCK_THRESHOLD = 0.95


@dataclass(frozen=True)
class ReceiptFraudDecision:
    status: ReceiptEventStatus
    score: float
    reason_codes: list[str]


@dataclass(frozen=True)
class ReferralFraudDecision:
    status: ReferralStatus
    score: float
    reason_codes: list[str]


class ReceiptFraudPolicy:
    def evaluate(
        self,
        *,
        request: ReceiptProgressRequest,
        existing_owner: str | None,
    ) -> ReceiptFraudDecision:
        if existing_owner == request.user_id:
            return ReceiptFraudDecision(
                ReceiptEventStatus.DUPLICATE,
                0.0,
                ["receipt_already_processed"],
            )
        if existing_owner is not None:
            return ReceiptFraudDecision(
                ReceiptEventStatus.REJECTED,
                1.0,
                ["receipt_claimed_by_another_user"],
            )
        if request.receipt.purchased_at > request.now + RECEIPT_FUTURE_TOLERANCE:
            return ReceiptFraudDecision(
                ReceiptEventStatus.PENDING_REVIEW,
                0.8,
                ["receipt_timestamp_in_future"],
            )
        return ReceiptFraudDecision(
            ReceiptEventStatus.VERIFIED,
            0.0,
            ["receipt_verified"],
        )


class ReferralFraudPolicy:
    def evaluate(
        self,
        *,
        request: ReferralEvaluationRequest,
        existing_inviter: str | None,
    ) -> ReferralFraudDecision:
        if request.inviter_user_id == request.invitee_user_id:
            return ReferralFraudDecision(
                ReferralStatus.REJECTED,
                1.0,
                ["self_referral"],
            )
        # Code ownership is independent of shared-device/payment signals.
        if not verify_invite_code(request.invite_code, request.inviter_user_id):
            return ReferralFraudDecision(
                ReferralStatus.REJECTED,
                1.0,
                ["invite_code_does_not_match_inviter"],
            )
        if existing_inviter == request.inviter_user_id:
            return ReferralFraudDecision(
                ReferralStatus.DUPLICATE,
                0.0,
                ["referral_already_rewarded"],
            )
        if existing_inviter is not None:
            return ReferralFraudDecision(
                ReferralStatus.REJECTED,
                1.0,
                ["invitee_already_attributed"],
            )

        signals: list[tuple[str, float]] = []
        if (
            request.inviter_device_hash is not None
            and request.inviter_device_hash == request.invitee_device_hash
        ):
            signals.append(("shared_device_hash", 0.75))
        if (
            request.inviter_payment_hash is not None
            and request.inviter_payment_hash == request.invitee_payment_hash
        ):
            signals.append(("shared_payment_hash", 0.8))

        score = max((weight for _, weight in signals), default=0.0)
        reason_codes = [reason for reason, _ in signals]
        if score >= REFERRAL_BLOCK_THRESHOLD:
            return ReferralFraudDecision(
                ReferralStatus.REJECTED,
                score,
                reason_codes,
            )
        if score >= REFERRAL_REVIEW_THRESHOLD:
            return ReferralFraudDecision(
                ReferralStatus.PENDING_REVIEW,
                score,
                reason_codes,
            )
        return ReferralFraudDecision(
            ReferralStatus.APPROVED,
            score,
            reason_codes or ["no_high_precision_fraud_signal"],
        )
