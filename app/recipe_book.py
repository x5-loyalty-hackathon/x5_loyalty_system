from __future__ import annotations

from app.contracts import (
    SavedRecipeCollection,
    SavedRecipeSaveRequest,
    SavedRecipeSaveResponse,
)
from app.state import InMemoryStateRepository


class RecipeBookService:
    """Process-local PoC recipe book used to close the save → repeat loop."""

    def __init__(self, *, repository: InMemoryStateRepository) -> None:
        self._repository = repository

    def save(self, request: SavedRecipeSaveRequest) -> SavedRecipeSaveResponse:
        outcome = self._repository.save_recipe(
            user_id=request.user_id,
            recipe_id=request.recipe_id,
        )
        return SavedRecipeSaveResponse(
            status=outcome.status,
            user_id=request.user_id,
            saved_recipe_ids=list(outcome.saved_recipe_ids),
        )

    def list(self, user_id: str) -> SavedRecipeCollection:
        return SavedRecipeCollection(
            user_id=user_id,
            saved_recipe_ids=list(self._repository.saved_recipe_ids(user_id)),
        )
