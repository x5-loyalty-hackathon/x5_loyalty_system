from __future__ import annotations

from typing import Protocol

from app.contracts import (
    ModelRecommendation,
    RecommendationMode,
    RecommendationRequest,
)


class RecommendationEngine(Protocol):
    """Boundary implemented by either the deterministic mock or the ML adapter."""

    def rank(
        self,
        request: RecommendationRequest,
    ) -> list[ModelRecommendation]: ...


class DeterministicMockEngine:
    """Explainable baseline used until the teammate model implements the protocol."""

    def rank(self, request: RecommendationRequest) -> list[ModelRecommendation]:
        receipt_ingredients = {
            ingredient_id
            for item in request.current_receipt.items
            for ingredient_id in item.ingredient_ids
        }
        history_categories = set(request.user.history_categories)
        history_categories.update(
            item.category
            for receipt in request.purchase_history
            for item in receipt.items
        )

        ranked: list[ModelRecommendation] = []
        for recipe in request.recipe_catalog:
            if not recipe.verified:
                continue

            ingredient_ids = {
                ingredient.ingredient_id for ingredient in recipe.ingredients
            }
            categories = {ingredient.category for ingredient in recipe.ingredients}
            current_hits = len(ingredient_ids & receipt_ingredients)
            history_hits = len(categories & history_categories)

            if recipe.recipe_id in request.user.saved_recipe_ids:
                mode = RecommendationMode.REPEAT
                mode_bonus = 0.25
                reason_codes = ["saved_recipe_repeat"]
            elif current_hits:
                mode = RecommendationMode.CURRENT
                mode_bonus = 0.2
                reason_codes = ["current_receipt_overlap"]
            else:
                mode = RecommendationMode.EXPLORE
                mode_bonus = 0.1
                reason_codes = ["personalized_discovery"]

            if request.requested_mode is not None and mode != request.requested_mode:
                continue

            denominator = max(len(recipe.ingredients), 1)
            coverage = min(current_hits / denominator, 1.0)
            affinity = min(history_hits / denominator, 1.0)
            score = min(0.25 + 0.35 * coverage + 0.25 * affinity + mode_bonus, 1.0)

            if history_hits:
                reason_codes.append("category_history_match")
            if recipe.preparation_minutes is not None and recipe.preparation_minutes <= 30:
                reason_codes.append("quick_recipe")

            ranked.append(
                ModelRecommendation(
                    recipe_id=recipe.recipe_id,
                    mode=mode,
                    score=round(score, 4),
                    reason_codes=reason_codes,
                )
            )

        return sorted(ranked, key=lambda item: (-item.score, item.recipe_id))
