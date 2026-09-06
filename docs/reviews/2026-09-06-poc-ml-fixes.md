# C1: выборочный перенос исправлений ML

Дата: 06.09.2026. Рабочая база — `experiment/vxofi@17bbe72`, дерево
совпадало с `main@05cc691`. Источник —
`origin/experiment/recsys-benchmark-clean-authorship@70f3af558daa9e146b4e8483744cf5033ef74614`.
Изменения подготовлены локально, без cherry-pick, merge, commit и push.
Границы — [план C1](../poc-execution-plan.md), API 1.3, ADR-001–005 и
[integration handoff](../integration-handoff.md).

## Что перенесено

| Исходный SHA | Применение и файлы | Совместимость / ограничения |
|---|---|---|
| `c4370ddabad5c03312d2a726c6862597616b1f5a` | Не перенесён | L9 вместо `REGIMES[:9]` меняет исследовательскую выборку; отложено к D3 |
| `0bf824098ff58f91f15e2b9fa5ec483c37e6bf16` | Частично: `recsys/benchmark.py` записывает `recipe_catalog_hash`; `recsys/generate_examples.py` объясняет назначение live-каталога; `tests/test_benchmark.py` | Сохранены default live47 и явный `recipes=`. Переход benchmark/diagnostics/llm_audit на baseline37 и смена regime-fixture отложены к D3. Hash использует `experimental.catalog_freeze`, совместимый с типами стенда |
| `364ca214f35c458c4a6e91c06e2bc642b8760049` | Частично: `missing_vs_basket` включён в effort registry в `recsys/model.py` и `recsys/experimental/model.py`; проверки в `tests/test_poc_ml_fixes.py` | Default serving сохраняет `include_effort_features=True`: проверены одинаковые веса, bias и финальные meal-ответы до/после исправления. Исправленный preference-only arm требует нового измерения; residual-variance guard `0.45` не переносился |
| `70f85dcba31cc61289c67dcbfa3bd435854a837e` | Частично: комментарий в `recsys/experimental/service.py` и текст генератора `recsys/experiment2_service_logic.py` | Исправлено происхождение cap: development train panel/base deficit, не `REGIMES[:9]`. Значение 6 сохранено только в research. Числа 603/p50=4/p75=6/p90=8/max=14 явно атрибутированы повторной проверке исходного SHA; локальный прогон их заново не измерял. `app/service.py` не менялся |
| `93eff2737e9039149b0c381f0c633cdc71c6aecf` | `recsys/catalog.py`, `recsys/generate_recipe_doc.py`, `tests/test_price_calibration.py`, `docs/recipe-catalog.md` | Коэффициент вычисляется из медиан: текущая цитата ×2.31. Цены, рецепты, порции и допустимый диапазон не менялись; это отношение к историческому reference, не новая оценка инфляции |
| `b8ab65d1245ae14a52db5bd18319bd817e900e88` | `recsys/ready_food_pairs.py`, `recsys/generate_recipe_doc.py`, `tests/test_recsys_ready_food_pairs.py`, `docs/recipe-catalog.md` | Добавлены require/exclude и исправлены пять групп ложных совпадений: паста-намазка, иные овощи по-корейски, некуриный гриль, салат без грибов, гречка без грибов. Для гречки с грибами отсутствие аналога явно записано; число рецептов с парами 29 → 28 |
| `70f3af558daa9e146b4e8483744cf5033ef74614` | `app/fraud.py`, новый `app/referral_codes.py`, актуальные `tests/test_progress_and_referral.py`, `tests/test_poc_ml_fixes.py`, `examples/referral_request.json` | Код проверяется на принадлежность inviter до attribution/duplicate. API 1.3, shared-device/payment review, once-only reward 20/20 XP и отсутствие XP за обычный чек сохранены |

`docs/recipe-catalog.md` пришлось пересоздать: иначе документ продолжал бы
предлагать подтверждённые ложные пары и цитировать ×2.4. В генератор добавлено
сохранение research-banner, актуального пути `experimental/recipes.py` и
уточнение, что `price_is_estimate` отсутствует в HTTP API 1.3. Ранее ручной banner
исчезал при регенерации. Остальные отчёты и JSON-панели не регенерировались.

## Referral для demo

```python
from app.referral_codes import issue_invite_code

invite_code = issue_invite_code(inviter_user_id)
```

`generate_invite_code` оставлен как alias имени из исходной ML-ветки.
Для `user_17` при default PoC-secret код — `6YT2RGZT`; он записан в существующий
JSON-пример. `REFERRAL_CODE_SECRET` должен совпадать у выдающего и проверяющего
кода процесса. При смене secret старые коды перестают проходить проверку;
при custom secret статический пример нужно сформировать helper-ом заново.

Отдельного HTTP endpoint выдачи кода нет. Default secret публичный и служит
воспроизводимости demo; любой читатель исходника может выпустить код. Проверка
не является production-auth, доказательством реального приглашения или покупки.
Ввод пробелов/нижнего регистра допускается. В отличие от прямого переноса SHA,
не-ASCII ввод безопасно отвергается: `hmac.compare_digest` со строкой Unicode
иначе мог выбросить исключение вместо ответа API.

## Проверки

Первая целевая группа — **86 passed** (11.99 s):

```bash
.venv/bin/python -m pytest tests/test_progress_and_referral.py tests/test_poc_ml_fixes.py tests/test_recsys_ready_food_pairs.py tests/test_price_calibration.py tests/test_benchmark.py tests/test_recsys_model.py tests/test_recsys_merge_boundaries.py
```

В том числе: forged/arbitrary/Unicode referral, проверка неверного кода при
повторе, смена secret, сохранённые concurrency/20 XP assertions; suppression
`missing_vs_basket` только в preference-only; тождественные веса и два финальных
meal-ответа API 1.3 при старом и новом registry; отсутствие experimental imports
в model HTTP-процессе, frozen training hash и исходные четыре panel manifests.

Дополнительная группа после исправления генератора research-banner:

```bash
.venv/bin/python -m pytest tests/test_price_calibration.py tests/test_model_features.py tests/test_experiment1_rankers.py tests/test_diagnostics.py tests/test_ready_meal_alternative.py tests/test_experiment3_catalog_coverage.py tests/test_experimental_recsys_evaluation.py tests/test_recsys_catalog_and_recipes.py tests/test_recsys_expanded_recipe_catalog.py
```

Вторая группа — **67 passed, 3 skipped** (58.07 s): два skips относятся к
неустановленному optional tree challenger, один — к fixture без saved recipes.
Две известные deprecation warnings
первой группы относятся к установленным Starlette/httpx/AnyIO.
`git diff --check` — успешно. Общий suite, C2/C3/C4 и клиент сводит основной агент.

## Оставлено к D3 и риски

- L9 действительно устраняет перекос сортированного `REGIMES[:9]`, но меняет
  популяцию измерений и восстановление исторически просмотренных профилей в
  `split_audit`. Нужны согласованные новый паспорт/seed и обращение со старыми
  отчётами; исходная выборка сохранена.
- Default37 для benchmark/diagnostics/llm_audit делает train/eval сравнимыми по
  каталогу, но исключает десять кандидатов из оцениваемого результата. Сейчас
  добавлена наблюдаемость hash, а выбор eval-каталога оставлен D3.
- Residual-variance guard `0.45` калиброван на исходном эксперименте, включая
  смену eval-каталога. Его число и статистическая диагностика не становятся
  CI-критерием качества API 1.3 без отдельного решения. Исправление provenance
  `missing_vs_basket` защищено детерминированным regression test.
- Исправления ready-пар и preference-only registry могут изменить новые числа
  исследовательских запусков. Исторические benchmark/sensitivity/experiment
  отчёты остаются историей; эта волна не объявляет их заново воспроизведёнными.
- Name-based ready-пары остаются исследовательскими кандидатами из snapshot,
  не доказательством наличия, состава, срока или полной эквивалентности блюду.
  Например, общий pool пасты всё ещё шире точного рецепта томатной пасты.
  Serving по-прежнему требует собственный meal match и safety по inventory;
  API не импортирует этот модуль.
- Авторитетность XP, reward limits, экономические предположения, методы оценки
  на людях и финальный hit rate эта волна не меняет и не подтверждает.

Чужие `pyproject.toml`, `recsys/data/foodru/`, `recsys/offline/`,
`tests/test_foodru_offline.py`, личный research, mobile и файлы параллельных
C2/C3/C4 задач не редактировались исполнителем C1.
