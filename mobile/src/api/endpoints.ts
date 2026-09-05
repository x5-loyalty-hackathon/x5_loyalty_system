import { request } from './client';
import { receiptEvent } from '../fixtures/receiptEvent';
import { recommendationRequest } from '../fixtures/recommendationRequest';
import type {
  ProgressSnapshot,
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
