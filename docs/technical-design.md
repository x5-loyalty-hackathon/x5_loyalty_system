# Technical design: recipe-first X5 Domovoi PoC

- **Статус:** B1–B3 implemented in working branch, team review required,
  2026-09-03.
- **Decision source:** [ADR-001](decisions/001-recipe-first-poc.md).
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
- обучение ML-модели внутри backend;
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

`ModelRecommendation` содержит только решение model layer:

```json
{
  "recipe_id": "recipe_128",
  "mode": "explore",
  "score": 0.82,
  "reason_codes": [
    "quick_dinner_affinity",
    "discovery_acceptance_high"
  ]
}
```

Backend затем:

1. находит рецепт в переданном каталоге;
2. вычисляет покрытие текущим чеком и явными `home_ingredient_ids`;
3. фильтрует inventory по safety/radius/availability;
4. прикладывает markdown и full-price options только к ингредиентам рецепта;
5. исключает recipe candidate с обязательным недоступным ингредиентом;
6. сортирует оставшиеся кандидаты по `missing_count ASC`, затем
   `model_score DESC`;
7. возвращает warnings и число отфильтрованных кандидатов.

`RecommendationEngine` отвечает за персональную relevance eligibility и не
должен отдавать заведомо нерелевантные кандидаты. Конкретный model threshold
выбирает ML/Recsys owner по evaluation; backend не подменяет его произвольным
числом. Safety и availability всё равно применяются после модели.

## 6. HTTP API v1

### `GET /health`

Проверка запуска сервиса.

### `POST /api/v1/recommendations`

Input:

- `user`: radius, явные исключения, сохранённые рецепты и observed affinities;
- `current_receipt`: последний подтверждённый чек;
- `purchase_history`: опциональная синтетическая история для model layer;
- `recipe_catalog`: небольшой проверенный каталог;
- `inventory_snapshot`: synthetic availability магазинов/доставки;
- `now`: фиксируемое время для воспроизводимой safety-проверки.

Output:

- до трёх безопасных рекомендаций;
- mode, score, missing count и reason codes;
- состояние каждого ингредиента;
- безопасные markdown/full-price варианты и fulfillment capabilities;
- warning об отсутствии брони;
- число model candidates, исключённых safety/availability.

Схемы в коде являются source of truth. Пример запроса находится в
`examples/recommendation_request.json`.

## 7. Safety policy

### Product safety

- `safety_eligible=false` всегда исключает SKU;
- `expires_at <= now` исключает SKU;
- `available_quantity <= 0` исключает SKU;
- товар вне `user.radius_km` исключается;
- user-excluded category/ingredient исключается;
- markdown допускается только для утверждённых rescue-категорий;
- food safety не выводится LLM и не изменяется model score;
- для production category cutoffs должны задаваться владельцем safety policy,
  а не обучаться из кликов.

### Product trust

- markdown помечен как незабронированный best-effort option;
- full-price fallback явно отличается от markdown;
- out-of-recipe SKU не возвращаются;
- backend не делает health/family/lifestyle inference;
- commercial metadata отсутствует в model/API contract organic ranking.

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
recommendation_created
→ recipe_saved
→ fulfillment_selected(delivery | next_visit)
→ receipt_received
→ receipt_verified | pending_review
→ ingredients_matched
→ personal_progress_updated
```

HTTP endpoints:

- `POST /api/v1/events/receipts`;
- `GET /api/v1/progress/{user_id}`;
- `POST /api/v1/referrals/evaluate`.

Process-local in-memory repository атомарно хранит владельца `receipt_id`, уникальные
purchase dates, recipe completions, фактическую markdown-экономию, rescue item
count и уже вознаграждённый referral. Повторный receipt id не меняет state;
несколько чеков в один день дают только один purchase-day increment.

Progress response содержит только собственную позицию, размер synthetic cohort
и percentile. Endpoint публичного leaderboard отсутствует; ФИО и адреса не
входят в схемы.

Referral reward выдаётся один раз после первого verified purchase day invitee.
Это virtual progress с `monetary_value=0`. Self-referral и повторная атрибуция
отклоняются. Совпадение device/payment hash имеет demo score `0.75/0.80` и
уходит в `pending_review`; hard-block threshold равен `0.95`. Это прозрачные
PoC-константы, не обученные и не принятые как production thresholds.

## 9. Error and fallback behavior

| Ситуация | Поведение |
|---|---|
| markdown SKU отсутствует/unsafe | удалить option, попробовать full-price |
| нет full-price аналога | ingredient `unavailable`; recipe candidate исключить |
| все рецепты исключены | вернуть `recommendations=[]` и explainable warnings |
| model вернул неизвестный `recipe_id` | исключить candidate и записать warning |
| model недоступен | переключиться на deterministic mock только в demo mode |
| delivery недоступна | оставить `next_visit` |
| availability изменилась | стандартное уведомление; денежной компенсации нет |

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
- receipt update идемпотентен;
- cross-user replay отклоняется, future timestamp уходит в review;
- один день покупки начисляется один раз;
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
