"""Taste, derived from what people actually bought — not from an archetype rule.

The problem this addresses
--------------------------
Every preference signal in this project is invented by us.
``_label_for_pair`` reads ``ARCHETYPES``, ``oracle_relevant`` reads the same
table, and the model learns to reproduce them. ADR-003 named the consequence
directly: **personas have no taste** — no simulator prefers borsch to pasta —
so ``dish_type`` and ``cuisine`` sit in the contract, unused by any feature,
because there is nothing for them to predict.

There is one place real taste is observable without a recipe product existing
yet: **ready-meal purchases**. ``recsys.ready_food_pairs`` already maps 29
recipes onto 259 real retailer PLUs. If someone repeatedly buys prepared
borsch, that is an observed, transactional statement that they like borsch —
recorded before we ever showed them anything, so it cannot be circular.

This module turns receipts into that signal. It is written against the receipt
contract rather than against the synthetic generator, so the same code runs on
real X5 receipt lines: the only thing it needs is a product identifier that can
be matched to the pair table.

The direction of the signal is not obvious, and that is deliberate
-------------------------------------------------------------------
Buying prepared borsch says two things at once: *likes borsch*, and *does not
cook borsch*. Which one dominates is exactly what a recipe-first product needs
to find out — the ready-meal buyer is either the easiest person to convert or
the hardest. So this module exposes the evidence and refuses to decide the
sign; ``ready_meal_share`` is published alongside the affinities precisely so a
model can separate "likes this dish" from "does not cook, ever".

Facets come from the recipe, not from the product card
------------------------------------------------------
A meal's ``dish_type``/``cuisine`` is only present when the collector captured
a product card, so meal-side facets are sparse. Recipe-side facets are
complete, and the pair table already says which recipe a PLU stands in for, so
the recipe's vocabulary is used throughout. One vocabulary, full coverage.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from app.contracts import Receipt, ReceiptItem
from recsys.ready_food_pairs import pairs_for_plu
from recsys.recipes import RECIPES_BY_ID

#: Category marking a receipt line as a prepared meal rather than an
#: ingredient. Deliberately NOT added to ``recsys.catalog.CATEGORIES``: a
#: prepared meal is not an ingredient category, and everything computing
#: category shares iterates that tuple, so keeping it outside means these lines
#: cannot silently distort ingredient-level features.
READY_MEAL_CATEGORY = "ready_meal"

#: How long a taste observation stays at full weight, in days. Far longer than
#: the pantry half-lives in ``recsys.pantry``: those model whether food is
#: physically gone, this models whether a preference still holds. Liking borsch
#: does not expire in five days.
TASTE_HALF_LIFE_DAYS = 60.0


def ready_meal_ref(chain: str, plu: str) -> str:
    """The receipt-line identifier for a prepared product.

    ``chain:plu`` rather than a synthetic sku id, because these are real
    products with real retailer identifiers. On real X5 data this is the join
    key; on synthetic data it is written by
    ``synthesize_ready_meal_purchases``.
    """
    return f"{chain}:{plu}"


def parse_ready_meal_ref(sku_id: str) -> tuple[str, str] | None:
    """``chain:plu`` back into its parts, or ``None`` if this is not one.

    Isolated in one function so pointing this pipeline at a different
    identifier scheme — an X5 internal product id, say — is a one-line change
    rather than a search through the module.
    """
    if ":" not in sku_id:
        return None
    chain, _, plu = sku_id.partition(":")
    if not chain or not plu:
        return None
    return chain, plu


@dataclass(frozen=True)
class ObservedDish:
    """One prepared-meal purchase, resolved to the recipes it stands in for."""

    recipe_ids: tuple[str, ...]
    purchased_at: datetime
    quantity: float
    unit_price: float

    def weight(self, now: datetime, half_life_days: float = TASTE_HALF_LIFE_DAYS) -> float:
        """Recency weight. A dish bought last week counts more than last year."""
        age_days = max((now - self.purchased_at).total_seconds() / 86400.0, 0.0)
        return self.quantity * 0.5 ** (age_days / max(half_life_days, 0.5))


@dataclass
class DishSignal:
    """What a shopper's prepared-meal purchases say about their taste."""

    #: recipe_id -> recency-weighted evidence for that exact dish.
    recipe_weight: dict[str, float] = field(default_factory=dict)
    dish_type_weight: dict[str, float] = field(default_factory=dict)
    cuisine_weight: dict[str, float] = field(default_factory=dict)
    #: Prepared-meal lines as a share of all receipt lines. High values mean
    #: "buys dinner rather than making it", which a recipe product should treat
    #: as information, not as enthusiasm.
    ready_meal_share: float = 0.0
    n_observations: int = 0

    @property
    def has_signal(self) -> bool:
        return self.n_observations > 0

    def _share(self, table: dict[str, float], key: str | None) -> float:
        if key is None or not table:
            return 0.0
        total = sum(table.values())
        return table.get(key, 0.0) / total if total else 0.0

    def dish_type_affinity(self, dish_type: str | None) -> float:
        return self._share(self.dish_type_weight, dish_type)

    def cuisine_affinity(self, cuisine: str | None) -> float:
        return self._share(self.cuisine_weight, cuisine)

    def same_dish_affinity(self, recipe_id: str) -> float:
        """Evidence for this exact dish, as a share of all dish evidence.

        The strongest of the three and the sparsest: most shoppers will have
        bought a counterpart for no recipe in the catalog at all.
        """
        return self._share(self.recipe_weight, recipe_id)


def observed_dishes(receipts: list[Receipt]) -> list[ObservedDish]:
    """Every prepared-meal line in these receipts, resolved through the pair table.

    Lines that are not prepared meals, or are prepared meals we have no recipe
    counterpart for, are skipped — the second case silently, because the pair
    table covers 29 of 47 recipes and an unmapped PLU is expected, not an error.
    """
    out: list[ObservedDish] = []
    for receipt in receipts:
        for item in receipt.items:
            reference = parse_ready_meal_ref(item.sku_id)
            if reference is None:
                continue
            pairs = pairs_for_plu(*reference)
            if not pairs:
                continue
            out.append(
                ObservedDish(
                    recipe_ids=tuple(pair.recipe_id for pair in pairs),
                    purchased_at=receipt.purchased_at,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )
            )
    return out


def dish_signal(
    receipts: list[Receipt],
    *,
    now: datetime,
    half_life_days: float = TASTE_HALF_LIFE_DAYS,
) -> DishSignal:
    """Aggregate prepared-meal purchases into a taste profile.

    Only receipts strictly before ``now`` contribute: this is a feature, and a
    feature that reads the future is a leak. The same discipline
    ``recsys.profiles`` now enforces on history generation.
    """
    usable = [r for r in receipts if r.purchased_at <= now]
    dishes = observed_dishes(usable)

    recipe_weight: dict[str, float] = defaultdict(float)
    dish_type_weight: dict[str, float] = defaultdict(float)
    cuisine_weight: dict[str, float] = defaultdict(float)

    for dish in dishes:
        weight = dish.weight(now, half_life_days)
        if not dish.recipe_ids:
            continue
        # One purchase can stand in for several recipes ("Плов с курицей" is a
        # counterpart to both pilaf recipes). Split the evidence rather than
        # counting it once per recipe, so an ambiguous product does not
        # outweigh an unambiguous one.
        share = weight / len(dish.recipe_ids)
        for recipe_id in dish.recipe_ids:
            recipe_weight[recipe_id] += share
            recipe = RECIPES_BY_ID.get(recipe_id)
            if recipe is None:
                continue
            if recipe.dish_type:
                dish_type_weight[recipe.dish_type] += share
            if recipe.cuisine:
                cuisine_weight[recipe.cuisine] += share

    total_lines = sum(len(r.items) for r in usable)
    return DishSignal(
        recipe_weight=dict(recipe_weight),
        dish_type_weight=dict(dish_type_weight),
        cuisine_weight=dict(cuisine_weight),
        ready_meal_share=len(dishes) / total_lines if total_lines else 0.0,
        n_observations=len(dishes),
    )


#: Feature names this module contributes, in the order ``dish_features``
#: returns them. Kept next to the function so a caller adding them to
#: ``recsys.model.FEATURE_NAMES`` cannot get the order wrong.
DISH_FEATURE_NAMES: tuple[str, ...] = (
    "same_dish_ready_affinity",
    "dish_type_affinity",
    "cuisine_affinity",
    "ready_meal_share",
    "has_dish_signal",
)


def dish_features(signal: DishSignal, recipe) -> dict[str, float]:
    """The taste features for one (shopper, recipe) pair.

    ``has_dish_signal`` is the same guard ``history_is_known`` provides for the
    history proxies: without it a shopper with no prepared-meal purchases is
    indistinguishable from one whose purchases all missed this dish, and the
    model reads a structural zero as a measured dislike.
    """
    return {
        "same_dish_ready_affinity": signal.same_dish_affinity(recipe.recipe_id),
        "dish_type_affinity": signal.dish_type_affinity(recipe.dish_type),
        "cuisine_affinity": signal.cuisine_affinity(recipe.cuisine),
        "ready_meal_share": min(signal.ready_meal_share * 4.0, 1.0),
        "has_dish_signal": 1.0 if signal.has_signal else 0.0,
    }


# --- simulation support ----------------------------------------------------


def ready_meal_receipt_item(
    *,
    chain: str,
    plu: str,
    name: str,
    price_rub: float,
    quantity: float = 1,
) -> ReceiptItem:
    """A receipt line for a prepared meal.

    ``ingredient_ids`` is empty on purpose: buying a prepared lasagne is not
    buying its ingredients, and every pantry/coverage feature keys off that
    set. Leaving it empty is what keeps this line out of ingredient-level
    features instead of quietly inflating them.
    """
    return ReceiptItem(
        sku_id=ready_meal_ref(chain, plu),
        name=name,
        category=READY_MEAL_CATEGORY,
        ingredient_ids=set(),
        quantity=quantity,
        unit_price=round(price_rub, 2),
    )
