# Что нужно от backend

Минимальный список. Всё остальное фронтенд уже берёт из существующего
контракта: `POST /api/v1/recommendations`, `POST /api/v1/events/receipts`,
`GET /api/v1/progress/{user_id}`.

## 1. Кладовка пользователя

```text
GET /api/v1/kitchen/{user_id} -> { items: [{ ingredient_id, name, quantity, expires_at }] }
```

Что лежит дома по подтверждённым чекам и сколько осталось до конца срока.
Сейчас это статический список в `src/data/demo.ts`, поэтому кухня не растёт
от покупок. `ReceiptItem` срока годности не содержит, остатки backend не
считает.

## 2. Событие «рецепт приготовлен»

```text
POST /api/v1/events/recipe-completed { user_id, recipe_id, ingredient_ids } -> ProgressSnapshot
```

Прогресс начисляется за приготовленный рецепт, а не за чек: покупка и готовка
— разные события, между ними проходят дни. Это же событие должно списывать
использованные продукты из кладовки.

Сейчас фронтенд шлёт `POST /api/v1/events/receipts` с `recipe_completed: true`,
и это создаёт две проблемы: событие требует чек, которого при готовке нет, а
идемпотентность по `receipt_id` не даёт приготовить два рецепта подряд —
второй возвращает `duplicate`.

## 3. Карточка рецепта

```text
GET /api/v1/recipes/{recipe_id} -> { title, time_minutes, servings, description, steps[] }
```

Время, порции, описание и шаги приготовления. `RecipeRecommendation` их не
содержит, поэтому они лежат в `src/data/demo.ts` как демо-контент. Шаги нужны
на экране готовки.

---

Отдельного API на товары не нужно: замены приходят в
`recommendations[].ingredients[].product_options`, и там уже есть `source:
'markdown'` и `original_price` — этого хватает, чтобы помечать уценку.
