"""Read-only descriptive analytics over the synthetic process-local ledger.

These are event counters, not an exposure funnel or an experiment estimator.
No user ID, receipt ID, item or store detail leaves this API.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from pydantic import Field

from app.contracts import ApiModel, MealRoute, RankCohort
from app.state import BUSINESS_TIMEZONE, InMemoryStateRepository


class MetricsWindow(ApiModel):
    start_date: date
    end_date: date
    timezone: str = "Europe/Moscow"
    inclusive: bool = True
    cohort: RankCohort | None = None


class MetricsCounts(ApiModel):
    observed_event_users: int = 0
    unclassified_event_users: int = 0
    purchasing_users: int = 0
    verified_receipts: int = 0
    purchase_user_days: int = 0
    receipt_amount_rub: float = 0.0
    markdown_savings_rub: float = 0.0
    meal_offers_issued: int = 0
    cook_plans_created: int = 0
    ready_plans_created: int = 0
    cook_plans_completed: int = 0
    ready_plans_completed: int = 0
    rewarded_completed_plans: int = 0
    meal_xp_earned: int = 0


class PurchaseFrequency(ApiModel):
    purchase_threshold: int
    denominator: str = "observed_event_users_in_window"
    receipts_per_observed_user: float | None
    purchase_days_per_observed_user: float | None
    users_at_least_n_receipts: int
    share_at_least_n_receipts: float | None
    users_at_least_n_purchase_days: int
    share_at_least_n_purchase_days: float | None


class MetricsMetadata(ApiModel):
    data_scope: str = "synthetic_process_memory_since_last_reset"
    clock_basis: str = "synthetic_business_timestamps_not_trusted_ingestion_time"
    population_basis: str = "users_with_verified_receipt_or_issued_offer_or_plan_created_or_completed_in_window"
    cohort_basis: str = "current_known_label_from_first_verified_receipt_client_supplied_in_poc"
    limitations: list[str] = Field(default_factory=lambda: [
        "Observed users are not an assigned experiment roster; no ITT or causal uplift.",
        "Issued offers are server outputs, not UI impressions; counters are not a sequential conversion funnel.",
        "Empty recommendation responses and recipe-book-only actions have no dated ledger entry and do not add observed users.",
        "Receipt sums are gross item amounts, not net revenue or margin; returns and costs are not recorded.",
        "Meal XP is attributed to completion date; its purchase-day cap can refer to an earlier date.",
        "Unknown cohorts are included only without a cohort filter; cohort is not historical event-time segmentation.",
        "Endpoints have no production authorization; use only with synthetic demo data.",
    ])
    unavailable: dict[str, str] = Field(default_factory=lambda: {
        "itt_purchase_frequency_and_uplift": "No randomized assignment roster or control group.",
        "margin_per_participant_and_roi": "No cost, margin, cannibalization or causal incremental revenue data.",
        "ui_impressions_clicks_and_retention": "No client exposure/open/session event ledger.",
        "period_referral_xp": "Referral awards have no retained event timestamps.",
        "fraud_rates_and_precision": "Rejected/review decisions and ground-truth labels are not retained in this ledger.",
        "saved_recipe_events": "Recipe book stores a set without save timestamps.",
    })


class MetricsSummary(ApiModel):
    window: MetricsWindow
    metadata: MetricsMetadata = Field(default_factory=MetricsMetadata)
    counts: MetricsCounts
    purchase_frequency: PurchaseFrequency


class MetricsDay(ApiModel):
    date: date
    counts: MetricsCounts


class MetricsDaily(ApiModel):
    window: MetricsWindow
    metadata: MetricsMetadata = Field(default_factory=MetricsMetadata)
    days: list[MetricsDay]


def metrics_window(
    start_date: date, end_date: date, cohort: RankCohort | None = None,
) -> MetricsWindow:
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")
    if (end_date - start_date).days >= 366:
        raise ValueError("date window must contain at most 366 inclusive days")
    return MetricsWindow(start_date=start_date, end_date=end_date, cohort=cohort)


@dataclass
class _Bucket:
    users: set[str] = field(default_factory=set)
    receipts: Counter[str] = field(default_factory=Counter)
    purchase_days: set[tuple[str, date]] = field(default_factory=set)
    counts: MetricsCounts = field(default_factory=MetricsCounts)

    def finish(self, known_cohorts: dict[str, RankCohort]) -> MetricsCounts:
        return self.counts.model_copy(update={
            "observed_event_users": len(self.users),
            "unclassified_event_users": len(self.users - known_cohorts.keys()),
            "purchasing_users": len(self.receipts),
            "verified_receipts": sum(self.receipts.values()),
            "purchase_user_days": len(self.purchase_days),
            "receipt_amount_rub": round(self.counts.receipt_amount_rub, 2),
            "markdown_savings_rub": round(self.counts.markdown_savings_rub, 2),
        })


class MetricsService:
    def __init__(self, repository: InMemoryStateRepository) -> None:
        self._repository = repository

    def _aggregate(
        self, window: MetricsWindow,
    ) -> tuple[_Bucket, dict[date, _Bucket], dict[str, RankCohort]]:
        snapshot = self._repository.metrics_snapshot()
        total = _Bucket()
        days = {
            window.start_date + timedelta(days=offset): _Bucket()
            for offset in range((window.end_date - window.start_date).days + 1)
        }

        def buckets(user_id: str, timestamp: datetime) -> tuple[_Bucket, ...]:
            if (window.cohort is not None
                    and snapshot.receipt_cohorts.get(user_id) != window.cohort):
                return ()
            day = timestamp.astimezone(BUSINESS_TIMEZONE).date()
            if day not in days:
                return ()
            total.users.add(user_id)
            days[day].users.add(user_id)
            return (total, days[day])

        for user_id, receipt in snapshot.receipts:
            for bucket in buckets(user_id, receipt.purchased_at):
                bucket.receipts[user_id] += 1
                bucket.purchase_days.add((user_id, receipt.purchased_at.astimezone(BUSINESS_TIMEZONE).date()))
                for item in receipt.items:
                    bucket.counts.receipt_amount_rub += item.unit_price * item.quantity
                    if item.is_markdown and item.original_unit_price is not None:
                        bucket.counts.markdown_savings_rub += (
                            item.original_unit_price - item.unit_price
                        ) * item.quantity
        for user_id, issued_at in snapshot.offers:
            for bucket in buckets(user_id, issued_at):
                bucket.counts.meal_offers_issued += 1
        for plan in snapshot.plans:
            for bucket in buckets(plan.user_id, plan.created_at):
                if plan.route == MealRoute.COOK:
                    bucket.counts.cook_plans_created += 1
                else:
                    bucket.counts.ready_plans_created += 1
            if plan.completed_at is not None:
                for bucket in buckets(plan.user_id, plan.completed_at):
                    if plan.route == MealRoute.COOK:
                        bucket.counts.cook_plans_completed += 1
                    else:
                        bucket.counts.ready_plans_completed += 1
                    bucket.counts.rewarded_completed_plans += int(plan.awarded_xp > 0)
                    bucket.counts.meal_xp_earned += plan.awarded_xp
        return total, days, snapshot.receipt_cohorts

    def summary(self, window: MetricsWindow, purchase_threshold: int) -> MetricsSummary:
        total, _, cohorts = self._aggregate(window)
        count_days = Counter(user_id for user_id, _ in total.purchase_days)
        n_receipts = sum(count >= purchase_threshold for count in total.receipts.values())
        n_days = sum(count >= purchase_threshold for count in count_days.values())

        def per_user(value: int) -> float | None:
            return value / len(total.users) if total.users else None

        return MetricsSummary(
            window=window, counts=total.finish(cohorts),
            purchase_frequency=PurchaseFrequency(
                purchase_threshold=purchase_threshold,
                receipts_per_observed_user=per_user(sum(total.receipts.values())),
                purchase_days_per_observed_user=per_user(len(total.purchase_days)),
                users_at_least_n_receipts=n_receipts,
                share_at_least_n_receipts=per_user(n_receipts),
                users_at_least_n_purchase_days=n_days,
                share_at_least_n_purchase_days=per_user(n_days),
            ),
        )

    def daily(self, window: MetricsWindow) -> MetricsDaily:
        _, days, cohorts = self._aggregate(window)
        return MetricsDaily(window=window, days=[
            MetricsDay(date=day, counts=bucket.finish(cohorts))
            for day, bucket in days.items()
        ])
