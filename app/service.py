from __future__ import annotations

from dataclasses import dataclass

from app.contracts import (
    FulfillmentOption,
    IngredientRecommendation,
    IngredientSource,
    InventoryProduct,
    ModelRecommendation,
    ProductOption,
    ReadyMealOption,
    Recipe,
    RecipeIngredient,
    RecipeRecommendation,
    RecommendationRequest,
    RecommendationResponse,
    SafetyStatus,
)
from app.recommender import RecommendationEngine
from app.safety import SafetyPolicy


NO_RESERVATION_WARNING = (
    "Markdown availability is best-effort: the item is not reserved."
)

#: Missing-ingredient count at which a recipe is treated as maximally effortful
#: when a policy needs to put effort on a 0..1 scale.
MAX_EFFORT_MISSING_COUNT = 8


@dataclass(frozen=True)
class RankingPolicy:
    """How assembled candidates are ordered before the response is truncated.

    This is a product decision that was previously implicit in one ``sort``
    call, and it turned out to dominate the model entirely: ordering by
    ``missing_count`` first makes ``model_score`` a tiebreaker, so a trained
    ranker and a random one return the same top-3 for most users (measured in
    ``docs/benchmark-report.md``). Making the policy an object means the choice
    can be stated, compared between arms and defended, instead of being a line
    nobody re-reads.

    ``model_weight`` is the share of the blended score that comes from the
    recommender; the rest comes from how little the user has to buy.
    """

    name: str
    model_weight: float = 0.0
    #: When True, order strictly by missing_count and use the score only to
    #: break ties. This is the behaviour the service shipped with.
    effort_first: bool = True

    def sort_key(self, item: RecipeRecommendation) -> tuple:
        if self.effort_first:
            return (item.missing_count, -item.model_score, item.recipe_id)
        effort_score = 1.0 - min(item.missing_count, MAX_EFFORT_MISSING_COUNT) / (
            MAX_EFFORT_MISSING_COUNT
        )
        blended = (
            self.model_weight * item.model_score
            + (1.0 - self.model_weight) * effort_score
        )
        return (-round(blended, 6), item.missing_count, item.recipe_id)


#: Ship-as-is: easiest-to-cook first, relevance only as a tiebreaker.
EFFORT_FIRST = RankingPolicy(name="effort_first", model_weight=0.0, effort_first=True)

#: Equal say to relevance and effort.
BLENDED = RankingPolicy(name="blended", model_weight=0.5, effort_first=False)

#: Relevance dominates; effort still breaks ties.
RELEVANCE_FIRST = RankingPolicy(
    name="relevance_first", model_weight=0.9, effort_first=False
)

DEFAULT_RANKING_POLICY = EFFORT_FIRST


class RecommendationService:
    def __init__(
        self,
        *,
        engine: RecommendationEngine,
        safety_policy: SafetyPolicy,
        ranking_policy: RankingPolicy = DEFAULT_RANKING_POLICY,
    ) -> None:
        self._engine = engine
        self._safety_policy = safety_policy
        self._ranking_policy = ranking_policy

    def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        recipes = {recipe.recipe_id: recipe for recipe in request.recipe_catalog}
        model_candidates = self._engine.rank(request)
        recommendations: list[RecipeRecommendation] = []
        filtered_candidates = 0
        response_warnings: list[str] = []
        seen_recipe_ids: set[str] = set()

        for candidate in model_candidates:
            if (
                request.requested_mode is not None
                and candidate.mode != request.requested_mode
            ):
                filtered_candidates += 1
                continue
            if candidate.recipe_id in seen_recipe_ids:
                filtered_candidates += 1
                response_warnings.append(
                    f"duplicate model candidate ignored: {candidate.recipe_id}"
                )
                continue
            seen_recipe_ids.add(candidate.recipe_id)

            recipe = recipes.get(candidate.recipe_id)
            if recipe is None:
                filtered_candidates += 1
                response_warnings.append(
                    f"unknown model recipe ignored: {candidate.recipe_id}"
                )
                continue

            assembled, filter_reason = self._assemble_recipe(
                recipe=recipe,
                candidate=candidate,
                request=request,
            )
            if assembled is None:
                filtered_candidates += 1
                response_warnings.append(
                    f"recipe {candidate.recipe_id} filtered: {filter_reason}"
                )
                continue
            recommendations.append(assembled)

        recommendations.sort(key=self._ranking_policy.sort_key)

        return RecommendationResponse(
            user_id=request.user.user_id,
            receipt_id=request.current_receipt.receipt_id,
            recommendations=recommendations[: request.limit],
            filtered_candidates=filtered_candidates,
            warnings=response_warnings,
        )

    def _assemble_recipe(
        self,
        *,
        recipe: Recipe,
        candidate: ModelRecommendation,
        request: RecommendationRequest,
    ) -> tuple[RecipeRecommendation | None, str | None]:
        if not recipe.verified:
            return None, "recipe_not_verified"
        receipt_ingredient_ids = {
            ingredient_id
            for item in request.current_receipt.items
            for ingredient_id in item.ingredient_ids
        }
        ingredients: list[IngredientRecommendation] = []
        missing_count = 0
        has_markdown = False
        common_fulfillment = {
            FulfillmentOption.DELIVERY,
            FulfillmentOption.NEXT_VISIT,
        }

        for ingredient in recipe.ingredients:
            if (
                ingredient.ingredient_id in request.user.excluded_ingredient_ids
                or ingredient.category in request.user.excluded_categories
            ):
                return None, f"ingredient_excluded:{ingredient.ingredient_id}"

            if ingredient.ingredient_id in receipt_ingredient_ids:
                ingredients.append(
                    IngredientRecommendation(
                        ingredient_id=ingredient.ingredient_id,
                        name=ingredient.name,
                        category=ingredient.category,
                        source=IngredientSource.RECEIPT,
                    )
                )
                continue

            valid_products = self._valid_products(
                request=request,
                ingredient=ingredient,
            )
            if not valid_products and ingredient.required:
                return None, f"no_safe_product:{ingredient.ingredient_id}"
            if not valid_products:
                ingredients.append(
                    IngredientRecommendation(
                        ingredient_id=ingredient.ingredient_id,
                        name=ingredient.name,
                        category=ingredient.category,
                        source=IngredientSource.UNAVAILABLE,
                    )
                )
                continue

            missing_count += 1
            product_options = [self._to_product_option(item) for item in valid_products]
            source = product_options[0].source
            has_markdown = has_markdown or source == IngredientSource.MARKDOWN
            ingredient_fulfillment = set().union(
                *(item.fulfillment_options for item in product_options)
            )
            common_fulfillment &= ingredient_fulfillment
            if not common_fulfillment:
                return None, "no_common_fulfillment"

            ingredients.append(
                IngredientRecommendation(
                    ingredient_id=ingredient.ingredient_id,
                    name=ingredient.name,
                    category=ingredient.category,
                    source=source,
                    product_options=product_options,
                )
            )

        warnings = [NO_RESERVATION_WARNING] if has_markdown else []
        ready_meal_options = self._ready_meal_options(
            recipe_id=recipe.recipe_id, request=request
        )
        return (
            RecipeRecommendation(
                recipe_id=recipe.recipe_id,
                title=recipe.title,
                mode=candidate.mode,
                model_score=candidate.score,
                missing_count=missing_count,
                reason_codes=candidate.reason_codes,
                ingredients=ingredients,
                fulfillment_options=common_fulfillment,
                safety_status=(
                    SafetyStatus.ADJUSTED if warnings else SafetyStatus.APPROVED
                ),
                warnings=warnings,
                ready_meal_alternative=ready_meal_options[0] if ready_meal_options else None,
                ready_meal_option_count=len(ready_meal_options),
            ),
            None,
        )

    @staticmethod
    def _ready_meal_options(
        *,
        recipe_id: str,
        request: RecommendationRequest,
    ) -> list[ReadyMealOption]:
        """Prepared counterparts for one recipe, cheapest first.

        Options without a price sort last rather than being dropped: a known
        counterpart with an unknown price is still worth showing, it just
        cannot lead the "or buy it ready for N ₽" offer.
        """
        options = [
            option
            for option in request.ready_meal_options
            if recipe_id in option.recipe_ids
        ]
        return sorted(
            options,
            key=lambda option: (
                option.price is None,
                option.price if option.price is not None else 0.0,
                option.chain,
                option.plu,
            ),
        )

    def _valid_products(
        self,
        *,
        request: RecommendationRequest,
        ingredient: RecipeIngredient,
    ) -> list[InventoryProduct]:
        valid: list[InventoryProduct] = []
        for product in request.inventory_snapshot:
            decision = self._safety_policy.evaluate_product(
                product=product,
                ingredient=ingredient,
                user=request.user,
                now=request.now,
            )
            if decision.approved:
                valid.append(product)

        return sorted(
            valid,
            key=lambda item: (
                not item.is_markdown,
                item.distance_km,
                item.price,
                item.sku_id,
            ),
        )

    @staticmethod
    def _to_product_option(product: InventoryProduct) -> ProductOption:
        return ProductOption(
            sku_id=product.sku_id,
            name=product.name,
            category=product.category,
            store_id=product.store_id,
            distance_km=product.distance_km,
            price=product.price,
            original_price=product.original_price,
            brand=product.brand,
            source=(
                IngredientSource.MARKDOWN
                if product.is_markdown
                else IngredientSource.FULL_PRICE
            ),
            expires_at=product.expires_at,
            fulfillment_options=product.fulfillment_options,
            price_is_estimate=product.price_is_estimate,
        )
