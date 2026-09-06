from __future__ import annotations

from enum import StrEnum
from datetime import date

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.explanations import (
    CHALLENGE_REASON_CODES,
    PUBLIC_WARNING_VALUES,
    RECIPE_REASON_CODES,
    ROUTE_REASON_CODES,
    STORE_REASON_CODES,
)


CONTRACT_VERSION = "1.3"


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecommendationMode(StrEnum):
    CURRENT = "current"
    REPEAT = "repeat"
    EXPLORE = "explore"


class MealRoute(StrEnum):
    COOK = "cook"
    READY = "ready"


class ShoppingAnchorType(StrEnum):
    CURRENT_LOCATION = "current_location"
    HOME = "home"
    WORK = "work"
    CUSTOM = "custom"


class RankCohort(StrEnum):
    COOKING_HOUSEHOLDS = "cooking_households"
    READY_HEAVY = "ready_heavy"


class MealPlanStatus(StrEnum):
    SAVED = "saved"
    COLLECTED = "collected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MealPlanSaveStatus(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class MealPlanCompletionStatus(StrEnum):
    COMPLETED = "completed"
    NOT_READY = "not_ready"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class SavedRecipeStatus(StrEnum):
    CREATED = "created"
    DUPLICATE = "duplicate"


class FulfillmentOption(StrEnum):
    DELIVERY = "delivery"
    NEXT_VISIT = "next_visit"


class IngredientSource(StrEnum):
    RECEIPT = "receipt"
    HOME = "home"
    MARKDOWN = "markdown"
    FULL_PRICE = "full_price"
    UNAVAILABLE = "unavailable"


class SafetyStatus(StrEnum):
    APPROVED = "approved"
    ADJUSTED = "adjusted"


class ReceiptEventStatus(StrEnum):
    VERIFIED = "verified"
    DUPLICATE = "duplicate"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class ReferralStatus(StrEnum):
    APPROVED = "approved"
    DUPLICATE = "duplicate"
    NOT_QUALIFIED = "not_qualified"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"


class UserProfile(ApiModel):
    user_id: str = Field(min_length=1)
    # Legacy fallback for clients without shopping_context. New clients should
    # send an anchor-relative walking radius in RecommendationRequest.
    radius_km: float = Field(default=0.75, gt=0, le=100)
    excluded_categories: set[str] = Field(default_factory=set)
    excluded_ingredient_ids: set[str] = Field(default_factory=set)
    home_ingredient_ids: set[str] = Field(default_factory=set)
    saved_recipe_ids: set[str] = Field(default_factory=set)
    history_categories: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)
    preferred_meal_route: MealRoute | None = None


class ShoppingContext(ApiModel):
    """Opaque, privacy-safe origin used to interpret inventory distances.

    The API deliberately accepts no address or coordinates. ``anchor_id`` can
    refer to a client-side saved place such as home or work; every
    ``InventoryProduct.distance_km`` in the request must already be calculated
    relative to this anchor.
    """

    anchor_type: ShoppingAnchorType = ShoppingAnchorType.CURRENT_LOCATION
    anchor_id: str | None = Field(default=None, min_length=1)
    radius_km: float = Field(default=0.75, gt=0, le=20)
    selected_store_id: str | None = Field(default=None, min_length=1)
    preferred_store_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_store_preferences(self) -> ShoppingContext:
        if len(self.preferred_store_ids) != len(set(self.preferred_store_ids)):
            raise ValueError("preferred_store_ids must be unique")
        return self


class ReceiptItem(ApiModel):
    sku_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    ingredient_ids: set[str] = Field(default_factory=set)
    brand: str | None = None
    quantity: float = Field(default=1, gt=0)
    unit_price: float = Field(ge=0)
    is_markdown: bool = False
    is_prepared_food: bool = False
    original_unit_price: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_receipt_markdown(self) -> ReceiptItem:
        if self.is_markdown and self.original_unit_price is None:
            raise ValueError("markdown receipt item requires original_unit_price")
        if (
            self.original_unit_price is not None
            and self.unit_price > self.original_unit_price
        ):
            raise ValueError("unit_price cannot exceed original_unit_price")
        return self


class Receipt(ApiModel):
    receipt_id: str = Field(min_length=1)
    purchased_at: AwareDatetime
    store_id: str = Field(min_length=1)
    items: list[ReceiptItem] = Field(min_length=1)


class RecipeIngredient(ApiModel):
    ingredient_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    quantity: float | None = Field(default=None, gt=0)
    unit: str | None = None
    required: bool = True


class Recipe(ApiModel):
    recipe_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    ingredients: list[RecipeIngredient] = Field(min_length=1)
    verified: bool = True
    preparation_minutes: int | None = Field(default=None, gt=0, le=1440)
    meal_intent_id: str | None = Field(default=None, min_length=1)


class InventoryProduct(ApiModel):
    sku_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    ingredient_ids: set[str] = Field(default_factory=set)
    store_id: str = Field(min_length=1)
    distance_km: float = Field(ge=0)
    price: float = Field(ge=0)
    original_price: float | None = Field(default=None, ge=0)
    brand: str | None = None
    is_markdown: bool = False
    is_prepared_food: bool = False
    meal_intent_ids: set[str] = Field(default_factory=set)
    contained_categories: set[str] = Field(default_factory=set)
    safety_eligible: bool = True
    expires_at: AwareDatetime | None = None
    available_quantity: int = Field(default=1, ge=0)
    fulfillment_options: set[FulfillmentOption] = Field(
        default_factory=lambda: {
            FulfillmentOption.DELIVERY,
            FulfillmentOption.NEXT_VISIT,
        }
    )

    @model_validator(mode="after")
    def validate_markdown_price(self) -> InventoryProduct:
        if (
            self.is_markdown
            and self.original_price is not None
            and self.price > self.original_price
        ):
            raise ValueError("markdown price cannot exceed original price")
        if self.is_prepared_food and not self.meal_intent_ids:
            raise ValueError("prepared food requires at least one meal_intent_id")
        if self.is_prepared_food and not self.contained_categories:
            raise ValueError("prepared food requires contained_categories")
        return self


class RecommendationRequest(ApiModel):
    user: UserProfile
    shopping_context: ShoppingContext | None = None
    current_receipt: Receipt
    purchase_history: list[Receipt] = Field(default_factory=list)
    recipe_catalog: list[Recipe] = Field(min_length=1)
    inventory_snapshot: list[InventoryProduct] = Field(default_factory=list)
    requested_mode: RecommendationMode | None = None
    now: AwareDatetime
    limit: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_unique_catalog_keys(self) -> RecommendationRequest:
        recipe_ids = [recipe.recipe_id for recipe in self.recipe_catalog]
        if len(recipe_ids) != len(set(recipe_ids)):
            raise ValueError("recipe_catalog recipe_id values must be unique")
        sku_ids = [product.sku_id for product in self.inventory_snapshot]
        if len(sku_ids) != len(set(sku_ids)):
            raise ValueError("inventory_snapshot sku_id values must be unique")
        return self


class ModelRecommendation(ApiModel):
    recipe_id: str = Field(min_length=1)
    mode: RecommendationMode
    score: float = Field(ge=0, le=1)
    reason_codes: list[str] = Field(min_length=1)


class ProductOption(ApiModel):
    sku_id: str
    name: str
    category: str
    store_id: str
    distance_km: float
    price: float
    original_price: float | None
    brand: str | None
    source: IngredientSource
    expires_at: AwareDatetime | None
    fulfillment_options: set[FulfillmentOption]


class PreparedProductOption(ProductOption):
    ingredient_ids: set[str]
    contained_categories: set[str] = Field(min_length=1)


class IngredientRecommendation(ApiModel):
    ingredient_id: str
    name: str
    category: str
    required: bool = True
    source: IngredientSource
    product_options: list[ProductOption] = Field(default_factory=list)


class BasketStoreOption(ApiModel):
    store_id: str = Field(min_length=1)
    distance_km: float = Field(ge=0)
    covered_required_ingredients: int = Field(ge=0)
    total_required_ingredients: int = Field(ge=1)
    complete: bool
    preferred_for_anchor: bool = False

    @model_validator(mode="after")
    def validate_coverage(self) -> BasketStoreOption:
        if self.covered_required_ingredients > self.total_required_ingredients:
            raise ValueError("store coverage cannot exceed required ingredients")
        if self.complete != (
            self.covered_required_ingredients == self.total_required_ingredients
        ):
            raise ValueError("complete must match store ingredient coverage")
        return self


class BasketStoreSelection(ApiModel):
    anchor_type: ShoppingAnchorType
    anchor_id: str | None = None
    # The response also describes legacy UserProfile radii up to 100 km.
    radius_km: float = Field(gt=0, le=100)
    selected_store_id: str = Field(min_length=1)
    reason_codes: list[str] = Field(min_length=1)
    options: list[BasketStoreOption] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_selection(self) -> BasketStoreSelection:
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("store reason codes must be unique")
        unknown = set(self.reason_codes) - STORE_REASON_CODES
        if unknown:
            raise ValueError(f"unknown store reason codes: {sorted(unknown)}")
        option_ids = [option.store_id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("store options must be unique")
        if self.selected_store_id not in option_ids:
            raise ValueError("selected store must be present in options")
        return self


class RecipeRecommendation(ApiModel):
    recipe_id: str
    title: str
    mode: RecommendationMode
    model_score: float
    missing_count: int = Field(ge=0)
    reason_codes: list[str] = Field(min_length=1)
    ingredients: list[IngredientRecommendation]
    store_selection: BasketStoreSelection | None = None
    fulfillment_options: set[FulfillmentOption]
    safety_status: SafetyStatus
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_public_reason_codes(self) -> RecipeRecommendation:
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("public recipe reason codes must be unique")
        unknown = set(self.reason_codes) - RECIPE_REASON_CODES
        if unknown:
            raise ValueError(f"unknown public recipe reason codes: {sorted(unknown)}")
        unknown_warnings = set(self.warnings) - PUBLIC_WARNING_VALUES
        if unknown_warnings:
            raise ValueError(f"unknown public warnings: {sorted(unknown_warnings)}")
        if (
            self.missing_count > 0
            and self.store_selection is None
            and "safe_ready_option_available" not in self.reason_codes
        ):
            raise ValueError("recommendation with missing products requires a store")
        return self


class ChallengeSelection(ApiModel):
    default_mode: RecommendationMode | None = None
    available_modes: list[RecommendationMode] = Field(default_factory=list)
    mode_reason_codes: dict[RecommendationMode, list[str]] = Field(
        default_factory=dict
    )
    explicit_choice_required: list[RecommendationMode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_mode_selection(self) -> ChallengeSelection:
        if len(self.available_modes) != len(set(self.available_modes)):
            raise ValueError("available_modes must be unique")
        if len(self.explicit_choice_required) != len(
            set(self.explicit_choice_required)
        ):
            raise ValueError("explicit_choice_required must be unique")
        reason_modes = set(self.mode_reason_codes)
        available_modes = set(self.available_modes)
        if reason_modes != available_modes:
            raise ValueError(
                "mode_reason_codes must contain exactly the available modes"
            )
        if not set(self.explicit_choice_required) <= available_modes:
            raise ValueError(
                "explicit_choice_required must be a subset of available_modes"
            )
        if self.default_mode is not None:
            if self.default_mode not in available_modes:
                raise ValueError("default_mode must be available")
            if self.default_mode in set(self.explicit_choice_required):
                raise ValueError("default_mode cannot require explicit choice")
        unknown = {
            code
            for codes in self.mode_reason_codes.values()
            for code in codes
            if code not in CHALLENGE_REASON_CODES
        }
        if unknown:
            raise ValueError(f"unknown public challenge reason codes: {sorted(unknown)}")
        if any(not codes for codes in self.mode_reason_codes.values()):
            raise ValueError("each available mode requires a reason code")
        if any(
            len(codes) != len(set(codes))
            for codes in self.mode_reason_codes.values()
        ):
            raise ValueError("public challenge reason codes must be unique per mode")
        return self


class RecommendationResponse(ApiModel):
    contract_version: str = CONTRACT_VERSION
    user_id: str
    receipt_id: str
    challenge_selection: ChallengeSelection
    recommendations: list[RecipeRecommendation]
    filtered_candidates: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selection_matches_recommendations(self) -> RecommendationResponse:
        recipe_ids = [item.recipe_id for item in self.recommendations]
        if len(recipe_ids) != len(set(recipe_ids)):
            raise ValueError("recommendations must contain unique recipe_id values")
        modes = {item.mode for item in self.recommendations}
        if modes != set(self.challenge_selection.available_modes):
            raise ValueError("available_modes must match recommendation modes")
        if self.challenge_selection.default_mode is not None:
            if not self.recommendations:
                raise ValueError("default_mode requires a recommendation")
            if self.recommendations[0].mode != self.challenge_selection.default_mode:
                raise ValueError("the default recommendation must be first")
        unknown_warnings = set(self.warnings) - PUBLIC_WARNING_VALUES
        if unknown_warnings:
            raise ValueError(f"unknown public warnings: {sorted(unknown_warnings)}")
        return self


class CookVariant(ApiModel):
    recipe_id: str = Field(min_length=1)
    preparation_minutes: int | None = Field(default=None, gt=0, le=1440)
    missing_count: int = Field(ge=0)
    ingredients: list[IngredientRecommendation]
    store_selection: BasketStoreSelection | None = None
    fulfillment_options: set[FulfillmentOption]
    warnings: list[str] = Field(default_factory=list)


class ReadyVariant(ApiModel):
    meal_intent_id: str = Field(min_length=1)
    product_options: list[PreparedProductOption] = Field(min_length=1)
    fulfillment_options: set[FulfillmentOption] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


class MealRecommendation(ApiModel):
    # HTTP serving fills this opaque token after safety/selection. Offline
    # evaluation may construct recommendations without issuing reward offers.
    offer_id: str | None = None
    meal_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    mode: RecommendationMode
    model_score: float = Field(ge=0, le=1)
    default_route: MealRoute
    available_routes: set[MealRoute] = Field(min_length=1)
    reason_codes: list[str] = Field(min_length=1)
    route_reason_codes: list[str] = Field(min_length=1)
    cook_variant: CookVariant | None = None
    ready_variant: ReadyVariant | None = None
    safety_status: SafetyStatus
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_routes(self) -> MealRecommendation:
        if self.default_route not in self.available_routes:
            raise ValueError("default_route must be available")
        if MealRoute.COOK in self.available_routes and self.cook_variant is None:
            raise ValueError("cook route requires cook_variant")
        if MealRoute.READY in self.available_routes and self.ready_variant is None:
            raise ValueError("ready route requires ready_variant")
        if self.cook_variant is not None and MealRoute.COOK not in self.available_routes:
            raise ValueError("cook_variant requires cook route")
        if self.ready_variant is not None and MealRoute.READY not in self.available_routes:
            raise ValueError("ready_variant requires ready route")
        recipe_unknown = set(self.reason_codes) - RECIPE_REASON_CODES
        if recipe_unknown:
            raise ValueError(
                f"unknown public recipe reason codes: {sorted(recipe_unknown)}"
            )
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("public recipe reason codes must be unique")
        if len(self.route_reason_codes) != len(set(self.route_reason_codes)):
            raise ValueError("public route reason codes must be unique")
        unknown = set(self.route_reason_codes) - ROUTE_REASON_CODES
        if unknown:
            raise ValueError(f"unknown public route reason codes: {sorted(unknown)}")
        unknown_warnings = set(self.warnings) - PUBLIC_WARNING_VALUES
        if unknown_warnings:
            raise ValueError(f"unknown public warnings: {sorted(unknown_warnings)}")
        return self


class MealRecommendationResponse(ApiModel):
    contract_version: str = CONTRACT_VERSION
    user_id: str
    receipt_id: str
    challenge_selection: ChallengeSelection
    recommendations: list[MealRecommendation]
    filtered_candidates: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_selection_matches_recommendations(
        self,
    ) -> MealRecommendationResponse:
        meal_ids = [item.meal_id for item in self.recommendations]
        if len(meal_ids) != len(set(meal_ids)):
            raise ValueError("recommendations must contain unique meal_id values")
        modes = {item.mode for item in self.recommendations}
        if modes != set(self.challenge_selection.available_modes):
            raise ValueError("available_modes must match recommendation modes")
        if self.challenge_selection.default_mode is not None:
            if not self.recommendations:
                raise ValueError("default_mode requires a recommendation")
            if self.recommendations[0].mode != self.challenge_selection.default_mode:
                raise ValueError("the default recommendation must be first")
        unknown_warnings = set(self.warnings) - PUBLIC_WARNING_VALUES
        if unknown_warnings:
            raise ValueError(f"unknown public warnings: {sorted(unknown_warnings)}")
        return self


class HealthResponse(ApiModel):
    status: str
    contract_version: str = CONTRACT_VERSION
    recommendation_engine: str
    model_fallback: bool


class SavedRecipeSaveRequest(ApiModel):
    user_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)


class SavedRecipeCollection(ApiModel):
    contract_version: str = CONTRACT_VERSION
    user_id: str
    saved_recipe_ids: list[str]

    @model_validator(mode="after")
    def validate_unique_recipes(self) -> SavedRecipeCollection:
        if self.saved_recipe_ids != sorted(set(self.saved_recipe_ids)):
            raise ValueError("saved_recipe_ids must be sorted and unique")
        return self


class SavedRecipeSaveResponse(SavedRecipeCollection):
    status: SavedRecipeStatus


class PrivateRank(ApiModel):
    cohort: RankCohort
    position: int = Field(ge=1)
    cohort_size: int = Field(ge=1)
    percentile: float = Field(ge=0, le=100)


class ProgressSnapshot(ApiModel):
    user_id: str
    verified_receipts: int = Field(ge=0)
    purchase_days: int = Field(ge=0)
    meals_completed: int = Field(ge=0)
    recipes_completed: int = Field(ge=0)
    ready_meals_completed: int = Field(ge=0)
    markdown_savings: float = Field(ge=0)
    rescue_items: float = Field(ge=0)
    referral_rewards: int = Field(ge=0)
    rewarded_meals: int = Field(default=0, ge=0)
    avatar_xp: int = Field(ge=0)
    avatar_level: int = Field(ge=1)
    xp_to_next_level: int = Field(ge=1)
    private_rank: PrivateRank


class MealPlanSaveRequest(ApiModel):
    offer_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    meal_id: str = Field(min_length=1)
    selected_route: MealRoute
    selected_recipe_id: str | None = Field(default=None, min_length=1)
    selected_product_ids: set[str] = Field(default_factory=set)
    fulfillment: FulfillmentOption
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_selected_route(self) -> MealPlanSaveRequest:
        if self.selected_route == MealRoute.COOK and self.selected_recipe_id is None:
            raise ValueError("cook route requires selected_recipe_id")
        if self.selected_route == MealRoute.READY and not self.selected_product_ids:
            raise ValueError("ready route requires selected_product_ids")
        return self


class MealRewardStatus(StrEnum):
    AWAITING_PURCHASE = "awaiting_purchase"
    NO_PURCHASE_EVIDENCE = "no_purchase_evidence"
    AVAILABLE = "available"
    AWARDED = "awarded"
    PURCHASE_DAY_REWARD_USED = "purchase_day_reward_used"


class MealReward(ApiModel):
    status: MealRewardStatus
    xp: int = Field(ge=0)
    purchase_day: date | None = None


class MealPlanSnapshot(ApiModel):
    offer_id: str
    plan_id: str
    user_id: str
    meal_id: str
    selected_route: MealRoute
    status: MealPlanStatus
    selected_recipe_id: str | None
    selected_product_ids: list[str]
    collected_product_ids: list[str]
    fulfillment: FulfillmentOption
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    completion_evidence: str | None = None
    reward: MealReward


class MealPlanSaveResponse(ApiModel):
    contract_version: str = CONTRACT_VERSION
    status: MealPlanSaveStatus
    reason_codes: list[str]
    plan: MealPlanSnapshot | None = None
    progress: ProgressSnapshot


class CookingConfirmationRequest(ApiModel):
    user_id: str = Field(min_length=1)
    now: AwareDatetime


class MealPlanCompletionResponse(ApiModel):
    contract_version: str = CONTRACT_VERSION
    status: MealPlanCompletionStatus
    reason_codes: list[str]
    plan: MealPlanSnapshot | None = None
    progress: ProgressSnapshot


class ReceiptProgressRequest(ApiModel):
    user_id: str = Field(min_length=1)
    rank_cohort: RankCohort = RankCohort.COOKING_HOUSEHOLDS
    receipt: Receipt
    meal_plan_id: str | None = Field(default=None, min_length=1)
    recipe_id: str | None = None
    recipe_completed: bool = False
    now: AwareDatetime

    @model_validator(mode="after")
    def validate_recipe_completion(self) -> ReceiptProgressRequest:
        if self.recipe_completed and self.recipe_id is None:
            raise ValueError("recipe_completed requires recipe_id")
        return self


class ReceiptProgressResponse(ApiModel):
    contract_version: str = CONTRACT_VERSION
    status: ReceiptEventStatus
    fraud_score: float = Field(ge=0, le=1)
    reason_codes: list[str]
    progress: ProgressSnapshot
    meal_plan: MealPlanSnapshot | None = None


class ReferralEvaluationRequest(ApiModel):
    inviter_user_id: str = Field(min_length=1)
    invitee_user_id: str = Field(min_length=1)
    invite_code: str = Field(min_length=6, max_length=64)
    inviter_device_hash: str | None = None
    invitee_device_hash: str | None = None
    inviter_payment_hash: str | None = None
    invitee_payment_hash: str | None = None


class ReferralReward(ApiModel):
    reward_type: str = "virtual_progress"
    inviter_xp: int = Field(default=20, ge=0)
    invitee_xp: int = Field(default=20, ge=0)
    monetary_value: float = Field(default=0, ge=0)


class ReferralEvaluationResponse(ApiModel):
    contract_version: str = CONTRACT_VERSION
    status: ReferralStatus
    fraud_score: float = Field(ge=0, le=1)
    reason_codes: list[str]
    reward: ReferralReward
    inviter_progress: ProgressSnapshot
    invitee_progress: ProgressSnapshot
