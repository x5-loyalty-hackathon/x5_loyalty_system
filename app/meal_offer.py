"""Server-issued selection snapshots, separate from recommender/ranking state.

Catalog, clock and inventory remain trusted synthetic inputs in this PoC. A
token binds a plan to the output actually returned by serving; it is not auth.
"""
from dataclasses import dataclass
from datetime import datetime

from app.contracts import (
    IngredientSource, MealPlanSaveRequest, MealRecommendation, MealRoute,
    ProductOption, Receipt,
)


@dataclass(frozen=True)
class IssuedMealOffer:
    user_id: str
    issued_at: datetime
    meal: MealRecommendation
    current_receipt: Receipt

    def selection_error(self, request: MealPlanSaveRequest) -> str | None:
        if request.user_id != self.user_id:
            return "meal_offer_owner_mismatch"
        if request.created_at < self.issued_at:
            return "meal_plan_predates_offer"
        if request.meal_id != self.meal.meal_id:
            return "meal_offer_selection_mismatch"
        if request.selected_route not in self.meal.available_routes:
            return "meal_offer_selection_mismatch"
        variant = (self.meal.cook_variant if request.selected_route == MealRoute.COOK
                   else self.meal.ready_variant)
        if variant is None or request.fulfillment not in variant.fulfillment_options:
            return "meal_offer_fulfillment_mismatch"
        if request.selected_route == MealRoute.READY:
            if request.selected_recipe_id is not None or len(request.selected_product_ids) != 1:
                return "meal_offer_selection_mismatch"
            groups = [variant.product_options]
        else:
            if request.selected_recipe_id != variant.recipe_id:
                return "meal_offer_selection_mismatch"
            groups = [item.product_options for item in variant.ingredients
                      if item.required and item.source not in {
                          IngredientSource.RECEIPT, IngredientSource.HOME}]
        # Exactly one offered, fulfillment-compatible SKU per required group;
        # extra/missing products and reusing a pack for two ingredients fail.
        choices = []
        for group in groups:
            found = [p.sku_id for p in group if p.sku_id in request.selected_product_ids
                     and request.fulfillment in p.fulfillment_options]
            if len(found) != 1:
                return "meal_offer_selection_mismatch"
            choices.extend(found)
        if len(choices) != len(set(choices)) or set(choices) != request.selected_product_ids:
            return "meal_offer_selection_mismatch"
        return None

    def selected_products(self, request: MealPlanSaveRequest) -> dict[str, ProductOption]:
        if request.selected_route == MealRoute.READY:
            products = self.meal.ready_variant.product_options
        else:
            products = [p for item in self.meal.cook_variant.ingredients for p in item.product_options]
        return {p.sku_id: p for p in products if p.sku_id in request.selected_product_ids}

    def required_ingredient_ids(self) -> set[str]:
        return ({i.ingredient_id for i in self.meal.cook_variant.ingredients if i.required}
                if self.meal.cook_variant else set())
