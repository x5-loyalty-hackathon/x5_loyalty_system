from __future__ import annotations

from app.contracts import (
    KitchenSnapshot,
    ProgressSnapshot,
    RecipeCompletionRequest,
    RecipeCompletionResponse,
    ReceiptEventStatus,
    ReceiptProgressRequest,
    ReceiptProgressResponse,
)
from app.fraud import ReceiptFraudPolicy
from app.state import InMemoryStateRepository


class ProgressService:
    def __init__(
        self,
        *,
        repository: InMemoryStateRepository,
        fraud_policy: ReceiptFraudPolicy,
    ) -> None:
        self._repository = repository
        self._fraud_policy = fraud_policy

    def process_receipt(
        self,
        request: ReceiptProgressRequest,
    ) -> ReceiptProgressResponse:
        decision = self._fraud_policy.evaluate(
            request=request,
            existing_owner=self._repository.get_receipt_owner(
                request.receipt.receipt_id
            ),
        )
        if decision.status != ReceiptEventStatus.VERIFIED:
            return ReceiptProgressResponse(
                status=decision.status,
                fraud_score=decision.score,
                reason_codes=decision.reason_codes,
                progress=self._repository.snapshot(request.user_id),
            )

        outcome = self._repository.record_receipt(
            user_id=request.user_id,
            receipt=request.receipt,
            recipe_completed=request.recipe_completed,
        )
        if not outcome.recorded:
            late_decision = self._fraud_policy.evaluate(
                request=request,
                existing_owner=outcome.existing_owner,
            )
            return ReceiptProgressResponse(
                status=late_decision.status,
                fraud_score=late_decision.score,
                reason_codes=late_decision.reason_codes,
                progress=self._repository.snapshot(request.user_id),
            )

        reason_codes = list(decision.reason_codes)
        if not outcome.is_new_purchase_day:
            reason_codes.append("same_day_receipt_collapsed")

        return ReceiptProgressResponse(
            status=ReceiptEventStatus.VERIFIED,
            fraud_score=decision.score,
            reason_codes=reason_codes,
            progress=self._repository.snapshot(request.user_id),
        )

    def get_progress(self, user_id: str) -> ProgressSnapshot:
        return self._repository.snapshot(user_id)

    def get_kitchen(self, user_id: str) -> KitchenSnapshot:
        return self._repository.kitchen_snapshot(user_id)

    def complete_recipe(
        self, request: RecipeCompletionRequest
    ) -> RecipeCompletionResponse:
        outcome = self._repository.complete_recipe(
            completion_id=request.completion_id,
            user_id=request.user_id,
            recipe_id=request.recipe_id,
            ingredient_ids=request.ingredient_ids,
        )
        return RecipeCompletionResponse(
            status=outcome.status,
            reason_codes=list(outcome.reason_codes),
            kitchen=self._repository.kitchen_snapshot(request.user_id),
            progress=self._repository.snapshot(request.user_id),
        )
