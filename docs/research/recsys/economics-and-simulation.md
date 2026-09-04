# Экономика и симуляция

> Реализация: [`recsys/simulation.py`](../../../recsys/simulation.py),
> [`recsys/economics.py`](../../../recsys/economics.py). Формулы — из
> [rescue-domovoi-concept.md §12-13,18](../persona_vxofi/rescue-domovoi-concept.md),
> **не** из более раннего
> [rescue-basket-economics.md](../monetization/rescue-basket-economics.md),
> который сам себя помечает как устаревший анализ альтернативы с бронью,
> сохранённый только для справки.

Метки: **FACT** / **INFERENCE** / **HYPOTHESIS** — как в остальных
research-документах репозитория. Все ставки/цены ниже — **HYPOTHESIS**,
иллюстративные demo-константы, а не измеренные показатели X5 (см. открытые
вопросы в [rescue-domovoi-concept.md §20](../persona_vxofi/rescue-domovoi-concept.md#20-оставшиеся-вопросы-команды)).

## 1. Почему это отдельная, более грубая симуляция

[recommender-design.md](recommender-design.md) и
[evaluation-and-metrics.md](evaluation-and-metrics.md) прогоняют
**настоящий** `RecommendationService` на десятках-сотнях полных синтетических
профилей — это правильная гранулярность для "профили с рекомендациями" и
"hit rate", но не для симуляции на 1–10 тысячах пользователей: материализовать
полные `InventoryProduct`/`Recipe` графы на 10 000 профилей не даёт
дополнительного аналитического сигнала и не нужно для того, что реально
описано в кейсе — funnel и экономика на уровне популяции
([rescue-domovoi-concept.md §13/§18](../persona_vxofi/rescue-domovoi-concept.md)).
Поэтому `recsys/simulation.py` — Monte Carlo по ставкам на уровне архетипа
(impression → open → save → purchase), а не по отдельным SKU. 10 000
пользователей на 60-дневном горизонте считаются за секунды, воспроизводимо
(фиксированный seed).

## 2. Funnel и base-case

```text
impression → open → save → conversion
                              ├── route A: новый purchase day (доп. визит)
                              └── route B: встроено в уже плановый день
                            conversion → markdown ИЛИ full-price
```

**Base-case намеренно не предполагает uplift**
([rescue-domovoi-concept.md §18](../persona_vxofi/rescue-domovoi-concept.md#18-симуляция-на-1-10-тысячах-пользователей)):
`route_a_probability = 0` в сценариях `base` и `pessimistic` — рекомендатель
никогда не создаёт "искусственный" дополнительный день покупки, если явно не
включить это в сценарии. Закреплено тестом
(`tests/test_recsys_simulation.py::test_base_and_pessimistic_scenarios_have_zero_induced_purchase_days`).

### Три сценария (иллюстративные, не измеренные)

| Сценарий | relevance × | markdown availability × | P(route A) | fallback→full-price | cannibalization |
|---|---:|---:|---:|---:|---:|
| pessimistic | 0.70 | 0.60 | 0% | 55% | 50% |
| base | 1.00 | 1.00 | 0% | 35% | 30% |
| optimistic | 1.25 | 1.30 | 6% | 20% | 15% |

## 3. Результаты (N=10 000, горизонт 60 дней)

| Метрика | pessimistic | base | optimistic |
|---|---:|---:|---:|
| impressions | 187 922 | 188 164 | 188 897 |
| opens | 67 452 | 96 162 | 120 576 |
| saves | 18 842 | 38 621 | 60 296 |
| conversions | 6 301 | 21 281 | 43 061 |
| mean purchase days /60d | 18.79 | 18.82 | 19.15 |
| **mean extra purchase days (Δ)** | **0.000** | **0.000** | **0.256** |
| P(days ≥ 19) | 50.3% | 50.8% | 52.9% |
| P(days ≥ 22) | 29.0% | 29.7% | 31.9% |
| markdown share of conversions | 11% | 28% | 45% |

`mean_extra_purchase_days` — прямой аналог case primary-метрики
`Δ distinct purchase days/user`; growing 0.000 → 0.256 монотонно от
pessimistic к optimistic — согласованное поведение, но абсолютная величина
в optimistic-сценарии скромная (~1.3% от базового уровня ~19 дней), что
соответствует духу нулевой гипотезы discovery: сама по себе механика не
гарантирует большой uplift. `P(days ≥ N)` посчитан у порогов, близких к
среднему (19, 22 из ~60 возможных дней) — на порогах вроде "≥10" метрика
насыщается (>97% во всех сценариях) и перестаёт что-либо различать; выбор
конкретного `N` для реального пилота — решение команды/бизнеса, не
техническое (см. [case-context.md](../../../docs/case-context.md)).

## 4. Экономика: `ΔCM_user` и `Δrescue_item`

Формулы (пересказ [rescue-domovoi-concept.md §12](../persona_vxofi/rescue-domovoi-concept.md#12-деньги)
как код в `recsys/economics.py`):

```text
gross_contribution = route_A_conversions × avg_new_basket_value × CM_rate
                    + route_B_conversions × avg_attach_value × CM_rate

net_CM = gross_contribution
       − cannibalization_rate × gross_contribution
       − variable_cost_per_conversion × conversions

rescue_delta (диагностика, НЕ прибавляется к net_CM повторно)
  = markdown_realized_value − markdown_baseline_sale_probability × markdown_realized_value
```

`rescue_delta` отвечает на отдельный вопрос из таблицы метрик ("несёт ли
markdown-механика собственную добавленную стоимость сверх уже существующей
уценки") — он не суммируется в `net_CM` второй раз, потому что реализованная
markdown-выручка уже учтена внутри `gross_contribution` через фактически
уплаченную цену. Проверено тестом
(`tests/test_recsys_economics.py::test_rescue_delta_is_not_added_into_net_cm`).

Параметры (`recsys.economics.EconomicsParams`, все — **HYPOTHESIS**):

| Параметр | Значение | Смысл |
|---|---:|---|
| `contribution_margin_rate` | 22% | иллюстративная CM-ставка на реализованную выручку |
| `avg_new_basket_value_rub` | 850 ₽ | route A: целая дополнительная покупка |
| `avg_attach_value_rub` | 180 ₽ | route B: докупка недостающих ингредиентов |
| `markdown_baseline_sale_probability` | 55% | вероятность, что markdown-товар продался бы и без рекомендателя |
| `variable_cost_per_conversion_rub` | 8 ₽ | serving/data/support/fraud-costs на конверсию |

### Результаты (N=10 000, 60 дней)

| Сценарий | net_CM/eligible user | rescue_delta (диагностика) |
|---|---:|---:|
| pessimistic | 7.4 ₽ | 12 367 ₽ (17.8 ₽/markdown-конверсию) |
| base | 42.0 ₽ | 104 354 ₽ (17.8 ₽/markdown-конверсию) |
| optimistic | 142.6 ₽ | 344 247 ₽ (17.8 ₽/markdown-конверсию) |

Числа монотонны по сценариям и стабильны на N=1000 vs N=10000 (в пределах
Monte Carlo шума, `net_CM/user` совпадает с точностью до ~1.5%) — это
тест внутренней согласованности, закреплённый
(`tests/test_recsys_economics.py::test_economics_scale_roughly_linearly_with_population`).
Скромная положительная величина (7–143 ₽/пользователя за 60 дней в
зависимости от сценария) — намеренно неагрессивная оценка: она не
предполагает, что механика сама по себе радикально меняет экономику
пользователя, только то, что при заданных (пока не измеренных) ставках
модель не показывает внутренних противоречий или очевидного отрицательного
результата.

## 5. Что это не доказывает

- Ставки (`CM_rate`, `avg_new_basket_value`, `markdown_baseline_sale_probability`
  и т.д.) не измерены на данных X5 — до пилота это управляемые допущения, не
  факты (см. открытые вопросы кейсодателю в
  [rescue-basket-economics.md §14](../monetization/rescue-basket-economics.md#14-вопросы-кейсодателюx5-до-защиты),
  многие из них применимы и здесь).
- Симуляция не учитывает reservation/no-show costs — они относятся к более
  ранней (устаревшей) reservation-концепции, не к recipe-first PoC.
- Positive `net_CM` в синтетической симуляции — не доказательство
  прибыльности в реальности; это проверка того, что заданные допущения
  внутренне непротиворечивы (нет двойного счёта, нет скрытого
  отрицательного сценария при разумных вариациях параметров).
- Причинный uplift частоты покупок проверяется только реальным пилотом с
  тест/контроль группами — как явно указано в
  [README.md](../../../README.md) и case-context.md.

## 6. Как воспроизвести

```bash
python -m pytest tests/test_recsys_simulation.py tests/test_recsys_economics.py -q
python -m recsys.simulation   # funnel-таблица на N=1000 и N=10000 × 3 сценария
python -m recsys.economics    # экономика на тех же N × сценариях
```
