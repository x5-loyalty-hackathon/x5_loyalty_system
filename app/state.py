from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from threading import RLock

from app.contracts import PrivateRank, ProgressSnapshot, Receipt


XP_PER_PURCHASE_DAY = 10
XP_PER_RECIPE = 20
XP_PER_REFERRAL_REWARD = 10
XP_PER_LEVEL = 50


@dataclass
class UserProgressRecord:
    user_id: str
    verified_receipts: int = 0
    purchase_dates: set[date] = field(default_factory=set)
    recipes_completed: int = 0
    markdown_savings: float = 0.0
    rescue_items: float = 0.0
    referral_rewards: int = 0

    @property
    def avatar_xp(self) -> int:
        return (
            len(self.purchase_dates) * XP_PER_PURCHASE_DAY
            + self.recipes_completed * XP_PER_RECIPE
            + self.referral_rewards * XP_PER_REFERRAL_REWARD
        )


@dataclass(frozen=True)
class ReceiptRecordOutcome:
    recorded: bool
    existing_owner: str | None
    is_new_purchase_day: bool = False


@dataclass(frozen=True)
class ReferralAwardOutcome:
    awarded: bool
    existing_inviter: str | None


class InMemoryStateRepository:
    """Demo-only state. Replace with a persistent adapter without changing APIs."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._users: dict[str, UserProgressRecord] = {}
        self._receipt_owners: dict[str, str] = {}
        self._referral_inviter_by_invitee: dict[str, str] = {}

    def reset(self) -> None:
        with self._lock:
            self._users.clear()
            self._receipt_owners.clear()
            self._referral_inviter_by_invitee.clear()

    def get_receipt_owner(self, receipt_id: str) -> str | None:
        with self._lock:
            return self._receipt_owners.get(receipt_id)

    def record_receipt(
        self,
        *,
        user_id: str,
        receipt: Receipt,
        recipe_completed: bool,
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
            purchase_date = receipt.purchased_at.date()
            is_new_purchase_day = purchase_date not in record.purchase_dates
            record.purchase_dates.add(purchase_date)
            if recipe_completed:
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
                recipes_completed=record.recipes_completed,
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
