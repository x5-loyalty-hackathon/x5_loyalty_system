from __future__ import annotations

from app.contracts import (
    ReferralEvaluationRequest,
    ReferralEvaluationResponse,
    ReferralReward,
    ReferralStatus,
)
from app.fraud import ReferralFraudPolicy
from app.state import InMemoryStateRepository


class ReferralService:
    def __init__(
        self,
        *,
        repository: InMemoryStateRepository,
        fraud_policy: ReferralFraudPolicy,
    ) -> None:
        self._repository = repository
        self._fraud_policy = fraud_policy

    def evaluate(
        self,
        request: ReferralEvaluationRequest,
    ) -> ReferralEvaluationResponse:
        decision = self._fraud_policy.evaluate(
            request=request,
            existing_inviter=self._repository.get_referral_inviter(
                request.invitee_user_id
            ),
        )
        reward = ReferralReward()

        if decision.status == ReferralStatus.APPROVED:
            if self._repository.purchase_days(request.invitee_user_id) < 1:
                return self._response(
                    request=request,
                    status=ReferralStatus.NOT_QUALIFIED,
                    fraud_score=decision.score,
                    reason_codes=["invitee_has_no_verified_purchase_day"],
                    reward=ReferralReward(inviter_xp=0, invitee_xp=0),
                )

            outcome = self._repository.award_referral_if_unclaimed(
                inviter_user_id=request.inviter_user_id,
                invitee_user_id=request.invitee_user_id,
            )
            if not outcome.awarded:
                late_decision = self._fraud_policy.evaluate(
                    request=request,
                    existing_inviter=outcome.existing_inviter,
                )
                return self._response(
                    request=request,
                    status=late_decision.status,
                    fraud_score=late_decision.score,
                    reason_codes=late_decision.reason_codes,
                    reward=ReferralReward(inviter_xp=0, invitee_xp=0),
                )
        elif decision.status != ReferralStatus.DUPLICATE:
            reward = ReferralReward(inviter_xp=0, invitee_xp=0)
        else:
            reward = ReferralReward(inviter_xp=0, invitee_xp=0)

        return self._response(
            request=request,
            status=decision.status,
            fraud_score=decision.score,
            reason_codes=decision.reason_codes,
            reward=reward,
        )

    def _response(
        self,
        *,
        request: ReferralEvaluationRequest,
        status: ReferralStatus,
        fraud_score: float,
        reason_codes: list[str],
        reward: ReferralReward,
    ) -> ReferralEvaluationResponse:
        return ReferralEvaluationResponse(
            status=status,
            fraud_score=fraud_score,
            reason_codes=reason_codes,
            reward=reward,
            inviter_progress=self._repository.snapshot(request.inviter_user_id),
            invitee_progress=self._repository.snapshot(request.invitee_user_id),
        )
