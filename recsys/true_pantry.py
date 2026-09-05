"""What the shopper *actually* has at home — the world's answer, not ours.

``recsys.pantry`` estimates stock from purchase history. This module decides
the truth, and the two must be kept apart or the bench measures nothing.

Why this exists
---------------
Crediting a shopper with inferred stock shrinks ``missing_count``, and every
response simulator decides partly on ``missing_count``. So switching pantry
inference on raised measured cooking by 2.4x — and the *optimistic* policy beat
the careful one, which is the tell: a metric where assuming more always wins is
not measuring belief quality, it is measuring how much we assumed.

The missing half is consequence. A wrong "you already have eggs" does not save
a trip, it strands someone mid-recipe. Until the world can contradict the
estimate, the bench rewards overconfidence.

Design
------
Ground truth uses a **different mechanism** than the estimator on purpose. If
the world consumed food at exactly the half-lives ``recsys.pantry`` assumes,
the estimator would be perfectly calibrated by construction and we would again
be grading our own homework. Here the world:

* runs faster than we guess (``TRUE_HALF_LIFE_DAYS`` is shorter across the
  board — people cook more than a purchase-recency model expects);
* varies per household, so the same history implies different stock for
  different people;
* is deterministic given (user, ingredient, purchase age) so a run stays
  reproducible.

The estimator is therefore systematically optimistic, which is the realistic
failure direction and the one worth measuring.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import datetime

from app.contracts import RecommendationRequest
from recsys._seeds import stable_seed
from recsys.catalog import ingredient_category

#: How long a purchase really lasts, by category. Shorter than the estimator's
#: ``recsys.pantry.CATEGORY_HALF_LIFE_DAYS`` — the gap is the modelling error
#: we want the bench to punish.
TRUE_HALF_LIFE_DAYS: dict[str, float] = {
    "pantry": 40.0,
    "grain": 18.0,
    "egg": 6.0,
    "dairy": 3.0,
    "meat": 2.5,
    "vegetable": 3.0,
    "fruit": 3.0,
}

DEFAULT_TRUE_HALF_LIFE_DAYS = 4.0

#: Spread of per-household consumption speed. A household at 0.6 gets through
#: food almost twice as fast as one at 1.4.
HOUSEHOLD_SPEED_RANGE = (0.6, 1.4)


@dataclass(frozen=True)
class PantryTruth:
    """Which ingredients the shopper genuinely still has."""

    present: frozenset[str]
    #: Days since last purchase per ingredient, for diagnostics.
    ages: dict[str, float]

    def has(self, ingredient_id: str) -> bool:
        return ingredient_id in self.present


def household_speed(user_id: str) -> float:
    low, high = HOUSEHOLD_SPEED_RANGE
    rng = random.Random(stable_seed("household", user_id))
    return low + rng.random() * (high - low)


def true_pantry(
    request: RecommendationRequest,
    *,
    now: datetime | None = None,
    consumption_multiplier: float = 1.0,
) -> PantryTruth:
    """The world's verdict on what is in this kitchen right now.

    Today's basket is present by definition. Everything else survives with a
    probability drawn from the world's own (faster, household-specific)
    consumption model, decided deterministically per ingredient.

    ``consumption_multiplier`` above 1 makes the world eat faster than the
    baseline guess. It exists because the whole pantry result rests on
    ``TRUE_HALF_LIFE_DAYS``, which nobody measured: a finding that only holds
    at the multiplier we happened to pick is not a finding. The random draw is
    deliberately *not* seeded on the multiplier, so a faster world yields a
    strict subset of a slower one and the comparison is not clouded by noise.
    """
    moment = now or request.now
    speed = household_speed(request.user.user_id)

    present: set[str] = set()
    ages: dict[str, float] = {}

    for item in request.current_receipt.items:
        for ingredient_id in item.ingredient_ids:
            present.add(ingredient_id)
            ages[ingredient_id] = 0.0

    latest: dict[str, float] = {}
    for receipt in request.purchase_history:
        age_days = (moment - receipt.purchased_at).total_seconds() / 86400.0
        if age_days < 0:
            continue
        for item in receipt.items:
            for ingredient_id in item.ingredient_ids:
                previous = latest.get(ingredient_id)
                if previous is None or age_days < previous:
                    latest[ingredient_id] = age_days

    for ingredient_id, age_days in latest.items():
        if ingredient_id in present:
            continue
        ages[ingredient_id] = age_days
        half_life = (
            TRUE_HALF_LIFE_DAYS.get(
                ingredient_category(ingredient_id), DEFAULT_TRUE_HALF_LIFE_DAYS
            )
            * speed
            / max(consumption_multiplier, 0.05)
        )
        survival = 0.5 ** (age_days / max(half_life, 0.5))
        rng = random.Random(
            stable_seed("pantry_truth", request.user.user_id, ingredient_id, round(age_days, 2))
        )
        if rng.random() < survival:
            present.add(ingredient_id)

    return PantryTruth(present=frozenset(present), ages=ages)
