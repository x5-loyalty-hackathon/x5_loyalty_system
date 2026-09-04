from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.contracts import InventoryProduct, RecipeIngredient, UserProfile


RESCUE_CATEGORIES = frozenset({"fruit", "vegetable", "dairy", "meat"})


@dataclass(frozen=True)
class ProductSafetyDecision:
    approved: bool
    reason: str | None = None


class SafetyPolicy:
    """Deterministic post-model policy. Model scores cannot bypass these rules."""

    def evaluate_product(
        self,
        *,
        product: InventoryProduct,
        ingredient: RecipeIngredient,
        user: UserProfile,
        now: datetime,
    ) -> ProductSafetyDecision:
        common_decision = self._evaluate_common_product(
            product=product,
            user=user,
            now=now,
        )
        if not common_decision.approved:
            return common_decision
        if product.is_prepared_food:
            return ProductSafetyDecision(False, "prepared_food_not_raw_ingredient")
        if ingredient.ingredient_id in user.excluded_ingredient_ids:
            return ProductSafetyDecision(False, "ingredient_excluded_by_user")
        if not self._matches(product, ingredient):
            return ProductSafetyDecision(False, "ingredient_mismatch")
        if product.is_markdown and product.category not in RESCUE_CATEGORIES:
            return ProductSafetyDecision(False, "markdown_category_not_allowed")
        return ProductSafetyDecision(True)

    def evaluate_ready_product(
        self,
        *,
        product: InventoryProduct,
        meal_intent_id: str,
        user: UserProfile,
        now: datetime,
    ) -> ProductSafetyDecision:
        common_decision = self._evaluate_common_product(
            product=product,
            user=user,
            now=now,
        )
        if not common_decision.approved:
            return common_decision
        if not product.is_prepared_food:
            return ProductSafetyDecision(False, "not_prepared_food")
        if meal_intent_id not in product.meal_intent_ids:
            return ProductSafetyDecision(False, "meal_intent_mismatch")
        if product.contained_categories & user.excluded_categories:
            return ProductSafetyDecision(False, "category_excluded_by_user")
        if product.ingredient_ids & user.excluded_ingredient_ids:
            return ProductSafetyDecision(False, "ingredient_excluded_by_user")
        if product.is_markdown and product.category not in RESCUE_CATEGORIES:
            return ProductSafetyDecision(False, "markdown_category_not_allowed")
        return ProductSafetyDecision(True)

    @staticmethod
    def _evaluate_common_product(
        *,
        product: InventoryProduct,
        user: UserProfile,
        now: datetime,
    ) -> ProductSafetyDecision:
        if product.category in user.excluded_categories:
            return ProductSafetyDecision(False, "category_excluded_by_user")
        if product.available_quantity <= 0:
            return ProductSafetyDecision(False, "out_of_stock")
        if product.distance_km > user.radius_km:
            return ProductSafetyDecision(False, "outside_user_radius")
        if not product.safety_eligible:
            return ProductSafetyDecision(False, "not_safety_eligible")
        if product.expires_at is not None and product.expires_at <= now:
            return ProductSafetyDecision(False, "expired")
        if not product.fulfillment_options:
            return ProductSafetyDecision(False, "no_fulfillment_option")
        return ProductSafetyDecision(True)

    @staticmethod
    def _matches(
        product: InventoryProduct,
        ingredient: RecipeIngredient,
    ) -> bool:
        if product.ingredient_ids:
            return ingredient.ingredient_id in product.ingredient_ids
        return ingredient.category == product.category
