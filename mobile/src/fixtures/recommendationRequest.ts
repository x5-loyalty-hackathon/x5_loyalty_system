import fixture from './mealRequest.json' with { type: 'json' };
import type { Anchor, RecommendationMode } from '../api/types.ts';

export const DEMO_USER_ID = fixture.user.user_id;
export const DEMO_NOW = fixture.now;
export const recentReceipt = fixture.current_receipt;

// Synthetic distances relative to the chosen anchor; no GPS/geocoding.
const distances: Record<Anchor, [number, number]> = {
  home: [0.4, 0.65], work: [0.7, 0.25],
  current_location: [0.55, 0.35], custom: [0.3, 0.7],
};
export function buildRecommendationRequest(
  mode: RecommendationMode | null = null, anchor: Anchor = 'home', storeId: string | null = null,
) {
  return {
    ...fixture,
    shopping_context: {
      anchor_type: anchor, anchor_id: `demo-${anchor}`, radius_km: 0.75,
      preferred_store_ids: [anchor === 'work' ? 'store_21' : 'store_17'],
      selected_store_id: storeId,
    },
    inventory_snapshot: distances[anchor].flatMap((distance, i) =>
      fixture.inventory_snapshot.map((product) => ({
        ...product, sku_id: i ? `${product.sku_id}_21` : product.sku_id,
        store_id: i ? 'store_21' : 'store_17', distance_km: distance,
      }))),
    requested_mode: mode,
  };
}
