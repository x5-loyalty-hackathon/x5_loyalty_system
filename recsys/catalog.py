"""Shared synthetic vocabulary: ingredients, categories and brands.

``recsys.profiles``, ``recsys.recipes`` and ``recsys.inventory`` all draw from
this one table so that ingredient ids, categories and brand names stay
consistent across generated receipts, recipes and inventory. Categories reuse
``app.safety.RESCUE_CATEGORIES`` rather than redefining the rescue allow-list,
so a change to the safety policy's markdown-eligible categories is
automatically reflected here.

All names are illustrative/synthetic. No real X5 catalog, pricing or
assortment data is used (see ``docs/research/recsys/synthetic-data-and-segments.md``).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.safety import RESCUE_CATEGORIES

# Categories beyond the four rescue categories (fruit/vegetable/dairy/meat,
# defined in app.safety.RESCUE_CATEGORIES) are never markdown-eligible in the
# current safety policy — that's intentional and mirrors the PoC's base
# category list in docs/research/persona_vxofi/rescue-domovoi-concept.md §9.
NON_RESCUE_CATEGORIES: tuple[str, ...] = ("egg", "pantry", "grain")

CATEGORIES: tuple[str, ...] = tuple(sorted(RESCUE_CATEGORIES)) + NON_RESCUE_CATEGORIES


@dataclass(frozen=True)
class IngredientDef:
    ingredient_id: str
    name: str
    category: str


# id -> (Russian display name, category). Deliberately a moderate, hand-picked
# vocabulary (not a bulk import) so every id is reviewable.
_INGREDIENTS: tuple[IngredientDef, ...] = (
    # dairy
    IngredientDef("milk", "Молоко", "dairy"),
    IngredientDef("cottage_cheese", "Творог", "dairy"),
    IngredientDef("sour_cream", "Сметана", "dairy"),
    IngredientDef("cheese", "Сыр", "dairy"),
    IngredientDef("kefir", "Кефир", "dairy"),
    IngredientDef("butter", "Сливочное масло", "dairy"),
    # vegetable (includes mushrooms, grouped with produce at retail)
    IngredientDef("tomato", "Томаты", "vegetable"),
    IngredientDef("zucchini", "Кабачок", "vegetable"),
    IngredientDef("onion", "Лук", "vegetable"),
    IngredientDef("potato", "Картофель", "vegetable"),
    IngredientDef("carrot", "Морковь", "vegetable"),
    IngredientDef("cucumber", "Огурцы", "vegetable"),
    IngredientDef("bell_pepper", "Болгарский перец", "vegetable"),
    IngredientDef("cabbage", "Капуста", "vegetable"),
    IngredientDef("mushroom", "Шампиньоны", "vegetable"),
    # fruit
    IngredientDef("apple", "Яблоки", "fruit"),
    IngredientDef("banana", "Бананы", "fruit"),
    IngredientDef("lemon", "Лимон", "fruit"),
    # meat
    IngredientDef("chicken", "Куриное филе", "meat"),
    IngredientDef("beef", "Говядина", "meat"),
    IngredientDef("pork", "Свинина", "meat"),
    IngredientDef("minced_meat", "Фарш говяжий", "meat"),
    # egg
    IngredientDef("egg", "Яйца", "egg"),
    # pantry (shelf-stable, never markdown in current safety policy)
    IngredientDef("flour", "Мука", "pantry"),
    IngredientDef("sugar", "Сахар", "pantry"),
    IngredientDef("vegetable_oil", "Растительное масло", "pantry"),
    IngredientDef("tomato_paste", "Томатная паста", "pantry"),
    # grain / bakery
    IngredientDef("rice", "Рис", "grain"),
    IngredientDef("pasta", "Макароны", "grain"),
    IngredientDef("buckwheat", "Гречка", "grain"),
    IngredientDef("bread", "Хлеб", "grain"),
    IngredientDef("oats", "Овсяные хлопья", "grain"),
)

INGREDIENTS: dict[str, IngredientDef] = {item.ingredient_id: item for item in _INGREDIENTS}

INGREDIENTS_BY_CATEGORY: dict[str, tuple[str, ...]] = {
    category: tuple(item.ingredient_id for item in _INGREDIENTS if item.category == category)
    for category in CATEGORIES
}

# Generic, non-trademarked placeholder brands plus "Зелёная линия", which the
# repo's own example (examples/recommendation_request.json) already uses.
BRANDS: tuple[str, ...] = (
    "Зелёная линия",
    "Фермерский дворик",
    "Хороший выбор",
    "Первым делом",
)

# Rough illustrative full price per unit (₽), used only to generate plausible
# synthetic prices/markdowns — not real X5 pricing. Labeled as such wherever
# it feeds economics output.
BASE_PRICE_RUB: dict[str, float] = {
    "milk": 89.0,
    "cottage_cheese": 129.0,
    "sour_cream": 99.0,
    "cheese": 349.0,
    "kefir": 79.0,
    "butter": 219.0,
    "tomato": 159.0,
    "zucchini": 89.0,
    "onion": 39.0,
    "potato": 49.0,
    "carrot": 45.0,
    "cucumber": 129.0,
    "bell_pepper": 179.0,
    "cabbage": 45.0,
    "mushroom": 149.0,
    "apple": 99.0,
    "banana": 89.0,
    "lemon": 119.0,
    "chicken": 279.0,
    "beef": 549.0,
    "pork": 399.0,
    "minced_meat": 429.0,
    "egg": 109.0,
    "flour": 65.0,
    "sugar": 69.0,
    "vegetable_oil": 129.0,
    "tomato_paste": 79.0,
    "rice": 99.0,
    "pasta": 89.0,
    "buckwheat": 95.0,
    "bread": 55.0,
    "oats": 85.0,
}


def ingredient_name(ingredient_id: str) -> str:
    return INGREDIENTS[ingredient_id].name


def ingredient_category(ingredient_id: str) -> str:
    return INGREDIENTS[ingredient_id].category
