import fixture from './mealRequest.json' with { type: 'json' };
import type { Anchor, RecommendationMode } from '../api/types.ts';

export const DEMO_USER_ID = fixture.user.user_id;
export const DEMO_NOW = fixture.now;
export const recentReceipt = fixture.current_receipt;

type Receipt = typeof recentReceipt;
type ReceiptItem = Receipt['items'][number];
export interface DemoProfile {
  id: string;
  userId: string;
  label: string;
  description: string;
  currentReceipt: Receipt;
  purchaseHistory: Receipt[];
  excludedCategories: string[];
}

const ingredient = (id: string, name: string, category: string, price: number): ReceiptItem => ({
  sku_id: `${id}_home`, name, category, ingredient_ids: [id], quantity: 1, unit_price: price,
});
const pasta = recentReceipt.items[0];
const mince = recentReceipt.items[1];
const tomato = recentReceipt.items[2];
const cheese = recentReceipt.items[3];
const chicken = ingredient('chicken', 'Куриное филе', 'meat', 299.9);
const carrot = ingredient('carrot', 'Морковь', 'vegetable', 59.9);
const onion = ingredient('onion', 'Лук репчатый', 'vegetable', 49.9);
const cabbage = ingredient('cabbage', 'Капуста', 'vegetable', 79.9);
const potato = ingredient('potato', 'Картофель', 'vegetable', 69.9);

function history(userId: string, baskets: ReceiptItem[][]): Receipt[] {
  return baskets.map((items, i) => ({
    receipt_id: `${userId}-history-2026-08-${19 + i * 4}`,
    purchased_at: `2026-08-${19 + i * 4}T18:00:00+03:00`,
    store_id: i % 2 ? 'store_21' : 'store_17', items,
  }));
}
const copyReceipt = (receipt: Receipt): Receipt => ({
  ...receipt, items: receipt.items.map((item) => ({ ...item, ingredient_ids: [...item.ingredient_ids] })),
});

// Synthetic examples within cooking households, not business segments or
// measured preferences. History is ML context, not verified purchase evidence.
export const DEMO_PROFILES: DemoProfile[] = [
  {
    id: 'family', userId: DEMO_USER_ID, label: 'Семья · паста',
    description: 'Часто покупают пасту, фарш и сыр. В недавнем чеке — основа болоньезе.',
    currentReceipt: recentReceipt,
    purchaseHistory: history(DEMO_USER_ID, [
      [pasta, mince, tomato, cheese], [mince, pasta, onion],
      [pasta, cheese, tomato], [mince, pasta, tomato, onion, cheese],
    ]),
    excludedCategories: [],
  },
  {
    id: 'vegetable', userId: 'user_mobile_vegetable', label: 'Овощные ужины',
    description: 'Готовят без мяса; в истории овощи, паста и сыр. В недавнем чеке — паста и томаты.',
    currentReceipt: { ...recentReceipt, receipt_id: 'user_mobile_vegetable-current-2026-09-04',
      items: [pasta, tomato, carrot] },
    purchaseHistory: history('user_mobile_vegetable', [
      [cabbage, carrot, onion], [pasta, tomato], [cheese, tomato, carrot], [pasta, cabbage, onion],
    ]),
    excludedCategories: ['meat'],
  },
  {
    id: 'soup', userId: 'user_mobile_soup', label: 'Домашний суп',
    description: 'Часто покупают курицу и овощи для супа. Недавний чек содержит курицу, морковь и лук.',
    currentReceipt: { ...recentReceipt, receipt_id: 'user_mobile_soup-current-2026-09-04',
      items: [chicken, carrot, onion] },
    purchaseHistory: history('user_mobile_soup', [
      [chicken, carrot, potato, onion], [chicken, cabbage, carrot],
      [potato, carrot, onion], [chicken, carrot, onion, cabbage],
    ]),
    excludedCategories: [],
  },
];
export const DEFAULT_DEMO_PROFILE = DEMO_PROFILES[0];

// The same three reviewed recipes remain available to every profile; complete
// synthetic stock also permits shopping for ingredients absent in its receipt.
const inventory = [
  ...fixture.inventory_snapshot,
  ...[pasta, mince, tomato, cheese].map((item) => ({
    sku_id: `${item.ingredient_ids[0]}_01`, name: item.name, category: item.category,
    ingredient_ids: item.ingredient_ids, store_id: 'store_17', distance_km: 0.4,
    price: item.unit_price, original_price: item.unit_price, is_markdown: false,
    safety_eligible: true, available_quantity: 10, fulfillment_options: ['delivery', 'next_visit'],
  })),
];

// Synthetic distances relative to the chosen anchor; no GPS/geocoding.
const distances: Record<Anchor, [number, number]> = {
  home: [0.4, 0.65], work: [0.7, 0.25],
  current_location: [0.55, 0.35], custom: [0.3, 0.7],
};
export function buildRecommendationRequest(
  mode: RecommendationMode | null = null, anchor: Anchor = 'home', storeId: string | null = null,
  profile: DemoProfile = DEFAULT_DEMO_PROFILE,
) {
  return {
    ...fixture,
    user: { ...fixture.user, user_id: profile.userId, excluded_categories: [...profile.excludedCategories],
      history_categories: [...new Set(profile.purchaseHistory.flatMap((receipt) => receipt.items.map((item) => item.category)))],
    },
    current_receipt: copyReceipt(profile.currentReceipt),
    purchase_history: profile.purchaseHistory.map(copyReceipt),
    shopping_context: {
      anchor_type: anchor, anchor_id: `demo-${anchor}`, radius_km: 0.75,
      preferred_store_ids: [anchor === 'work' ? 'store_21' : 'store_17'],
      selected_store_id: storeId,
    },
    inventory_snapshot: distances[anchor].flatMap((distance, i) =>
      inventory.map((product) => ({
        ...product, sku_id: i ? `${product.sku_id}_21` : product.sku_id,
        store_id: i ? 'store_21' : 'store_17', distance_km: distance,
      }))),
    requested_mode: mode,
  };
}
