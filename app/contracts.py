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
    HOME = "home"
    MARKDOWN = "markdown"
    FULL_PRICE = "full_price"
    UNAVAILABLE = "unavailable"


class SafetyStatus(StrEnum):
    APPROVED = "approved"
    ADJUSTED = "adjusted"


class UserProfile(ApiModel):
    user_id: str = Field(min_length=1)
    radius_km: float = Field(default=3.0, gt=0, le=100)
    excluded_categories: set[str] = Field(default_factory=set)
    excluded_ingredient_ids: set[str] = Field(default_factory=set)
    home_ingredient_ids: set[str] = Field(default_factory=set)
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


class RecommendationRequest(ApiModel):
    user: UserProfile
    current_receipt: Receipt
    purchase_history: list[Receipt] = Field(default_factory=list)
    recipe_catalog: list[Recipe] = Field(min_length=1)
    inventory_snapshot: list[InventoryProduct] = Field(default_factory=list)
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
