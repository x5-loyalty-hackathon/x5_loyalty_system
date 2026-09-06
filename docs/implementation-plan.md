# План реализации и сдачи

**Исторический план этапов от 03.09, не текущий статус работ.** Оперативная
очередь и незакрытые цели на 06.09 — [PoC readiness](poc-readiness.md),
исправления/merge — [план ревью](reviews/2026-09-06-fixes-and-merge.md).
Действующий API — 1.3; правила XP заменены [ADR-005](decisions/005-game-tasks-and-xp.md).

- **Текущее время планирования:** 03.09.2026 после 17:34, Europe/Moscow.
- **Промежуточный дедлайн:** 04.09.2026 10:00.
- **Финальный дедлайн:** 07.09.2026 10:00.
- **Решение:** [ADR-001](decisions/001-recipe-first-poc.md).
- **Scope и test gates:**
  [обязательный MVP](mvp-scope-and-test-plan.md).

## Контекст плана после Day 1

План включает не только код. Q13 — одностраничный план реального пилота —
является обязательным артефактом финальной сдачи и частью критического пути:
без него рабочий PoC не отвечает на вопрос, как отличить рост покупочных дней
от простого retention в игре. Актуальный draft: [pilot-plan.md](pilot-plan.md).

Текущий backend-приоритет после промежуточной сдачи:

1. закрыть `save → repeat` через process-local книгу рецептов;
2. собирать cook-корзину в одной точке относительно явно выбранного контекста
   `home/work/current/custom`, с пешим demo-радиусом 750 м;
3. не смешивать готовящие и ready-heavy когорты в личной позиции;
4. передать API 1.2 и примеры frontend-владельцу;
5. после появления UI прогнать живой four-screen smoke;
6. параллельно довести draft пилота, eval и simulation до честных финальных
   материалов.

Пункты 1–3 реализует Backend/Integration/Safety. Они не меняют ML-порог
релевантности, параметры экономики или дизайн экранов.

## Роли

| Роль | Владелец | Основной результат |
|---|---|---|
| ML/Recsys & Evaluation | участник 1 | синтетика, модели, reason codes, evaluation и simulation |
| Product/UX & Frontend | участник 2 | четыре экрана, frontend, продуктовые материалы и презентация |
| Backend/Integration/Safety | `vxofi` | API, state, интеграция, safety, antifraud и запуск |

Имена участников добавляются перед загрузкой презентации. Product, metric и
economic changes подтверждаются втроём.

## До промежуточной сдачи — 04.09 10:00

### P0: обязательный пакет

| Артефакт | Owner | Готово, когда |
|---|---|---|
| Intermediate slides | Product/UX | 9–10 слайдов, роли и честный статус |
| Intermediate project description | Product/UX + review команды | все обязательные разделы, ссылки на repo/demo |
| Product materials | Product/UX + Backend | brief, user flow, metrics/risks |
| Repository | Backend | clean start, README, tests, доступ проверен |
| Recsys evidence | ML/Recsys | ≥5 разных профилей, outputs и preliminary eval |
| Prototype | Product/UX | кликабельные четыре экрана на mock API |

### Backend/Integration/Safety — текущий инкремент

1. Зафиксировать ADR и technical design.
2. Создать FastAPI skeleton и versioned schemas.
3. Реализовать `RecommendationEngine` protocol и deterministic mock.
4. Реализовать post-model safety/availability policy.
5. Добавить example request и API tests.
6. Обновить README и передать contract обоим участникам.

Фактический статус в рабочей ветке: шаги 1–6, B2/B3
receipt/progress/referral, meal routes, challenge selector и пункты 1–3 выше
реализованы; число тестов намеренно не фиксируется в плане. До review это не
считается общей командной версией.

### Integration checkpoint

Frontend не ждёт модель: использует example JSON. ML owner не поднимает свой
HTTP-сервис: реализует adapter/function по Python contract либо отдаёт
совместимый JSON для первого промежуточного demo.

Перед сдачей:

- не заявлять mock как обученную модель;
- не заявлять synthetic simulation как causal uplift;
- проверить GitHub-ссылку без авторизации;
- экспортировать презентацию в требуемый формат;
- загрузить до 09:15, оставив 45 минут буфера.

## 04.09 после промежуточной сдачи

1. Собрать feedback и до 13:00 подтвердить scope freeze.
2. Заменить mock на model adapter.
3. Провести review receipt/progress/referral contract и согласовать только
   продуктовые константы, не переписывая стабильный flow без причины.
4. Соединить frontend с API.
5. Зафиксировать один воспроизводимый end-to-end demo.
6. Добавить contract/e2e test для интеграции модели и frontend fixture.

## 05.09 — functional completeness

- все четыре экрана используют API;
- работают `current / repeat / explore`;
- доступны delivery/next-visit paths;
- markdown/full-price/unavailable states покрыты тестами;
- receipt обновляет Домового и personal stats;
- referral и fraud examples воспроизводимы;
- simulation принимает 1–10k profiles.

Вечером 05.09 — end-to-end demo freeze. Новая функция после этого добавляется
только если закрывает обязательное требование.

## 06.09 — evidence and packaging

- evaluation на 30–50 профилях;
- simulation scenarios и economics sensitivity;
- screenshots/video fallback демонстрации;
- review и финализация [одностраничного pilot plan](pilot-plan.md);
- итоговое описание проекта;
- около трёх компактных product artifacts;
- финальные слайды с реальным вкладом участников;
- проверка запуска на чистом окружении.

Вечером 06.09 — feature/content freeze.

## 07.09 до 10:00

- только smoke test, экспорт и загрузка;
- проверить открытый доступ к repository/demo;
- проверить, что ссылки ведут на финальные версии;
- целевой upload cutoff команды — 09:00.

## Критический путь

```text
schema + example
→ frontend mock и model adapter параллельно
→ safety-validated API
→ receipt/progress state
→ integrated demo
→ eval + simulation
→ pilot contract + final artifacts
```

## Не делать до промежуточной сдачи

- production deployment и auth;
- настоящую интеграцию X5 delivery/catalog;
- сложный UI админки;
- LLM generation рецептов;
- gambling-like механику;
- публичный рейтинг;
- большой каталог и production-scale antifraud.
