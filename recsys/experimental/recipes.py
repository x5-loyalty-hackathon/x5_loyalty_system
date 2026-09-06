"""Research view of the shared catalog, with the original metadata schema.

Keep one source of recipe ingredients. The conversion recreates the legacy
JSON representation used by the frozen panel hashes, not the HTTP payload.
"""

from dataclasses import asdict

from recsys.experimental.contracts import Recipe
from recsys.recipe_metadata import RECIPE_METADATA
from recsys.recipes import QUICK_RECIPE_MINUTES, RECIPES as API_RECIPES


RECIPES: tuple[Recipe, ...] = tuple(
    Recipe.model_validate({
        **recipe.model_dump(mode="json", exclude={"meal_intent_id"}),
        **asdict(RECIPE_METADATA[recipe.recipe_id]),
    })
    for recipe in API_RECIPES
)
RECIPES_BY_ID = {recipe.recipe_id: recipe for recipe in RECIPES}
