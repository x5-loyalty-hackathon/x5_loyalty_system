/** Демо-payload под новый маршрут. Все товарные варианты — по обычной цене. */
export const recommendationRequest = {
  user: {
    user_id: 'user_demo_001',
    radius_km: 3,
    excluded_categories: [],
    excluded_ingredient_ids: [],
    home_ingredient_ids: [],
    saved_recipe_ids: ['syrniki'],
    history_categories: ['dairy', 'vegetable', 'meat', 'pantry'],
    preferred_brands: ['Макфа'],
  },
  current_receipt: {
    receipt_id: 'receipt_domovoi_demo_001',
    purchased_at: '2026-09-04T10:00:00+03:00',
    store_id: 'store_17',
    items: [
      { sku_id: 'pasta_home', name: 'Спагетти', category: 'pantry', ingredient_ids: ['pasta'], quantity: 1, unit_price: 89.99 },
      { sku_id: 'mince_home', name: 'Фарш индейки', category: 'meat', ingredient_ids: ['mince'], quantity: 1, unit_price: 239.99 },
      { sku_id: 'tomato_home', name: 'Помидоры', category: 'vegetable', ingredient_ids: ['tomato'], quantity: 1, unit_price: 159.9 },
      { sku_id: 'cheese_home', name: 'Пармезан', category: 'dairy', ingredient_ids: ['cheese'], quantity: 1, unit_price: 219.9 },
      { sku_id: 'curd_home', name: 'Творог', category: 'dairy', ingredient_ids: ['cottage_cheese'], quantity: 1, unit_price: 129.9 },
    ],
  },
  purchase_history: [],
  recipe_catalog: [
    {
      recipe_id: 'spaghetti_bolognese',
      title: 'Спагетти болоньезе',
      verified: true,
      preparation_minutes: 35,
      ingredients: [
        { ingredient_id: 'pasta', name: 'Спагетти', category: 'pantry', required: true },
        { ingredient_id: 'mince', name: 'Фарш индейки', category: 'meat', required: true },
        { ingredient_id: 'tomato', name: 'Помидоры', category: 'vegetable', required: true },
        { ingredient_id: 'onion', name: 'Лук репчатый', category: 'vegetable', required: true },
        { ingredient_id: 'cheese', name: 'Пармезан', category: 'dairy', required: true },
        { ingredient_id: 'basil', name: 'Базилик свежий', category: 'herbs', required: true },
      ],
    },
    {
      recipe_id: 'syrniki',
      title: 'Сырники',
      verified: true,
      preparation_minutes: 25,
      ingredients: [
        { ingredient_id: 'cottage_cheese', name: 'Творог', category: 'dairy', required: true },
        { ingredient_id: 'egg', name: 'Яйца', category: 'egg', required: true },
      ],
    },
    {
      recipe_id: 'chicken_soup',
      title: 'Куриный суп',
      verified: true,
      preparation_minutes: 45,
      ingredients: [
        { ingredient_id: 'chicken', name: 'Курица', category: 'meat', required: true },
        { ingredient_id: 'carrot', name: 'Морковь', category: 'vegetable', required: true },
      ],
    },
  ],
  inventory_snapshot: [
    { sku_id: 'onion_01', name: 'Лук репчатый', category: 'vegetable', ingredient_ids: ['onion'], store_id: 'store_17', distance_km: 0.8, price: 49.99, original_price: 49.99, is_markdown: false, safety_eligible: true, available_quantity: 20, fulfillment_options: ['delivery', 'next_visit'] },
    { sku_id: 'basil_01', name: 'Базилик свежий', category: 'herbs', ingredient_ids: ['basil'], store_id: 'store_17', distance_km: 0.8, price: 89.99, original_price: 89.99, is_markdown: false, safety_eligible: true, available_quantity: 10, fulfillment_options: ['delivery', 'next_visit'] },
    { sku_id: 'egg_01', name: 'Яйца C1', category: 'egg', ingredient_ids: ['egg'], store_id: 'store_17', distance_km: 0.8, price: 109.9, original_price: 109.9, is_markdown: false, safety_eligible: true, available_quantity: 8, fulfillment_options: ['delivery', 'next_visit'] },
    { sku_id: 'chicken_01', name: 'Филе куриное', category: 'meat', ingredient_ids: ['chicken'], store_id: 'store_21', distance_km: 1.4, price: 399.9, original_price: 399.9, is_markdown: false, safety_eligible: true, available_quantity: 6, fulfillment_options: ['delivery', 'next_visit'] },
    { sku_id: 'carrot_01', name: 'Морковь', category: 'vegetable', ingredient_ids: ['carrot'], store_id: 'store_21', distance_km: 1.4, price: 59.9, original_price: 59.9, is_markdown: false, safety_eligible: true, available_quantity: 30, fulfillment_options: ['delivery', 'next_visit'] },
  ],
  requested_mode: null,
  now: '2026-09-04T12:00:00+03:00',
  limit: 10,
} as const;
