from __future__ import annotations

from app.contracts import (
    CookingConfirmationRequest,
    MealPlanCompletionResponse,
    MealPlanSaveRequest,
    MealPlanSaveResponse,
)
from app.state import InMemoryStateRepository


class MealPlanService:
    def __init__(self, *, repository: InMemoryStateRepository) -> None:
        self._repository = repository

    def save(self, request: MealPlanSaveRequest) -> MealPlanSaveResponse:
        outcome = self._repository.save_meal_plan(request)
        return MealPlanSaveResponse(
            status=outcome.status,
            reason_codes=list(outcome.reason_codes),
            plan=outcome.plan,
            progress=self._repository.snapshot(request.user_id),
        )

    def confirm_cooking(
        self,
        *,
        plan_id: str,
        request: CookingConfirmationRequest,
    ) -> MealPlanCompletionResponse:
        outcome = self._repository.confirm_cook_plan(
            plan_id=plan_id,
            user_id=request.user_id,
            now=request.now,
        )
        return MealPlanCompletionResponse(
            status=outcome.status,
            reason_codes=list(outcome.reason_codes),
            plan=outcome.plan,
            progress=self._repository.snapshot(request.user_id),
        )
