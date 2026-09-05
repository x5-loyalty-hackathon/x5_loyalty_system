from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


CONTRACT_VERSION = "1.0"


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecommendationMode(StrEnum):
    CURRENT = "current"
    REPEAT = "repeat"
    EXPLORE = "explore"


class FulfillmentOption(StrEnum):
    DELIVERY = "delivery"
    NEXT_VISIT = "next_visit"


class IngredientSource(StrEnum):
    RECEIPT = "receipt"
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
    radius_km: float = Field(default=3.0, gt=0, le=100)
    excluded_categories: set[str] = Field(default_factory=set)
    excluded_ingredient_ids: set[str] = Field(default_factory=set)
    saved_recipe_ids: set[str] = Field(default_factory=set)
    history_categories: list[str] = Field(default_factory=list)
    preferred_brands: list[str] = Field(default_factory=list)


class ReceiptItem(ApiModel):
    sku_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str = Field(min_length=1)
    ingredient_ids: set[str] = Field(default_factory=set)
    brand: str | None = None
    quantity: float = Field(default=1, gt=0)
    unit_price: float = Field(ge=0)
    is_markdown: bool = False
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
    purchased_at: datetime
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
    # How many people the listed ingredient quantities feed. Quantities are
    # cook's approximations, so this is what makes them interpretable at all.
    servings: int = Field(default=2, ge=1, le=12)
    # "Тип блюда" / "Кухня" — the facets X5 itself puts on a ready-meal card.
    # Optional so an caller-supplied recipe without them stays valid; when set,
    # they let a recipe be compared with a prepared meal on the retailer's own
    # vocabulary instead of on product-name string matching.
    dish_type: str | None = Field(default=None, min_length=1)
    cuisine: str | None = Field(default=None, min_length=1)


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
    # True when ``price`` is modelled rather than observed; travels through to
    # ``ProductOption.price_is_estimate`` in the response.
    price_is_estimate: bool = False
    safety_eligible: bool = True
    expires_at: datetime | None = None
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
        return self


class ReadyMealOption(ApiModel):
    """A prepared meal X5 sells that is a counterpart to one or more recipes.

    Carries the retailer's own ``plu`` rather than a synthetic sku id: unlike
    ``InventoryProduct``, these are real products observed in a catalogue
    snapshot. ``recipe_ids`` mirrors ``InventoryProduct.ingredient_ids`` — the
    option describes what it can stand in for, so the request stays one flat
    list instead of a nested mapping.
    """

    chain: str = Field(min_length=1)
    plu: str = Field(min_length=1)
    name: str = Field(min_length=1)
    recipe_ids: set[str] = Field(min_length=1)
    price: float | None = Field(default=None, ge=0)
    dish_type: str | None = Field(default=None, min_length=1)
    cuisine: str | None = Field(default=None, min_length=1)


class RecommendationRequest(ApiModel):
    user: UserProfile
    current_receipt: Receipt
    purchase_history: list[Receipt] = Field(default_factory=list)
    recipe_catalog: list[Recipe] = Field(min_length=1)
    inventory_snapshot: list[InventoryProduct] = Field(default_factory=list)
    ready_meal_options: list[ReadyMealOption] = Field(default_factory=list)
    requested_mode: RecommendationMode | None = None
    now: datetime
    limit: int = Field(default=3, ge=1, le=10)


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
    expires_at: datetime | None
    fulfillment_options: set[FulfillmentOption]
    # True when ``price`` is modelled rather than observed. A recommendation
    # shows a cook-it basket next to a real ready-meal price
    # (``ReadyMealOption.price``, an observed PLU price), so the two must not
    # look equally solid.
    price_is_estimate: bool = False


class IngredientRecommendation(ApiModel):
    ingredient_id: str
    name: str
    category: str
    source: IngredientSource
    product_options: list[ProductOption] = Field(default_factory=list)


class RecipeRecommendation(ApiModel):
    recipe_id: str
    title: str
    mode: RecommendationMode
    model_score: float
    missing_count: int = Field(ge=0)
    reason_codes: list[str]
    ingredients: list[IngredientRecommendation]
    fulfillment_options: set[FulfillmentOption]
    safety_status: SafetyStatus
    warnings: list[str] = Field(default_factory=list)
    # The "or just buy it ready" side of the offer: the cheapest prepared
    # counterpart from the request, and how many were on offer in total.
    ready_meal_alternative: ReadyMealOption | None = None
    ready_meal_option_count: int = Field(default=0, ge=0)


class RecommendationResponse(ApiModel):
    contract_version: str = CONTRACT_VERSION
    user_id: str
    receipt_id: str
    recommendations: list[RecipeRecommendation]
    filtered_candidates: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(ApiModel):
    status: str
    contract_version: str = CONTRACT_VERSION


class PrivateRank(ApiModel):
    position: int = Field(ge=1)
    cohort_size: int = Field(ge=1)
    percentile: float = Field(ge=0, le=100)


class ProgressSnapshot(ApiModel):
    user_id: str
    verified_receipts: int = Field(ge=0)
    purchase_days: int = Field(ge=0)
    recipes_completed: int = Field(ge=0)
    markdown_savings: float = Field(ge=0)
    rescue_items: float = Field(ge=0)
    referral_rewards: int = Field(ge=0)
    avatar_xp: int = Field(ge=0)
    avatar_level: int = Field(ge=1)
    xp_to_next_level: int = Field(ge=1)
    private_rank: PrivateRank


class ReceiptProgressRequest(ApiModel):
    user_id: str = Field(min_length=1)
    receipt: Receipt
    recipe_id: str | None = None
    recipe_completed: bool = False
    now: datetime

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
    inviter_xp: int = Field(default=10, ge=0)
    invitee_xp: int = Field(default=10, ge=0)
    monetary_value: float = Field(default=0, ge=0)


class ReferralEvaluationResponse(ApiModel):
    contract_version: str = CONTRACT_VERSION
    status: ReferralStatus
    fraud_score: float = Field(ge=0, le=1)
    reason_codes: list[str]
    reward: ReferralReward
    inviter_progress: ProgressSnapshot
    invitee_progress: ProgressSnapshot
