from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from threading import RLock
from zoneinfo import ZoneInfo
from uuid import uuid4

from app.contracts import (
    FulfillmentOption,
    MealPlanCompletionStatus,
    MealPlanSaveRequest,
    MealPlanSaveStatus,
    MealPlanSnapshot,
    MealPlanStatus,
    MealRoute,
    MealReward,
    MealRewardStatus,
    MealRecommendationResponse,
    PrivateRank,
    ProgressSnapshot,
    RankCohort,
    Receipt,
    RecommendationRequest,
    SavedRecipeStatus,
)
from app.meal_offer import IssuedMealOffer


XP_PER_RECIPE = 20
XP_PER_REFERRAL_REWARD = 20
XP_PER_LEVEL = 50
BUSINESS_TIMEZONE = ZoneInfo("Europe/Moscow")


@dataclass
class UserProgressRecord:
    user_id: str
    rank_cohort: RankCohort = RankCohort.COOKING_HOUSEHOLDS
    verified_receipts: int = 0
    purchase_dates: set[date] = field(default_factory=set)
    meals_completed: int = 0
    recipes_completed: int = 0
    ready_meals_completed: int = 0
    markdown_savings: float = 0.0
    rescue_items: float = 0.0
    referral_rewards: int = 0
    meal_rewards: dict[date, str] = field(default_factory=dict)

    @property
    def avatar_xp(self) -> int:
        return (
            len(self.meal_rewards) * XP_PER_RECIPE
            + self.referral_rewards * XP_PER_REFERRAL_REWARD
        )


@dataclass
class MealPlanRecord:
    request: MealPlanSaveRequest
    offer: IssuedMealOffer
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
    anchor_receipt_id: str | None = None
    awarded_xp: int = 0
    collection_receipt_matches: dict[str, set[str]] = field(default_factory=dict)


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


@dataclass(frozen=True)
class SavedRecipeOutcome:
    status: SavedRecipeStatus
    saved_recipe_ids: tuple[str, ...]


class InMemoryStateRepository:
    """Demo-only state. Replace with a persistent adapter without changing APIs."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._users: dict[str, UserProgressRecord] = {}
        self._receipt_owners: dict[str, str] = {}
        self._receipt_plan_ids: dict[str, set[str]] = {}
        self._verified_receipts: dict[str, Receipt] = {}
        self._meal_offers: dict[str, IssuedMealOffer] = {}
        self._referral_inviter_by_invitee: dict[str, str] = {}
        self._meal_plans: dict[str, MealPlanRecord] = {}
        self._saved_recipe_ids_by_user: dict[str, set[str]] = {}

    def reset(self) -> None:
        with self._lock:
            self._users.clear()
            self._receipt_owners.clear()
            self._receipt_plan_ids.clear()
            self._verified_receipts.clear()
            self._meal_offers.clear()
            self._referral_inviter_by_invitee.clear()
            self._meal_plans.clear()
            self._saved_recipe_ids_by_user.clear()

    def save_recipe(self, *, user_id: str, recipe_id: str) -> SavedRecipeOutcome:
        """Idempotently add a recipe to the demo recipe book; awards no XP."""
        with self._lock:
            saved = self._saved_recipe_ids_by_user.setdefault(user_id, set())
            status = (
                SavedRecipeStatus.DUPLICATE
                if recipe_id in saved
                else SavedRecipeStatus.CREATED
            )
            saved.add(recipe_id)
            return SavedRecipeOutcome(
                status=status,
                saved_recipe_ids=tuple(sorted(saved)),
            )

    def saved_recipe_ids(self, user_id: str) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._saved_recipe_ids_by_user.get(user_id, set())))

    def issue_meal_offers(
        self, request: RecommendationRequest, response: MealRecommendationResponse,
    ) -> MealRecommendationResponse:
        with self._lock:
            meals = []
            for meal in response.recommendations:
                offered = meal.model_copy(update={"offer_id": str(uuid4())}, deep=True)
                self._meal_offers[offered.offer_id] = IssuedMealOffer(
                    user_id=request.user.user_id, issued_at=request.now,
                    meal=offered.model_copy(deep=True),
                    current_receipt=request.current_receipt.model_copy(deep=True),
                )
                meals.append(offered)
            return response.model_copy(update={"recommendations": meals})

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
                if existing.request != request:
                    return MealPlanSaveOutcome(
                        status=MealPlanSaveStatus.REJECTED,
                        reason_codes=("meal_plan_payload_mismatch",), plan=None,
                    )
                return MealPlanSaveOutcome(
                    status=MealPlanSaveStatus.DUPLICATE,
                    reason_codes=("meal_plan_already_saved",),
                    plan=self._meal_plan_snapshot(existing),
                )

            offer = self._meal_offers.get(request.offer_id)
            error = offer.selection_error(request) if offer else "meal_offer_not_found"
            if error:
                return MealPlanSaveOutcome(
                    status=MealPlanSaveStatus.REJECTED, reason_codes=(error,), plan=None,
                )
            plan = MealPlanRecord(
                request=request.model_copy(deep=True), offer=offer,
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
            if plan.selected_route == MealRoute.COOK and not plan.selected_product_ids:
                plan.status = MealPlanStatus.COLLECTED
            # The only pre-plan receipt allowed is the exact verified current
            # receipt bound to this issued offer. History/IDs alone prove nothing.
            current = self._verified_receipts.get(offer.current_receipt.receipt_id)
            if (current == offer.current_receipt
                    and self._receipt_owners.get(current.receipt_id) == plan.user_id
                    and current.purchased_at <= offer.issued_at):
                self._apply_plan_receipt(plan, current)
            return MealPlanSaveOutcome(
                status=MealPlanSaveStatus.CREATED,
                reason_codes=("meal_plan_saved",),
                plan=self._meal_plan_snapshot(plan),
            )

    def get_receipt_owner(self, receipt_id: str) -> str | None:
        with self._lock:
            return self._receipt_owners.get(receipt_id)

    def receipt_plan_snapshot(
        self, *, user_id: str, receipt_id: str, plan_id: str | None,
    ) -> MealPlanSnapshot | None:
        """Recover only a server-associated, owned plan; never replay evidence."""
        with self._lock:
            if self._receipt_owners.get(receipt_id) != user_id:
                return None
            if plan_id not in self._receipt_plan_ids.get(receipt_id, set()):
                return None
            plan = self._meal_plans.get(plan_id)
            if plan is None or plan.user_id != user_id:
                return None
            return self._meal_plan_snapshot(plan)

    def record_receipt(
        self,
        *,
        user_id: str,
        receipt: Receipt,
        recipe_completed: bool,
        meal_plan_id: str | None = None,
        rank_cohort: RankCohort = RankCohort.COOKING_HOUSEHOLDS,
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
            if record.verified_receipts == 0:
                # In production this cohort comes from a trusted segmentation
                # job, not from a public client. The event field is synthetic
                # PoC plumbing so unlike populations are not ranked together.
                record.rank_cohort = rank_cohort
            self._receipt_owners[receipt.receipt_id] = user_id
            self._verified_receipts[receipt.receipt_id] = receipt.model_copy(deep=True)
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
            elif (plan is not None and receipt.purchased_at < plan.created_at
                  and not self._is_bound_current_receipt(plan, receipt)):
                # The receipt remains a legitimate purchase event, but cannot
                # provide evidence for a plan that did not exist yet.
                meal_plan_reason_codes.append("receipt_predates_meal_plan")
                plan_snapshot = self._meal_plan_snapshot(plan)
                plan = None
            if plan is not None and plan.status != MealPlanStatus.COMPLETED:
                self._apply_plan_receipt(plan, receipt)
                if plan.selected_route == MealRoute.READY:
                    if recipe_completed:
                        meal_plan_reason_codes.append(
                            "ready_plan_cannot_be_manually_completed"
                        )
                    if plan.status == MealPlanStatus.COMPLETED:
                        meal_plan_reason_codes.append("ready_meal_plan_completed")
                    else:
                        meal_plan_reason_codes.append("ready_meal_not_matched")
                else:
                    if plan.status == MealPlanStatus.COLLECTED:
                        meal_plan_reason_codes.append("cook_ingredients_collected")
                    if recipe_completed:
                        meal_plan_reason_codes.append(
                            "cook_completion_requires_confirmation_endpoint"
                        )
            elif meal_plan_id is None and recipe_completed:
                # Kept as a readable legacy input, never as a reward/completion
                # authority. An explicitly selected issued meal plan is required.
                meal_plan_reason_codes.append("legacy_completion_ignored")

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
            self._award_meal(plan)
            return MealPlanCompletionOutcome(
                status=MealPlanCompletionStatus.COMPLETED,
                reason_codes=("cook_meal_plan_completed",),
                plan=self._meal_plan_snapshot(plan),
            )

    @staticmethod
    def _is_bound_current_receipt(plan: MealPlanRecord, receipt: Receipt) -> bool:
        return (receipt == plan.offer.current_receipt
                and receipt.purchased_at <= plan.offer.issued_at)

    def _apply_plan_receipt(self, plan: MealPlanRecord, receipt: Receipt) -> None:
        """Called only with owned verified evidence, under the repository lock."""
        self._receipt_plan_ids.setdefault(receipt.receipt_id, set()).add(plan.plan_id)
        selected = plan.offer.selected_products(plan.request)
        is_ready = plan.selected_route == MealRoute.READY
        matched = {
            item.sku_id for item in receipt.items
            if item.sku_id in selected
            and item.is_prepared_food == is_ready
            and selected[item.sku_id].store_id == receipt.store_id
        }
        plan.collected_product_ids.update(matched)
        if matched:
            plan.collection_receipt_matches[receipt.receipt_id] = matched
        current_evidence = (
            not is_ready and self._is_bound_current_receipt(plan, receipt)
            and any(not item.is_prepared_food and
                    bool(item.ingredient_ids & plan.offer.required_ingredient_ids())
                    for item in receipt.items)
        )
        collected = plan.selected_product_ids <= plan.collected_product_ids
        if collected and plan.selected_product_ids:
            # Canonical earliest purchase-time prefix covering the basket.
            # Keep overlapping evidence too: an older full receipt can make a
            # later partial receipt unnecessary, regardless of arrival order.
            covered: set[str] = set()
            for receipt_id in sorted(plan.collection_receipt_matches, key=lambda rid: (
                self._verified_receipts[rid].purchased_at, rid,
            )):
                covered.update(plan.collection_receipt_matches[receipt_id])
                if plan.selected_product_ids <= covered:
                    plan.anchor_receipt_id = receipt_id
                    break
        elif collected and current_evidence:
            plan.anchor_receipt_id = receipt.receipt_id
        if is_ready and collected:
            plan.status = MealPlanStatus.COMPLETED
            plan.completed_at = max(plan.created_at, receipt.purchased_at)
            plan.completion_evidence = f"verified_receipt:{receipt.receipt_id}"
            record = self._get_or_create(plan.user_id)
            record.meals_completed += 1
            record.ready_meals_completed += 1
            self._award_meal(plan)
        elif not is_ready and collected:
            plan.status = MealPlanStatus.COLLECTED

    def _meal_reward(self, plan: MealPlanRecord) -> MealReward:
        receipt = self._verified_receipts.get(plan.anchor_receipt_id)
        purchase_day = (receipt.purchased_at.astimezone(BUSINESS_TIMEZONE).date()
                        if receipt is not None else None)
        if plan.awarded_xp:
            return MealReward(status=MealRewardStatus.AWARDED, xp=plan.awarded_xp,
                              purchase_day=purchase_day)
        if purchase_day is None:
            waiting = bool(plan.selected_product_ids - plan.collected_product_ids)
            return MealReward(status=(MealRewardStatus.AWAITING_PURCHASE if waiting
                                      else MealRewardStatus.NO_PURCHASE_EVIDENCE), xp=0)
        used = purchase_day in self._get_or_create(plan.user_id).meal_rewards
        return MealReward(
            status=(MealRewardStatus.PURCHASE_DAY_REWARD_USED if used else MealRewardStatus.AVAILABLE),
            xp=0 if used else XP_PER_RECIPE, purchase_day=purchase_day,
        )

    def _award_meal(self, plan: MealPlanRecord) -> None:
        if plan.status != MealPlanStatus.COMPLETED:
            return
        reward = self._meal_reward(plan)
        if reward.status == MealRewardStatus.AVAILABLE:
            self._get_or_create(plan.user_id).meal_rewards[reward.purchase_day] = plan.plan_id
            plan.awarded_xp = XP_PER_RECIPE

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
            cohort = [
                other
                for other in cohort
                if other.rank_cohort == record.rank_cohort
            ]
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
                rewarded_meals=len(record.meal_rewards),
                avatar_xp=record.avatar_xp,
                avatar_level=level,
                xp_to_next_level=xp_to_next_level,
                private_rank=PrivateRank(
                    cohort=record.rank_cohort,
                    position=position,
                    cohort_size=cohort_size,
                    percentile=percentile,
                ),
            )

    def _get_or_create(self, user_id: str) -> UserProgressRecord:
        return self._users.setdefault(user_id, UserProgressRecord(user_id=user_id))

    def _meal_plan_snapshot(self, plan: MealPlanRecord) -> MealPlanSnapshot:
        return MealPlanSnapshot(
            offer_id=plan.request.offer_id,
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
            reward=self._meal_reward(plan),
        )
