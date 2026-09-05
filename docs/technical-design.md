# Technical design: meal-first X5 Domovoi PoC

- **Статус:** API contract `1.2`, selector, книга, single-store и `cook/ready`
  meal-flow реализованы. UI и актуальный ML scorer интегрированы, локальные
  автопроверки пройдены; ручной прогон на телефоне и финальный eval открыты,
  2026-09-05. [Карта интеграции и адаптаций](integration-handoff.md).
- **Decision source:** [ADR-001](decisions/001-recipe-first-poc.md).
- **Meal extension:** [ADR-002](decisions/002-personal-meal-contract.md).
- **Selector / API 1.2:** [ADR-003](decisions/003-challenge-mode-selection.md),
  [ADR-004](decisions/004-recipe-book-and-shopping-context.md).
- **Product source:** [current concept](research/persona_vxofi/rescue-domovoi-concept.md).
- **Scope:** backend/integration/safety contract; frontend и ML могут
  разрабатываться параллельно.

## 1. Цель backend-контура

Дать frontend стабильный HTTP/JSON-контракт, который уже работает на
детерминированном mock recommender. ML-участник затем заменяет только реализацию
`RecommendationEngine.rank(request)`, сохраняя вход и выход.

Контур должен доказать техническую связность:

```text
synthetic profile + receipt + recipes + inventory
→ model/mock ranking
→ deterministic safety and availability policy
→ API response with reason codes
→ frontend
```

## 2. Goals

- versioned recommendation API;
- Pydantic-схемы как исполняемый контракт;
- заменяемый mock/model engine;
- сортировка безопасных кандидатов по missing count и model score;
- ingredient-level `receipt / home / markdown / full_price / unavailable`;
- доставка и следующий визит как fulfillment options;
- deterministic safety filter и explainable warnings;
- тесты happy path, fallback и отклонения unsafe inventory;
- runnable local service и README.

## 3. Non-goals первого инкремента

- production-интеграция с каталогом, кассой или доставкой;
- промышленный training pipeline/model registry; demo-модель пока обучается
  на синтетике при создании адаптера;
- production database и authentication;
- production antifraud/referral engine;
- LLM-generated recipes или food-safety instructions;
- реальные платежи, бронь, reward и push;
- промышленная нагрузка.

## 4. Архитектура

```text
┌──────────────────┐        POST /api/v1/recommendations
│ Frontend / Figma │ ─────────────────────────────────────┐
└──────────────────┘                                      │
                                                          ▼
                                              ┌──────────────────────┐
                                              │ FastAPI              │
                                              │ RecommendationService│
                                              └──────────┬───────────┘
                                                         │
                              ┌──────────────────────────┼─────────────────────┐
                              ▼                          ▼                     ▼
                    ┌──────────────────┐       ┌─────────────────┐   ┌─────────────────┐
                    │ Recommendation   │       │ SafetyPolicy    │   │ Response mapper │
                    │ Engine protocol  │       │ deterministic   │   │ + reason codes  │
                    └────────┬─────────┘       └─────────────────┘   └─────────────────┘
                             │
                    ┌────────┴─────────┐
                    ▼                  ▼
              Mock engine         ML adapter
              (сейчас)            (участник 1)
```

Safety располагается **после** model ranking и не может быть отменён score.
Backend не интерпретирует внутренние признаки модели и не обучает её.

## 5. RecommendationEngine contract

Python boundary:

```python
class RecommendationEngine(Protocol):
    def rank(
        self,
        request: RecommendationRequest,
    ) -> list[ModelRecommendation]: ...
```

`ModelRecommendation` содержит внутренний результат model layer:

```json
{
  "recipe_id": "recipe_128",
  "mode": "explore",
  "score": 0.82,
  "reason_codes": [
    "quick_recipe",
    "personalized_discovery"
  ]
}
```

В текущем smoke-adapter поле `mode` остаётся legacy hint для совместимости
параллельной разработки. Начиная с HTTP contract `1.1`, оно не является
финальным типом челленджа: один рецепт может быть допустим для нескольких
стратегий. Внешний mode назначает challenge selector после safety. Целевой
внутренний контракт модели описан в
[ADR-003](decisions/003-challenge-mode-selection.md#7-граница-с-mlrecsys).
Внутренние model reason codes также не копируются напрямую в HTTP-ответ:
публичные объяснения пересчитываются по фактически собранному и прошедшему
safety офферу через реестр `app/explanations.py`.

Backend затем:

1. находит рецепт в переданном каталоге;
2. вычисляет покрытие текущим чеком и явными `home_ingredient_ids`;
3. фильтрует inventory по safety/radius/availability относительно явно
   выбранного `home/work/current/custom` anchor;
4. выбирает одну точку сбора по coverage → привычности → расстоянию либо
   принимает явный выбор пользователя;
5. прикладывает markdown и full-price options только к ингредиентам рецепта и
   только из выбранной точки;
6. исключает recipe candidate с обязательным недоступным ингредиентом;
7. определяет допустимость каждого безопасного рецепта для
   `current/repeat/explore`;
8. сортирует кандидатов каждой стратегии по `missing_count ASC`, затем
   `model_score DESC`;
9. выбирает default mode и до двух уникальных альтернатив;
10. возвращает публичные availability warnings и число отфильтрованных model
   candidates; конкретные внутренние причины фильтрации пишет только в log.

`RecommendationEngine` отвечает за персональную relevance eligibility и не
должен отдавать заведомо нерелевантные кандидаты. Конкретный model threshold
выбирает ML/Recsys owner по evaluation; backend не подменяет его произвольным
числом. Safety и availability всё равно применяются после модели.

## 6. HTTP API v1

### `GET /health`

Проверка запуска сервиса.

### `POST /api/v1/recommendations`

Input:

- `user`: legacy radius, явные исключения, сохранённые рецепты и observed
  affinities;
- `shopping_context`: тип выбранного места, непрозрачный ID, пеший радиус
  (demo default 750 м), привычные точки и необязательный ручной выбор магазина;
- `current_receipt`: последний подтверждённый чек;
- `purchase_history`: опциональная синтетическая история для model layer;
- `recipe_catalog`: небольшой проверенный каталог;
- `inventory_snapshot`: synthetic availability магазинов/доставки;
- `now`: фиксируемое время для воспроизводимой safety-проверки.

Output:

- `challenge_selection`: default mode, доступные режимы, причины выбора и
  режимы, требующие явного opt-in;
- в начальной выдаче — до трёх безопасных рекомендаций, не более одной на
  mode и без повторения recipe;
- mode, score, missing count и reason codes;
- состояние каждого ингредиента;
- `store_selection`: одна точка cook-корзины, объяснение выбора и варианты с
  явным признаком полного покрытия;
- безопасные markdown/full-price варианты и fulfillment capabilities;
- warning об отсутствии брони;
- число model candidates, исключённых safety/availability.

Схемы в коде являются source of truth. Пример запроса находится в
`examples/recommendation_request.json`.

При `requested_mode=null` API выбирает основной челлендж и возвращает только
уникальные mode-альтернативы. При явном `requested_mode` может быть возвращено
до `limit` рецептов одного режима. `explore` означает новизну, поэтому может
использовать текущий чек; полная новая корзина без `receipt/home` ингредиентов
не становится default без явного выбора. Полные правила и инварианты —
[ADR-003](decisions/003-challenge-mode-selection.md).

### `POST /api/v1/meal-recommendations`

Meal-level обёртка над recipe flow с тем же `challenge_selection`. Для блюда
возвращает `default_route`, доступные `cook/ready` варианты и отдельные reason
codes выбора route. `ready` появляется только при явном проверенном mapping
`meal_intent_id → prepared SKU` после safety/availability фильтрации.

### `POST /api/v1/saved-recipes`

Идемпотентно добавляет рецепт в process-local книгу пользователя. Сохранение
не начисляет XP. На следующем recommendation-вызове backend объединяет эту
книгу с legacy `user.saved_recipe_ids`, замыкая `save → repeat`.

### `GET /api/v1/saved-recipes/{user_id}`

Возвращает отсортированный список сохранённых recipe IDs. Production storage,
удаление и синхронизация между устройствами находятся вне PoC.

### `POST /api/v1/meal-plans`

Сохраняет выбранный `cook` либо `ready` route, список выбранных SKU и способ
получения. Повтор `plan_id` идемпотентен, а попытка использовать чужой plan id
отклоняется.

### `POST /api/v1/meal-plans/{plan_id}/complete-cook`

Отдельное подтверждение пользователя «приготовлено». Для плана с недостающими
товарами доступно только после их появления в подтверждённых чеках. `ready`
нельзя завершить этим endpoint: для него нужен совпавший подтверждённый чек.

## 7. Safety policy

### Product safety

- `safety_eligible=false` всегда исключает SKU;
- `expires_at <= now` исключает SKU;
- `available_quantity <= 0` исключает SKU;
- товар вне `shopping_context.radius_km` исключается; если новый контекст не
  передан, используется legacy `user.radius_km`;
- адреса и координаты backend не принимает: расстояния inventory уже
  рассчитаны источником относительно непрозрачного anchor;
- user-excluded category/ingredient исключается;
- markdown допускается только для утверждённых rescue-категорий;
- food safety не выводится LLM и не изменяется model score;
- для production category cutoffs должны задаваться владельцем safety policy,
  а не обучаться из кликов.

### Product trust

- markdown помечен как незабронированный best-effort option;
- full-price fallback явно отличается от markdown;
- out-of-recipe SKU не возвращаются;
- cook-вариант не смешивает SKU нескольких магазинов; явно выбранная неполная
  точка не подменяется скрытым split-store fallback;
- backend не делает health/family/lifestyle inference;
- commercial metadata отсутствует в model/API contract organic ranking.
- готовый SKU должен иметь явный `meal_intent_id`; LLM не создаёт соответствие
  блюд на лету;
- ограничения пользователя проверяются также по `contained_categories`
  готового блюда, а не только по общей категории `prepared_food`;
- отсутствие безопасного ready-варианта не скрывает cook-вариант;
- пользовательский route имеет приоритет над demo-selector.

### Event safety

- idempotency по `receipt_id`;
- все чеки дня схлопываются в один purchase day;
- duplicate receipt не меняет state повторно;
- receipt replay другим пользователем отклоняется;
- неоднозначный referral collision → `pending_review`;
- жалоба/stock mismatch не считается fraud автоматически;
- личный прогресс не отнимается по спорному событию без reconciliation.

## 8. Реализованный state/event contract

```text
meal_recommendation_created
→ optional recipe_saved → repeat_eligible
→ meal_plan_saved(cook | ready)
→ fulfillment_selected(delivery | next_visit)
→ receipt_received
→ receipt_verified | pending_review
→ cook: ingredients_matched → cooking_confirmed
  ready: prepared_meal_matched
→ meal_plan_completed
→ personal_progress_updated
```

HTTP endpoints:

- `POST /api/v1/meal-recommendations`;
- `POST /api/v1/saved-recipes`;
- `GET /api/v1/saved-recipes/{user_id}`;
- `POST /api/v1/meal-plans`;
- `POST /api/v1/meal-plans/{plan_id}/complete-cook`;
- `POST /api/v1/events/receipts`;
- `GET /api/v1/progress/{user_id}`;
- `POST /api/v1/referrals/evaluate`.

Process-local in-memory repository атомарно хранит recipe book, meal plans, владельца
`receipt_id`, уникальные purchase dates, cook/ready completions, фактическую
markdown-экономию, rescue item count и уже вознаграждённый referral. Повторный
receipt id или завершённый `plan_id` не меняет progress; несколько чеков в один
московский календарный день дают только один purchase-day increment независимо
от исходного UTC offset. Все входные timestamps обязаны содержать timezone;
naive datetime отклоняется схемой с HTTP 422.

Progress response содержит только собственную позицию, размер synthetic cohort
и percentile. Cooking households и ready-heavy пользователи сравниваются в
разных когортах; единичный выбор route не меняет сегмент. Endpoint публичного
leaderboard отсутствует; ФИО и адреса не входят в схемы.

Referral reward выдаётся один раз после первого verified purchase day invitee.
Оба участника получают по `20 XP`; это virtual progress с `monetary_value=0`.
Self-referral и повторная атрибуция
отклоняются. Совпадение device/payment hash имеет demo score `0.75/0.80` и
уходит в `pending_review`; hard-block threshold равен `0.95`. Это прозрачные
PoC-константы, не обученные и не принятые как production thresholds.

## 9. Error and fallback behavior

| Ситуация | Поведение |
|---|---|
| markdown SKU отсутствует/unsafe | удалить option, попробовать full-price |
| нет full-price аналога | cook ingredient `unavailable`; recipe endpoint исключает candidate, meal endpoint независимо проверяет ready |
| все кандидаты после safety исключены | вернуть `recommendations=[]` и один общий public warning без recipe/SKU ID |
| model вернул неизвестный `recipe_id` | исключить candidate, увеличить `filtered_candidates`, детали записать только в log |
| model недоступен | переключиться на deterministic mock в demo mode, записать ошибку и показать fallback в `/health` |
| delivery недоступна | оставить `next_visit` |
| availability изменилась | стандартное уведомление; денежной компенсации нет |
| ready SKU не прошёл safety | удалить ready-вариант, сохранить cook-вариант |
| cook собрать нельзя, но ready безопасен | вернуть ready-only рекомендацию |
| ready SKU не найден в чеке | сохранить plan без завершения и начисления XP |
| manual completion для ready | отклонить; нужен подтверждённый чек |

## 10. Testing

Unit/API tests backend-контура:

- health endpoint;
- текущий чек закрывает ингредиент;
- markdown option ранжируется перед full-price;
- full-price используется при отсутствии markdown;
- expired/unsafe/out-of-radius SKU не проходит;
- explicit exclusion применяется;
- рецепт с unavailable required ingredient исключается;
- меньше missing items ранжируются выше;
- reason codes и no-reservation warning присутствуют;
- ответ соответствует versioned schema.
- meal recommendation возвращает согласованные `default_route` и variants;
- unsafe ready SKU не скрывает cook-вариант;
- ready plan завершается только совпавшим verified receipt;
- cook plan требует collection и отдельное cooking confirmation;
- один meal plan не начисляет XP повторно;
- receipt update идемпотентен;
- cross-user replay отклоняется, future timestamp уходит в review;
- один день покупки начисляется один раз;
- разные UTC offset одного московского дня схлопываются, naive time отклоняется;
- avatar XP/level и private rank обновляются детерминированно;
- referral требует verified purchase, награждается один раз;
- параллельные duplicate receipt/referral не обходят idempotency;
- self-referral блокируется, device/payment collision уходит в review.

Model/eval tests принадлежат ML/Recsys owner:

- hit rate на 30–50 профилях;
- own-history vs shuffled-history;
- coverage и diversity;
- stability contract/schema;
- quality отдельных `current / repeat / explore` modes.

## 11. Ownership

| Зона | Owner | Reviewer |
|---|---|---|
| Synthetic data/model/eval | ML/Recsys & Evaluation | Backend/Integration/Safety |
| Frontend/user flow/slides | Product/UX & Frontend | команда |
| API/state/integration | Backend/Integration/Safety | ML/Recsys owner |
| Safety/antifraud policy | Backend/Integration/Safety | Product/UX owner |
| Product/metric/economic changes | команда | команда |

## 12. Definition of Done backend-инкремента

- `python -m pytest` проходит;
- `uvicorn app.main:app --reload` запускает API;
- example request возвращает три или меньше рекомендаций;
- unsafe fixture не попадает в ответ;
- receipt/referral не меняют state дважды;
- личный rank не раскрывает список других пользователей;
- frontend может работать только по опубликованной схеме;
- README и промежуточные материалы не заявляют незавершённое как результат.
