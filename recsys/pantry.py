"""Scorer availability adapter, ported from recsys-benchmark@c28b613.

API 1.2 default: raw ingredients in current_receipt plus explicit user HOME.
The supplied receipt need not be from today; it is evidence of a purchase,
not proof of remaining quantity, freshness, or food safety.

Historical depletion estimates below are experimental and DISABLED in serving.
Their category half-lives and probabilities are hypotheses, not expiry dates.
An enabled experimental model must not turn those estimates into safe product
options: final availability/safety remains the responsibility of app.service.
See docs/integration-handoff.md for provenance and compatibility boundaries.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from app.contracts import RecommendationRequest
from recsys.catalog import INGREDIENTS, ingredient_category

#: How long one purchase of a category typically lasts, in days. These are
#: assumptions, not measurements or safe storage periods. Sensitivity
#: experiments remain on the source ML branch, outside this integration.
CATEGORY_HALF_LIFE_DAYS: dict[str, float] = {
    "pantry": 60.0,
    "grain": 30.0,
    "egg": 10.0,
    "dairy": 5.0,
    "meat": 4.0,
    "vegetable": 5.0,
    "fruit": 5.0,
}

DEFAULT_HALF_LIFE_DAYS = 7.0

#: Probability at or above which an ingredient is treated as already at home.
#: High on purpose: see the asymmetry note in the module docstring.
DEFAULT_CONFIDENCE_THRESHOLD = 0.7

#: Weight of the category prior when blending it with a shopper's own rhythm.
#: Two observations of a personal interval move the estimate halfway off the
#: category default; one barely moves it. Without shrinkage a single lucky gap
#: would override the prior outright.
PERSONAL_PRIOR_WEIGHT = 2.0

#: Personal intervals outside this range are treated as noise, not rhythm.
MIN_PERSONAL_INTERVAL_DAYS = 1.0
MAX_PERSONAL_INTERVAL_DAYS = 90.0


@dataclass(frozen=True)
class PantryEstimate:
    ingredient_id: str
    probability: float
    days_since_purchase: float | None
    #: Why we believe it, in one token, so a response can explain itself.
    reason: str

    @property
    def is_observed(self) -> bool:
        """Observed in the supplied receipt; does not certify stock or freshness."""
        return self.reason == "in_basket"


@dataclass(frozen=True)
class PantryPolicy:
    """Whether and how confidently to count inferred stock as available."""

    enabled: bool = False
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD
    #: Scales every half-life. A dial for sensitivity sweeps: below 1 assumes
    #: food runs out faster than we guessed.
    half_life_multiplier: float = 1.0
    #: Use the shopper's own repurchase rhythm instead of a category constant.
    #:
    #: "Milk lasts five days" is true of a category, not of a person. Somebody
    #: who rebuys milk every three days is out of it on day five; somebody who
    #: rebuys every ten still has it. Both facts are already in the purchase
    #: history, and the category constant throws them away.
    use_personal_rhythm: bool = False

    @classmethod
    def disabled(cls) -> PantryPolicy:
        return cls(enabled=False)

    @classmethod
    def confident(cls) -> PantryPolicy:
        """Counts stock the model is quite sure about."""
        return cls(enabled=True, confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD)

    @classmethod
    def personal(cls) -> PantryPolicy:
        """Same caution, but timed to the shopper rather than the category."""
        return cls(
            enabled=True,
            confidence_threshold=DEFAULT_CONFIDENCE_THRESHOLD,
            use_personal_rhythm=True,
        )

    @classmethod
    def optimistic(cls) -> PantryPolicy:
        """Counts anything more likely than not. Strands users more often."""
        return cls(enabled=True, confidence_threshold=0.4)


DISABLED_PANTRY = PantryPolicy.disabled()


def category_half_life_days(ingredient_id: str) -> float:
    if ingredient_id not in INGREDIENTS:
        return DEFAULT_HALF_LIFE_DAYS
    return CATEGORY_HALF_LIFE_DAYS.get(
        ingredient_category(ingredient_id), DEFAULT_HALF_LIFE_DAYS
    )


def purchase_intervals(request: RecommendationRequest) -> dict[str, list[float]]:
    """Gaps in days between consecutive purchases of each ingredient."""
    dates: dict[str, list[datetime]] = {}
    for receipt in [*request.purchase_history, request.current_receipt]:
        for item in receipt.items:
            if item.is_prepared_food:
                continue
            for ingredient_id in item.ingredient_ids:
                dates.setdefault(ingredient_id, []).append(receipt.purchased_at)

    intervals: dict[str, list[float]] = {}
    for ingredient_id, moments in dates.items():
        ordered = sorted(moments)
        gaps = [
            (later - earlier).total_seconds() / 86400.0
            for earlier, later in zip(ordered, ordered[1:])
        ]
        usable = [
            gap
            for gap in gaps
            if MIN_PERSONAL_INTERVAL_DAYS <= gap <= MAX_PERSONAL_INTERVAL_DAYS
        ]
        if usable:
            intervals[ingredient_id] = usable
    return intervals


def half_life_days(
    ingredient_id: str,
    policy: PantryPolicy = DISABLED_PANTRY,
    intervals: dict[str, list[float]] | None = None,
) -> float:
    """How long one purchase of this item lasts *this* shopper.

    Falls back to the category constant when the history says nothing. A
    personal repurchase interval is the natural half-life: somebody who rebuys
    every three days has roughly run out by day three, which is exactly what a
    half-life of three days encodes.
    """
    base = category_half_life_days(ingredient_id)
    if policy.use_personal_rhythm and intervals:
        observed = intervals.get(ingredient_id)
        if observed:
            personal = statistics.median(observed)
            n = len(observed)
            base = (n * personal + PERSONAL_PRIOR_WEIGHT * base) / (
                n + PERSONAL_PRIOR_WEIGHT
            )
    return max(base * policy.half_life_multiplier, 0.5)


def survival_probability(
    days_since_purchase: float,
    ingredient_id: str,
    policy: PantryPolicy = DISABLED_PANTRY,
    intervals: dict[str, list[float]] | None = None,
) -> float:
    """Hypothetical remaining-stock probability; never food safety/expiry."""
    if days_since_purchase <= 0:
        return 1.0
    return 0.5 ** (
        days_since_purchase / half_life_days(ingredient_id, policy, intervals)
    )


def _last_purchase_days(
    request: RecommendationRequest, now: datetime
) -> dict[str, float]:
    """Days since each ingredient was last bought, over the whole history."""
    latest: dict[str, float] = {}
    for receipt in request.purchase_history:
        age_days = (now - receipt.purchased_at).total_seconds() / 86400.0
        if age_days < 0:
            continue
        for item in receipt.items:
            if item.is_prepared_food:
                continue
            for ingredient_id in item.ingredient_ids:
                previous = latest.get(ingredient_id)
                if previous is None or age_days < previous:
                    latest[ingredient_id] = age_days
    return latest


def estimate_pantry(
    request: RecommendationRequest,
    *,
    now: datetime | None = None,
    policy: PantryPolicy = DISABLED_PANTRY,
) -> dict[str, PantryEstimate]:
    """Per-ingredient belief that the shopper already has it.

    Receipt and explicit HOME are fixed inputs. Only experimental opt-in uses
    history decay. A score of 1 for an input means inclusion, not verified stock.
    """
    moment = now or request.now
    estimates: dict[str, PantryEstimate] = {}

    for item in request.current_receipt.items:
        if item.is_prepared_food:
            continue
        for ingredient_id in item.ingredient_ids:
            estimates[ingredient_id] = PantryEstimate(
                ingredient_id=ingredient_id,
                probability=1.0,
                days_since_purchase=0.0,
                reason="in_basket",
            )

    for ingredient_id in request.user.home_ingredient_ids:
        estimates.setdefault(ingredient_id, PantryEstimate(
            ingredient_id=ingredient_id, probability=1.0,
            days_since_purchase=None, reason="explicit_home",
        ))

    if not policy.enabled:
        return estimates

    intervals = purchase_intervals(request) if policy.use_personal_rhythm else None
    for ingredient_id, age_days in _last_purchase_days(request, moment).items():
        if ingredient_id in estimates:
            continue
        probability = survival_probability(age_days, ingredient_id, policy, intervals)
        estimates[ingredient_id] = PantryEstimate(
            ingredient_id=ingredient_id,
            probability=round(probability, 4),
            days_since_purchase=round(age_days, 2),
            reason="likely_in_pantry" if probability >= policy.confidence_threshold
            else "probably_used_up",
        )
    return estimates


def available_ingredient_ids(
    request: RecommendationRequest,
    *,
    now: datetime | None = None,
    policy: PantryPolicy = DISABLED_PANTRY,
) -> set[str]:
    """Ingredients to treat as already at home.

    Default: raw receipt ingredients and explicit HOME; historical inference
    stays disabled. This does not set the challenge mode to current.
    """
    return {
        estimate.ingredient_id
        for estimate in estimate_pantry(request, now=now, policy=policy).values()
        if estimate.is_observed or estimate.probability >= policy.confidence_threshold
    }
