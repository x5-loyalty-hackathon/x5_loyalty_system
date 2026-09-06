"""Synthetic per-request store inventory generator.

Prices come from ``recsys.catalog.BASE_PRICE_RUB``, which is calibrated against
a real X5 price distribution but still modelled per item, so every product this
generates is marked ``price_is_estimate``.

``InventoryProduct.distance_km`` is already user-relative in the contract
(``app/contracts.py``), so inventory is generated per request/profile rather
than as one global catalog with coordinates — distances are sampled around
each profile's own radius so both "inside radius" and "outside radius"
products exist to exercise ``app.safety.SafetyPolicy`` for real, alongside
expired, out-of-stock, not-safety-eligible and no-candidate-at-all cases.
This is a deliberate design choice, not an oversight: it directly implements
the "tuned so SafetyPolicy genuinely exercises all branches" requirement from
the plan.
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.contracts import FulfillmentOption, InventoryProduct
from app.safety import RESCUE_CATEGORIES
from recsys.catalog import BASE_PRICE_RUB, BRANDS, INGREDIENTS, ingredient_category, ingredient_name
from recsys.sku_mapping import synthetic_sku_id

# Probabilities are illustrative demo constants (see
# docs/research/recsys/economics-and-simulation.md), not measured X5 supply
# rates. They're kept as module constants so evaluation/simulation
# sensitivity scenarios can override them explicitly.
P_NO_PRODUCT_AT_ALL = 0.08
P_WITHIN_RADIUS = 0.70
P_SAFETY_INELIGIBLE = 0.05
P_OUT_OF_STOCK = 0.10
P_MARKDOWN_OFFERED = 0.50
P_MARKDOWN_ALREADY_EXPIRED = 0.10


@dataclass(frozen=True)
class InventoryAssumptions:
    """Supply-side numbers we invented, gathered so they can be swept.

    Every field is a guess pending X5 data. Bundling them lets
    ``recsys.sensitivity`` ask the question that actually matters — *which of
    our guesses would change the conclusion if we are wrong* — instead of the
    team weighing all of them equally. Defaults reproduce the module constants,
    so existing callers are unaffected.
    """

    no_product_at_all: float = P_NO_PRODUCT_AT_ALL
    within_radius: float = P_WITHIN_RADIUS
    safety_ineligible: float = P_SAFETY_INELIGIBLE
    out_of_stock: float = P_OUT_OF_STOCK
    markdown_offered: float = P_MARKDOWN_OFFERED
    markdown_already_expired: float = P_MARKDOWN_ALREADY_EXPIRED
    #: Scales every price in ``recsys.catalog.BASE_PRICE_RUB``. Those prices are
    #: calibrated against 2018-2019 receipts with an observed 2.4x era factor;
    #: this dial asks what happens if that factor is wrong.
    price_level: float = 1.0


DEFAULT_INVENTORY_ASSUMPTIONS = InventoryAssumptions()


def _distance_km(
    rng: random.Random,
    user_radius_km: float,
    assumptions: InventoryAssumptions = DEFAULT_INVENTORY_ASSUMPTIONS,
) -> float:
    if rng.random() < assumptions.within_radius:
        return round(rng.uniform(0.1, max(0.2, user_radius_km * 0.95)), 2)
    return round(user_radius_km + rng.uniform(0.3, 4.0), 2)


def _fulfillment_options(rng: random.Random) -> set[FulfillmentOption]:
    if rng.random() < 0.9:
        return {FulfillmentOption.DELIVERY, FulfillmentOption.NEXT_VISIT}
    return {FulfillmentOption.NEXT_VISIT}


def _full_price_product(
    rng: random.Random,
    *,
    ingredient_id: str,
    store_id: str,
    now: datetime,
    user_radius_km: float,
    index: int,
    assumptions: InventoryAssumptions = DEFAULT_INVENTORY_ASSUMPTIONS,
) -> InventoryProduct:
    base_price = BASE_PRICE_RUB[ingredient_id] * assumptions.price_level
    price = round(base_price * rng.uniform(0.95, 1.2), 2)
    return InventoryProduct(
        sku_id=synthetic_sku_id(ingredient_id, "fp", index),
        name=ingredient_name(ingredient_id),
        category=ingredient_category(ingredient_id),
        ingredient_ids={ingredient_id},
        store_id=store_id,
        distance_km=_distance_km(rng, user_radius_km, assumptions),
        price=price,
        original_price=price,
        brand=rng.choice(BRANDS) if rng.random() < 0.7 else None,
        is_markdown=False,
        safety_eligible=rng.random() >= assumptions.safety_ineligible,
        expires_at=None,
        available_quantity=(
            0 if rng.random() < assumptions.out_of_stock else rng.randint(1, 25)
        ),
        fulfillment_options=_fulfillment_options(rng),
        price_is_estimate=True,
    )


def _markdown_product(
    rng: random.Random,
    *,
    ingredient_id: str,
    store_id: str,
    now: datetime,
    user_radius_km: float,
    index: int,
    assumptions: InventoryAssumptions = DEFAULT_INVENTORY_ASSUMPTIONS,
) -> InventoryProduct:
    base_price = BASE_PRICE_RUB[ingredient_id] * assumptions.price_level
    original_price = round(base_price * rng.uniform(0.95, 1.2), 2)
    price = round(original_price * rng.uniform(0.45, 0.7), 2)
    if rng.random() < assumptions.markdown_already_expired:
        expires_at = now - timedelta(hours=rng.uniform(1, 12))
    else:
        expires_at = now + timedelta(hours=rng.uniform(6, 72))
    return InventoryProduct(
        sku_id=synthetic_sku_id(ingredient_id, "md", index),
        name=ingredient_name(ingredient_id),
        category=ingredient_category(ingredient_id),
        ingredient_ids={ingredient_id},
        store_id=store_id,
        distance_km=_distance_km(rng, user_radius_km, assumptions),
        price=price,
        original_price=original_price,
        brand=rng.choice(BRANDS) if rng.random() < 0.5 else None,
        is_markdown=True,
        safety_eligible=rng.random() >= assumptions.safety_ineligible,
        expires_at=expires_at,
        available_quantity=(
            0 if rng.random() < assumptions.out_of_stock else rng.randint(1, 6)
        ),
        fulfillment_options=_fulfillment_options(rng),
        price_is_estimate=True,
    )


def generate_inventory(
    rng: random.Random,
    *,
    now: datetime,
    home_store_id: str,
    user_radius_km: float,
    ingredient_ids: Iterable[str] | None = None,
    markdown_supply_rate: float | None = None,
    assumptions: InventoryAssumptions = DEFAULT_INVENTORY_ASSUMPTIONS,
) -> list[InventoryProduct]:
    """Build a synthetic inventory snapshot for one recommendation request.

    Covers every requested ingredient (default: the full catalog) with a mix
    of full-price and, for rescue categories, markdown options — including
    deliberately-filtered cases (expired, ineligible, out of stock,
    out-of-radius, no option at all) so the safety policy is genuinely
    exercised rather than always trivially passing.
    """
    markdown_rate = (
        markdown_supply_rate
        if markdown_supply_rate is not None
        else assumptions.markdown_offered
    )
    ids = list(ingredient_ids) if ingredient_ids is not None else list(INGREDIENTS)
    nearby_stores = [home_store_id, f"{home_store_id}_annex", "store_hub_1"]
    products: list[InventoryProduct] = []
    index = 0
    for ingredient_id in ids:
        if rng.random() < assumptions.no_product_at_all:
            continue
        store_id = rng.choice(nearby_stores)
        products.append(
            _full_price_product(
                rng,
                ingredient_id=ingredient_id,
                store_id=store_id,
                now=now,
                user_radius_km=user_radius_km,
                index=index,
                assumptions=assumptions,
            )
        )
        index += 1

        if (
            ingredient_category(ingredient_id) in RESCUE_CATEGORIES
            and rng.random() < markdown_rate
        ):
            store_id = rng.choice(nearby_stores)
            products.append(
                _markdown_product(
                    rng,
                    ingredient_id=ingredient_id,
                    store_id=store_id,
                    now=now,
                    user_radius_km=user_radius_km,
                    index=index,
                    assumptions=assumptions,
                )
            )
            index += 1
    return products
