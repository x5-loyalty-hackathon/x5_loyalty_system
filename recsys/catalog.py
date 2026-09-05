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

import json
from dataclasses import dataclass
from pathlib import Path

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
    #: Spices, dried herbs and other flavourings a cook adds "по вкусу".
    #: Recipes list them like any other ingredient, but they are never
    #: required: a missing bay leaf must not make a dinner candidate
    #: unavailable (see ``app.service`` where only required ingredients gate a
    #: recommendation). Marked here rather than in ``recsys.recipes`` so the
    #: same item cannot be a seasoning in one recipe and a hard requirement in
    #: the next.
    is_seasoning: bool = False


# id -> (Russian display name, category).  This is still a hand-curated
# vocabulary: the recipe source ``Ингредиенты .txt`` was normalized into this
# table so every item can be resolved to a synthetic SKU in the demo.
_INGREDIENTS: tuple[IngredientDef, ...] = (
    # dairy
    IngredientDef("milk", "Молоко", "dairy"),
    IngredientDef("cottage_cheese", "Творог", "dairy"),
    IngredientDef("sour_cream", "Сметана", "dairy"),
    IngredientDef("cheese", "Сыр", "dairy"),
    IngredientDef("kefir", "Кефир", "dairy"),
    IngredientDef("butter", "Сливочное масло", "dairy"),
    IngredientDef("greek_yogurt", "Греческий йогурт", "dairy"),
    IngredientDef("processed_cheese", "Сыр плавленый", "dairy"),
    IngredientDef("feta", "Фета", "dairy"),
    IngredientDef("parmesan", "Пармезан", "dairy"),
    IngredientDef("cream", "Сливки", "dairy"),
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
    IngredientDef("green_beans", "Стручковая фасоль", "vegetable"),
    IngredientDef("vegetable_mix", "Овощная смесь", "vegetable"),
    IngredientDef("garlic", "Чеснок", "vegetable"),
    IngredientDef("chili_pepper", "Перец чили", "vegetable", is_seasoning=True),
    IngredientDef("beetroot", "Свёкла", "vegetable"),
    IngredientDef("parsley_root", "Корень петрушки", "vegetable"),
    IngredientDef("green_onion", "Лук зелёный", "vegetable"),
    IngredientDef("romaine_lettuce", "Салат романо", "vegetable"),
    IngredientDef("cherry_tomato", "Томаты черри", "vegetable"),
    IngredientDef("dill", "Укроп", "vegetable", is_seasoning=True),
    IngredientDef("parsley", "Петрушка", "vegetable", is_seasoning=True),
    IngredientDef("sauerkraut", "Капуста квашеная", "vegetable"),
    IngredientDef("pumpkin", "Тыква", "vegetable"),
    # fruit
    IngredientDef("apple", "Яблоки", "fruit"),
    IngredientDef("banana", "Бананы", "fruit"),
    IngredientDef("lemon", "Лимон", "fruit"),
    IngredientDef("berries", "Ягоды", "fruit"),
    IngredientDef("seasonal_fruit", "Сезонные фрукты", "fruit"),
    # meat
    IngredientDef("chicken", "Куриное филе", "meat"),
    IngredientDef("beef", "Говядина", "meat"),
    IngredientDef("pork", "Свинина", "meat"),
    IngredientDef("minced_meat", "Фарш говяжий", "meat"),
    IngredientDef("cutlet_semi_finished", "Котлеты-полуфабрикаты", "meat"),
    IngredientDef("anchovy", "Анчоусы", "meat"),
    IngredientDef("herring", "Сельдь солёная", "meat"),
    IngredientDef("boiled_sausage", "Колбаса варёная", "meat"),
    IngredientDef("smoked_meats", "Копчёности мясные", "meat"),
    # egg
    IngredientDef("egg", "Яйца", "egg"),
    # pantry (shelf-stable, never markdown in current safety policy)
    IngredientDef("flour", "Мука", "pantry"),
    IngredientDef("sugar", "Сахар", "pantry"),
    IngredientDef("vegetable_oil", "Растительное масло", "pantry"),
    IngredientDef("tomato_paste", "Томатная паста", "pantry"),
    IngredientDef("salt", "Соль", "pantry", is_seasoning=True),
    IngredientDef("black_pepper", "Перец чёрный молотый", "pantry", is_seasoning=True),
    IngredientDef("peppercorn", "Перец чёрный горошком", "pantry", is_seasoning=True),
    IngredientDef("allspice", "Перец душистый", "pantry", is_seasoning=True),
    IngredientDef("baking_powder", "Разрыхлитель", "pantry"),
    IngredientDef("raisins", "Изюм", "pantry"),
    IngredientDef("vanilla_sugar", "Сахар ванильный", "pantry", is_seasoning=True),
    IngredientDef("peanut_butter", "Арахисовая паста", "pantry"),
    IngredientDef("honey", "Мёд", "pantry"),
    IngredientDef("nuts", "Орехи", "pantry"),
    IngredientDef("chicken_seasoning", "Приправа для курицы", "pantry", is_seasoning=True),
    IngredientDef("dried_herbs", "Сушёные травы", "pantry", is_seasoning=True),
    IngredientDef("bouillon_cube", "Бульонный кубик", "pantry", is_seasoning=True),
    IngredientDef("basil", "Базилик", "pantry", is_seasoning=True),
    IngredientDef("pilaf_seasoning", "Приправа для плова", "pantry", is_seasoning=True),
    IngredientDef("cumin", "Зира", "pantry", is_seasoning=True),
    IngredientDef("barberry", "Барбарис сушёный", "pantry", is_seasoning=True),
    IngredientDef("dried_apricots", "Курага", "pantry"),
    IngredientDef("turmeric", "Куркума", "pantry", is_seasoning=True),
    IngredientDef("paprika", "Паприка", "pantry", is_seasoning=True),
    IngredientDef("bay_leaf", "Лавровый лист", "pantry", is_seasoning=True),
    IngredientDef("vinegar", "Уксус", "pantry"),
    IngredientDef("oregano", "Орегано", "pantry", is_seasoning=True),
    IngredientDef("olive_oil", "Оливковое масло", "pantry"),
    IngredientDef("olives", "Оливки", "pantry"),
    IngredientDef("dijon_mustard", "Горчица дижонская", "pantry"),
    IngredientDef("caesar_dressing", "Соус Цезарь", "pantry"),
    IngredientDef("cinnamon", "Корица", "pantry", is_seasoning=True),
    IngredientDef("mayonnaise", "Майонез", "pantry"),
    IngredientDef("green_peas", "Горошек зелёный консервированный", "pantry"),
    IngredientDef("pickled_cucumber", "Огурцы солёные", "pantry"),
    IngredientDef("soy_sauce", "Соус соевый", "pantry"),
    IngredientDef("teriyaki_sauce", "Соус терияки", "pantry"),
    IngredientDef("korean_seasoning", "Приправа для моркови по-корейски", "pantry", is_seasoning=True),
    IngredientDef("chickpeas", "Нут", "pantry"),
    IngredientDef("tahini", "Паста кунжутная тахини", "pantry"),
    # grain / bakery
    IngredientDef("rice", "Рис", "grain"),
    IngredientDef("pasta", "Макароны", "grain"),
    IngredientDef("buckwheat", "Гречка", "grain"),
    IngredientDef("bread", "Хлеб", "grain"),
    IngredientDef("oats", "Овсяные хлопья", "grain"),
    IngredientDef("breadcrumbs", "Панировочные сухари", "grain"),
    IngredientDef("baguette", "Багет", "grain"),
    IngredientDef("croutons", "Сухарики", "grain"),
    IngredientDef("noodles", "Лапша пшеничная", "grain"),
    IngredientDef("dried_peas", "Горох сухой", "grain"),
)

INGREDIENTS: dict[str, IngredientDef] = {item.ingredient_id: item for item in _INGREDIENTS}

#: Ingredients a recipe adds "по вкусу" rather than measuring.
SEASONING_IDS: frozenset[str] = frozenset(
    item.ingredient_id for item in _INGREDIENTS if item.is_seasoning
)

#: Unit shown for a seasoning instead of a quantity.
TO_TASTE = "по вкусу"

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

#: Aggregate price reference from recsys-benchmark@c28b613. Its calibration
#: script/data remain on that branch; this JSON is not live SKU pricing.
#: See docs/integration-handoff.md for what is and is not reproduced here.
PRICE_REFERENCE: dict = json.loads(
    (Path(__file__).with_name("data") / "price_reference.json").read_text(
        encoding="utf-8"
    )
)

REFERENCE_MEDIAN_PRICE_RUB: float = PRICE_REFERENCE["percentiles_rub"]["50"]

#: How far ``BASE_PRICE_RUB`` sits above the 2018–2019 reference. This is an
#: comparison band inherited from the source experiment, not a measured
#: inflation estimate or an integration quality gate.
PRICE_ERA_MULTIPLIER_BAND: tuple[float, float] = (1.8, 3.0)

# Per-unit full price (₽) for one ingredient, for a 2026 Moscow basket.
#
# These are still hand-written per item — no dataset maps "молоко" to a price,
# because the transaction dump's product ids are hashed. What they are not any
# more is unanchored: the source experiment compares the aggregate distribution
# to PRICE_REFERENCE. API 1.2 has no price_is_estimate field: generated stock
# and the mobile fixture are explicitly synthetic, not observed store offers.
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
    "greek_yogurt": 119.0, "processed_cheese": 129.0, "feta": 229.0, "parmesan": 399.0,
    "green_beans": 159.0, "vegetable_mix": 149.0, "garlic": 69.0, "chili_pepper": 129.0,
    "beetroot": 49.0, "parsley_root": 89.0, "green_onion": 69.0, "romaine_lettuce": 149.0,
    "cherry_tomato": 229.0, "berries": 279.0, "seasonal_fruit": 199.0, "dill": 59.0, "parsley": 59.0,
    "cutlet_semi_finished": 299.0, "anchovy": 199.0,
    "salt": 39.0, "black_pepper": 89.0, "peppercorn": 99.0, "allspice": 99.0,
    "baking_powder": 49.0, "raisins": 139.0, "vanilla_sugar": 39.0, "peanut_butter": 249.0,
    "honey": 329.0, "nuts": 349.0, "chicken_seasoning": 69.0, "dried_herbs": 79.0,
    "bouillon_cube": 59.0, "basil": 79.0, "pilaf_seasoning": 79.0, "cumin": 89.0,
    "barberry": 129.0, "dried_apricots": 239.0, "turmeric": 79.0, "paprika": 79.0,
    "bay_leaf": 59.0, "vinegar": 89.0, "oregano": 79.0, "olive_oil": 499.0, "olives": 199.0,
    "dijon_mustard": 149.0, "caesar_dressing": 179.0, "cinnamon": 69.0,
    "breadcrumbs": 89.0, "baguette": 79.0, "croutons": 69.0,
    # Ingredients added for the ready-food-paired recipes (see
    # recsys/ready_food_pairs.py). Same illustrative-price caveat applies.
    "cream": 149.0, "sauerkraut": 119.0, "pumpkin": 79.0,
    "herring": 229.0, "boiled_sausage": 289.0, "smoked_meats": 449.0,
    "mayonnaise": 149.0, "green_peas": 89.0, "pickled_cucumber": 139.0,
    "soy_sauce": 129.0, "teriyaki_sauce": 189.0, "korean_seasoning": 69.0,
    "chickpeas": 149.0, "tahini": 349.0,
    "noodles": 119.0, "dried_peas": 79.0,
}


#: Approximate amount of one ingredient in a **2-serving** dish, as
#: ``(quantity, unit)``. Recipes scale this by their own ``servings`` and may
#: override a single item where the dish demands it (see
#: ``recsys.recipes._recipe``).
#:
#: These are cook's approximations, not nutritional norms: the point is that a
#: shopping list says "300 г курицы" instead of "курица", not that the numbers
#: are laboratory-accurate. Seasonings deliberately have no entry — they are
#: carried as "по вкусу" and never quantified.
PORTION_PER_TWO_SERVINGS: dict[str, tuple[float, str]] = {
    # dairy
    "milk": (200, "мл"), "cottage_cheese": (250, "г"), "sour_cream": (100, "г"),
    "cheese": (100, "г"), "kefir": (200, "мл"), "butter": (30, "г"),
    "greek_yogurt": (150, "г"), "processed_cheese": (100, "г"), "feta": (100, "г"),
    "parmesan": (50, "г"), "cream": (200, "мл"),
    # vegetable
    "tomato": (200, "г"), "zucchini": (200, "г"), "onion": (1, "шт"),
    "potato": (300, "г"), "carrot": (100, "г"), "cucumber": (150, "г"),
    "bell_pepper": (1, "шт"), "cabbage": (200, "г"), "mushroom": (200, "г"),
    "green_beans": (150, "г"), "vegetable_mix": (200, "г"), "garlic": (2, "зубч."),
    "beetroot": (200, "г"), "parsley_root": (30, "г"), "green_onion": (20, "г"),
    "romaine_lettuce": (100, "г"), "cherry_tomato": (100, "г"),
    "sauerkraut": (150, "г"), "pumpkin": (400, "г"),
    # fruit
    "apple": (2, "шт"), "banana": (1, "шт"), "lemon": (0.5, "шт"),
    "berries": (100, "г"), "seasonal_fruit": (150, "г"),
    # meat
    "chicken": (300, "г"), "beef": (300, "г"), "pork": (300, "г"),
    "minced_meat": (300, "г"), "cutlet_semi_finished": (2, "шт"),
    "anchovy": (20, "г"), "herring": (150, "г"), "boiled_sausage": (150, "г"),
    "smoked_meats": (150, "г"),
    # egg
    "egg": (2, "шт"),
    # pantry
    "flour": (100, "г"), "sugar": (50, "г"), "vegetable_oil": (2, "ст. л."),
    "tomato_paste": (2, "ст. л."), "baking_powder": (1, "ч. л."), "raisins": (50, "г"),
    "peanut_butter": (1, "ст. л."), "honey": (1, "ст. л."), "nuts": (30, "г"),
    "vinegar": (1, "ст. л."), "olive_oil": (2, "ст. л."), "olives": (50, "г"),
    "dijon_mustard": (1, "ч. л."), "caesar_dressing": (50, "мл"),
    "mayonnaise": (100, "г"), "green_peas": (100, "г"), "pickled_cucumber": (150, "г"),
    "soy_sauce": (2, "ст. л."), "teriyaki_sauce": (3, "ст. л."),
    "chickpeas": (250, "г"), "tahini": (2, "ст. л."), "dried_apricots": (50, "г"),
    # grain
    "rice": (150, "г"), "pasta": (200, "г"), "buckwheat": (150, "г"),
    "bread": (2, "ломтика"), "oats": (80, "г"), "breadcrumbs": (50, "г"),
    "baguette": (100, "г"), "croutons": (30, "г"), "noodles": (200, "г"),
    "dried_peas": (200, "г"),
}

#: Units counted in whole-ish items rather than mass, so scaling rounds them
#: to a half rather than to the nearest ten.
COUNTED_UNITS: frozenset[str] = frozenset(
    {"шт", "зубч.", "ст. л.", "ч. л.", "ломтика"}
)

DEFAULT_SERVINGS = 2


def ingredient_portion(
    ingredient_id: str, servings: int = DEFAULT_SERVINGS
) -> tuple[float, str] | None:
    """Approximate amount of ``ingredient_id`` for ``servings`` people.

    Returns ``None`` for seasonings, which are never quantified.
    """
    entry = PORTION_PER_TWO_SERVINGS.get(ingredient_id)
    if entry is None:
        return None
    quantity, unit = entry
    scaled = quantity * servings / DEFAULT_SERVINGS
    if unit in COUNTED_UNITS:
        scaled = round(scaled * 2) / 2
        return (int(scaled) if scaled == int(scaled) else scaled), unit
    if scaled >= 50:
        scaled = round(scaled / 10) * 10
    else:
        scaled = round(scaled / 5) * 5 or 5
    return float(scaled), unit


def ingredient_name(ingredient_id: str) -> str:
    return INGREDIENTS[ingredient_id].name


def ingredient_category(ingredient_id: str) -> str:
    return INGREDIENTS[ingredient_id].category


def is_seasoning(ingredient_id: str) -> bool:
    return INGREDIENTS[ingredient_id].is_seasoning
