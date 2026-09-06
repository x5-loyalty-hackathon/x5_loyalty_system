"""Small explicit recipe catalog for the API/mobile PoC.

This is presentation content, not the recommender's catalog and not a claim
about real X5 recipe data.  It only supplies the detail screen while the
production recipe-content source is undecided.
"""

from app.contracts import RecipeDetails, RecipeStep


MOCK_RECIPE_DETAILS: dict[str, RecipeDetails] = {
    "spaghetti_bolognese": RecipeDetails(
        recipe_id="spaghetti_bolognese", title="Спагетти болоньезе",
        preparation_minutes=35, servings=2,
        description="Синтетическая карточка для сквозного PoC-сценария.",
        ingredient_ids={"pasta", "mince", "tomato", "onion", "cheese", "basil"},
        steps=[RecipeStep(title="Подготовить продукты", minutes=10), RecipeStep(title="Приготовить соус и пасту", minutes=25)],
    ),
    "syrniki": RecipeDetails(
        recipe_id="syrniki", title="Сырники", preparation_minutes=25, servings=2,
        description="Синтетическая карточка для сквозного PoC-сценария.",
        ingredient_ids={"cottage_cheese", "egg"},
        steps=[RecipeStep(title="Смешать творожную массу", minutes=10), RecipeStep(title="Обжарить сырники", minutes=15)],
    ),
    "chicken_soup": RecipeDetails(
        recipe_id="chicken_soup", title="Куриный суп", preparation_minutes=45, servings=2,
        description="Синтетическая карточка для сквозного PoC-сценария.",
        ingredient_ids={"chicken", "carrot"},
        steps=[RecipeStep(title="Подготовить овощи", minutes=10), RecipeStep(title="Сварить суп", minutes=35)],
    ),
}
