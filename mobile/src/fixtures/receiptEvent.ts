/** Копия examples/receipt_event.json из backend. */
/** Legacy design reference; NOT used by the API 1.2 flow. See makeDemoReceipt. */
export const receiptEvent = {
  "user_id": "user_demo_001",
  "receipt": {
    "receipt_id": "receipt_followup_001",
    "purchased_at": "2026-09-03T18:10:00+03:00",
    "store_id": "store_17",
    "items": [
      {
        "sku_id": "milk_markdown_930",
        "name": "Молоко 3,2%",
        "category": "dairy",
        "ingredient_ids": ["milk"],
        "quantity": 2,
        "unit_price": 49.99,
        "is_markdown": true,
        "original_unit_price": 99.99
      }
    ]
  },
  "recipe_id": "vegetable_omelette",
  "recipe_completed": true,
  "now": "2026-09-03T18:15:00+03:00"
};
