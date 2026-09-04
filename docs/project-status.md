# Текущее состояние

Последнее обновление: 2026-09-04.

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
- Команда выбрала meal-first PoC: рекомендации после чека, ingredient-level
  markdown/full-price выбор, доставка или следующий визит и личная кухня
  Домового без gambling/public leaderboard. В той же карточке блюда доступна
  персональная под-опция `Приготовить / Без готовки`; отдельный экран и
  независимая рекламная выдача готовой еды не создаются.
- Первый сегмент — домохозяйства, регулярно покупающие ингредиенты для готовки.
  Ready-heavy пользователи рассматриваются как отдельный анализируемый сегмент,
  а не смешиваются с ним в одной средней метрике.
- Роли распределены на `ML/Recsys & Evaluation`, `Product/UX & Frontend` и
  `Backend/Integration/Safety`.
- Зафиксированы [ADR-001](decisions/001-recipe-first-poc.md),
  [ADR-002](decisions/002-personal-meal-contract.md),
  [technical design](technical-design.md) и
  [план до двух дедлайнов](implementation-plan.md).
- В рабочей ветке реализованы backend-инкременты B1–B3 и meal-контракт:
  versioned
  recommendation contract, deterministic mock, post-model safety, idempotent
  receipt/progress state, private rank, referral reward и rule-based
  precision-first antifraud, а также `cook / ready` рекомендации, сохранение
  meal plan и разное подтверждение завершения двух route. Это ещё не означает
  готовность общего PoC: frontend и pilot evidence принадлежат следующим
  integration gates.
- В API 1.2 замкнут пользовательский цикл `save → repeat`: отдельная
  process-local книга рецептов влияет на следующую рекомендацию без ручного
  эха состояния со стороны frontend. Cook-корзина теперь относится ровно к
  одной точке, выбранной пользователем или рекомендованной по покрытию,
  привычности и расстоянию. Контекст может быть `home`, `work`, текущим или
  произвольным сохранённым местом; demo-дефолт — 750 м без передачи адреса.
- Private rank разделён на `cooking_households` и `ready_heavy`; route одного
  заказа не используется как сегмент.
- Q13 перенесён из рабочего списка вопросов в отдельный
  [одностраничный draft пилота](pilot-plan.md) и включён в план реализации.
- Общий regression gate проходит локально на полном test suite без фиксации
  хрупкого числа тестов в документации. XP-схема подтверждена командой как
  demo-константа; fraud weights и порог ready-affinity всё ещё требуют
  product/model review.
- В общей истории репозитория реализован runnable ML/Recsys smoke-контур поверх
  неизменного backend-контракта: `recsys.model.MLRecommendationEngine`
  (синтетически обучаемый адаптер `RecommendationEngine`, переключаемый через
  `RECOMMENDATION_ENGINE=model`), генераторы профилей, evaluation runner,
  симуляция на 1–10k и экономика. Он нужен, чтобы не блокировать API и smoke,
  но не считается финальной моделью или финальным evidence: профили, labels,
  oracle и funnel rates пока заданы связанными синтетическими правилами.
- Текущие outputs (`100%` hit rate и для own, и для shuffled history; нулевой
  frequency uplift в base simulation) не интерпретируются как измеренный
  продуктовый результат. Они лишь подтверждают исполнимость пайплайна. Финальные
  методика, профили и результаты остаются deliverable владельца ML/Recsys &
  Evaluation.
- Ветка `feat/mobile-demo` синхронизирована 04.09: в ней пока есть только план
  мобильного демо, без frontend-кода. План приведён к актуальному
  `meal-recommendations → meal-plans → receipt/complete-cook → progress`
  контракту.

## Следующий командный шаг к MVP

### P0 — блокирует целостный demo

1. **Product/UX & Frontend:** добавить в ветку реальный frontend-код и провести
   один 4-screen happy path по актуальному meal API. Минимум: рекомендация →
   выбор route → сохранение плана → synthetic-чек → личный прогресс.
2. **ML/Recsys + Product/UX:** проверить принятый в ADR-003 и уже реализованный выбор
   типа челленджа: один default `current/repeat/explore`, отдельное объяснение и
   только релевантные альтернативы. `cook/ready` остаётся другим уровнем —
   способом закрыть потребность в еде, а не игровой механикой.
3. **ML/Recsys & Evaluation:** поверх smoke-scaffold предоставить финальные
   профили, модель/правила и eval, в котором качество считается на 30–50
   профилях и сравнивается с matched/generic baseline. Отдельно показать
   результаты по cooking-heavy, time-limited, hybrid и ready-heavy персонам,
   если ready-route входит в финальный pitch.
4. **ML/Recsys + Product:** заменить demo funnel rates на явно согласованный
   набор сценарных допущений и связать выводы с primary metric кейса. До этого
   simulation/economics можно показывать только как работающий калькулятор, а
   не как ожидаемый uplift.

### P1 — обязательные evidence и сдача

5. **Backend/Integration/Safety:** передать frontend API 1.2, examples и
   `save → repeat` / single-store fixtures; сохранить зелёным автоматический
   smoke обоих route. Следующий новый backend scope — только после UI integration.
6. **Product + review команды:** проверить и зафиналить
   [одностраничный pilot plan](pilot-plan.md): test/control, primary metric,
   margin guardrail, раздельный анализ cooking/ready, длительность и stop rules.
7. **Команда:** записать 30–60-секундное резервное видео полного сценария и
   сверить финальные утверждения в слайдах с фактическими eval/simulation
   outputs.
