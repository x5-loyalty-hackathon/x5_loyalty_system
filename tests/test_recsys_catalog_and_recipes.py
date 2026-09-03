from app.contracts import Recipe
from app.safety import RESCUE_CATEGORIES
from recsys.catalog import BASE_PRICE_RUB, CATEGORIES, INGREDIENTS, INGREDIENTS_BY_CATEGORY
from recsys.recipes import RECIPES, RECIPES_BY_ID


def test_every_ingredient_has_a_price_and_known_category() -> None:
    for ingredient_id, item in INGREDIENTS.items():
        assert ingredient_id in BASE_PRICE_RUB
        assert item.category in CATEGORIES


def test_rescue_categories_are_a_subset_of_the_catalog_taxonomy() -> None:
    # recsys.catalog reuses app.safety.RESCUE_CATEGORIES rather than
    # redefining it — this checks that relationship stays intact.
    assert RESCUE_CATEGORIES.issubset(set(CATEGORIES))


def test_ingredients_by_category_partitions_all_ingredients() -> None:
    all_grouped = {i for ids in INGREDIENTS_BY_CATEGORY.values() for i in ids}
    assert all_grouped == set(INGREDIENTS)


def test_recipe_catalog_has_no_duplicate_ids() -> None:
    ids = [recipe.recipe_id for recipe in RECIPES]
    assert len(ids) == len(set(ids))
    assert len(RECIPES) >= 20


def test_recipes_validate_against_the_real_contract_schema() -> None:
    for recipe in RECIPES:
        assert isinstance(recipe, Recipe)
        assert recipe.verified is True
        assert len(recipe.ingredients) >= 2
        for ingredient in recipe.ingredients:
            assert ingredient.ingredient_id in INGREDIENTS
            assert ingredient.category == INGREDIENTS[ingredient.ingredient_id].category


def test_original_three_examples_are_preserved() -> None:
    for recipe_id in ("vegetable_omelette", "cottage_cheese_bake", "chicken_and_vegetables"):
        assert recipe_id in RECIPES_BY_ID


def test_catalog_has_a_spread_of_preparation_times() -> None:
    quick = [r for r in RECIPES if r.preparation_minutes is not None and r.preparation_minutes <= 30]
    slow = [r for r in RECIPES if r.preparation_minutes is not None and r.preparation_minutes > 30]
    assert quick, "need at least one quick (<=30 min) recipe for the time_limited archetype"
    assert slow, "need at least one slower recipe to make prep-time filtering meaningful"
