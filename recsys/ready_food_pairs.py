"""Recipe ↔ ready-meal pairs, resolved against real X5 PLUs.

Each pair says: "this recipe has a prepared counterpart X5 actually sells", so
a recommendation can offer both sides — cook it from a (possibly marked-down)
basket, or buy the ready portion. Unlike ``recsys.sku_mapping``, whose SKUs are
openly synthetic, the products here carry the retailer's real ``plu``, taken
from the September 2026 snapshot in ``recsys/data/ready_food_catalog.json``
(rebuild it with ``python -m recsys.extract_ready_food``).

A PLU is evidence that a product existed in that snapshot, not a live
assortment feed: it is scoped by ``SNAPSHOT_IDS``.

There is no geography in this module, deliberately. The demo is Moscow-only and
``recsys.extract_ready_food`` has already filtered the snapshot down to it, so
every product here is a Moscow product and a city field would be a column with
one value. The wider snapshot does show real regional variation — no SKU in it
reached all 15 Пятёрочка cities — but modelling that only becomes worth doing
when the demo covers more than one city.

How a meal is matched to a recipe
---------------------------------
Two signals, with deliberately different jobs:

``name_pattern``
    The classifier. Product names are the only field present for 100% of the
    catalog, so this is what actually finds candidates.

``Тип блюда`` (``dish_type``)
    The veto. It comes from ``detail_json['attributes']`` — the product card X5
    serves for the item — and is therefore authoritative where it exists, but
    it exists for only ~6% of the catalog (35 of 601 Moscow products; the
    collector captured full cards for a fraction of the run). A candidate is
    dropped when
    its card contradicts the recipe's own ``dish_type``, which is how
    "Сэндвич-ролл Цезарь" stops being offered as a counterpart to a Цезарь
    salad. Where there is no card, the name match stands on its own.

The facets are never used as a positive key on their own: most carded products
are just "Основное блюдо", which would pair every Russian main course with every
other one. ``Кухня`` is recorded and reported but not used to veto —
its values are inconsistent across near-identical dishes (a Цезарь is filed
under both Европейская and Итальянская), so it would reject correct matches.
"""

from __future__ import annotations

import json
import re
import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

from app.contracts import ReadyMealOption
from recsys.recipes import RECIPES_BY_ID

CATALOG_PATH = Path(__file__).with_name("data") / "ready_food_catalog.json"

#: Card dish types that do not contradict a recipe's own ``dish_type``. Only
#: recipe dish types that actually occur in the catalog need an entry; a recipe
#: whose dish type is absent here vetoes nothing, because we have no evidence
#: about what the retailer would call it.
COMPATIBLE_DISH_TYPES: dict[str, frozenset[str]] = {
    "Салат": frozenset({"Салат", "Закуска"}),
    "Закуска": frozenset({"Закуска", "Салат", "Гарнир"}),
    "Суп": frozenset({"Суп"}),
    "Основное блюдо": frozenset({"Основное блюдо", "Гарнир"}),
    "Гарнир": frozenset({"Гарнир", "Основное блюдо"}),
    "Паста": frozenset({"Паста", "Основное блюдо"}),
    "Блины": frozenset({"Блины"}),
    "Сырники": frozenset({"Сырники", "Оладьи"}),
    "Оладьи": frozenset({"Оладьи", "Сырники"}),
    "Запеканка": frozenset({"Запеканка"}),
    "Каша": frozenset({"Каша"}),
    "Омлет": frozenset({"Омлет"}),
    "Сэндвич": frozenset({"Сэндвич", "Сэндвич-ролл"}),
    "Выпечка": frozenset({"Выпечка"}),
}


@dataclass(frozen=True)
class ReadyMeal:
    """One prepared product, identified by the retailer's own PLU."""

    chain: str
    plu: str
    name: str
    median_price_rub: float | None
    #: From the product card's "Тип блюда"/"Кухня"; ``None`` when the collector
    #: did not capture a card for this product.
    dish_type: str | None = None
    cuisine: str | None = None

    @property
    def has_card_facets(self) -> bool:
        return self.dish_type is not None or self.cuisine is not None


def _load_catalog(
    catalog_path: Path = CATALOG_PATH,
) -> tuple[tuple[ReadyMeal, ...], tuple[str, ...]]:
    """Load the derived catalog with an actionable schema error."""
    try:
        raw: Any = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read ready-food catalog {catalog_path}: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError("ready-food catalog must be a JSON object")

    snapshot_ids = raw.get("snapshot_ids")
    products = raw.get("products")
    if not isinstance(snapshot_ids, list) or not all(
        isinstance(snapshot_id, str) and snapshot_id for snapshot_id in snapshot_ids
    ):
        raise ValueError("ready-food catalog snapshot_ids must be non-empty strings")
    if not isinstance(products, list):
        raise ValueError("ready-food catalog products must be a list")

    meals: list[ReadyMeal] = []
    for index, item in enumerate(products):
        if not isinstance(item, dict):
            raise ValueError(f"ready-food catalog products[{index}] must be an object")
        for field in ("chain", "plu", "name"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ValueError(
                    f"ready-food catalog products[{index}].{field} must be a non-empty string"
                )
        price = item.get("median_price_rub")
        if price is not None and (not isinstance(price, (int, float)) or price <= 0):
            raise ValueError(
                f"ready-food catalog products[{index}].median_price_rub must be positive or null"
            )
        facets = {field: item.get(field) for field in ("dish_type", "cuisine")}
        if any(value is not None and not isinstance(value, str) for value in facets.values()):
            raise ValueError(
                f"ready-food catalog products[{index}] facets must be strings or null"
            )
        meals.append(
            ReadyMeal(
                chain=item["chain"],
                plu=item["plu"],
                name=item["name"],
                median_price_rub=float(price) if price is not None else None,
                dish_type=facets["dish_type"],
                cuisine=facets["cuisine"],
            )
        )
    return tuple(meals), tuple(snapshot_ids)


READY_FOOD_CATALOG, SNAPSHOT_IDS = _load_catalog()

#: Lowercased names, computed once: the classifiers below scan the whole
#: catalog and re-lowering per pattern dominated import time.
_LOWER_NAMES: tuple[str, ...] = tuple(meal.name.lower() for meal in READY_FOOD_CATALOG)


@dataclass(frozen=True)
class ReadyFoodPair:
    """One home recipe and the ready meals that are its counterpart."""

    recipe_id: str
    concept: str
    name_pattern: str
    meals: tuple[ReadyMeal, ...]

    @property
    def plus(self) -> tuple[str, ...]:
        """The real ``chain:plu`` identifiers behind this pair."""
        return tuple(f"{meal.chain}:{meal.plu}" for meal in self.meals)

    @property
    def chains(self) -> frozenset[str]:
        """Chains offering a counterpart — both, or only one of them."""
        return frozenset(meal.chain for meal in self.meals)

    @property
    def facet_confirmed_count(self) -> int:
        """Meals whose product card carried "Тип блюда"/"Кухня"."""
        return sum(1 for meal in self.meals if meal.has_card_facets)

    @cached_property
    def median_price_rub(self) -> float | None:
        prices = [m.median_price_rub for m in self.meals if m.median_price_rub is not None]
        return round(statistics.median(prices), 2) if prices else None

    def cheapest_meal(self) -> ReadyMeal | None:
        """The lowest-priced counterpart — the one a "buy it ready" offer shows."""
        priced = [m for m in self.meals if m.median_price_rub is not None]
        return min(priced, key=lambda m: m.median_price_rub) if priced else None


@dataclass(frozen=True)
class PairDefinition:
    """How one recipe finds its counterparts in the product catalog.

    ``name_pattern`` alone proved too coarse. Product names are the only field
    present for the whole catalog, but a single "does this word appear" test
    cannot tell a dish from a different dish that shares a word, and the card
    facets that could veto it exist for ~6% of products. Two measured
    consequences, both of which reached the generated catalog document as
    "готовый аналог":

    * "Гречка с грибами" was paired with "Гречка отварная со сливочным маслом"
      — none of its nine matches contained a mushroom at all.
    * "Паста с томатным соусом" was paired with "Паста Санта Бремор с тунцом и
      лососем", a fish spread for sandwiches, because it was the cheapest thing
      matching the word "паста".

    So a definition may also carry:

    ``require``
        A second pattern the name must *also* match — the recipe's defining
        ingredient. This is what makes a pair mean "the same dish" rather than
        "a dish from the same family".
    ``exclude``
        A pattern that disqualifies a name outright, for false friends that
        share the keyword but belong to another product category entirely.

    Where ``require`` leaves a recipe with no counterpart, that is the honest
    answer and the recipe belongs in ``RECIPES_WITHOUT_READY_FOOD_PAIR`` with
    a stated reason, not paired with an approximation.
    """

    recipe_id: str
    concept: str
    name_pattern: str
    require: str | None = None
    exclude: str | None = None


# Concepts a recipe has no counterpart for are listed in
# RECIPES_WITHOUT_READY_FOOD_PAIR below.
_PAIR_DEFINITIONS: tuple[PairDefinition, ...] = tuple(
    PairDefinition(*entry) for entry in (
    ("bliny", "Блины и блинчики", r"блин"),
    ("meat_cutlets_with_mash", "Котлеты и тефтели с гарниром", r"котлет|биточек|тефтел|шницел|фрикадельк"),
    ("cheese_tomato_toast", "Сэндвичи и тосты", r"сэндвич|сендвич|тост"),
    # "Паста" is both a dish and a spread. The Санта Бремор / Балтийский Берег
    # seafood spreads are sandwich paste, not a pasta dish, and being the
    # cheapest matches they took the headline offer.
    (
        "pasta_tomato",
        "Паста и лазанья",
        r"\bпаста |макарон|спагетти|фузилли|фарфале|лазань",
        None,
        r"санта бремор|балтийский берег|морепродукт|криль|creme le mare|мидии",
    ),
    # "по-корейски" is a preparation, not a vegetable: it also matches спаржа,
    # капуста and фунчоза по-корейски.
    (
        "korean_carrot",
        "Морковь по-корейски",
        r"по-корейски|по корейски",
        r"морков",
        r"куриц",
    ),
    ("syrniki", "Сырники", r"сырник|сырничк"),
    # A bare "гриль" matched "Овощи гриль" (no meat), "Филе индейки гриль"
    # (turkey) and a grilled-pepper sandwich, while the exact counterpart
    # ("Шашлык куриный гриль") sat in the same pool. The pattern is now the
    # skewer/wing forms themselves; "куриное" is not *required*, because a
    # wing is chicken by default and naming it is optional ("Крыло гриль"),
    # so the other meats are excluded instead.
    (
        "grilled_chicken_skewers",
        "Куриный шашлык и крылья",
        r"шашлык|крылышк|крыло|голень",
        None,
        r"свинин|индейк|баранин|говядин|овощ",
    ),
    ("teriyaki_chicken_noodles", "Азиатская лапша и курица терияки", r"терияки|лапша вок|удон|\bвок\b"),
    (
        "chicken_mushroom_salad",
        "Салат с курицей и грибами",
        r"салат.*(курице|курицей|курочка)|черепаха|метёлк|метелк",
        r"гриб|шампиньон",
        None,
    ),
    ("caesar_salad", "Салат Цезарь", r"цезарь"),
    ("cottage_cheese_bake", "Творожная запеканка", r"запеканк"),
    ("healthy_cottage_cheese_bake", "Творожная запеканка", r"запеканк"),
    ("oatmeal_with_banana", "Молочные каши", r"\bкаша\b|\bкаши\b"),
    ("borsch", "Борщ", r"борщ"),
    ("homemade_chicken_nuggets", "Наггетсы", r"наггетс|круггетс|стрипс"),
    ("olivier_salad", "Салат Оливье и Столичный", r"оливье|салат столичн"),
    ("chicken_pilaf", "Плов", r"плов"),
    ("beef_pilaf", "Плов", r"плов"),
    ("meat_french_style", "Мясо по-французски и запечённое с картофелем", r"по-французски|отбивн|картофель томлен|томлен.*картоф"),
    ("vinegret", "Винегрет", r"винегрет"),
    ("chicken_and_vegetables", "Курица с овощами и рисом", r"курица.*овощ|кур.*с рисом и овощ"),
    ("herring_under_fur_coat", "Сельдь под шубой", r"под шубой"),
    ("hummus", "Хумус", r"хумус"),
    ("solyanka", "Солянка", r"солянк"),
    ("pea_soup_with_smoked_meats", "Гороховый суп с копчёностями", r"горохов"),
    ("chicken_potato_soup", "Куриный суп с лапшой", r"суп куриный|куриный суп|суп с лапшой|лапша.*суп"),
    ("chicken_vegetable_stew", "Рагу и жаркое", r"рагу|чахохбили|жарко"),
    ("pumpkin_cream_soup", "Крем-суп из тыквы", r"(крем-суп|суп-пюре|суп).*тыкв|тыкв.*(крем-суп|суп-пюре|суп)"),
    ("vegetable_omelette", "Омлет", r"омлет"),
    )
)

#: Recipes with no prepared counterpart in the Moscow slice. Kept explicit so
#: the absence stays a reviewed fact rather than a lookup that silently misses:
#: ``cheese_soup`` and ``greek_salad`` matched zero products, ``apple_pie`` and
#: ``carrot_fritters`` matched only false friends (a puff pastry and a chicken
#: patty), ``chicken_vegetable_stew`` has counterparts elsewhere in the snapshot
#: but none in Moscow, and the last three are too generic to map onto.
RECIPES_WITHOUT_READY_FOOD_PAIR: frozenset[str] = frozenset(
    {
        "cheese_soup",
        "greek_salad",
        "apple_pie",
        "carrot_fritters",
        # Nine products matched the word "гречка"; not one of them contained a
        # mushroom. The dish exists in the snapshot only as buckwheat with
        # butter, turkey or liver, so under "a pair means the same dish" this
        # recipe has no counterpart rather than an approximate one.
        "buckwheat_with_mushrooms",
        "chicken_vegetable_stew",
        "braised_pork_with_vegetables",
        "chicken_cucumber_salad",
        "vegetable_cheese_salad",
        # Added for docs/research/recsys/experiment-3-catalog-coverage-report.md:
        # short everyday dishes too generic/homemade to have a distinct
        # prepared-meal counterpart in the September 2026 snapshot (no attempt
        # was made to find one — see that report's "угрозы валидности").
        "fried_chicken_breast",
        "pork_chops",
        "braised_beef_with_onion",
        "fried_minced_meat_with_onion",
        "pan_fried_semi_finished_cutlets",
        "chicken_in_sour_cream",
        "fried_zucchini_with_cheese",
        "braised_cabbage",
        "rice_milk_porridge",
        "cottage_cheese_with_sour_cream",
    }
)


def _card_contradicts(recipe_dish_type: str | None, meal: ReadyMeal) -> bool:
    """True when the product card says this meal is a different kind of dish."""
    if meal.dish_type is None or recipe_dish_type is None:
        return False
    compatible = COMPATIBLE_DISH_TYPES.get(recipe_dish_type)
    if compatible is None:
        return False
    return meal.dish_type not in compatible


def _build_pairs() -> tuple[ReadyFoodPair, ...]:
    pairs: list[ReadyFoodPair] = []
    for definition in _PAIR_DEFINITIONS:
        recipe = RECIPES_BY_ID[definition.recipe_id]
        compiled = re.compile(definition.name_pattern)
        required = re.compile(definition.require) if definition.require else None
        excluded = re.compile(definition.exclude) if definition.exclude else None
        meals = tuple(
            meal
            for meal, lowered in zip(READY_FOOD_CATALOG, _LOWER_NAMES)
            if compiled.search(lowered)
            and (required is None or required.search(lowered))
            and (excluded is None or not excluded.search(lowered))
            and not _card_contradicts(recipe.dish_type, meal)
        )
        if not meals:
            continue
        pairs.append(
            ReadyFoodPair(
                recipe_id=definition.recipe_id,
                concept=definition.concept,
                name_pattern=definition.name_pattern,
                meals=meals,
            )
        )
    pairs.sort(key=lambda pair: (-len(pair.meals), pair.recipe_id))
    return tuple(pairs)


READY_FOOD_PAIRS: tuple[ReadyFoodPair, ...] = _build_pairs()

PAIRS_BY_RECIPE_ID: dict[str, ReadyFoodPair] = {p.recipe_id: p for p in READY_FOOD_PAIRS}

PAIRS_BY_PLU: dict[str, tuple[ReadyFoodPair, ...]] = {}
for _pair in READY_FOOD_PAIRS:
    for _key in _pair.plus:
        PAIRS_BY_PLU[_key] = (*PAIRS_BY_PLU.get(_key, ()), _pair)


def pair_for_recipe(recipe_id: str) -> ReadyFoodPair | None:
    """Return the ready-meal pair for ``recipe_id``, or ``None`` if it has none."""
    return PAIRS_BY_RECIPE_ID.get(recipe_id)


def pairs_for_plu(chain: str, plu: str) -> tuple[ReadyFoodPair, ...]:
    """Return the recipes a real ready-meal PLU is a counterpart to.

    More than one can apply — "Плов с курицей" is a counterpart to both pilaf
    recipes — so callers get all of them and pick by their own criteria.
    """
    return PAIRS_BY_PLU.get(f"{chain}:{plu}", ())


def pairs_by_chain(chain: str) -> tuple[ReadyFoodPair, ...]:
    """Pairs with at least one counterpart in ``chain``."""
    return tuple(pair for pair in READY_FOOD_PAIRS if chain in pair.chains)


def ready_meal_options(
    recipe_ids: Iterable[str] | None = None,
) -> list[ReadyMealOption]:
    """Render the pair table as ``RecommendationRequest.ready_meal_options``.

    One entry per real product, carrying every recipe it stands in for, so the
    request stays a flat list. Restrict it with ``recipe_ids`` to ship only the
    counterparts for the recipes actually in play.
    """
    wanted = set(recipe_ids) if recipe_ids is not None else None
    by_product: dict[tuple[str, str], tuple[ReadyMeal, set[str]]] = {}
    for pair in READY_FOOD_PAIRS:
        if wanted is not None and pair.recipe_id not in wanted:
            continue
        for meal in pair.meals:
            key = (meal.chain, meal.plu)
            if key not in by_product:
                by_product[key] = (meal, set())
            by_product[key][1].add(pair.recipe_id)
    return [
        ReadyMealOption(
            chain=meal.chain,
            plu=meal.plu,
            name=meal.name,
            recipe_ids=ids,
            price=meal.median_price_rub,
            dish_type=meal.dish_type,
            cuisine=meal.cuisine,
        )
        for meal, ids in by_product.values()
    ]
