# X5 Game Loyalty PoC

Proof of concept персонального игрового слоя поверх программы лояльности X5 для
недельного хакатона ИТМО по кейсу X5 Tech.

Проект перешёл от discovery к реализации recipe-first PoC. После покупки
recommender предлагает персональные рецепты, позволяет выбрать для недостающих
ингредиентов markdown/full-price товары в достижимом радиусе и передать список
в доставку либо сохранить к следующему визиту. Следующий чек обновляет личную
кухню Домового. Текущие решения зафиксированы в
[ADR-001](docs/decisions/001-recipe-first-poc.md), а технический контракт — в
[design doc](docs/technical-design.md).

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
- [Current idea brief](docs/research/persona_vxofi/x5-domovoi-team-brief.md) —
  компактное описание согласованной концепции;
- [Technical design](docs/technical-design.md) — API, границы модели и safety;
- [План реализации](docs/implementation-plan.md) — владельцы и два дедлайна;
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

Сервис пока использует детерминированный mock recommender. Модель подключается
через `RecommendationEngine.rank()` без изменения HTTP-контракта.

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
