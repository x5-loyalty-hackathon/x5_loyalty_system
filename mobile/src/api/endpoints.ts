import { request } from './client';
import { DEMO_USER_ID, DEMO_NOW, DEFAULT_DEMO_PROFILE, buildRecommendationRequest } from '../fixtures/recommendationRequest';
import type { DemoProfile } from '../fixtures/recommendationRequest';
import type {
  Anchor, RecommendationMode, HealthResponse, MealResponse, PlanRequest,
  PlanResponse, CompletionResponse, RecipeBook, ProgressSnapshot, ReceiptProgressResponse, HomeDecorationSnapshot,
} from './types';
import type { DemoReceiptEvent } from '../domain/mealFlow';

export { DEMO_USER_ID };
const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) });
export const getHealth = () => request<HealthResponse>('/health');
export const getRecommendations = async (
  mode: RecommendationMode | null, anchor: Anchor, storeId: string | null, profile: DemoProfile = DEFAULT_DEMO_PROFILE,
) => {
  // Explicit synthetic event bootstrap, not proof inferred from recommendation
  // history. Stable receipt ID makes reruns idempotent; no passive XP is awarded.
  const evidence = await post<ReceiptProgressResponse>('/api/v1/events/receipts', {
    user_id: profile.userId, receipt: profile.currentReceipt, now: DEMO_NOW,
  });
  if (!['verified', 'duplicate'].includes(evidence.status)) throw new Error('Текущий demo-чек не подтверждён.');
  return post<MealResponse>('/api/v1/meal-recommendations', buildRecommendationRequest(mode, anchor, storeId, profile));
};
export const getRecipeBook = (userId = DEMO_USER_ID) => request<RecipeBook>(`/api/v1/saved-recipes/${encodeURIComponent(userId)}`);
export const saveRecipe = (recipeId: string, userId = DEMO_USER_ID) => post<RecipeBook & { status: 'created' | 'duplicate' }>(
  '/api/v1/saved-recipes', { user_id: userId, recipe_id: recipeId });
export const saveMealPlan = (body: PlanRequest) => post<PlanResponse>('/api/v1/meal-plans', body);
export const submitReceipt = (body: DemoReceiptEvent) => post<ReceiptProgressResponse>('/api/v1/events/receipts', body);
export const completeCook = (planId: string, userId = DEMO_USER_ID) => post<CompletionResponse>(
  `/api/v1/meal-plans/${encodeURIComponent(planId)}/complete-cook`, { user_id: userId, now: DEMO_NOW });
export const getProgress = (userId = DEMO_USER_ID) => request<ProgressSnapshot>(`/api/v1/progress/${encodeURIComponent(userId)}`);
const decorationPath = (userId: string) => `/api/v1/home-decoration/${encodeURIComponent(userId)}`;
export const getHomeDecoration = (userId = DEMO_USER_ID) => request<HomeDecorationSnapshot>(decorationPath(userId));
export const setHomeDecorationGoal = (itemId: string | null, userId = DEMO_USER_ID) =>
  post<HomeDecorationSnapshot>(`${decorationPath(userId)}/goal`, { item_id: itemId });
export const applyHomeDecoration = (itemId: string, userId = DEMO_USER_ID) =>
  post<HomeDecorationSnapshot>(`${decorationPath(userId)}/apply`, { item_id: itemId });
