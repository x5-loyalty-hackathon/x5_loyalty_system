# X5 Game Loyalty PoC

Proof of concept персонального игрового слоя поверх программы лояльности X5 для
недельного хакатона ИТМО по кейсу X5 Tech.

Проект перешёл от discovery к реализации meal-first PoC. После покупки
recommender предлагает персональный приём пищи с вариантами `приготовить` и
`взять готовое`. Для рецепта можно выбрать markdown/full-price ингредиенты в
одной точке рядом с текущим местом, домом или работой и передать список в
доставку либо сохранить к следующему визиту. Сам рецепт сохраняется в книгу и
становится вариантом `repeat`. Подтверждённый чек и подтверждение готовки обновляют личную
кухню Домового. Продуктовые и контрактные решения зафиксированы в
[ADR-001](docs/decisions/001-recipe-first-poc.md),
[ADR-002](docs/decisions/002-personal-meal-contract.md),
[ADR-003](docs/decisions/003-challenge-mode-selection.md) и
[ADR-004](docs/decisions/004-recipe-book-and-shopping-context.md); актуальная схема API
описана в [design doc](docs/technical-design.md).

## Что должно войти в PoC

- кликабельный прототип из 3–4 связанных экранов;
- персональный челлендж на основе синтетической истории покупок;
- объяснимый выбор игровой механики;
- обновление прогресса аватара и места в рейтинге;
- расчёт реферальной награды;
- базовый антифрод чеков и приглашений;
- симуляция на 1–10 тысячах синтетических пользователей;
- одностраничный план реального пилота.

Подробные требования, ограничения и критерии собраны в
[контексте кейса](docs/case-context.md).

## Навигация

- [Текущее состояние](docs/project-status.md) — что уже известно и что делать
  дальше;
- [Чеклист до PoC и защиты](docs/poc-readiness.md) — оставшиеся задачи,
  критерии готовности и очередь свежих изменений mobile;
- [Интеграция frontend + ML: памятка для команды](docs/integration-handoff.md) —
  исходные коммиты, адаптации к API 1.2, карта кода и проверки перед слиянием;
- [Исследование существующего X5 Клуба](docs/research/x5-loyalty-current-state.md)
  — факты, выводы и вопросы для брейншторма;
- [Синтез конкурентного исследования](docs/research/benchmarks/competitive-synthesis.md)
  — что работает, где ломается причинность и как фильтровать идеи;
- [Матрица российских и международных кейсов](docs/research/benchmarks/competitive-case-matrix.md)
  — быстрый обзор ЦА, механик, результатов и качества evidence;
- [План и методика исследования](docs/research/benchmarks/research-plan.md) —
  вопросы, единый шаблон и уровни E1–E4;
- [Вопросы для kickoff](docs/kickoff-questions.md) — список для командного
  обсуждения;
- [Журнал решений](docs/decision-log.md) — источник принятых продуктовых и
  инженерных решений;
- [Контракт `cook / ready`](docs/decisions/002-personal-meal-contract.md) —
  единая meal-рекомендация, планы, события и LLM-персоны;
- [Выбор типа челленджа](docs/decisions/003-challenge-mode-selection.md) — один
  default `current/repeat/explore`, объяснимые альтернативы и full-basket opt-in;
- [Книга рецептов и точка сбора](docs/decisions/004-recipe-book-and-shopping-context.md)
  — `save → repeat`, home/work/current/custom и одна cook-точка;
- [Одностраничный план пилота](docs/pilot-plan.md) — test/control, покупочные
  дни, маржинальный guardrail и правила остановки;
- [Current idea brief](docs/research/persona_vxofi/x5-domovoi-team-brief.md) —
  компактное описание согласованной концепции;
- [Technical design](docs/technical-design.md) — API, границы модели и safety;
- [ML/Recsys & Evaluation](docs/research/recsys/ml-recsys-overview.md) —
  продуктовая гипотеза, схема recommender, ограничения и критерии проверки
  контура синтетических данных/модели/оценки/экономики;
- [План реализации](docs/implementation-plan.md) — владельцы и два дедлайна;
- [Обязательный MVP и test gates](docs/mvp-scope-and-test-plan.md) — что входит
  в Day 1, финал и automated checks;
- [Как внести изменение](CONTRIBUTING.md) — ветки, коммиты и pull request;
- [Настройка GitHub](docs/github-setup.md) — рекомендуемые параметры репозитория.

## Быстрый старт backend

Требуется Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
uvicorn app.main:app --reload
```

Те же тесты автоматически запускаются в GitHub Actions на push и pull request;
CI проверяет минимальную поддерживаемую Python 3.11 и Python 3.14.

Swagger UI: `http://127.0.0.1:8000/docs`.

Контракт можно проверить и без HTTP-сервера:

```bash
python -m app.demo
```

Пример вызова:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data @examples/recommendation_request.json \
  http://127.0.0.1:8000/api/v1/recommendations
```

Рабочий flow с альтернативой готового блюда:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data @examples/meal_recommendation_request.json \
  http://127.0.0.1:8000/api/v1/meal-recommendations

curl -sS \
  -H 'Content-Type: application/json' \
  --data @examples/saved_recipe_request.json \
  http://127.0.0.1:8000/api/v1/saved-recipes

curl -sS \
  -H 'Content-Type: application/json' \
  --data @examples/meal_plan_request.json \
  http://127.0.0.1:8000/api/v1/meal-plans

curl -sS \
  -H 'Content-Type: application/json' \
  --data @examples/ready_receipt_event.json \
  http://127.0.0.1:8000/api/v1/events/receipts
```

Receipt/progress и referral можно воспроизвести после запуска API:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data @examples/receipt_event.json \
  http://127.0.0.1:8000/api/v1/events/receipts

curl -sS \
  -H 'Content-Type: application/json' \
  --data @examples/referral_request.json \
  http://127.0.0.1:8000/api/v1/referrals/evaluate
```

Сервис по умолчанию использует детерминированный mock recommender и
process-local in-memory state; state сбрасывается при перезапуске процесса —
это ограничение PoC, а не production design. Синтетический ML/Recsys
smoke-адаптер подключается без изменения HTTP-контракта через
`RecommendationEngine.rank()` и переменную окружения. Он проверяет интеграцию
и не должен выдаваться за финальную модель или измеренный uplift:

```bash
RECOMMENDATION_ENGINE=model uvicorn app.main:app --reload
```

## Быстрый старт ML/Recsys

Требует тот же `.venv`, что и backend, плюс необязательные extras только для
офлайн-калибровки на реальных данных (`pip install -e '.[ml]'` — не нужно
для запуска модели/оценки/симуляции).

```bash
python -m pytest tests/test_recsys_*.py       # тесты контура
python -m recsys.generate_examples            # 10 профилей через реальный API
python -m recsys.evaluation                   # hit rate own vs shuffled-history
python -m recsys.simulation                   # funnel на 1k/10k пользователях
python -m recsys.economics                    # ΔCM_user по трём сценариям
```

Гипотеза, схема recommender, ограничения и критерии проверки —
[docs/research/recsys/ml-recsys-overview.md](docs/research/recsys/ml-recsys-overview.md).

## Git workflow для участника

После публикации репозитория на GitHub:

```bash
git clone https://github.com/x5-loyalty-hackathon/x5_loyalty_system.git
cd x5_loyalty_system
git switch -c feat/<short-task-name>
```

Внесите изменение, проверьте его локально и отправьте ветку:

```bash
git add <changed-files>
git commit -m "feat: краткое описание"
git push -u origin HEAD
```

Затем откройте pull request в `main` и назначьте одного участника на review.

## Принципы работы с результатами

- требования кейса, гипотезы, принятые решения и измеренные результаты не
  смешиваются;
- используем только синтетические данные без ПДн и внутренних данных X5;
- результат симуляции проверяет согласованность допущений, но не доказывает
  причинный uplift;
- секреты и локальные `.env`-файлы не коммитятся.
