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

A recipe lists every ingredient it actually uses, in one flat list — there is
no per-recipe required/optional split to maintain. The required/"по вкусу"
distinction is a property of the ingredient, not of the recipe: anything
flagged ``is_seasoning`` in ``recsys.catalog`` is carried as
``required=False`` with the unit ``по вкусу``, everything else is required and
therefore gates availability in ``app.service``. That keeps a bay leaf from
being a hard requirement in one recipe and a garnish in the next, and it means
adding a recipe means listing its ingredients rather than also deciding which
of them are allowed to be missing.
"""

from __future__ import annotations

from app.contracts import Recipe, RecipeIngredient
from recsys.catalog import (
    DEFAULT_SERVINGS,
    TO_TASTE,
    ingredient_category,
    ingredient_name,
    ingredient_portion,
    is_seasoning,
)


def _ing(
    ingredient_id: str,
    *,
    servings: int,
    amounts: dict[str, tuple[float, str]],
) -> RecipeIngredient:
    if is_seasoning(ingredient_id):
        # Never quantified: a cook adds these to taste, and the API must not
        # imply a measurement we did not make.
        return RecipeIngredient(
            ingredient_id=ingredient_id,
            name=ingredient_name(ingredient_id),
            category=ingredient_category(ingredient_id),
            unit=TO_TASTE,
            required=False,
        )
    portion = amounts.get(ingredient_id) or ingredient_portion(ingredient_id, servings)
    quantity, unit = portion
    return RecipeIngredient(
        ingredient_id=ingredient_id,
        name=ingredient_name(ingredient_id),
        category=ingredient_category(ingredient_id),
        quantity=quantity,
        unit=unit,
        required=True,
    )


def _recipe(
    recipe_id: str,
    title: str,
    ingredient_ids: list[str],
    *,
    preparation_minutes: int,
    dish_type: str,
    cuisine: str,
    servings: int = DEFAULT_SERVINGS,
    amounts: dict[str, tuple[float, str]] | None = None,
) -> Recipe:
    """Build one recipe, seasonings last and never required.

    Quantities come from ``recsys.catalog.PORTION_PER_TWO_SERVINGS`` scaled to
    ``servings``, so a shopping list can say "300 г курицы". ``amounts``
    overrides a single ingredient where the catalog default is wrong for this
    dish — pass the amount already scaled for ``servings``.

    ``dish_type``/``cuisine`` use the vocabulary of the "Тип блюда"/"Кухня"
    attributes X5 puts on its own ready-meal cards, so a recipe and a prepared
    meal can be compared on the retailer's own facets rather than on our
    wording (see ``recsys.ready_food_pairs``).
    """
    ordered = [i for i in ingredient_ids if not is_seasoning(i)]
    ordered += [i for i in ingredient_ids if is_seasoning(i)]
    overrides = amounts or {}
    return Recipe(
        recipe_id=recipe_id,
        title=title,
        ingredients=[_ing(i, servings=servings, amounts=overrides) for i in ordered],
        verified=True,
        preparation_minutes=preparation_minutes,
        servings=servings,
        dish_type=dish_type,
        cuisine=cuisine,
    )


# Recipes 1–19 are the normalized, editorially reviewed recipes from
# ``Ингредиенты .txt``.
RECIPES: tuple[Recipe, ...] = (
    _recipe(
        "vegetable_omelette", "Овощной омлет",
        ["egg", "milk", "bell_pepper", "onion", "tomato", "green_beans", "vegetable_mix", "cheese",
         "dill", "parsley", "salt", "black_pepper"],
        preparation_minutes=20, dish_type="Омлет", cuisine="Европейская",
    ),
    _recipe(
        "cottage_cheese_bake", "Творожная запеканка",
        ["cottage_cheese", "egg", "sour_cream", "sugar", "flour", "baking_powder", "vanilla_sugar"],
        preparation_minutes=40, servings=4, amounts={"flour": (60, "г"), "sugar": (80, "г")},
        dish_type="Запеканка", cuisine="Русская",
    ),
    _recipe(
        "healthy_cottage_cheese_bake", "ПП творожная запеканка",
        ["cottage_cheese", "greek_yogurt", "berries", "egg"],
        preparation_minutes=40, servings=4, dish_type="Запеканка", cuisine="Русская",
    ),
    _recipe(
        "syrniki", "Сырники",
        ["cottage_cheese", "sugar", "egg", "flour", "vanilla_sugar", "salt"],
        preparation_minutes=25, amounts={"flour": (60, "г"), "sugar": (2, "ст. л.")},
        dish_type="Сырники", cuisine="Русская",
    ),
    _recipe(
        "bliny", "Блины",
        ["egg", "sugar", "milk", "flour", "vegetable_oil", "salt"],
        preparation_minutes=30, servings=4, amounts={"sugar": (2, "ст. л.")},
        dish_type="Блины", cuisine="Русская",
    ),
    _recipe(
        "oatmeal_with_banana", "Овсяная каша с бананом",
        ["oats", "milk", "banana", "salt"],
        preparation_minutes=10, dish_type="Каша", cuisine="Русская",
    ),
    _recipe(
        "chicken_vegetable_stew", "Овощное рагу с курицей",
        ["chicken", "tomato", "potato", "carrot", "zucchini", "bell_pepper", "onion", "garlic",
         "vegetable_oil", "chili_pepper", "chicken_seasoning", "dried_herbs", "bouillon_cube"],
        preparation_minutes=90, servings=4, amounts={"tomato": (300, "г")},
        dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "buckwheat_with_mushrooms", "Гречка с грибами",
        ["buckwheat", "mushroom", "carrot", "onion", "garlic", "vegetable_oil", "salt",
         "black_pepper"],
        preparation_minutes=30, dish_type="Гарнир", cuisine="Русская",
    ),
    _recipe(
        "pasta_tomato", "Паста с томатным соусом",
        ["pasta", "cheese", "tomato", "garlic", "vegetable_oil", "sugar", "basil", "salt",
         "black_pepper"],
        preparation_minutes=20, amounts={"sugar": (1, "ч. л.")},
        dish_type="Паста", cuisine="Итальянская",
    ),
    _recipe(
        "chicken_pilaf", "Плов с курицей",
        ["chicken", "rice", "carrot", "garlic", "onion", "vegetable_oil", "pilaf_seasoning",
         "salt", "black_pepper"],
        preparation_minutes=50, servings=4, dish_type="Основное блюдо", cuisine="Узбекская",
    ),
    _recipe(
        "beef_pilaf", "Плов с говядиной",
        ["beef", "rice", "carrot", "onion", "garlic", "vegetable_oil", "cumin", "barberry",
         "turmeric", "chili_pepper", "black_pepper", "salt"],
        preparation_minutes=60, servings=4, dish_type="Основное блюдо", cuisine="Узбекская",
    ),
    _recipe(
        "meat_cutlets_with_mash", "Котлеты с картофельным пюре",
        ["minced_meat", "onion", "bread", "milk", "breadcrumbs", "vegetable_oil", "potato",
         "butter", "salt", "black_pepper"],
        preparation_minutes=45, amounts={"milk": (100, "мл")},
        dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "homemade_chicken_nuggets", "Домашние куриные наггетсы",
        ["chicken", "breadcrumbs", "vegetable_oil", "egg", "paprika", "salt"],
        preparation_minutes=30, amounts={"egg": (1, "шт")},
        dish_type="Основное блюдо", cuisine="Американская",
    ),
    _recipe(
        "chicken_potato_soup", "Куриный суп с картофелем",
        ["chicken", "potato", "onion", "carrot", "bay_leaf", "dill", "paprika",
         "salt", "black_pepper", "peppercorn"],
        preparation_minutes=40, servings=4, dish_type="Суп", cuisine="Русская",
    ),
    _recipe(
        "borsch", "Борщ",
        ["beef", "beetroot", "cabbage", "carrot", "parsley_root", "potato", "onion", "garlic",
         "tomato_paste", "vinegar", "sugar", "butter",
         "parsley", "bay_leaf", "allspice", "peppercorn", "salt"],
        preparation_minutes=90, servings=4, amounts={"sugar": (1, "ч. л."), "butter": (30, "г"), "vinegar": (1, "ст. л.")},
        dish_type="Суп", cuisine="Русская",
    ),
    _recipe(
        "cheese_soup", "Сырный суп",
        ["processed_cheese", "potato", "onion", "carrot", "garlic", "vegetable_oil", "croutons",
         "salt", "black_pepper"],
        preparation_minutes=40, servings=4, dish_type="Суп", cuisine="Европейская",
    ),
    _recipe(
        "greek_salad", "Греческий салат",
        ["tomato", "cucumber", "bell_pepper", "onion", "feta", "olive_oil", "olives", "oregano"],
        preparation_minutes=10, dish_type="Салат", cuisine="Средиземноморская",
    ),
    _recipe(
        "caesar_salad", "Салат Цезарь",
        ["romaine_lettuce", "parmesan", "chicken", "baguette", "cherry_tomato", "egg",
         "dijon_mustard", "vinegar", "anchovy", "garlic", "vegetable_oil", "black_pepper"],
        preparation_minutes=30, dish_type="Салат", cuisine="Европейская",
    ),
    _recipe(
        "apple_pie", "Яблочный пирог",
        ["apple", "flour", "egg", "sugar", "milk", "baking_powder", "butter", "cinnamon"],
        preparation_minutes=60, servings=6, amounts={"apple": (4, "шт"), "flour": (250, "г"), "egg": (3, "шт"), "sugar": (150, "г"), "milk": (150, "мл"), "butter": (100, "г")},
        dish_type="Выпечка", cuisine="Русская",
    ),
    # Existing compact recipes retain variety beyond the supplied source file.
    _recipe(
        "chicken_and_vegetables", "Курица с овощами",
        ["chicken", "zucchini", "salt", "black_pepper"],
        preparation_minutes=30, dish_type="Основное блюдо", cuisine="Европейская",
    ),
    _recipe(
        "braised_pork_with_vegetables", "Тушёная свинина с овощами",
        ["pork", "zucchini", "bell_pepper", "onion", "salt", "black_pepper"],
        preparation_minutes=40, dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "chicken_cucumber_salad", "Салат с курицей и огурцом",
        ["chicken", "cucumber", "sour_cream", "salt", "black_pepper"],
        preparation_minutes=15, dish_type="Салат", cuisine="Европейская",
    ),
    _recipe(
        "vegetable_cheese_salad", "Овощной салат с сыром",
        ["cucumber", "tomato", "bell_pepper", "cheese", "salt", "black_pepper"],
        preparation_minutes=15, dish_type="Салат", cuisine="Европейская",
    ),
    _recipe(
        "cheese_tomato_toast", "Тосты с сыром и помидором",
        ["bread", "cheese", "tomato", "black_pepper"],
        preparation_minutes=10, dish_type="Сэндвич", cuisine="Европейская",
    ),
    _recipe(
        "carrot_fritters", "Морковные оладьи",
        ["carrot", "egg", "flour", "salt"],
        preparation_minutes=20, dish_type="Оладьи", cuisine="Русская",
    ),
    # Recipes below were added because the September 2026 ready-food snapshot
    # (see ``recsys/ready_food_pairs.py``) shows a broadly stocked prepared
    # counterpart for each of them, so a "cook it / buy it ready" pair can be
    # shown.
    _recipe(
        "korean_carrot", "Морковь по-корейски",
        ["carrot", "garlic", "vinegar", "vegetable_oil", "sugar",
         "korean_seasoning", "chili_pepper", "salt", "black_pepper"],
        preparation_minutes=20, amounts={"sugar": (1, "ч. л."), "vinegar": (1, "ст. л.")},
        dish_type="Закуска", cuisine="Корейская",
    ),
    _recipe(
        "teriyaki_chicken_noodles", "Лапша вок с курицей терияки",
        ["chicken", "noodles", "teriyaki_sauce", "bell_pepper", "carrot", "onion",
         "garlic", "vegetable_oil", "chili_pepper"],
        preparation_minutes=25, dish_type="Основное блюдо", cuisine="Азиатская",
    ),
    _recipe(
        "hummus", "Хумус",
        ["chickpeas", "tahini", "lemon", "garlic", "olive_oil", "cumin", "paprika", "salt"],
        preparation_minutes=15, dish_type="Закуска", cuisine="Арабская",
    ),
    _recipe(
        "vinegret", "Винегрет",
        ["beetroot", "potato", "carrot", "pickled_cucumber", "sauerkraut", "green_peas", "onion",
         "vegetable_oil", "dill", "salt", "black_pepper"],
        preparation_minutes=50, servings=4, dish_type="Салат", cuisine="Русская",
    ),
    _recipe(
        "olivier_salad", "Салат Оливье",
        ["potato", "carrot", "egg", "green_peas", "pickled_cucumber", "boiled_sausage",
         "mayonnaise", "dill", "salt", "black_pepper"],
        preparation_minutes=60, servings=4, dish_type="Салат", cuisine="Русская",
    ),
    _recipe(
        "herring_under_fur_coat", "Сельдь под шубой",
        ["herring", "beetroot", "potato", "carrot", "egg", "onion", "mayonnaise", "dill",
         "black_pepper"],
        preparation_minutes=90, servings=4, dish_type="Салат", cuisine="Русская",
    ),
    _recipe(
        "grilled_chicken_skewers", "Шашлык из курицы",
        ["chicken", "onion", "vegetable_oil", "vinegar", "garlic",
         "paprika", "chicken_seasoning", "chili_pepper", "dried_herbs", "salt", "black_pepper"],
        preparation_minutes=60, amounts={"onion": (2, "шт")},
        dish_type="Основное блюдо", cuisine="Кавказская",
    ),
    _recipe(
        "chicken_mushroom_salad", "Салат с курицей и грибами",
        ["chicken", "mushroom", "egg", "cheese", "onion", "mayonnaise", "dill",
         "salt", "black_pepper"],
        preparation_minutes=30, dish_type="Салат", cuisine="Русская",
    ),
    _recipe(
        "solyanka", "Солянка сборная мясная",
        ["smoked_meats", "boiled_sausage", "pickled_cucumber", "olives", "onion", "tomato_paste",
         "vegetable_oil", "bay_leaf", "peppercorn", "parsley", "salt"],
        preparation_minutes=60, servings=4, amounts={"tomato_paste": (2, "ст. л.")},
        dish_type="Суп", cuisine="Русская",
    ),
    _recipe(
        "meat_french_style", "Мясо по-французски с картофелем",
        ["pork", "potato", "onion", "cheese", "mayonnaise",
         "dried_herbs", "salt", "black_pepper"],
        preparation_minutes=60, servings=4, dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "pea_soup_with_smoked_meats", "Гороховый суп с копчёностями",
        ["dried_peas", "smoked_meats", "potato", "carrot", "onion", "vegetable_oil", "bay_leaf", "dill", "salt", "black_pepper"],
        preparation_minutes=70, servings=4, amounts={"dried_peas": (300, "г")},
        dish_type="Суп", cuisine="Русская",
    ),
    _recipe(
        "pumpkin_cream_soup", "Крем-суп из тыквы",
        ["pumpkin", "cream", "onion", "carrot", "garlic", "vegetable_oil",
         "turmeric", "salt", "black_pepper"],
        preparation_minutes=35, servings=4, dish_type="Суп", cuisine="Европейская",
    ),
    # Recipes below were added for docs/research/recsys/experiment-3-catalog-coverage-report.md:
    # on the synthetic basket panel, the recipe that came closest to a random
    # basket was overwhelmingly a short one (see the report), and "routine"
    # baskets (dairy/vegetable/meat core) were the worst-covered archetype
    # specifically because the catalog had few *short*, low-seasoning-count
    # meat dishes to overlap with. These are ordinary short home dishes, not
    # the elaborate ones already in the catalog above — the gap was in
    # everyday quick cooking, not in dish variety. All ingredients already
    # exist in ``recsys.catalog`` (no new vocabulary), including
    # ``cutlet_semi_finished``, which had zero recipes using it before this.
    _recipe(
        "fried_chicken_breast", "Жареная куриная грудка",
        ["chicken", "vegetable_oil", "salt", "black_pepper"],
        preparation_minutes=20, dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "pork_chops", "Свиные отбивные",
        ["pork", "vegetable_oil", "paprika", "salt", "black_pepper"],
        preparation_minutes=25, dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "braised_beef_with_onion", "Говядина, тушённая с луком",
        ["beef", "onion", "vegetable_oil", "bay_leaf", "salt", "black_pepper"],
        preparation_minutes=70, dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "fried_minced_meat_with_onion", "Жареный фарш с луком",
        ["minced_meat", "onion", "vegetable_oil", "salt", "black_pepper"],
        preparation_minutes=20, dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "pan_fried_semi_finished_cutlets", "Котлеты жареные из полуфабриката",
        ["cutlet_semi_finished", "vegetable_oil", "salt"],
        preparation_minutes=15, dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "chicken_in_sour_cream", "Куриное филе в сметане",
        ["chicken", "sour_cream", "onion", "vegetable_oil", "dried_herbs", "salt", "black_pepper"],
        preparation_minutes=35, dish_type="Основное блюдо", cuisine="Русская",
    ),
    _recipe(
        "fried_zucchini_with_cheese", "Кабачки, жареные с сыром",
        ["zucchini", "cheese", "vegetable_oil", "salt", "black_pepper"],
        preparation_minutes=20, dish_type="Гарнир", cuisine="Русская",
    ),
    _recipe(
        "braised_cabbage", "Тушёная капуста",
        ["cabbage", "onion", "vegetable_oil", "salt", "black_pepper"],
        preparation_minutes=30, dish_type="Гарнир", cuisine="Русская",
    ),
    _recipe(
        "rice_milk_porridge", "Рисовая каша на молоке",
        ["rice", "milk", "sugar", "salt"],
        preparation_minutes=25, amounts={"sugar": (1, "ст. л.")},
        dish_type="Каша", cuisine="Русская",
    ),
    _recipe(
        "cottage_cheese_with_sour_cream", "Творог со сметаной",
        ["cottage_cheese", "sour_cream"],
        preparation_minutes=5, dish_type="Закуска", cuisine="Русская",
    ),
)

RECIPES_BY_ID: dict[str, Recipe] = {recipe.recipe_id: recipe for recipe in RECIPES}

QUICK_RECIPE_MINUTES = 30
