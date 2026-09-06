# Дизайн recommender: признаки, ranking, reason codes

> Реализация: [`recsys/model.py`](../../../recsys/model.py),
> [`recsys/_logistic.py`](../../../recsys/_logistic.py),
> [`recsys/reason_codes.py`](../../../recsys/reason_codes.py). Контракт (вход
> и выход, safety, HTTP API) уже описан в
> [technical-design.md](../../technical-design.md) — этот документ не
> повторяет его, а объясняет, что происходит внутри
> `MLRecommendationEngine.rank()`.

## 1. Признаки

`recsys.model.compute_features(request, recipe)` считает восемь признаков из
полей, которые реально есть в `RecommendationRequest` (никогда — из
синтетического ярлыка архетипа, который существует только на этапе
генерации данных, не в реальном API):

| Признак | Смысл | Источник |
|---|---|---|
| `coverage` | доля ингредиентов рецепта, уже купленных сегодня | `current_receipt` |
| `history_affinity` | доля категорий рецепта, знакомых по истории | `purchase_history` + `user.history_categories` |
| `ingredient_affinity` | доля **конкретных** ингредиентов рецепта, уже покупавшихся | `purchase_history` (ingredient-level, не только категория) |
| `is_saved` | рецепт в сохранённых | `user.saved_recipe_ids` |
| `novelty` | 1 − взвешенная комбинация `ingredient_affinity`/`history_affinity` | производный |
| `time_fit` | мягкий штраф за рецепты дольше 30 минут | `recipe.preparation_minutes` |
| `missing_ratio` | доля недостающих ингредиентов | `current_receipt` |
| `missing_cost_norm` | оценка стоимости докупки (по средним ценам каталога) | `recsys.catalog.BASE_PRICE_RUB` |
| `markdown_supply_signal` | доля недостающих ингредиентов, у которых в радиусе есть markdown-товар | `inventory_snapshot` |

`ingredient_affinity` — намеренное усиление по сравнению с
`DeterministicMockEngine`, который учитывает совпадение только на уровне
категории (7 категорий). При всего 7 категориях shuffled- и own-история дают
почти одинаковый category-level сигнал просто потому, что у большинства
архетипов пересекаются core-категории — ingredient-level (32 ингредиента)
даёт заметно более специфичный, более чувствительный к конкретной истории
сигнал (см. [evaluation-and-metrics.md](evaluation-and-metrics.md) о том, как
это повлияло на own-vs-shuffled тест).

## 2. Ranking: recipe_score

Реализует формулу, уже согласованную в
[rescue-domovoi-concept.md §7](../persona_vxofi/rescue-domovoi-concept.md#7-recommender-system):

```text
recipe_score = relevance
             + current-basket coverage
             + repeat/discovery fit
             + time/budget fit
             − missing_count penalty
             − missing_cost penalty
             − constraint violations
```

Вместо того чтобы вручную подбирать веса каждого слагаемого,
`recsys/_logistic.py` реализует небольшую логистическую регрессию (без
numpy/sklearn — обычный batch gradient descent на списках Python), которая
**обучается** на implicit-метках, полученных из тех же архетипов, что
генерируют синтетическую популяцию (`recsys.profiles.ARCHETYPES`):

```text
для (профиль, рецепт):
  label = 1, если:
    missing_count ≤ tolerance архетипа (+1, если рецепт markdown-friendly
                                          и архетип markdown-affine)
    И recipe.preparation_minutes совместим с time_limit архетипа
    И (rецепт сохранён ИЛИ высокое current-coverage
        ИЛИ (низкий combined_affinity И discovery_acceptance архетипа) ИЛИ
        высокий combined_affinity)
  иначе label = 0
```

Это честный bootstrap, а не подгонка под реальную обратную связь
пользователей: модель учится обобщать явное, читаемое правило в непрерывном
пространстве признаков вместо того, чтобы вручную фиксировать веса. Обучение
происходит один раз при создании `MLRecommendationEngine()` (~1.2 сек на 300
синтетических профилей × 6 случайных рецептов), не на каждый запрос.

Фактически выученные веса (обучение с seed=999, 300 профилей):

| Признак | Вес |
|---|---:|
| `coverage` | +1.20 |
| `history_affinity` | +1.07 |
| `ingredient_affinity` | +0.80 |
| `time_fit` | +1.25 |
| `markdown_supply_signal` | +0.40 |
| `novelty` | −0.49 |
| `missing_ratio` | −0.91 |
| `missing_cost_norm` | −1.45 |
| `is_saved` | +0.002 |

Знаки соответствуют ожиданиям (coverage/affinity/time_fit положительные,
missing-штрафы отрицательные). `is_saved` вышел почти нулевым — честное
наблюдение, не скрытая проблема: сохранённые рецепты в генераторе всегда
выбираются из core-категорий архетипа, поэтому `is_saved` сильно
коррелирует с `history_affinity`/`ingredient_affinity`, и регрессия
перераспределила вес на них. Это не ломает продуктовое поведение — режим
`repeat` всё равно присваивается детерминированно (по факту нахождения в
`saved_recipe_ids`), а не через вес классификатора — но стоит иметь в виду
при дальнейшей настройке признаков.

## 3. Mode и reason codes

С 04.09 командой принят [ADR-003](../../decisions/003-challenge-mode-selection.md):
`current / repeat / explore` — стратегии челленджа, а не взаимоисключающие
свойства рецепта. Новый рецепт может одновременно подходить для `current`
(использует сегодняшний чек) и `explore` (ещё не знаком пользователю), а
сохранённый — для `current` и `repeat`.

Текущий `MLRecommendationEngine` всё ещё присваивает один mode старым
приоритетным правилом. В HTTP API `1.1` это поле считается legacy hint:
`RecommendationService` получает recipe relevance, после safety самостоятельно
строит допустимые mode-пулы, выбирает default и не более одного представителя
каждой стратегии. Это временная граница smoke-контура, а не целевой model
contract. Финальная модель должна выдавать независимый recipe relevance либо
score для каждой пары `(recipe, mode)`.

Model adapter может вычислять внутренние feature codes, но они не являются
готовыми утверждениями для UI. `RecommendationService` после safety заново
выводит только проверяемые публичные причины (фактическое пересечение с чеком,
число докупок, реально доступную уценку и т.п.). Их исполняемый реестр и
русский смысл находятся в `app/explanations.py`; неизвестный код никогда не
отображается пользователю как сырой идентификатор.

## 4. Пример вывода на 10 профилях

`recsys/generate_examples.py` прогоняет 10 профилей (по 2–3 на каждый из
четырёх архетипов) через **настоящий** `app.service.RecommendationService` +
`app.safety.SafetyPolicy` (импортированы как есть, не переопределены) с
`MLRecommendationEngine`. Результат — `recsys/examples/sample_recommendations.json`
(не хранит ничего, кроме синтетических данных). Один пример
(`synthetic_routine_0004`, архетип `routine`, радиус 2.5 км):

```json
{
  "mode": "current",
  "recipe_id": "cheese_omelette",
  "model_score": 0.9698,
  "missing_count": 1,
  "reason_codes": [
    "current_receipt_overlap",
    "safe_markdown_option_available"
  ],
  "ingredients": [
    {"name": "Яйца", "source": "receipt"},
    {"name": "Молоко", "source": "markdown"},
    {"name": "Сыр", "source": "receipt"}
  ]
}
```

а рядом для того же профиля — `explore`-рекомендация с missing_count=2:
разные профили и разные рецепты для
одного и того же профиля получают заметно разные mode/missing_count/reason
codes, что и требовалось ("5–10 профилей с разными рекомендациями") —
подробная методика оценки этого разнообразия в
[evaluation-and-metrics.md](evaluation-and-metrics.md).
