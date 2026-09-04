"""Small, hand-curated, verified recipe catalog.

Per ``docs/technical-design.md`` non-goals, recipe generation is not
LLM-based and the catalog stays small and editorially reviewable rather than
bulk-imported from a recipe dataset — every recipe below is hand-written.
Kaggle recipe datasets (see
``docs/research/recsys/synthetic-data-and-segments.md``) were only used to
sanity-check realistic ingredient counts/cuisine spread, not as a data
source.

Ingredient ids/categories/names all come from ``recsys.catalog`` so the
catalog, recipes and generated inventory never drift apart.
"""

from __future__ import annotations

from app.contracts import Recipe, RecipeIngredient
from recsys.catalog import ingredient_category, ingredient_name


def _ing(ingredient_id: str, *, required: bool = True) -> RecipeIngredient:
    return RecipeIngredient(
        ingredient_id=ingredient_id,
        name=ingredient_name(ingredient_id),
        category=ingredient_category(ingredient_id),
        required=required,
    )


def _recipe(
    recipe_id: str,
    title: str,
    ingredient_ids: list[str],
    *,
    preparation_minutes: int,
    optional_ingredient_ids: tuple[str, ...] = (),
) -> Recipe:
    ingredients = [_ing(i) for i in ingredient_ids] + [
        _ing(i, required=False) for i in optional_ingredient_ids
    ]
    return Recipe(
        recipe_id=recipe_id,
        title=title,
        ingredients=ingredients,
        verified=True,
        preparation_minutes=preparation_minutes,
    )


# The first three keep the exact ids/ingredients used in
# examples/recommendation_request.json so existing example output stays
# recognizable inside the larger catalog.
RECIPES: tuple[Recipe, ...] = (
    _recipe(
        "vegetable_omelette", "Овощной омлет",
        ["milk", "tomato", "egg"], preparation_minutes=20,
    ),
    _recipe(
        "cottage_cheese_bake", "Творожная запеканка",
        ["cottage_cheese", "flour", "egg"], preparation_minutes=45,
    ),
    _recipe(
        "chicken_and_vegetables", "Курица с овощами",
        ["chicken", "zucchini"], preparation_minutes=30,
    ),
    _recipe(
        "chicken_potato_soup", "Куриный суп с картофелем",
        ["chicken", "potato", "carrot", "onion"], preparation_minutes=40,
    ),
    _recipe(
        "vegetable_stew", "Овощное рагу",
        ["zucchini", "potato", "carrot", "onion", "tomato"], preparation_minutes=35,
    ),
    _recipe(
        "buckwheat_with_mushrooms", "Гречка с грибами",
        ["buckwheat", "mushroom", "onion"], preparation_minutes=25,
    ),
    _recipe(
        "pasta_tomato", "Паста с томатным соусом",
        ["pasta", "tomato", "tomato_paste", "onion"], preparation_minutes=20,
        optional_ingredient_ids=("cheese",),
    ),
    _recipe(
        "chicken_pilaf", "Плов с курицей",
        ["rice", "chicken", "carrot", "onion"], preparation_minutes=50,
    ),
    _recipe(
        "beef_pilaf", "Плов с говядиной",
        ["rice", "beef", "carrot", "onion"], preparation_minutes=60,
    ),
    _recipe(
        "cucumber_tomato_salad", "Салат с огурцом и помидором",
        ["cucumber", "tomato", "vegetable_oil"], preparation_minutes=10,
        optional_ingredient_ids=("sour_cream",),
    ),
    _recipe(
        "syrniki", "Сырники",
        ["cottage_cheese", "egg", "flour", "sugar"], preparation_minutes=25,
    ),
    _recipe(
        "bliny", "Блины",
        ["flour", "milk", "egg", "sugar"], preparation_minutes=30,
    ),
    _recipe(
        "borsch", "Борщ",
        ["beef", "cabbage", "potato", "carrot", "onion", "tomato_paste"],
        preparation_minutes=90,
        optional_ingredient_ids=("sour_cream",),
    ),
    _recipe(
        "meat_cutlets_with_mash", "Котлеты с картофельным пюре",
        ["minced_meat", "potato", "egg", "onion"], preparation_minutes=45,
    ),
    _recipe(
        "cheese_omelette", "Омлет с сыром",
        ["egg", "milk", "cheese"], preparation_minutes=15,
    ),
    _recipe(
        "homemade_chicken_nuggets", "Куриные наггетсы домашние",
        ["chicken", "egg", "flour"], preparation_minutes=30,
    ),
    _recipe(
        "oatmeal_with_banana", "Овсяная каша с бананом",
        ["milk", "oats", "banana"], preparation_minutes=10,
    ),
    _recipe(
        "apple_pie", "Яблочный пирог",
        ["flour", "apple", "sugar", "butter", "egg"], preparation_minutes=60,
    ),
    _recipe(
        "braised_pork_with_vegetables", "Тушёная свинина с овощами",
        ["pork", "zucchini", "bell_pepper", "onion"], preparation_minutes=40,
    ),
    _recipe(
        "chicken_cucumber_salad", "Салат с курицей и огурцом",
        ["chicken", "cucumber", "sour_cream"], preparation_minutes=15,
    ),
    _recipe(
        "cheese_soup", "Сырный суп",
        ["cheese", "potato", "carrot", "onion"], preparation_minutes=35,
    ),
    _recipe(
        "vegetable_cheese_salad", "Овощной салат с сыром",
        ["cucumber", "tomato", "bell_pepper", "cheese"], preparation_minutes=15,
    ),
    _recipe(
        "cheese_tomato_toast", "Тосты с сыром и помидором",
        ["bread", "cheese", "tomato"], preparation_minutes=10,
    ),
    _recipe(
        "carrot_fritters", "Морковные оладьи",
        ["carrot", "egg", "flour"], preparation_minutes=20,
    ),
)

RECIPES_BY_ID: dict[str, Recipe] = {recipe.recipe_id: recipe for recipe in RECIPES}

QUICK_RECIPE_MINUTES = 30
