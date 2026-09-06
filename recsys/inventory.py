"""Synthetic per-request store inventory generator.

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
from datetime import datetime, timedelta

from app.contracts import FulfillmentOption, InventoryProduct
from app.safety import RESCUE_CATEGORIES
from recsys.catalog import BASE_PRICE_RUB, BRANDS, INGREDIENTS, ingredient_category, ingredient_name

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


def _distance_km(rng: random.Random, user_radius_km: float) -> float:
    if rng.random() < P_WITHIN_RADIUS:
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
) -> InventoryProduct:
    base_price = BASE_PRICE_RUB[ingredient_id]
    price = round(base_price * rng.uniform(0.95, 1.2), 2)
    return InventoryProduct(
        sku_id=f"{ingredient_id}_fp_{index}",
        name=ingredient_name(ingredient_id),
        category=ingredient_category(ingredient_id),
        ingredient_ids={ingredient_id},
        store_id=store_id,
        distance_km=_distance_km(rng, user_radius_km),
        price=price,
        original_price=price,
        brand=rng.choice(BRANDS) if rng.random() < 0.7 else None,
        is_markdown=False,
        safety_eligible=rng.random() >= P_SAFETY_INELIGIBLE,
        expires_at=None,
        available_quantity=0 if rng.random() < P_OUT_OF_STOCK else rng.randint(1, 25),
        fulfillment_options=_fulfillment_options(rng),
    )


def _markdown_product(
    rng: random.Random,
    *,
    ingredient_id: str,
    store_id: str,
    now: datetime,
    user_radius_km: float,
    index: int,
) -> InventoryProduct:
    base_price = BASE_PRICE_RUB[ingredient_id]
    original_price = round(base_price * rng.uniform(0.95, 1.2), 2)
    price = round(original_price * rng.uniform(0.45, 0.7), 2)
    if rng.random() < P_MARKDOWN_ALREADY_EXPIRED:
        expires_at = now - timedelta(hours=rng.uniform(1, 12))
    else:
        expires_at = now + timedelta(hours=rng.uniform(6, 72))
    return InventoryProduct(
        sku_id=f"{ingredient_id}_md_{index}",
        name=ingredient_name(ingredient_id),
        category=ingredient_category(ingredient_id),
        ingredient_ids={ingredient_id},
        store_id=store_id,
        distance_km=_distance_km(rng, user_radius_km),
        price=price,
        original_price=original_price,
        brand=rng.choice(BRANDS) if rng.random() < 0.5 else None,
        is_markdown=True,
        safety_eligible=rng.random() >= P_SAFETY_INELIGIBLE,
        expires_at=expires_at,
        available_quantity=0 if rng.random() < P_OUT_OF_STOCK else rng.randint(1, 6),
        fulfillment_options=_fulfillment_options(rng),
    )


def generate_inventory(
    rng: random.Random,
    *,
    now: datetime,
    home_store_id: str,
    user_radius_km: float,
    ingredient_ids: Iterable[str] | None = None,
    markdown_supply_rate: float = P_MARKDOWN_OFFERED,
) -> list[InventoryProduct]:
    """Build a synthetic inventory snapshot for one recommendation request.

    Covers every requested ingredient (default: the full catalog) with a mix
    of full-price and, for rescue categories, markdown options — including
    deliberately-filtered cases (expired, ineligible, out of stock,
    out-of-radius, no option at all) so the safety policy is genuinely
    exercised rather than always trivially passing.
    """
    # Callers often pass a set. Sorting makes seeded generation stable across
    # processes with different PYTHONHASHSEED values.
    ids = sorted(ingredient_ids) if ingredient_ids is not None else sorted(INGREDIENTS)
    nearby_stores = [home_store_id, f"{home_store_id}_annex", "store_hub_1"]
    products: list[InventoryProduct] = []
    index = 0
    for ingredient_id in ids:
        if rng.random() < P_NO_PRODUCT_AT_ALL:
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
            )
        )
        index += 1

        if (
            ingredient_category(ingredient_id) in RESCUE_CATEGORIES
            and rng.random() < markdown_supply_rate
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
                )
            )
            index += 1
    return products
