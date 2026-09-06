# Контракты backend для mobile PoC

Статус на 2026-09-06: все три endpoint ниже существуют как **синтетический
mock backend**. Это позволяет собрать и проверить end-to-end flow, но не
утверждает, что данные о кладовке, рецептах или остатках получены от X5.

Минимальный список. Всё остальное фронтенд уже берёт из существующего
контракта: `POST /api/v1/recommendations`, `POST /api/v1/events/receipts`,
`GET /api/v1/progress/{user_id}`.

## 1. Кладовка пользователя — mock реализован

```text
GET /api/v1/kitchen/{user_id} -> { items: [{ ingredient_id, name, quantity }] }
```

Что лежит дома по подтверждённым чекам. В mock это синтетический баланс,
построенный из `ReceiptItem.ingredient_ids`; ответ явно содержит
`data_source: synthetic_from_verified_receipts`.

Срока годности в ответе нет намеренно: `ReceiptItem` его не содержит, а
`expires_at` есть только у `InventoryProduct` и `ProductOption` — это витрина
магазина, а не покупка. Пока backend не научится связывать купленный SKU с его
партией, срок показывать нечестно.

## 2. Событие «рецепт приготовлен» — mock реализован

```text
POST /api/v1/events/recipes/completed {
  completion_id, user_id, recipe_id, ingredient_ids, completed_at
} -> { status, kitchen, progress }
```

Прогресс начисляется за приготовленный рецепт, а не за чек: покупка и готовка
— разные события, между ними проходят дни. `completion_id` делает событие
идемпотентным. Mock принимает только полный набор ингредиентов из явной
синтетической карточки рецепта и только если они уже есть в кладовке.

Поле `recipe_completed` в receipt endpoint сохранено только ради обратной
совместимости старого demo-flow. Новый mobile flow должен использовать этот
endpoint, а не перегружать событие чека.

## 3. Карточка рецепта — mock реализован

```text
GET /api/v1/recipes/{recipe_id} -> { title, time_minutes, servings, description, steps[] }
```

Время, порции, описание и шаги приготовления. Ответы берутся из маленького
явно синтетического каталога `app/mock_recipes.py`; он не является источником
реального recipe-content и не должен использоваться для ML-оценки.

---

Отдельного API на товары не нужно: замены приходят в
`recommendations[].ingredients[].product_options`, и там уже есть `source:
'markdown'` и `original_price` — этого хватает, чтобы помечать уценку.
