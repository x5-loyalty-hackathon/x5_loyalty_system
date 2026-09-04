from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from threading import RLock
from zoneinfo import ZoneInfo

from app.contracts import (
    FulfillmentOption,
    MealPlanCompletionStatus,
    MealPlanSaveRequest,
    MealPlanSaveStatus,
    MealPlanSnapshot,
    MealPlanStatus,
    MealRoute,
    PrivateRank,
    ProgressSnapshot,
    Receipt,
)


XP_PER_PURCHASE_DAY = 10
XP_PER_RECIPE = 20
XP_PER_REFERRAL_REWARD = 10
XP_PER_LEVEL = 50
BUSINESS_TIMEZONE = ZoneInfo("Europe/Moscow")


@dataclass
class UserProgressRecord:
    user_id: str
    verified_receipts: int = 0
    purchase_dates: set[date] = field(default_factory=set)
    meals_completed: int = 0
    recipes_completed: int = 0
    ready_meals_completed: int = 0
    markdown_savings: float = 0.0
    rescue_items: float = 0.0
    referral_rewards: int = 0

    @property
    def avatar_xp(self) -> int:
        return (
            len(self.purchase_dates) * XP_PER_PURCHASE_DAY
            + self.meals_completed * XP_PER_RECIPE
            + self.referral_rewards * XP_PER_REFERRAL_REWARD
        )


@dataclass
class MealPlanRecord:
    plan_id: str
    user_id: str
    meal_id: str
    selected_route: MealRoute
    status: MealPlanStatus
    selected_recipe_id: str | None
    selected_product_ids: set[str]
    collected_product_ids: set[str]
    fulfillment: FulfillmentOption
    created_at: datetime
    completed_at: datetime | None = None
    completion_evidence: str | None = None


@dataclass(frozen=True)
class ReceiptRecordOutcome:
    recorded: bool
    existing_owner: str | None
    is_new_purchase_day: bool = False
    meal_plan: MealPlanSnapshot | None = None
    meal_plan_reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferralAwardOutcome:
    awarded: bool
    existing_inviter: str | None


@dataclass(frozen=True)
class MealPlanSaveOutcome:
    status: MealPlanSaveStatus
    reason_codes: tuple[str, ...]
    plan: MealPlanSnapshot | None


@dataclass(frozen=True)
class MealPlanCompletionOutcome:
    status: MealPlanCompletionStatus
    reason_codes: tuple[str, ...]
    plan: MealPlanSnapshot | None


class InMemoryStateRepository:
    """Demo-only state. Replace with a persistent adapter without changing APIs."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._users: dict[str, UserProgressRecord] = {}
        self._receipt_owners: dict[str, str] = {}
        self._referral_inviter_by_invitee: dict[str, str] = {}
        self._meal_plans: dict[str, MealPlanRecord] = {}

    def reset(self) -> None:
        with self._lock:
            self._users.clear()
            self._receipt_owners.clear()
            self._referral_inviter_by_invitee.clear()
            self._meal_plans.clear()

    def save_meal_plan(self, request: MealPlanSaveRequest) -> MealPlanSaveOutcome:
        with self._lock:
            existing = self._meal_plans.get(request.plan_id)
            if existing is not None:
                if existing.user_id != request.user_id:
                    return MealPlanSaveOutcome(
                        status=MealPlanSaveStatus.REJECTED,
                        reason_codes=("meal_plan_claimed_by_another_user",),
                        plan=None,
                    )
                return MealPlanSaveOutcome(
                    status=MealPlanSaveStatus.DUPLICATE,
                    reason_codes=("meal_plan_already_saved",),
                    plan=self._meal_plan_snapshot(existing),
                )

            plan = MealPlanRecord(
                plan_id=request.plan_id,
                user_id=request.user_id,
                meal_id=request.meal_id,
                selected_route=request.selected_route,
                status=MealPlanStatus.SAVED,
                selected_recipe_id=request.selected_recipe_id,
                selected_product_ids=set(request.selected_product_ids),
                collected_product_ids=set(),
                fulfillment=request.fulfillment,
                created_at=request.created_at,
            )
            self._meal_plans[plan.plan_id] = plan
            return MealPlanSaveOutcome(
                status=MealPlanSaveStatus.CREATED,
                reason_codes=("meal_plan_saved",),
                plan=self._meal_plan_snapshot(plan),
            )

    def get_receipt_owner(self, receipt_id: str) -> str | None:
        with self._lock:
            return self._receipt_owners.get(receipt_id)

    def record_receipt(
        self,
        *,
        user_id: str,
        receipt: Receipt,
        recipe_completed: bool,
        meal_plan_id: str | None = None,
    ) -> ReceiptRecordOutcome:
        """Atomically claim and record a receipt for idempotent processing."""
        with self._lock:
            existing_owner = self._receipt_owners.get(receipt.receipt_id)
            if existing_owner is not None:
                return ReceiptRecordOutcome(
                    recorded=False,
                    existing_owner=existing_owner,
                )

            record = self._get_or_create(user_id)
            self._receipt_owners[receipt.receipt_id] = user_id
            record.verified_receipts += 1
            purchase_date = receipt.purchased_at.astimezone(BUSINESS_TIMEZONE).date()
            is_new_purchase_day = purchase_date not in record.purchase_dates
            record.purchase_dates.add(purchase_date)
            meal_plan_reason_codes: list[str] = []
            plan = self._meal_plans.get(meal_plan_id) if meal_plan_id else None
            plan_snapshot: MealPlanSnapshot | None = None
            if meal_plan_id is not None and plan is None:
                meal_plan_reason_codes.append("meal_plan_not_found")
            elif plan is not None and plan.user_id != user_id:
                meal_plan_reason_codes.append("meal_plan_owner_mismatch")
                plan = None
            elif plan is not None and plan.status == MealPlanStatus.COMPLETED:
                meal_plan_reason_codes.append("meal_plan_already_completed")
            elif plan is not None and receipt.purchased_at < plan.created_at:
                # The receipt remains a legitimate purchase event, but cannot
                # provide evidence for a plan that did not exist yet.
                meal_plan_reason_codes.append("receipt_predates_meal_plan")
                plan_snapshot = self._meal_plan_snapshot(plan)
                plan = None
            if plan is not None and plan.status != MealPlanStatus.COMPLETED:
                receipt_product_ids = {item.sku_id for item in receipt.items}
                plan.collected_product_ids.update(
                    plan.selected_product_ids & receipt_product_ids
                )
                if plan.selected_route == MealRoute.READY:
                    if recipe_completed:
                        meal_plan_reason_codes.append(
                            "ready_plan_cannot_be_manually_completed"
                        )
                    if plan.collected_product_ids:
                        plan.status = MealPlanStatus.COMPLETED
                        plan.completed_at = receipt.purchased_at
                        plan.completion_evidence = (
                            f"verified_receipt:{receipt.receipt_id}"
                        )
                        record.meals_completed += 1
                        record.ready_meals_completed += 1
                        meal_plan_reason_codes.append("ready_meal_plan_completed")
                    else:
                        meal_plan_reason_codes.append("ready_meal_not_matched")
                else:
                    if plan.selected_product_ids.issubset(
                        plan.collected_product_ids
                    ):
                        plan.status = MealPlanStatus.COLLECTED
                        meal_plan_reason_codes.append("cook_ingredients_collected")
                    if recipe_completed:
                        meal_plan_reason_codes.append(
                            "cook_completion_requires_confirmation_endpoint"
                        )
            elif meal_plan_id is None and recipe_completed:
                record.meals_completed += 1
                record.recipes_completed += 1

            for item in receipt.items:
                if not item.is_markdown:
                    continue
                record.rescue_items += item.quantity
                if item.original_unit_price is not None:
                    record.markdown_savings += (
                        item.original_unit_price - item.unit_price
                    ) * item.quantity
            return ReceiptRecordOutcome(
                recorded=True,
                existing_owner=None,
                is_new_purchase_day=is_new_purchase_day,
                meal_plan=(
                    self._meal_plan_snapshot(plan)
                    if plan is not None
                    else plan_snapshot
                ),
                meal_plan_reason_codes=tuple(meal_plan_reason_codes),
            )

    def confirm_cook_plan(
        self,
        *,
        plan_id: str,
        user_id: str,
        now: datetime,
    ) -> MealPlanCompletionOutcome:
        with self._lock:
            plan = self._meal_plans.get(plan_id)
            if plan is None:
                return MealPlanCompletionOutcome(
                    status=MealPlanCompletionStatus.REJECTED,
                    reason_codes=("meal_plan_not_found",),
                    plan=None,
                )
            if plan.user_id != user_id:
                return MealPlanCompletionOutcome(
                    status=MealPlanCompletionStatus.REJECTED,
                    reason_codes=("meal_plan_owner_mismatch",),
                    plan=None,
                )
            if plan.selected_route != MealRoute.COOK:
                return MealPlanCompletionOutcome(
                    status=MealPlanCompletionStatus.REJECTED,
                    reason_codes=("ready_plan_requires_verified_receipt",),
                    plan=self._meal_plan_snapshot(plan),
                )
            if plan.status == MealPlanStatus.COMPLETED:
                return MealPlanCompletionOutcome(
                    status=MealPlanCompletionStatus.DUPLICATE,
                    reason_codes=("meal_plan_already_completed",),
                    plan=self._meal_plan_snapshot(plan),
                )
            if now < plan.created_at:
                return MealPlanCompletionOutcome(
                    status=MealPlanCompletionStatus.REJECTED,
                    reason_codes=("cooking_confirmation_predates_plan",),
                    plan=self._meal_plan_snapshot(plan),
                )
            if (
                plan.selected_product_ids
                and plan.status != MealPlanStatus.COLLECTED
            ):
                return MealPlanCompletionOutcome(
                    status=MealPlanCompletionStatus.NOT_READY,
                    reason_codes=("cook_ingredients_not_collected",),
                    plan=self._meal_plan_snapshot(plan),
                )

            plan.status = MealPlanStatus.COMPLETED
            plan.completed_at = now
            plan.completion_evidence = "user_cooking_confirmation"
            record = self._get_or_create(user_id)
            record.meals_completed += 1
            record.recipes_completed += 1
            return MealPlanCompletionOutcome(
                status=MealPlanCompletionStatus.COMPLETED,
                reason_codes=("cook_meal_plan_completed",),
                plan=self._meal_plan_snapshot(plan),
            )

    def get_referral_inviter(self, invitee_user_id: str) -> str | None:
        with self._lock:
            return self._referral_inviter_by_invitee.get(invitee_user_id)

    def award_referral_if_unclaimed(
        self,
        *,
        inviter_user_id: str,
        invitee_user_id: str,
    ) -> ReferralAwardOutcome:
        with self._lock:
            existing_inviter = self._referral_inviter_by_invitee.get(
                invitee_user_id
            )
            if existing_inviter is not None:
                return ReferralAwardOutcome(
                    awarded=False,
                    existing_inviter=existing_inviter,
                )

            self._referral_inviter_by_invitee[invitee_user_id] = inviter_user_id
            self._get_or_create(inviter_user_id).referral_rewards += 1
            self._get_or_create(invitee_user_id).referral_rewards += 1
            return ReferralAwardOutcome(
                awarded=True,
                existing_inviter=None,
            )

    def purchase_days(self, user_id: str) -> int:
        with self._lock:
            record = self._users.get(user_id)
            return len(record.purchase_dates) if record is not None else 0

    def snapshot(self, user_id: str) -> ProgressSnapshot:
        with self._lock:
            record = self._users.get(user_id)
            is_ephemeral = record is None
            if record is None:
                record = UserProgressRecord(user_id=user_id)
            cohort = list(self._users.values())
            if is_ephemeral:
                cohort.append(record)
            position = 1 + sum(
                other.avatar_xp > record.avatar_xp for other in cohort
            )
            cohort_size = max(len(cohort), 1)
            percentile = round(
                100 * (cohort_size - position + 1) / cohort_size,
                2,
            )
            level = 1 + record.avatar_xp // XP_PER_LEVEL
            xp_to_next_level = XP_PER_LEVEL - record.avatar_xp % XP_PER_LEVEL
            return ProgressSnapshot(
                user_id=user_id,
                verified_receipts=record.verified_receipts,
                purchase_days=len(record.purchase_dates),
                meals_completed=record.meals_completed,
                recipes_completed=record.recipes_completed,
                ready_meals_completed=record.ready_meals_completed,
                markdown_savings=round(record.markdown_savings, 2),
                rescue_items=round(record.rescue_items, 3),
                referral_rewards=record.referral_rewards,
                avatar_xp=record.avatar_xp,
                avatar_level=level,
                xp_to_next_level=xp_to_next_level,
                private_rank=PrivateRank(
                    position=position,
                    cohort_size=cohort_size,
                    percentile=percentile,
                ),
            )

    def _get_or_create(self, user_id: str) -> UserProgressRecord:
        return self._users.setdefault(user_id, UserProgressRecord(user_id=user_id))

    @staticmethod
    def _meal_plan_snapshot(plan: MealPlanRecord) -> MealPlanSnapshot:
        return MealPlanSnapshot(
            plan_id=plan.plan_id,
            user_id=plan.user_id,
            meal_id=plan.meal_id,
            selected_route=plan.selected_route,
            status=plan.status,
            selected_recipe_id=plan.selected_recipe_id,
            selected_product_ids=sorted(plan.selected_product_ids),
            collected_product_ids=sorted(plan.collected_product_ids),
            fulfillment=plan.fulfillment,
            created_at=plan.created_at,
            completed_at=plan.completed_at,
            completion_evidence=plan.completion_evidence,
        )
