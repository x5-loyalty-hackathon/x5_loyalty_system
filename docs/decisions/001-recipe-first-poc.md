# ADR-001: Recipe-first PoC и границы ответственности

- Дата: 2026-09-03
- Статус: accepted
- Владелец: команда
- Связанные issue/PR: будут добавлены после публикации веток реализации

## Контекст

Команде нужно до 04.09.2026 10:00 представить промежуточные материалы, а до
07.09.2026 10:00 — работающий PoC персонального игрового слоя X5. Ранее
рассматривался заранее собранный физический rescue-бокс с бронью. Командное
обсуждение сместило MVP к recipe-first сценарию без отдельного лота и брони.

## Рассмотренные варианты

1. Бронь отдельных short-life SKU (`exact-item reservation`).
2. Заранее собранный прозрачный rescue-набор.
3. Recipe-first цифровая корзина с выбором markdown/full-price ингредиентов.
4. Вариант 3 с миром Домового и личным прогрессом.

## Решение

Для PoC выбран вариант `3 + 4`:

- после чека recommender предлагает знакомые и новые рецепты;
- при сопоставимой релевантности меньше missing ingredients ранжируются выше;
- для недостающего ингредиента можно выбрать markdown SKU в достижимом радиусе;
- если markdown нет, используется full-price fallback;
- в PoC нет out-of-recipe cross-sell;
- список отправляется в стандартную доставку либо сохраняется к следующему
  визиту;
- отдельной брони rescue-позиции и денежной награды нет;
- базовые rescue-категории: фрукты, овощи, молочные продукты и мясо;
- первый сегмент: домохозяйства, регулярно покупающие продукты для готовки;
- gambling-like механика и public leaderboard не входят в PoC;
- показывается только личный прогресс и статистика;
- recipe feed доступен ежедневно, push имеет отдельный frequency cap.

Распределение ответственности:

| Контур | Owner |
|---|---|
| Синтетические данные, модели, recommender и evaluation | ML/Recsys & Evaluation |
| Product/UX, frontend и презентация | Product/UX & Frontend |
| Backend, интеграция, state, safety и базовый antifraud | Backend/Integration/Safety (`vxofi`) |

Product, metric и economic changes согласуются командой; owner отвечает за
реализацию своего контура, а не принимает межконтурные решения единолично.

## Причины и последствия

Плюсы:

- ежедневная recipe utility не зависит от наличия markdown;
- нет труда сборки отдельного набора, reservation/no-show flow и предоплаты;
- rescue становится explainable option внутри пользовательской цели;
- frontend может работать на mock до готовности модели;
- модель и safety отделены стабильным контрактом.

Последствия и риски:

- markdown availability без брони может устареть до покупки;
- full-price fallback может превратить rescue в обычный recipe commerce;
- доставка может лишь заменить следующий визит, а не создать новый purchase day;
- сортировка по missing count не должна побеждать relevance/safety;
- вклад Домового нужно отделять от utility recipe card.

## Как проверим

- hit rate и blind `own-history vs shuffled-history` ≥70% на 30–50 профилях;
- safety tests не пропускают expired/unsafe/restricted/out-of-radius SKU;
- API одинаково работает с mock и модельным adapter;
- `C0 current → C1 recipes → C2 markdown/full-price → C3 Domovoi`;
- primary: `Δpurchase days` / `ΔP(days ≥ N)` на 30/60 днях;
- guardrail: contribution/user не ниже control;
- delivery/store channel shift, split receipts и app-only retention считаются
  отдельно.
