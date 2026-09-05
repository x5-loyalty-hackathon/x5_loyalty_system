"""Synthetic profile generator built on four behavioral archetypes.

The archetypes (`routine` / `explorer` / `value` / `time_limited`) are the
ones already named in
``docs/research/persona_vxofi/rescue-domovoi-concept.md §6``. Each archetype
is a small parameter bundle (cadence, basket composition, discovery
acceptance, markdown affinity, repeat behavior, brand loyalty, radius,
missing-item tolerance, time budget). The parameters are literature-informed
defaults (see ``docs/research/recsys/synthetic-data-and-segments.md`` for the
Instacart/recipe-dataset grounding and FACT/INFERENCE/HYPOTHESIS labels), not
fitted on real X5 data.

``generate_population(n, seed=...)`` samples N profiles from the archetype
mixture. Requesting 10, 50 or 10,000 profiles uses the exact same generator
and the same population mixture — scaling "representatively to all X5
customers" is just drawing more samples, per the project's stated data
strategy.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.contracts import Receipt, ReceiptItem, UserProfile
from recsys.catalog import (
    BASE_PRICE_RUB,
    BRANDS,
    CATEGORIES,
    INGREDIENTS_BY_CATEGORY,
    ingredient_category,
    ingredient_name,
)
from recsys.recipes import RECIPES

MSK = timezone(timedelta(hours=3))
# Matches the `now` used in examples/recommendation_request.json so generated
# and hand-written examples stay on the same clock.
DEFAULT_NOW = datetime(2026, 9, 3, 18, 0, 0, tzinfo=MSK)
HISTORY_WINDOW_DAYS = 45


@dataclass(frozen=True)
class ArchetypeParams:
    name: str
    population_share: float
    cadence_days_mean: float
    cadence_days_std: float
    basket_size_range: tuple[int, int]
    core_categories: tuple[str, ...]
    core_category_weight: float  # combined draw probability for core categories
    discovery_acceptance: float  # P(archetype accepts an explore-mode recipe)
    markdown_affinity: float  # P(archetype prefers a markdown option when offered)
    repeat_probability: float  # P(archetype saves/repeats a recipe)
    brand_loyalty: float  # 0..1, higher = fewer distinct brands used
    radius_km_range: tuple[float, float]
    max_missing_tolerance: int  # max missing ingredients still judged relevant
    time_limit_minutes: int | None  # max acceptable prep time, None = no cap


ARCHETYPES: dict[str, ArchetypeParams] = {
    "routine": ArchetypeParams(
        name="routine",
        population_share=0.40,
        cadence_days_mean=3.0,
        cadence_days_std=1.0,
        basket_size_range=(5, 9),
        core_categories=("dairy", "vegetable", "meat"),
        core_category_weight=0.65,
        discovery_acceptance=0.15,
        markdown_affinity=0.35,
        repeat_probability=0.65,
        brand_loyalty=0.75,
        radius_km_range=(2.0, 4.0),
        max_missing_tolerance=3,
        time_limit_minutes=None,
    ),
    "explorer": ArchetypeParams(
        name="explorer",
        population_share=0.20,
        cadence_days_mean=4.0,
        cadence_days_std=1.5,
        basket_size_range=(6, 10),
        core_categories=("vegetable", "fruit", "grain"),
        core_category_weight=0.55,
        discovery_acceptance=0.65,
        markdown_affinity=0.30,
        repeat_probability=0.25,
        brand_loyalty=0.30,
        radius_km_range=(3.0, 6.0),
        max_missing_tolerance=5,
        time_limit_minutes=None,
    ),
    "value": ArchetypeParams(
        name="value",
        population_share=0.25,
        cadence_days_mean=3.5,
        cadence_days_std=1.2,
        basket_size_range=(5, 8),
        core_categories=("vegetable", "dairy", "grain"),
        core_category_weight=0.60,
        discovery_acceptance=0.30,
        markdown_affinity=0.80,
        repeat_probability=0.45,
        brand_loyalty=0.40,
        radius_km_range=(3.0, 7.0),
        max_missing_tolerance=4,
        time_limit_minutes=None,
    ),
    "time_limited": ArchetypeParams(
        name="time_limited",
        population_share=0.15,
        cadence_days_mean=2.5,
        cadence_days_std=0.8,
        basket_size_range=(3, 6),
        core_categories=("dairy", "egg", "grain"),
        core_category_weight=0.65,
        discovery_acceptance=0.10,
        markdown_affinity=0.30,
        repeat_probability=0.70,
        brand_loyalty=0.60,
        radius_km_range=(1.0, 2.5),
        max_missing_tolerance=2,
        time_limit_minutes=30,
    ),
}

assert abs(sum(a.population_share for a in ARCHETYPES.values()) - 1.0) < 1e-9


ArchetypeTable = dict[str, ArchetypeParams]


@dataclass
class SyntheticProfile:
    archetype: str
    user: UserProfile
    current_receipt: Receipt
    purchase_history: list[Receipt] = field(default_factory=list)
    now: datetime = DEFAULT_NOW


def sample_archetype(
    rng: random.Random, archetypes: ArchetypeTable | None = None
) -> ArchetypeParams:
    table = archetypes if archetypes is not None else ARCHETYPES
    names = list(table)
    weights = [table[n].population_share for n in names]
    return table[rng.choices(names, weights=weights, k=1)[0]]


def _weighted_category(rng: random.Random, params: ArchetypeParams) -> str:
    if rng.random() < params.core_category_weight:
        return rng.choice(params.core_categories)
    other = [c for c in CATEGORIES if c not in params.core_categories]
    return rng.choice(other)


def _price_with_noise(rng: random.Random, ingredient_id: str) -> float:
    base = BASE_PRICE_RUB[ingredient_id]
    return round(base * rng.uniform(0.9, 1.15), 2)


def _pick_brand(rng: random.Random, preferred: list[str], loyalty: float) -> str | None:
    if preferred and rng.random() < loyalty:
        return rng.choice(preferred)
    if rng.random() < 0.5:
        return rng.choice(BRANDS)
    return None


def _generate_receipt(
    rng: random.Random,
    *,
    receipt_id: str,
    purchased_at: datetime,
    store_id: str,
    params: ArchetypeParams,
    preferred_brands: list[str],
) -> Receipt:
    basket_size = rng.randint(*params.basket_size_range)
    items: list[ReceiptItem] = []
    used_ingredients: set[str] = set()
    attempts = 0
    while len(items) < basket_size and attempts < basket_size * 5:
        attempts += 1
        category = _weighted_category(rng, params)
        candidates = [
            i for i in INGREDIENTS_BY_CATEGORY[category] if i not in used_ingredients
        ]
        if not candidates:
            continue
        ingredient_id = rng.choice(candidates)
        used_ingredients.add(ingredient_id)

        brand = _pick_brand(rng, preferred_brands, params.brand_loyalty)
        is_markdown = rng.random() < (params.markdown_affinity * 0.3)
        # For markdown items, price down from a higher original price so
        # unit_price <= original_unit_price always holds (schema invariant).
        original_price = _price_with_noise(rng, ingredient_id) if is_markdown else None
        unit_price = (
            round(original_price * rng.uniform(0.55, 0.8), 2)
            if is_markdown and original_price is not None
            else _price_with_noise(rng, ingredient_id)
        )
        items.append(
            ReceiptItem(
                sku_id=f"{ingredient_id}_{(brand or 'generic')[:3].lower()}_{len(items)}",
                name=ingredient_name(ingredient_id),
                category=ingredient_category(ingredient_id),
                ingredient_ids={ingredient_id},
                brand=brand,
                quantity=1 if rng.random() > 0.15 else 2,
                unit_price=unit_price,
                is_markdown=is_markdown,
                original_unit_price=original_price,
            )
        )
    if not items:
        # Extremely unlikely fallback so a receipt is never empty (schema
        # requires at least one item): grab any single ingredient.
        ingredient_id = rng.choice(list(INGREDIENTS_BY_CATEGORY["pantry"]))
        items.append(
            ReceiptItem(
                sku_id=f"{ingredient_id}_fallback_0",
                name=ingredient_name(ingredient_id),
                category=ingredient_category(ingredient_id),
                ingredient_ids={ingredient_id},
                quantity=1,
                unit_price=_price_with_noise(rng, ingredient_id),
            )
        )
    return Receipt(
        receipt_id=receipt_id,
        purchased_at=purchased_at,
        store_id=store_id,
        items=items,
    )


def _sample_saved_recipes(rng: random.Random, params: ArchetypeParams) -> set[str]:
    if rng.random() > params.repeat_probability:
        return set()
    matching = [
        recipe.recipe_id
        for recipe in RECIPES
        if any(ing.category in params.core_categories for ing in recipe.ingredients)
    ]
    if not matching:
        return set()
    count = rng.choice([1, 1, 2])
    return set(rng.sample(matching, k=min(count, len(matching))))


def generate_profile(
    rng: random.Random,
    index: int,
    now: datetime = DEFAULT_NOW,
    *,
    archetypes: ArchetypeTable | None = None,
) -> SyntheticProfile:
    """Sample one profile.

    ``archetypes`` lets a caller run the same generator inside a different
    behavioural world (``recsys.regimes``) without redefining the generator.
    Defaults to the module-level ``ARCHETYPES``, so existing callers are
    unaffected.
    """
    params = sample_archetype(rng, archetypes)
    user_id = f"synthetic_{params.name}_{index:04d}"
    store_id = f"store_{10 + (index % 12)}"

    preferred_brands = (
        [rng.choice(BRANDS)] if rng.random() < params.brand_loyalty else rng.sample(list(BRANDS), k=2)
    )

    n_receipts = max(2, round(HISTORY_WINDOW_DAYS / params.cadence_days_mean))
    offsets_days = sorted(
        max(0.2, rng.gauss(i * params.cadence_days_mean, params.cadence_days_std))
        for i in range(1, n_receipts + 1)
    )
    history: list[Receipt] = []
    history_categories: list[str] = []
    for i, offset in enumerate(offsets_days):
        purchased_at = now - timedelta(days=HISTORY_WINDOW_DAYS - offset)
        receipt = _generate_receipt(
            rng,
            receipt_id=f"{user_id}_hist_{i:03d}",
            purchased_at=purchased_at,
            store_id=store_id,
            params=params,
            preferred_brands=preferred_brands,
        )
        history.append(receipt)
        history_categories.extend(item.category for item in receipt.items)

    current_receipt = _generate_receipt(
        rng,
        receipt_id=f"{user_id}_current",
        purchased_at=now - timedelta(hours=rng.uniform(0.5, 6)),
        store_id=store_id,
        params=params,
        preferred_brands=preferred_brands,
    )

    excluded_categories: set[str] = set()
    if rng.random() < 0.15:
        excluded_categories = {rng.choice([c for c in CATEGORIES if c not in params.core_categories])}
    excluded_ingredient_ids: set[str] = set()
    if rng.random() < 0.15:
        pool = [i for cat in CATEGORIES for i in INGREDIENTS_BY_CATEGORY[cat]]
        excluded_ingredient_ids = {rng.choice(pool)}

    user = UserProfile(
        user_id=user_id,
        radius_km=round(rng.uniform(*params.radius_km_range), 1),
        excluded_categories=excluded_categories,
        excluded_ingredient_ids=excluded_ingredient_ids,
        saved_recipe_ids=_sample_saved_recipes(rng, params),
        history_categories=sorted(set(history_categories)),
        preferred_brands=preferred_brands,
    )

    return SyntheticProfile(
        archetype=params.name,
        user=user,
        current_receipt=current_receipt,
        purchase_history=history,
        now=now,
    )


def generate_population(
    n: int,
    *,
    seed: int = 42,
    now: datetime = DEFAULT_NOW,
    archetypes: ArchetypeTable | None = None,
) -> list[SyntheticProfile]:
    """Sample N profiles from the archetype mixture. Deterministic given seed."""
    rng = random.Random(seed)
    return [generate_profile(rng, i, now=now, archetypes=archetypes) for i in range(n)]


def generate_balanced_sample(
    per_archetype: int,
    *,
    seed: int = 7,
    now: datetime = DEFAULT_NOW,
) -> list[SyntheticProfile]:
    """Deterministically sample an equal number of profiles per archetype.

    Used for the committed example set so every archetype is visibly
    represented regardless of population weighting.
    """
    rng = random.Random(seed)
    profiles: list[SyntheticProfile] = []
    index = 0
    for name in ARCHETYPES:
        collected = 0
        while collected < per_archetype:
            candidate = generate_profile(rng, index, now=now)
            index += 1
            if candidate.archetype != name:
                continue
            profiles.append(candidate)
            collected += 1
    return profiles
