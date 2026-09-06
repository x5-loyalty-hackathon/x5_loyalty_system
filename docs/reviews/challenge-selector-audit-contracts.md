# Контракты аудита challenge selector

- Дата: 2026-09-04
- Статус: выполнено; независимый commit/push gate пройден
- Объект проверки: API `1.1`, ADR-003 и связанные изменения meal-first PoC

## 1. Зафиксированное решение — не предмет повторного голосования

Аудиторы принимают как заданное:

- `current/repeat/explore` — стратегии челленджа, а не взаимоисключающие
  свойства рецепта;
- начальная выдача содержит один default и не более одного уникального блюда на
  каждый доступный mode;
- слабая альтернатива не добавляется только ради заполнения трёх карточек;
- явный `requested_mode` открывает каталог внутри выбранного режима и допускает
  несколько рекомендаций одного mode;
- `explore` может использовать `receipt/home`; full-basket `explore` не может
  стать default без явного выбора;
- mode selection, recipe selection и `cook/ready` route имеют разные причины;
- safety после модели нельзя обойти score или выбором режима.

Источник решения: [ADR-003](../decisions/003-challenge-mode-selection.md).

Аудит может показать, что правило невозможно однозначно реализовать или что его
следствия нежелательны. В таком случае finding маркируется `decision gap`, а не
выдаётся за обычную ошибку кода.

## 2. Единый формат finding

Каждый finding должен содержать:

```text
ID и severity: blocker | high | medium | low
Тип: correctness | invariant | contract drift | missing case | explainability
Где: файл:строка или конкретное поле контракта
Контрпример: минимальный вход/последовательность событий
Фактическое поведение
Почему это проблема для MVP или защиты
Предлагаемый инвариант или минимальное исправление
Какой автотест должен падать до исправления и проходить после
```

Не включать общие пожелания, stylistic nit и production-функции вне PoC.
Отсутствие проблемы тоже является допустимым результатом, но должно сопровождаться
перечнем проверенных сценариев.

## 3. Audit A — reason codes и объяснимость

### Цель

Проверить, что коды действительно объясняют три разных решения, не дублируют и
не противоречат друг другу, а frontend может безопасно превратить их в короткий
текст.

### Обязательный охват

1. Собрать все реально эмитируемые коды из:
   - `app/service.py` — challenge и route;
   - `app/recommender.py`, `recsys/model.py` — recipe;
   - fraud/referral/progress — проверить случайные пересечения имён;
   - документации и UI-плана.
2. Для каждого кода определить уровень:
   - `challenge_selection.mode_reason_codes`;
   - `recommendation.reason_codes`;
   - `meal_recommendation.route_reason_codes`;
   - warning, safety или antifraud — не смешивать с explanation.
3. Найти:
   - одинаковый смысл под разными именами;
   - разные смыслы под одним именем;
   - причины, которые лишь повторяют mode/поле ответа;
   - причины, которые заявляют больше, чем следует из входных данных;
   - противоречивые наборы кодов в одном ответе;
   - коды без зарегистрированного текста и тексты без эмитируемого кода;
   - нестабильный порядок, дубли и пустые списки;
   - утечки чувствительных выводов о семье, здоровье или доходе.
4. Проверить минимум сценарии:
   - новый рецепт, использующий текущий чек (`current + explore` eligibility);
   - сохранённый рецепт из текущего чека (`current + repeat`);
   - full-basket explore;
   - явный mode;
   - отсутствие выбранного default;
   - ready preference и ready fallback в cook.

### Выход

- таблица `emitted code → level → condition → documented UI meaning`;
- findings по единому формату;
- минимальный предлагаемый словарь кодов без преждевременного переписывания
  всей модели.

## 4. Audit B — selector, инварианты и граничные случаи

### Цель

Попытаться нарушить ADR-003 входами, которые не покрыты happy path.

### Обязательный охват

- `limit = 1/2/3/10`;
- пустой результат после safety;
- только full-basket explore;
- partial explore, который после recipe dedup заменяется полной корзиной;
- один recipe, допустимый сразу для двух режимов;
- несколько сохранённых/current/novel recipes;
- повторяющиеся и неизвестные candidate IDs от model adapter;
- `requested_mode`, для которого нет безопасных кандидатов;
- одинаковые missing count и score;
- optional unavailable ingredients;
- рецепт только из `home`, только из `receipt`, только из покупаемых SKU;
- excluded/expired/out-of-radius SKU после mode selection;
- согласованность recipe- и meal-level ответа.

### Проверяемые инварианты

- default либо `null`, либо реально присутствует в выдаче;
- default не требует opt-in;
- ключи mode reason codes совпадают с доступными режимами;
- initial response не дублирует mode или recipe;
- requested response содержит только requested mode;
- full-basket вычисляется по фактически возвращённому кандидату;
- safety применяется до финального объявления mode доступным;
- результат детерминирован для одинакового входа;
- selector не использует чувствительные или отсутствующие признаки.

### Выход

Findings и список недостающих unit/property/API tests. Код не изменять.

## 5. Audit C — совместимость API и целостность end-to-end flow

### Цель

Проверить, что API `1.1` реально можно использовать в четырёхэкранном демо и
что изменение selector не сломало соседние контуры.

### Обязательный охват

- Pydantic schema и OpenAPI для обоих recommendation endpoints;
- bump `contract_version` и его последствия для receipt/referral/progress;
- propagation `challenge_selection` в meal response;
- старый `ModelRecommendation.mode` как legacy hint;
- mock и `RECOMMENDATION_ENGINE=model`;
- опубликованные example requests и generated samples;
- frontend plan: initial mode, opt-in, повторный requested-mode запрос;
- cook/ready selection, meal-plan save, receipt completion и progress;
- отсутствие frontend-кода в текущем `feat/mobile-demo` учитывать как известный
  внешний блокер, а не дефект backend;
- backward compatibility: явно определить, что сломано намеренно, а что
  случайно.

### Выход

Findings по единому формату, минимальный integration checklist и команды
воспроизведения. Код не изменять.

## 6. Финальный независимый code review после исправлений

Финальный reviewer получает только:

- diff относительно `origin/feat/mobile-demo`;
- ADR-002/ADR-003 и technical design;
- команду полного test suite.

Он не участвует в исправлениях и не редактирует файлы. Приоритет проверки:

1. correctness и расхождение кода с ADR;
2. потеря данных, двойное начисление прогресса и обход safety;
3. Pydantic/API invariants;
4. детерминизм и изоляция состояния тестов;
5. пропущенные негативные тесты;
6. только затем maintainability.

Review считается пройденным, если нет blocker/high findings, все принятые
medium findings исправлены либо явно записаны как ограничение, полный suite и
`git diff --check` проходят.

## 7. Результат первого цикла аудита

Три независимых read-only аудита нашли и передали в исправление:

- reason codes: смешение mode/recipe причин, недоказанные утверждения об
  affinity/уценке/бюджете, пустой публичный список и сырые debug warnings;
- selector: неверный порядок tie-break, разбор готового блюда на сырые
  ингредиенты, optional-гарнир в определении full basket и дубли ID во входе;
- API/E2E: завершение meal plan чеком из прошлого, неявный model fallback,
  неупорядоченные mode-поля и устаревший generated sample.

Принятые findings закрыты инвариантами схемы и негативными тестами. Порог
recipe relevance намеренно не придуман backend-контуром: до ML-eval candidate
от model adapter считается прошедшим upstream eligibility gate. Окончательное
заключение выносит новый reviewer, который не участвовал ни в аудите, ни в
исправлениях.

## 8. Независимый review gate

Финальный reviewer не участвовал в реализации и трижды проверял изменяющийся
diff. Первые проходы остановили commit из-за:

- потери безопасного `ready`, если нельзя собрать `cook`;
- двойного purchase-day progress при разных UTC offset и допуска naive time;
- обхода verified recipe gate через ready-only route;
- ложного `current` у ready-only предложения.

После исправлений и regression tests итоговый вердикт: `0 blocker`, `0 high`,
`0 medium`, полный suite — `102 passed`, targeted regressions и
`git diff --check` прошли. Изменение допущено к commit/push.
