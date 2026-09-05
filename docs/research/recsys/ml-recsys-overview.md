# ML/Recsys & Evaluation: гипотеза, схема, ограничения, критерии проверки

Обновление 05.09: актуальный перенос каталога/scorer и его границы описаны в
[памятке интеграции](../../integration-handoff.md). Числа в этом более раннем
документе не являются результатами повторного eval новой общей сборки.

> **Статус:** рабочие материалы контура ML/Recsys & Evaluation, 2026-09-03.
> Продуктовое ядро (recipe-first PoC) уже зафиксировано в
> [ADR-001](../../decisions/001-recipe-first-poc.md) и
> [technical design](../../technical-design.md) — этот документ не
> пересматривает их, а формализует продуктовую гипотезу этого контура,
> описывает, как модель встраивается в уже согласованный контракт, и честно
> перечисляет ограничения и критерии проверки. Реализация:
> [`recsys/`](../../../recsys/).

## Как читать этот раздел

Как и остальной репозиторий, различаем **требование** кейса, **гипотезу**,
**решение** команды и воспроизводимо измеренный **результат** (см.
[case-context.md](../../../docs/case-context.md)). Числа ниже — результаты,
полученные на синтетических данных этого PoC; они проверяют внутреннюю
согласованность модели и экономики, а не доказывают причинный эффект на
реальных пользователях X5.

## 1. Формальная продуктовая гипотеза

Отвечаем на вопросы из [kickoff-questions.md](../../kickoff-questions.md)
("Продуктовая гипотеза") явно, одним связным утверждением:

| Элемент | Формулировка |
|---|---|
| **Сегмент** | Домохозяйства, регулярно покупающие ингредиенты для готовки (не только готовую еду и единичные товары) — первый сегмент PoC, зафиксирован в [ADR-001](../../decisions/001-recipe-first-poc.md). |
| **Целевое поведение** | Рост доли уникальных дней с покупкой (`Δ distinct purchase days/user`, `ΔP(days ≥ N)` на 30/60 днях) между уже происходящими визитами, без снижения `contribution margin/eligible user`. |
| **Механизм (почему)** | (1) recipe-рекомендация сразу даёт utility от уже случившегося чека — ценность не требует новой покупки, что снижает порог возврата в приложение; (2) явный missing-ingredient список с markdown-опцией снижает трение докупки нескольких недостающих товаров; (3) Домовой даёт ненейтральную (non-monetary) причину возвращаться без discount-seeking поведения — без gambling/streak/public rank. |
| **Контрольный сценарий** | `C0` — текущий опыт без персональных рецептов после чека (см. лестницу компонентов `C0→C3` в [rescue-domovoi-concept.md §17](../persona_vxofi/rescue-domovoi-concept.md)). |
| **Primary метрика** | `Δ distinct purchase days/user`, `ΔP(days ≥ N)` — заданы кейсом, не нами. |
| **Guardrail-метрики** | `Δ contribution margin/eligible user` не ниже control; unavailable/fallback rate; complaints; opt-out — см. [метрики §13](../persona_vxofi/rescue-domovoi-concept.md#13-метрики). |
| **Условия фальсификации (kill criteria)** | Полный список — [rescue-domovoi-concept.md §19](../persona_vxofi/rescue-domovoi-concept.md#19-kill--simplify-criteria); ключевое для этого контура: own-history relevance < 70% на 30–50 профилях, или recipe-list растит только корзину/только game-retention, но не частоту. |

Гипотеза остаётся в рамке **нулевой гипотезы discovery**, уже зафиксированной
в [project-status.md](../../project-status.md): ещё один рекомендательный
слой сам по себе не гарантирует uplift, если рекомендации нерелевантны или
markdown insufficient. Этот документ и его результаты не опровергают и не
подтверждают её окончательно — только продвигают проверку на один шаг
(synthetic evaluation + simulation вместо чисто теоретического аргумента).

## 2. Схема recommender

Реализует уже согласованный backend-контракт
([technical-design.md §4-5](../../technical-design.md)) — этот раздел
описывает, что происходит **внутри** `RecommendationEngine.rank()`
(`recsys/model.py`) и как это встраивается в неизменный контур
`app.service`/`app.safety`:

```text
чек (current_receipt) + история + предпочтения
  │
  ▼
кандидаты рецептов
  • совпадение с текущим чеком (current)
  • сохранённые/повторяемые рецепты (repeat)
  • редакционно проверенный каталог (explore)
  │
  ▼
recsys.model.MLRecommendationEngine.rank()
  • признаки: coverage, history/ingredient affinity, novelty, time_fit,
    missing_ratio, missing_cost, markdown_supply_signal, is_saved
  • score = логистическая регрессия по признакам (0..1)
  • mode: current | repeat | explore
  • reason_codes: recsys/reason_codes.py
  │
  ▼ ModelRecommendation (recipe_id, mode, score, reason_codes)
  │
  ▼
app.safety.SafetyPolicy — НЕИЗМЕНЁН, применяется после модели
  • excluded/radius/expired/unsafe/rescue-category правила
  • модель не может обойти safety своим score
  │
  ▼
app.service.RecommendationService
  • ingredient → receipt | home | markdown | full_price | unavailable
  • сортировка: missing_count ASC, затем model_score DESC
  • fallback markdown → full_price → unavailable
  │
  ▼
до 3 RecipeRecommendation + warnings
  │
  ▼
доставка ИЛИ следующий визит → новый чек → прогресс Домового
```

`recsys/model.py` — единственная замена: тот же вход/выход, что и у
`app.recommender.DeterministicMockEngine`, поэтому переключение делается
одной переменной окружения (`RECOMMENDATION_ENGINE=model`, см.
`app/main.py`), без изменения HTTP-контракта, safety или state.

## 3. Ограничения

- **Только синтетические данные.** Ни архетипы, ни каталог рецептов, ни
  экономические параметры не основаны на реальных данных X5 или ПДн — см.
  [synthetic-data-and-segments.md](synthetic-data-and-segments.md).
- **Каталог рецептов небольшой (24, hand-curated).** Не LLM-генерация, не
  bulk-импорт — редакционно обозримый набор, как того требует
  [technical design](../../technical-design.md#3-non-goals-первого-инкремента).
  При таком соотношении каталога (24 рецепта) и размера чека (5–9 позиций)
  режим `current` (совпадение с сегодняшним чеком) выигрывает у бо́льшей
  части кандидатов почти всегда — это унаследовано от уже принятого правила
  mode-присвоения в `DeterministicMockEngine` (любое пересечение с чеком →
  `current`), не переопределено нами в одностороннем порядке, и вынесено как
  открытый вопрос ниже и в
  [evaluation-and-metrics.md](evaluation-and-metrics.md).
- **Экономические и funnel-параметры — иллюстративные demo-константы**
  (open rate, save rate, markdown baseline sale probability, contribution
  margin rate и т.д.), не измеренные показатели X5. Симуляция проверяет
  внутреннюю согласованность допущений, а не причинный uplift — см.
  [economics-and-simulation.md](economics-and-simulation.md).
- **Оценка релевантности частично самореферентна.** Оракул в
  `recsys/evaluation.py` использует ту же структуру правил, что и генератор
  implicit-меток для обучения (`recsys/model.py`) — оба выведены из одних и
  тех же архетипов (`recsys/profiles.py`). Абсолютный `hit_rate_own`
  показывает в первую очередь, что модель выучила заданное правило; более
  показателен разрыв own-vs-shuffled — подробности и честная интерпретация
  в [evaluation-and-metrics.md](evaluation-and-metrics.md).
- **Модель намеренно простая и прозрачная** (логистическая регрессия на ~9
  признаках, без numpy/sklearn в runtime) — соответствует требованию
  safety/explainability из технического дизайна, не production-масштаб ML.
- **Не входит:** LLM-генерация рецептов, реальный каталог/цены X5, реальные
  платежи/бронь, gambling-механика, публичный рейтинг, production база
  данных и аутентификация — как и во всём остальном PoC
  ([mvp-scope-and-test-plan.md §6](../../mvp-scope-and-test-plan.md)).

## 4. Критерии проверки

| Критерий | Источник требования | Статус в этой поставке |
|---|---|---|
| Стабильный output-контракт, ≥5 профилей | [mvp-scope-and-test-plan.md](../../mvp-scope-and-test-plan.md) | ✅ 10 профилей через реальный `RecommendationService`, см. [recommender-design.md](recommender-design.md) |
| Hit rate own-history ≥70% на 30–50 профилях | [ADR-001](../../decisions/001-recipe-first-poc.md) | ✅ формально пройден (100% на N=10/50/300) — с оговоркой о частичной самореферентности оракула, см. [evaluation-and-metrics.md](evaluation-and-metrics.md) |
| Own-history genuinely лучше shuffled-history | [technical-design.md §10](../../technical-design.md) | ⚠️ частично: на срезе repeat/explore (где history вообще может повлиять) разрыв небольшой и шумный на малом N (+4 п.п. при N=300) — открытый вопрос для дальнейшей работы |
| Coverage/diversity | [technical-design.md §10](../../technical-design.md) | ✅ 100% профилей получают ≥1 рекомендацию; 24/24 уникальных рецептов встречаются на N=300 |
| Simulation 1–10k, детерминированный seed | [mvp-scope-and-test-plan.md](../../mvp-scope-and-test-plan.md) | ✅ `recsys/simulation.py`, воспроизводимо на 10 000 пользователей за секунды |
| Base-case без uplift (`Δpurchase_days = 0`) | [rescue-domovoi-concept.md §18](../persona_vxofi/rescue-domovoi-concept.md) | ✅ инвариант закреплён тестом (`tests/test_recsys_simulation.py`) |
| Экономика без двойного счёта | [rescue-domovoi-concept.md §12](../persona_vxofi/rescue-domovoi-concept.md) | ✅ инвариант закреплён тестом (`tests/test_recsys_economics.py`) |
| Safety нельзя обойти score модели | [technical-design.md §5](../../technical-design.md) | ✅ по построению — `recsys/model.py` не импортирует и не изменяет `app.safety`/`app.service`; исходные 23 backend-теста не изменены и остаются зелёными |
| Контракт/схемы валидны | — | ✅ 65 автоматических тестов (23 исходных + 42 новых), `python -m pytest` |
| Реальная релевантность для живых пользователей | вне PoC | ❌ не проверялось и не может быть проверено синтетическими данными — требует пилота |
| Архетипы, откалиброванные на реальных данных X5/Kaggle | вне этой поставки | ⚠️ путь построен (`recsys/calibration/fit_from_kaggle.py`), но не запускался на реальном датасете в этой поставке |

## Материалы контура

- [Синтетические данные и сегменты](synthetic-data-and-segments.md) — откуда
  архетипы, как это соотносится с Kaggle, как масштабируется на всех
  клиентов X5.
- [Дизайн recommender](recommender-design.md) — признаки, ranking,
  reason codes, пример вывода на 10 профилях.
- [Оценка и метрики](evaluation-and-metrics.md) — методика и фактические
  числа hit rate/coverage/diversity.
- [Экономика и симуляция](economics-and-simulation.md) — формулы, сценарии,
  фактические числа на 1k/10k пользователях.
