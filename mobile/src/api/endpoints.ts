import { request } from './client';
import { DEMO_USER_ID, DEMO_NOW, recentReceipt, buildRecommendationRequest } from '../fixtures/recommendationRequest';
import type {
  Anchor, RecommendationMode, HealthResponse, MealResponse, PlanRequest,
  PlanResponse, CompletionResponse, RecipeBook, ProgressSnapshot, ReceiptProgressResponse,
} from './types';
import type { DemoReceiptEvent } from '../domain/mealFlow';

export { DEMO_USER_ID };
const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const getHealth = () => request<HealthResponse>('/health');
export const getRecommendations = async (mode: RecommendationMode | null, anchor: Anchor, storeId: string | null) => {
  // Explicit synthetic event bootstrap, not proof inferred from recommendation
  // history. Stable receipt ID makes reruns idempotent; no passive XP is awarded.
  const evidence = await post<ReceiptProgressResponse>('/api/v1/events/receipts', {
    user_id: DEMO_USER_ID, receipt: recentReceipt, now: DEMO_NOW,
  });
  if (!['verified', 'duplicate'].includes(evidence.status)) throw new Error('Текущий demo-чек не подтверждён.');
  return post<MealResponse>('/api/v1/meal-recommendations', buildRecommendationRequest(mode, anchor, storeId));
};
export const getRecipeBook = () => request<RecipeBook>(`/api/v1/saved-recipes/${DEMO_USER_ID}`);
export const saveRecipe = (recipeId: string) => post<RecipeBook & { status: 'created' | 'duplicate' }>(
  '/api/v1/saved-recipes', { user_id: DEMO_USER_ID, recipe_id: recipeId });
export const saveMealPlan = (body: PlanRequest) => post<PlanResponse>('/api/v1/meal-plans', body);
export const submitReceipt = (body: DemoReceiptEvent) => post<ReceiptProgressResponse>('/api/v1/events/receipts', body);
export const completeCook = (planId: string) => post<CompletionResponse>(
  `/api/v1/meal-plans/${encodeURIComponent(planId)}/complete-cook`, { user_id: DEMO_USER_ID, now: DEMO_NOW });
export const getProgress = () => request<ProgressSnapshot>(`/api/v1/progress/${DEMO_USER_ID}`);
