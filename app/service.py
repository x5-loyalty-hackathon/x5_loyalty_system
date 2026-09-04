from __future__ import annotations

import logging

from app.contracts import (
    ChallengeSelection,
    CookVariant,
    FulfillmentOption,
    IngredientRecommendation,
    IngredientSource,
    InventoryProduct,
    MealRecommendation,
    MealRecommendationResponse,
    MealRoute,
    ModelRecommendation,
    PreparedProductOption,
    ProductOption,
    ReadyVariant,
    Recipe,
    RecipeIngredient,
    RecipeRecommendation,
    RecommendationMode,
    RecommendationRequest,
    RecommendationResponse,
    SafetyStatus,
)
from app.recommender import RecommendationEngine
from app.safety import SafetyPolicy
from app.explanations import (
    NO_RESERVATION_WARNING,
    NO_SAFE_RECOMMENDATIONS_WARNING,
)


logger = logging.getLogger(__name__)

MODE_ORDER = (
    RecommendationMode.CURRENT,
    RecommendationMode.REPEAT,
    RecommendationMode.EXPLORE,
)


class RecommendationService:
    def __init__(
        self,
        *,
        engine: RecommendationEngine,
        safety_policy: SafetyPolicy,
    ) -> None:
        self._engine = engine
        self._safety_policy = safety_policy

    def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        ranked_recipes, filtered_candidates = self._rank_recipes(request)
        recipes = {recipe.recipe_id: recipe for recipe in request.recipe_catalog}
        assembled_recommendations: list[RecipeRecommendation] = []
        for recipe, candidate in ranked_recipes:
            assembled, filter_reason = self._assemble_recipe(
                recipe=recipe,
                candidate=candidate,
                request=request,
            )
            if assembled is None:
                filtered_candidates += 1
                logger.info(
                    "recipe %s filtered: %s", candidate.recipe_id, filter_reason
                )
                continue
            assembled_recommendations.append(assembled)

        assembled_recommendations.sort(
            key=lambda item: (item.missing_count, -item.model_score, item.recipe_id)
        )
        recommendations, challenge_selection = self._select_challenges(
            request=request,
            recipes=recipes,
            recommendations=assembled_recommendations,
        )

        return RecommendationResponse(
            user_id=request.user.user_id,
            receipt_id=request.current_receipt.receipt_id,
            challenge_selection=challenge_selection,
            recommendations=recommendations,
            filtered_candidates=filtered_candidates,
            warnings=self._empty_result_warnings(
                recommendations=recommendations,
                filtered_candidates=filtered_candidates,
            ),
        )

    def recommend_meals(
        self,
        request: RecommendationRequest,
    ) -> MealRecommendationResponse:
        ranked_recipes, filtered_candidates = self._rank_recipes(request)
        recipes = {recipe.recipe_id: recipe for recipe in request.recipe_catalog}
        selection_candidates: list[RecipeRecommendation] = []
        variants: dict[
            str,
            tuple[RecipeRecommendation | None, ReadyVariant | None],
        ] = {}

        for recipe, candidate in ranked_recipes:
            cook_recommendation, cook_filter_reason = self._assemble_recipe(
                recipe=recipe,
                candidate=candidate,
                request=request,
            )
            meal_intent_id = recipe.meal_intent_id or recipe.recipe_id
            ready_variant = self._build_ready_variant(
                meal_intent_id=meal_intent_id,
                products=self._valid_ready_products(
                    request=request,
                    meal_intent_id=meal_intent_id,
                ),
            )
            if cook_recommendation is None and ready_variant is None:
                filtered_candidates += 1
                logger.info(
                    "meal %s filtered: cook=%s, ready=unavailable",
                    candidate.recipe_id,
                    cook_filter_reason,
                )
                continue
            selector_candidate = cook_recommendation or self._ready_selection_candidate(
                request=request,
                recipe=recipe,
                candidate=candidate,
                ready_variant=ready_variant,
            )
            selection_candidates.append(selector_candidate)
            variants[recipe.recipe_id] = (cook_recommendation, ready_variant)

        selection_candidates.sort(key=self._recommendation_sort_key)
        selected, challenge_selection = self._select_challenges(
            request=request,
            recipes=recipes,
            recommendations=selection_candidates,
        )
        meal_recommendations: list[MealRecommendation] = []

        for recommendation in selected:
            recipe = recipes[recommendation.recipe_id]
            cook_recommendation, ready_variant = variants[recommendation.recipe_id]
            available_routes: set[MealRoute] = set()
            if cook_recommendation is not None:
                available_routes.add(MealRoute.COOK)
            if ready_variant is not None:
                available_routes.add(MealRoute.READY)
            default_route, route_reason_codes = self._select_default_route(
                request=request,
                available_routes=available_routes,
            )
            warnings = (
                list(cook_recommendation.warnings)
                if cook_recommendation is not None
                else []
            )
            if ready_variant is not None:
                warnings.extend(ready_variant.warnings)
            warnings = list(dict.fromkeys(warnings))

            meal_recommendations.append(
                MealRecommendation(
                    meal_id=recommendation.recipe_id,
                    title=recommendation.title,
                    mode=recommendation.mode,
                    model_score=recommendation.model_score,
                    default_route=default_route,
                    available_routes=available_routes,
                    reason_codes=recommendation.reason_codes,
                    route_reason_codes=route_reason_codes,
                    cook_variant=(
                        CookVariant(
                            recipe_id=recommendation.recipe_id,
                            preparation_minutes=recipe.preparation_minutes,
                            missing_count=cook_recommendation.missing_count,
                            ingredients=cook_recommendation.ingredients,
                            fulfillment_options=(
                                cook_recommendation.fulfillment_options
                            ),
                            warnings=cook_recommendation.warnings,
                        )
                        if cook_recommendation is not None
                        else None
                    ),
                    ready_variant=ready_variant,
                    safety_status=(
                        SafetyStatus.ADJUSTED
                        if warnings
                        else SafetyStatus.APPROVED
                    ),
                    warnings=warnings,
                )
            )

        return MealRecommendationResponse(
            user_id=request.user.user_id,
            receipt_id=request.current_receipt.receipt_id,
            challenge_selection=challenge_selection,
            recommendations=meal_recommendations,
            filtered_candidates=filtered_candidates,
            warnings=self._empty_result_warnings(
                recommendations=meal_recommendations,
                filtered_candidates=filtered_candidates,
            ),
        )

    def _rank_recipes(
        self,
        request: RecommendationRequest,
    ) -> tuple[list[tuple[Recipe, ModelRecommendation]], int]:
        """Resolve model output once while keeping adapter diagnostics private."""
        recipes = {recipe.recipe_id: recipe for recipe in request.recipe_catalog}
        # The current ML adapter still emits one legacy mode hint per recipe.
        # Challenge modes are ranking strategies in API 1.1, so the service
        # asks the engine for unfiltered recipe relevance and expands safe
        # recipes into every strategy for which they are eligible.
        engine_request = request.model_copy(update={"requested_mode": None})
        model_candidates = self._engine.rank(engine_request)
        ranked: list[tuple[Recipe, ModelRecommendation]] = []
        filtered_candidates = 0
        seen_recipe_ids: set[str] = set()
        for candidate in model_candidates:
            if candidate.recipe_id in seen_recipe_ids:
                filtered_candidates += 1
                logger.warning(
                    "duplicate model candidate ignored: %s", candidate.recipe_id
                )
                continue
            seen_recipe_ids.add(candidate.recipe_id)
            recipe = recipes.get(candidate.recipe_id)
            if recipe is None:
                filtered_candidates += 1
                logger.warning(
                    "unknown model recipe ignored: %s", candidate.recipe_id
                )
                continue
            if not recipe.verified:
                filtered_candidates += 1
                logger.warning(
                    "unverified model recipe ignored: %s", candidate.recipe_id
                )
                continue
            ranked.append((recipe, candidate))
        return ranked, filtered_candidates

    def _select_challenges(
        self,
        *,
        request: RecommendationRequest,
        recipes: dict[str, Recipe],
        recommendations: list[RecipeRecommendation],
    ) -> tuple[list[RecipeRecommendation], ChallengeSelection]:
        pools: dict[RecommendationMode, list[RecipeRecommendation]] = {
            mode: [] for mode in MODE_ORDER
        }
        for recommendation in recommendations:
            recipe = recipes[recommendation.recipe_id]
            for mode in self._eligible_modes(
                request=request,
                recipe=recipe,
                recommendation=recommendation,
            ):
                pools[mode].append(
                    recommendation.model_copy(
                        update={
                            "mode": mode,
                            "reason_codes": recommendation.reason_codes,
                        }
                    )
                )

        for candidates in pools.values():
            candidates.sort(key=self._recommendation_sort_key)

        if request.requested_mode is not None:
            mode = request.requested_mode
            selected = pools[mode][: request.limit]
            available_modes = [mode] if selected else []
            return selected, ChallengeSelection(
                default_mode=mode if selected else None,
                available_modes=available_modes,
                mode_reason_codes=(
                    {
                        mode: [
                            self._strategy_reason_code(mode),
                            "explicit_mode_request",
                        ]
                    }
                    if selected
                    else {}
                ),
            )

        representatives: dict[RecommendationMode, RecipeRecommendation] = {}
        explicit_choice_required: set[RecommendationMode] = set()
        for mode in MODE_ORDER:
            candidates = pools[mode]
            if not candidates:
                continue
            if mode == RecommendationMode.EXPLORE:
                partial = next(
                    (
                        candidate
                        for candidate in candidates
                        if not self._is_full_basket(candidate)
                    ),
                    None,
                )
                representatives[mode] = partial or candidates[0]
                if partial is None:
                    explicit_choice_required.add(mode)
            else:
                representatives[mode] = candidates[0]

        default_candidates = {
            mode: recommendation
            for mode, recommendation in representatives.items()
            if mode not in explicit_choice_required
        }
        default_mode = (
            min(
                default_candidates,
                key=lambda mode: (
                    default_candidates[mode].missing_count,
                    -default_candidates[mode].model_score,
                    MODE_ORDER.index(mode),
                ),
            )
            if default_candidates
            else None
        )

        ordered_modes = list(MODE_ORDER)
        if default_mode is not None:
            ordered_modes.remove(default_mode)
            ordered_modes.insert(0, default_mode)

        selected: list[RecipeRecommendation] = []
        selected_modes: list[RecommendationMode] = []
        used_recipe_ids: set[str] = set()
        for mode in ordered_modes:
            if len(selected) >= request.limit:
                break
            preferred = representatives.get(mode)
            if preferred is None:
                continue
            candidate = next(
                (
                    item
                    for item in ([preferred] + pools[mode])
                    if item.recipe_id not in used_recipe_ids
                ),
                None,
            )
            if candidate is None:
                continue
            selected.append(candidate)
            selected_modes.append(mode)
            used_recipe_ids.add(candidate.recipe_id)
            if mode == RecommendationMode.EXPLORE:
                if self._is_full_basket(candidate):
                    explicit_choice_required.add(mode)
                else:
                    explicit_choice_required.discard(mode)

        available_modes = selected_modes
        explicit_choice_required &= set(available_modes)
        mode_reason_codes = {
            mode: self._mode_reason_codes(
                mode=mode,
                is_default=mode == default_mode,
                requires_explicit_choice=mode in explicit_choice_required,
            )
            for mode in selected_modes
        }
        if default_mode not in available_modes:
            default_mode = None

        return selected, ChallengeSelection(
            default_mode=default_mode,
            available_modes=available_modes,
            mode_reason_codes=mode_reason_codes,
            explicit_choice_required=[
                mode for mode in selected_modes if mode in explicit_choice_required
            ],
        )

    @staticmethod
    def _eligible_modes(
        *,
        request: RecommendationRequest,
        recipe: Recipe,
        recommendation: RecipeRecommendation,
    ) -> list[RecommendationMode]:
        if "safe_ready_option_available" in recommendation.reason_codes:
            # A ready-only offer does not consume raw products from the
            # current basket. Until an explicit ready-SKU overlap is modeled,
            # it can only be a repeat or a novel meal.
            return [
                RecommendationMode.REPEAT
                if recipe.recipe_id in request.user.saved_recipe_ids
                else RecommendationMode.EXPLORE
            ]
        receipt_ingredient_ids = RecommendationService._receipt_ingredient_ids(
            request
        )
        recipe_ingredient_ids = {
            ingredient.ingredient_id
            for ingredient in recipe.ingredients
            if ingredient.required
        }
        modes: set[RecommendationMode] = set()
        if recipe_ingredient_ids & receipt_ingredient_ids:
            modes.add(RecommendationMode.CURRENT)
        if recipe.recipe_id in request.user.saved_recipe_ids:
            modes.add(RecommendationMode.REPEAT)
        else:
            # Explore means novelty for this user. It is intentionally
            # orthogonal to receipt coverage, so a new recipe may still reuse
            # today's purchase or products explicitly marked as present at home.
            modes.add(RecommendationMode.EXPLORE)
        return [mode for mode in MODE_ORDER if mode in modes]

    @staticmethod
    def _recommendation_sort_key(
        recommendation: RecipeRecommendation,
    ) -> tuple[int, float, str]:
        return (
            recommendation.missing_count,
            -recommendation.model_score,
            recommendation.recipe_id,
        )

    @staticmethod
    def _is_full_basket(recommendation: RecipeRecommendation) -> bool:
        if "safe_ready_option_available" in recommendation.reason_codes:
            # Buying one matched ready dish is not the full raw-ingredient
            # basket whose friction ADR-003 puts behind explicit opt-in.
            return False
        owned_sources = {IngredientSource.RECEIPT, IngredientSource.HOME}
        return not any(
            ingredient.required and ingredient.source in owned_sources
            for ingredient in recommendation.ingredients
        )

    @staticmethod
    def _mode_reason_codes(
        *,
        mode: RecommendationMode,
        is_default: bool,
        requires_explicit_choice: bool,
    ) -> list[str]:
        codes = [RecommendationService._strategy_reason_code(mode)]
        if requires_explicit_choice:
            codes.append("full_basket_requires_explicit_choice")
        elif is_default:
            codes.append("selected_by_effort_then_relevance")
        return codes

    @staticmethod
    def _strategy_reason_code(mode: RecommendationMode) -> str:
        return {
            RecommendationMode.CURRENT: "current_basket_strategy",
            RecommendationMode.REPEAT: "saved_recipe_strategy",
            RecommendationMode.EXPLORE: "novel_recipe_strategy",
        }[mode]

    def _assemble_recipe(
        self,
        *,
        recipe: Recipe,
        candidate: ModelRecommendation,
        request: RecommendationRequest,
    ) -> tuple[RecipeRecommendation | None, str | None]:
        if not recipe.verified:
            return None, "recipe_not_verified"
        receipt_ingredient_ids = self._receipt_ingredient_ids(request)
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
                        required=ingredient.required,
                        source=IngredientSource.RECEIPT,
                    )
                )
                continue

            if ingredient.ingredient_id in request.user.home_ingredient_ids:
                ingredients.append(
                    IngredientRecommendation(
                        ingredient_id=ingredient.ingredient_id,
                        name=ingredient.name,
                        category=ingredient.category,
                        required=ingredient.required,
                        source=IngredientSource.HOME,
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
                        required=ingredient.required,
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
                    required=ingredient.required,
                    source=source,
                    product_options=product_options,
                )
            )

        warnings = [NO_RESERVATION_WARNING] if has_markdown else []
        return (
            RecipeRecommendation(
                recipe_id=recipe.recipe_id,
                title=recipe.title,
                mode=candidate.mode,
                model_score=candidate.score,
                missing_count=missing_count,
                reason_codes=self._public_recipe_reason_codes(
                    request=request,
                    recipe=recipe,
                    ingredients=ingredients,
                    missing_count=missing_count,
                ),
                ingredients=ingredients,
                fulfillment_options=common_fulfillment,
                safety_status=(
                    SafetyStatus.ADJUSTED if warnings else SafetyStatus.APPROVED
                ),
                warnings=warnings,
            ),
            None,
        )

    @staticmethod
    def _receipt_ingredient_ids(request: RecommendationRequest) -> set[str]:
        """Raw ingredients bought now; prepared dishes are not decomposed."""
        return {
            ingredient_id
            for item in request.current_receipt.items
            if not item.is_prepared_food
            for ingredient_id in item.ingredient_ids
        }

    @staticmethod
    def _public_recipe_reason_codes(
        *,
        request: RecommendationRequest,
        recipe: Recipe,
        ingredients: list[IngredientRecommendation],
        missing_count: int,
    ) -> list[str]:
        """Derive user-facing facts from the post-safety assembled result."""
        codes: list[str] = []
        if any(item.source == IngredientSource.RECEIPT for item in ingredients):
            codes.append("current_receipt_overlap")

        history_categories = set(request.user.history_categories)
        history_categories.update(
            item.category
            for receipt in request.purchase_history
            for item in receipt.items
        )
        if history_categories & {item.category for item in recipe.ingredients}:
            codes.append("category_history_match")
        if recipe.preparation_minutes is not None and recipe.preparation_minutes <= 30:
            codes.append("quick_recipe")
        if 0 < missing_count <= 2:
            codes.append("low_missing_count")
        if any(item.source == IngredientSource.HOME for item in ingredients):
            codes.append("home_ingredient_reuse")
        if any(
            option.source == IngredientSource.MARKDOWN
            for item in ingredients
            for option in item.product_options
        ):
            codes.append("safe_markdown_option_available")

        preferred_brands = set(request.user.preferred_brands)
        if preferred_brands:
            matching_option_brand = any(
                option.brand in preferred_brands
                for item in ingredients
                for option in item.product_options
            )
            if matching_option_brand:
                codes.append("preferred_brand_option_available")

        return codes or ["safe_recipe_available"]

    def _ready_selection_candidate(
        self,
        *,
        request: RecommendationRequest,
        recipe: Recipe,
        candidate: ModelRecommendation,
        ready_variant: ReadyVariant | None,
    ) -> RecipeRecommendation:
        if ready_variant is None:  # pragma: no cover - guarded by caller
            raise ValueError("ready selection candidate requires ready_variant")
        receipt_ids = self._receipt_ingredient_ids(request)
        ingredients = [
            IngredientRecommendation(
                ingredient_id=ingredient.ingredient_id,
                name=ingredient.name,
                category=ingredient.category,
                required=ingredient.required,
                source=(
                    IngredientSource.RECEIPT
                    if ingredient.ingredient_id in receipt_ids
                    else (
                        IngredientSource.HOME
                        if ingredient.ingredient_id
                        in request.user.home_ingredient_ids
                        else IngredientSource.UNAVAILABLE
                    )
                ),
            )
            for ingredient in recipe.ingredients
        ]
        # The selector compares purchase effort. A ready-only route requires
        # one prepared item rather than every unavailable raw ingredient.
        return RecipeRecommendation(
            recipe_id=recipe.recipe_id,
            title=recipe.title,
            mode=candidate.mode,
            model_score=candidate.score,
            missing_count=1,
            reason_codes=["safe_ready_option_available"],
            ingredients=ingredients,
            fulfillment_options=ready_variant.fulfillment_options,
            safety_status=(
                SafetyStatus.ADJUSTED
                if ready_variant.warnings
                else SafetyStatus.APPROVED
            ),
        )

    @staticmethod
    def _empty_result_warnings(
        *,
        recommendations: list[object],
        filtered_candidates: int,
    ) -> list[str]:
        if not recommendations and filtered_candidates:
            return [NO_SAFE_RECOMMENDATIONS_WARNING]
        return []

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

    def _valid_ready_products(
        self,
        *,
        request: RecommendationRequest,
        meal_intent_id: str,
    ) -> list[InventoryProduct]:
        valid: list[InventoryProduct] = []
        for product in request.inventory_snapshot:
            decision = self._safety_policy.evaluate_ready_product(
                product=product,
                meal_intent_id=meal_intent_id,
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

    def _build_ready_variant(
        self,
        *,
        meal_intent_id: str,
        products: list[InventoryProduct],
    ) -> ReadyVariant | None:
        if not products:
            return None
        product_options = [
            self._to_prepared_product_option(product) for product in products
        ]
        fulfillment_options = set().union(
            *(product.fulfillment_options for product in products)
        )
        has_markdown = any(product.is_markdown for product in products)
        warnings = [NO_RESERVATION_WARNING] if has_markdown else []
        return ReadyVariant(
            meal_intent_id=meal_intent_id,
            product_options=product_options,
            fulfillment_options=fulfillment_options,
            warnings=warnings,
        )

    @staticmethod
    def _select_default_route(
        *,
        request: RecommendationRequest,
        available_routes: set[MealRoute],
    ) -> tuple[MealRoute, list[str]]:
        preferred_route = request.user.preferred_meal_route
        if preferred_route is not None:
            if preferred_route in available_routes:
                return preferred_route, [f"explicit_{preferred_route.value}_preference"]
            fallback_route = (
                MealRoute.COOK
                if MealRoute.COOK in available_routes
                else MealRoute.READY
            )
            return fallback_route, [
                f"{preferred_route.value}_route_unavailable",
                f"{fallback_route.value}_route_fallback",
            ]

        if available_routes == {MealRoute.READY}:
            return MealRoute.READY, ["only_ready_route_available"]

        observed_items = list(request.current_receipt.items)
        observed_items.extend(
            item
            for receipt in request.purchase_history
            for item in receipt.items
        )
        prepared_share = (
            sum(item.is_prepared_food for item in observed_items)
            / len(observed_items)
            if observed_items
            else 0.0
        )
        if prepared_share >= 0.5 and MealRoute.READY in available_routes:
            return MealRoute.READY, ["prepared_food_share_supports_ready"]
        if prepared_share >= 0.5:
            return MealRoute.COOK, [
                "prepared_food_share_supports_ready",
                "ready_route_unavailable",
                "cook_route_fallback",
            ]
        return MealRoute.COOK, ["ingredient_purchase_history_supports_cook"]

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
        )

    @staticmethod
    def _to_prepared_product_option(
        product: InventoryProduct,
    ) -> PreparedProductOption:
        base = RecommendationService._to_product_option(product)
        return PreparedProductOption(
            **base.model_dump(),
            ingredient_ids=product.ingredient_ids,
            contained_categories=product.contained_categories,
        )
