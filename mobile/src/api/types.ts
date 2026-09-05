/** Client-facing API 1.2 types; app/contracts.py remains authoritative. */
export type IngredientSource = 'receipt' | 'home' | 'markdown' | 'full_price' | 'unavailable';
export type RecommendationMode = 'current' | 'repeat' | 'explore';
export type FulfillmentOption = 'delivery' | 'next_visit';
export type MealRoute = 'cook' | 'ready';
export type Anchor = 'home' | 'work' | 'current_location' | 'custom';
export interface ProductOption {
  sku_id: string; name: string; category: string; store_id: string;
  distance_km: number; price: number; original_price: number | null;
  brand: string | null; source: IngredientSource; expires_at: string | null;
  fulfillment_options: FulfillmentOption[];
}
export interface IngredientRecommendation {
  ingredient_id: string; name: string; category: string; required: boolean;
  source: IngredientSource; product_options: ProductOption[];
}
export interface StoreSelection {
  anchor_type: Anchor; anchor_id: string | null; radius_km: number;
  selected_store_id: string; reason_codes: string[];
  options: Array<{
    store_id: string; distance_km: number; covered_required_ingredients: number;
    total_required_ingredients: number; complete: boolean; preferred_for_anchor: boolean;
  }>;
}
export interface MealRecommendation {
  meal_id: string; title: string; mode: RecommendationMode; model_score: number;
  default_route: MealRoute; available_routes: MealRoute[];
  reason_codes: string[]; route_reason_codes: string[];
  cook_variant: null | {
    recipe_id: string; preparation_minutes: number | null; missing_count: number;
    ingredients: IngredientRecommendation[]; store_selection: StoreSelection | null;
    fulfillment_options: FulfillmentOption[]; warnings: string[];
  };
  ready_variant: null | {
    meal_intent_id: string;
    product_options: Array<ProductOption & { ingredient_ids: string[]; contained_categories: string[] }>;
    fulfillment_options: FulfillmentOption[]; warnings: string[];
  };
  safety_status: 'approved' | 'adjusted'; warnings: string[];
}
export interface MealResponse {
  contract_version: string; user_id: string; receipt_id: string;
  challenge_selection: {
    default_mode: RecommendationMode | null;
    available_modes: RecommendationMode[];
    explicit_choice_required: RecommendationMode[];
    mode_reason_codes: Partial<Record<RecommendationMode, string[]>>;
  };
  recommendations: MealRecommendation[]; filtered_candidates: number; warnings: string[];
}
export interface HealthResponse {
  status: string; contract_version: string; recommendation_engine: string; model_fallback: boolean;
}
export interface RecipeBook {
  contract_version: string; user_id: string; saved_recipe_ids: string[];
}
export interface ProgressSnapshot {
  user_id: string; verified_receipts: number; purchase_days: number;
  meals_completed: number; recipes_completed: number; ready_meals_completed: number;
  markdown_savings: number; rescue_items: number; referral_rewards: number;
  avatar_xp: number; avatar_level: number; xp_to_next_level: number;
  private_rank: {
    cohort: 'cooking_households' | 'ready_heavy'; position: number; cohort_size: number; percentile: number;
  };
}
export interface PlanRequest {
  plan_id: string; user_id: string; meal_id: string; selected_route: MealRoute;
  selected_recipe_id: string | null; selected_product_ids: string[];
  fulfillment: FulfillmentOption; created_at: string;
}
export interface MealPlan extends PlanRequest {
  status: 'saved' | 'collected' | 'completed' | 'cancelled';
  collected_product_ids: string[]; completed_at: string | null; completion_evidence: string | null;
}
export interface PlanResponse {
  contract_version: string; status: 'created' | 'duplicate' | 'rejected';
  reason_codes: string[]; plan: MealPlan | null;
}
export interface CompletionResponse {
  contract_version: string; status: 'completed' | 'duplicate' | 'not_ready' | 'rejected';
  reason_codes: string[]; plan: MealPlan | null; progress: ProgressSnapshot;
}
export interface ReceiptProgressResponse {
  contract_version: string; status: 'verified' | 'duplicate' | 'pending_review' | 'rejected';
  fraud_score: number; reason_codes: string[]; progress: ProgressSnapshot; meal_plan: MealPlan | null;
}
