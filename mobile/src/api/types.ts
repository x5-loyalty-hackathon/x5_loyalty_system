/** Повторяет app/contracts.py. Менять только вслед за backend-контрактом. */
export type IngredientSource = 'receipt' | 'home' | 'markdown' | 'full_price' | 'unavailable';
export type RecommendationMode = 'current' | 'repeat' | 'explore';
export type FulfillmentOption = 'delivery' | 'next_visit';
export type SafetyStatus = 'approved' | 'adjusted';
export type ReceiptEventStatus = 'verified' | 'duplicate' | 'pending_review' | 'rejected';

export interface ProductOption {
  sku_id: string;
  name: string;
  category: string;
  store_id: string;
  distance_km: number;
  price: number;
  original_price: number | null;
  brand: string | null;
  source: IngredientSource;
  expires_at: string | null;
  fulfillment_options: FulfillmentOption[];
}

export interface IngredientRecommendation {
  ingredient_id: string;
  name: string;
  category: string;
  source: IngredientSource;
  product_options: ProductOption[];
}

export interface RecipeRecommendation {
  recipe_id: string;
  title: string;
  mode: RecommendationMode;
  model_score: number;
  missing_count: number;
  reason_codes: string[];
  ingredients: IngredientRecommendation[];
  fulfillment_options: FulfillmentOption[];
  safety_status: SafetyStatus;
  warnings: string[];
}

export interface RecommendationResponse {
  contract_version: string;
  user_id: string;
  receipt_id: string;
  recommendations: RecipeRecommendation[];
  filtered_candidates: number;
  warnings: string[];
}

export interface PrivateRank {
  position: number;
  cohort_size: number;
  percentile: number;
}

export interface ProgressSnapshot {
  user_id: string;
  verified_receipts: number;
  purchase_days: number;
  recipes_completed: number;
  markdown_savings: number;
  rescue_items: number;
  referral_rewards: number;
  avatar_xp: number;
  avatar_level: number;
  xp_to_next_level: number;
  private_rank: PrivateRank;
}

export interface ReceiptProgressResponse {
  contract_version: string;
  status: ReceiptEventStatus;
  fraud_score: number;
  reason_codes: string[];
  progress: ProgressSnapshot;
}
