import re

from recsys.catalog import (
    BASE_PRICE_RUB,
    COUNTED_UNITS,
    INGREDIENTS,
    PORTION_PER_TWO_SERVINGS,
    SEASONING_IDS,
    TO_TASTE,
)
from recsys.ready_food_pairs import (
    COMPATIBLE_DISH_TYPES,
    PAIRS_BY_RECIPE_ID,
    READY_FOOD_CATALOG,
    READY_FOOD_PAIRS,
    RECIPES_WITHOUT_READY_FOOD_PAIR,
    SNAPSHOT_IDS,
    _card_contradicts,
    pair_for_recipe,
    pairs_by_chain,
    pairs_for_plu,
)
from recsys.experimental.recipes import RECIPES, RECIPES_BY_ID
from recsys.sku_mapping import INGREDIENT_SKU_MAPPINGS

# Recipes added because the September 2026 ready-food snapshot showed a
# broadly stocked prepared counterpart for each of them.
READY_FOOD_PAIRED_RECIPE_IDS = {
    "korean_carrot", "teriyaki_chicken_noodles", "hummus", "vinegret",
    "olivier_salad", "herring_under_fur_coat", "grilled_chicken_skewers",
    "chicken_mushroom_salad", "solyanka", "meat_french_style",
    "pea_soup_with_smoked_meats", "pumpkin_cream_soup",
}

CHAINS = {"pyaterochka", "perekrestok"}


def test_ready_food_paired_recipes_are_in_the_catalog() -> None:
    assert READY_FOOD_PAIRED_RECIPE_IDS.issubset(RECIPES_BY_ID)


def test_new_recipe_ingredients_have_price_and_synthetic_sku_mapping() -> None:
    ingredient_ids = {
        ingredient.ingredient_id
        for recipe_id in READY_FOOD_PAIRED_RECIPE_IDS
        for ingredient in RECIPES_BY_ID[recipe_id].ingredients
    }
    assert ingredient_ids.issubset(INGREDIENTS)
    assert ingredient_ids.issubset(BASE_PRICE_RUB)
    assert ingredient_ids.issubset(INGREDIENT_SKU_MAPPINGS)


def test_every_recipe_is_either_paired_or_explicitly_unpaired() -> None:
    assert set(PAIRS_BY_RECIPE_ID) | RECIPES_WITHOUT_READY_FOOD_PAIR == set(RECIPES_BY_ID)
    assert not set(PAIRS_BY_RECIPE_ID) & RECIPES_WITHOUT_READY_FOOD_PAIR


def test_every_new_recipe_has_a_ready_food_pair() -> None:
    for recipe_id in READY_FOOD_PAIRED_RECIPE_IDS:
        assert pair_for_recipe(recipe_id) is not None


def test_pairs_carry_real_plus() -> None:
    for pair in READY_FOOD_PAIRS:
        assert pair.meals
        assert len(pair.plus) == len(pair.meals)
        for meal in pair.meals:
            # A real X5 PLU, not a "syn_" placeholder from recsys.sku_mapping.
            assert meal.plu.isdigit()
            assert meal.chain in CHAINS
        assert pair.chains <= CHAINS
        assert pair.median_price_rub is None or pair.median_price_rub > 0


def test_catalog_products_are_uniquely_identified_by_chain_and_plu() -> None:
    keys = [(meal.chain, meal.plu) for meal in READY_FOOD_CATALOG]
    assert len(keys) == len(set(keys))
    assert len(SNAPSHOT_IDS) == 2


def test_pairs_are_ordered_by_how_many_counterparts_they_have() -> None:
    counts = [len(pair.meals) for pair in READY_FOOD_PAIRS]
    assert counts == sorted(counts, reverse=True)


def test_a_real_plu_resolves_back_to_its_recipes() -> None:
    pilaf = pair_for_recipe("chicken_pilaf")
    assert pilaf is not None
    chain, plu = pilaf.meals[0].chain, pilaf.meals[0].plu
    # One ready meal can be the counterpart of several recipes.
    assert {p.recipe_id for p in pairs_for_plu(chain, plu)} == {"chicken_pilaf", "beef_pilaf"}
    assert pairs_for_plu("pyaterochka", "no-such-plu") == ()


def test_pairs_can_be_filtered_to_one_chain() -> None:
    for chain in CHAINS:
        pairs = pairs_by_chain(chain)
        assert pairs
        for pair in pairs:
            assert any(meal.chain == chain for meal in pair.meals)
    assert pairs_by_chain("magnit") == ()


def test_cheapest_meal_is_the_lowest_priced_counterpart() -> None:
    for pair in READY_FOOD_PAIRS:
        cheapest = pair.cheapest_meal()
        priced = [m.median_price_rub for m in pair.meals if m.median_price_rub is not None]
        if not priced:
            assert cheapest is None
            continue
        assert cheapest is not None
        assert cheapest.median_price_rub == min(priced)


def test_a_contradicting_product_card_vetoes_a_name_match() -> None:
    # "Сэндвич-ролл Цезарь" matches the Цезарь classifier by name, but its card
    # calls it a sandwich roll, so it must not be offered as a salad.
    caesar = pair_for_recipe("caesar_salad")
    assert caesar is not None
    pattern = re.compile(caesar.name_pattern)
    vetoed = [
        meal
        for meal in READY_FOOD_CATALOG
        if pattern.search(meal.name.lower())
        and _card_contradicts(RECIPES_BY_ID["caesar_salad"].dish_type, meal)
    ]
    assert vetoed, "expected at least one card-vetoed Цезарь match"
    assert not set(vetoed) & set(caesar.meals)


def test_card_veto_only_fires_when_the_card_actually_disagrees() -> None:
    salad = RECIPES_BY_ID["caesar_salad"]
    for meal in READY_FOOD_CATALOG:
        if meal.dish_type is None:
            assert not _card_contradicts(salad.dish_type, meal)
        elif meal.dish_type in COMPATIBLE_DISH_TYPES[salad.dish_type]:
            assert not _card_contradicts(salad.dish_type, meal)


def test_recipes_declare_dish_type_and_cuisine_in_the_retailer_vocabulary() -> None:
    catalog_dish_types = {m.dish_type for m in READY_FOOD_CATALOG if m.dish_type}
    catalog_cuisines = {m.cuisine for m in READY_FOOD_CATALOG if m.cuisine}
    for recipe in RECIPES:
        assert recipe.dish_type
        assert recipe.cuisine
    # Every paired recipe's dish type needs a veto rule, otherwise a
    # contradicting product card could never rule a candidate out. The card
    # facets themselves cover only ~3% of the catalog, so the observed values
    # are a subset of the modelled vocabulary, not the other way round.
    for recipe_id in PAIRS_BY_RECIPE_ID:
        assert RECIPES_BY_ID[recipe_id].dish_type in COMPATIBLE_DISH_TYPES
    assert catalog_dish_types <= set(COMPATIBLE_DISH_TYPES) | {
        # Ready-meal-only kinds no recipe claims.
        "Сэндвич-ролл", "Пицца", "Роллы", "Хот-дог", "Поке", "Онигири", "Шаурма",
    }
    assert catalog_cuisines  # cuisine is recorded even though it never vetoes


def test_seasonings_are_to_taste_and_never_required() -> None:
    seen_seasoning = False
    for recipe in RECIPES:
        for ingredient in recipe.ingredients:
            if ingredient.ingredient_id in SEASONING_IDS:
                seen_seasoning = True
                assert ingredient.required is False
                assert ingredient.unit == TO_TASTE
                # A seasoning is never quantified: we did not measure it.
                assert ingredient.quantity is None
            else:
                assert ingredient.required is True
                assert ingredient.unit != TO_TASTE
    assert seen_seasoning


def test_every_non_seasoning_ingredient_is_quantified() -> None:
    for recipe in RECIPES:
        assert 1 <= recipe.servings <= 12
        for ingredient in recipe.ingredients:
            if ingredient.ingredient_id in SEASONING_IDS:
                continue
            assert ingredient.quantity is not None, (
                f"{recipe.recipe_id}/{ingredient.ingredient_id} has no amount"
            )
            assert ingredient.quantity > 0
            assert ingredient.unit


def test_portions_cover_every_non_seasoning_ingredient() -> None:
    assert set(PORTION_PER_TWO_SERVINGS) == set(INGREDIENTS) - SEASONING_IDS


def test_counted_units_stay_whole_or_half() -> None:
    """A recipe may ask for 1.5 lemons; it may not ask for 1.7 eggs."""
    for recipe in RECIPES:
        for ingredient in recipe.ingredients:
            if ingredient.unit in COUNTED_UNITS and ingredient.quantity is not None:
                assert (ingredient.quantity * 2) % 1 == 0, (
                    f"{recipe.recipe_id}/{ingredient.ingredient_id}"
                    f" = {ingredient.quantity} {ingredient.unit}"
                )


def test_every_recipe_has_at_least_one_required_ingredient() -> None:
    for recipe in RECIPES:
        required = [i for i in recipe.ingredients if i.required]
        assert len(required) >= 2, recipe.recipe_id


def test_seasonings_are_listed_after_the_real_ingredients() -> None:
    for recipe in RECIPES:
        flags = [i.ingredient_id in SEASONING_IDS for i in recipe.ingredients]
        assert flags == sorted(flags), recipe.recipe_id


def test_confirmed_false_matches_do_not_survive() -> None:
    """Named products that were paired with the wrong dish, kept as a guard.

    Each of these reached docs/recipe-catalog.md as a "готовый аналог" and, in
    three of the four cases, as the headline "дешевле всего" offer, because it
    was the cheapest thing matching a keyword.
    """
    forbidden = {
        # A fish spread for sandwiches, matched on the word "паста".
        "pasta_tomato": ("санта бремор", "балтийский берег", "криль"),
        # "по-корейски" is a preparation, not a vegetable.
        "korean_carrot": ("спаржа по-корейски", "капуста по-корейски", "фунчоза"),
        # A bare "гриль" matched anything grilled, including vegetables.
        "grilled_chicken_skewers": ("овощи гриль", "индейки", "сэндвич"),
        # A chicken-and-beans salad standing in for chicken-and-mushroom.
        "chicken_mushroom_salad": ("фасолью", "цезарь"),
    }
    for recipe_id, banned in forbidden.items():
        pair = pair_for_recipe(recipe_id)
        assert pair is not None, f"{recipe_id} lost its pair entirely"
        names = " | ".join(meal.name.lower() for meal in pair.meals)
        for phrase in banned:
            assert phrase not in names, (
                f"{recipe_id} still matches {phrase!r}: {names}"
            )


def test_a_recipe_with_no_true_counterpart_says_so() -> None:
    """"Гречка с грибами" had nine matches and not one contained a mushroom.

    Under "a pair means the same dish", the honest answer is no pair, recorded
    explicitly, rather than buckwheat-with-butter presented as the counterpart.
    """
    assert pair_for_recipe("buckwheat_with_mushrooms") is None
    assert "buckwheat_with_mushrooms" in RECIPES_WITHOUT_READY_FOOD_PAIR


def test_required_ingredient_keeps_only_the_real_counterpart() -> None:
    pair = pair_for_recipe("chicken_mushroom_salad")
    assert pair is not None
    assert all(
        "гриб" in meal.name.lower() or "шампиньон" in meal.name.lower()
        for meal in pair.meals
    )
