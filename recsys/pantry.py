"""What the shopper probably already has at home.

The pipeline treats "you have it" as "it is on today's receipt". Measured over
the synthetic population, that overstates the shopping list badly: **20% of
the ingredients we tell people to buy were bought by them within the last
seven days**, 29% within fourteen, 46% within thirty. Eggs are the extreme
case at 96%.

For a product built around availability this is not a detail — ``missing_count``
is the quantity the whole ranking policy sorts on, and it is inflated.

Why a threshold would be wrong
------------------------------
"Bought in the last week, therefore has it" fails in both directions. Staples
break it hardest: only 6% of ``pantry`` items (flour, oil, salt) appear in a
recent receipt, not because people lack them but because one purchase lasts
months. Perishables break it the other way — milk bought six days ago is
probably gone.

So this models *depletion*, not recency: one purchase lasts a category-typical
time, and the probability it survives decays from there.

Asymmetry of being wrong
------------------------
The two errors are not equal. Telling someone they need to buy flour they
already have is a small annoyance. Telling them they have eggs when they do not
strands them at the stove with a half-made dinner. So the default threshold is
deliberately high, and an ingredient never seen in the history is assumed
absent rather than assumed to be a staple everyone owns.

Nothing here changes behaviour by default: ``PantryPolicy.disabled()`` is what
the service and the model use unless a caller opts in, so the effect can be
measured on the bench before it is shipped — the same discipline
``app.service.RankingPolicy`` follows.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from app.contracts import RecommendationRequest
from recsys.catalog import ingredient_category

#: How long one purchase of a category typically lasts, in days. These are
#: cook's estimates, not measurements — ``recsys.sensitivity`` is the place to
#: ask whether being wrong about them changes anything.
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
        """True only for today's receipt — the one case that is not a guess."""
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
    return CATEGORY_HALF_LIFE_DAYS.get(
        ingredient_category(ingredient_id), DEFAULT_HALF_LIFE_DAYS
    )


def purchase_intervals(request: RecommendationRequest) -> dict[str, list[float]]:
    """Gaps in days between consecutive purchases of each ingredient."""
    dates: dict[str, list[datetime]] = {}
    for receipt in [*request.purchase_history, request.current_receipt]:
        for item in receipt.items:
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
    """Probability one purchase is still usable after this many days."""
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

    Today's basket is certainty; everything else decays. Ingredients never seen
    in the history are simply absent from the result — assuming an unseen
    staple is owned is the error that strands people.
    """
    moment = now or request.now
    estimates: dict[str, PantryEstimate] = {}

    for item in request.current_receipt.items:
        for ingredient_id in item.ingredient_ids:
            estimates[ingredient_id] = PantryEstimate(
                ingredient_id=ingredient_id,
                probability=1.0,
                days_since_purchase=0.0,
                reason="in_basket",
            )

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

    With the default disabled policy this is exactly today's receipt, so the
    shipped behaviour is unchanged until someone opts in.
    """
    return {
        estimate.ingredient_id
        for estimate in estimate_pantry(request, now=now, policy=policy).values()
        if estimate.is_observed or estimate.probability >= policy.confidence_threshold
    }
