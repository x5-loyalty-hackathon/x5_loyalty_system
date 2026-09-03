# Текущее состояние

Последнее обновление: 2026-09-03.

## Сейчас

- Private-репозиторий опубликован в организации `x5-loyalty-hackathon` и
  подготовлен для работы через issues, ветки и pull request.
- Исходная постановка и критерии отделены от будущих командных решений.
- Публичная система X5 Клуба исследована: ядро, персонализация, игровые
  механики, экономика, ограничения и пространство кейса записаны в
  `docs/research/x5-loyalty-current-state.md`.
- Проведено конкурентное исследование: российский grocery, «Золотое Яблоко» и
  другие российские отрасли, международные success/retired/fraud-damaged cases,
  а также экспериментальные работы по отдельным механизмам. Итоговые материалы:
  `docs/research/benchmarks/competitive-case-matrix.md` и
  `docs/research/benchmarks/competitive-synthesis.md`.
- Зафиксирована нулевая гипотеза discovery: ещё одна игра, коллекция или аватар
  сами по себе не гарантируют incremental uplift. Это рамка проверки, а не
  принятое продуктовое решение.
- Команда выбрала recipe-first PoC: рекомендации после чека, ingredient-level
  markdown/full-price выбор, доставка или следующий визит и личная кухня
  Домового без gambling/public leaderboard.
- Первый сегмент — домохозяйства, регулярно покупающие ингредиенты для готовки.
- Роли распределены на `ML/Recsys & Evaluation`, `Product/UX & Frontend` и
  `Backend/Integration/Safety`.
- Зафиксированы [ADR-001](decisions/001-recipe-first-poc.md),
  [technical design](technical-design.md) и
  [план до двух дедлайнов](implementation-plan.md).
- В рабочей ветке реализованы backend-инкременты B1–B3: versioned
  recommendation contract, deterministic mock, post-model safety, idempotent
  receipt/progress state, private rank, referral reward и rule-based
  precision-first antifraud. Это ещё не означает готовность общего PoC:
  frontend, model adapter, evaluation, simulation и pilot evidence принадлежат
  следующим integration gates.
- Backend regression gate: 23 теста проходят локально. Fraud weights и XP
  являются demo-константами и требуют командного/product review.

## Следующий командный шаг

До промежуточной сдачи 04.09.2026 10:00:

1. проверить backend contract и три example requests;
2. подключить frontend к mock JSON;
3. получить первые outputs ML/Recsys owner минимум на пяти профилях;
4. собрать четыре экрана и промежуточную презентацию;
5. подготовить обязательное Markdown-описание и компактные product artifacts;
6. проверить доступ к репозиторию без авторизации.

После сдачи mock заменяется model adapter, frontend соединяется с API и
добавляется единый end-to-end fixture. Затем обязательные evidence gates:
evaluation, simulation, экономика и pilot plan.
