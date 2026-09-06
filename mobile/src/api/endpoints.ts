import { request } from './client';
import { receiptEvent } from '../fixtures/receiptEvent';
import { recommendationRequest } from '../fixtures/recommendationRequest';
import type {
  ProgressSnapshot,
  KitchenSnapshot,
  RecipeCompletionResponse,
  RecipeDetails,
  ReceiptProgressResponse,
  RecommendationResponse,
} from './types';

export const DEMO_USER_ID = 'user_demo_001';

export function getHealth() {
  return request<{ status: string; contract_version: string }>('/health');
}

export function getRecommendations() {
  return request<RecommendationResponse>('/api/v1/recommendations', {
    method: 'POST',
    body: JSON.stringify(recommendationRequest),
  });
}

export function submitReceipt(recipeId: string) {
  return request<ReceiptProgressResponse>('/api/v1/events/receipts', {
    method: 'POST',
    body: JSON.stringify({ ...receiptEvent, recipe_id: recipeId }),
  });
}

export function getProgress(userId: string = DEMO_USER_ID) {
  return request<ProgressSnapshot>(`/api/v1/progress/${userId}`);
}

export function getKitchen(userId: string = DEMO_USER_ID) {
  return request<KitchenSnapshot>(`/api/v1/kitchen/${userId}`);
}

export function completeRecipe(input: {
  completion_id: string;
  user_id: string;
  recipe_id: string;
  ingredient_ids: string[];
  completed_at: string;
}) {
  return request<RecipeCompletionResponse>('/api/v1/events/recipes/completed', {
    method: 'POST', body: JSON.stringify(input),
  });
}

export function getRecipeDetails(recipeId: string) {
  return request<RecipeDetails>(`/api/v1/recipes/${recipeId}`);
}
