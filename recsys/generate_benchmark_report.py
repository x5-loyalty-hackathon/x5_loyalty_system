"""Run the full bench and write ``docs/benchmark-report.md``.

Usage::

    python -m recsys.generate_benchmark_report [--users 200] [--seed 20260905]

The report leads with the bench's own validity check rather than with results.
If a random ranker cannot be told apart from a trained one, every table below
that point is noise, and a reader should learn that before reading them.
"""

from __future__ import annotations

import argparse
import io
import statistics
import sys
import time
from pathlib import Path

from recsys.benchmark import (
    PRIMARY_METRIC,
    BenchmarkResult,
    Comparison,
    default_arms,
    run_benchmark,
)
from recsys.diagnostics import effort_confound, stratified_signal
from recsys.regimes import DIALS, REGIMES
from recsys.response_models import (
    DEFAULT_RESPONDERS,
    INDEPENDENT_RESPONDER_NAMES,
    UserAction,
)

OUTPUT_PATH = Path("docs/benchmark-report.md")

#: Comparisons the report always answers, as (baseline, challenger, question).
HEADLINE_COMPARISONS: tuple[tuple[str, str, str], ...] = (
    (
        "random/effort",
        "ml/effort",
        "Даёт ли обученная модель что-нибудь поверх случайной под текущей политикой?",
    ),
    (
        "heuristic/effort",
        "ml/effort",
        "Обыгрывает ли модель эвристику под текущей политикой?",
    ),
    (
        "ml/effort",
        "ml/blended",
        "Меняет ли что-нибудь смена политики ранжирования при той же модели?",
    ),
    (
        "random/relevance",
        "ml/relevance",
        "Когда политика пропускает ранжирование, видна ли разница модели и шума?",
    ),
    (
        "ml/blended",
        "ml_pref/blended",
        "Помогает ли убрать effort-фичи из модели, раз политика их уже учитывает?",
    ),
)


def _dial_of(regime_name: str, dial: str) -> str:
    for part in regime_name.split("/"):
        key, _, value = part.partition("=")
        if key == dial:
            return value
    return "?"


def win_rate_by_dial(comparison: Comparison, dial: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for level in DIALS[dial]:
        subset = [
            d
            for d in comparison.deltas
            if d.responder in INDEPENDENT_RESPONDER_NAMES
            and _dial_of(d.regime, dial) == level
        ]
        out[level] = (
            sum(1 for d in subset if d.challenger_wins) / len(subset) if subset else 0.0
        )
    return out


def _diagnostic_engines():
    from app.recommender import DeterministicMockEngine
    from recsys.model import MLRecommendationEngine

    return (
        ("`ml` (как в проде)", MLRecommendationEngine()),
        (
            "`ml_pref` (effort-фичи обнулены)",
            MLRecommendationEngine(include_effort_features=False),
        ),
        ("`heuristic`", DeterministicMockEngine()),
    )


def build(
    result: BenchmarkResult, runtime_s: float, *, diagnostic_profiles: int = 60
) -> str:
    out: list[str] = []
    w = out.append

    w("# Стенд рекомендателя: отчёт")
    w("")
    w(
        "Сгенерирован `python -m recsys.generate_benchmark_report`. "
        f"Прогон: {result.n_regimes} миров × {result.users_per_regime} пользователей × "
        f"{len(result.arms)} рук × {len(result.responder_names)} симуляторов "
        f"= {len(result.cells)} ячеек, {runtime_s:.0f} с."
    )
    w("")
    w("---")
    w("")
    w("## Что этот стенд может и чего не может")
    w("")
    w(
        "**Не может** предсказать uplift. У нас нет способа узнать, какой из "
        "правдоподобных миров похож на настоящую Пятёрочку, а победитель между "
        "мирами меняется. Любая фраза вида «B даст +4.2% GMV» из этих чисел не "
        "следует, сколько бы пользователей мы ни насимулировали: 10 000 "
        "пользователей одного мира описывают один мир."
    )
    w("")
    w(
        "**Может** дёшево отбраковывать плохие идеи и мерить хрупкость хороших. "
        "Формулировка, которую стенд поддерживает: «B выигрывает у A в N% "
        "(мир × симулятор) ячеек, и это держится при всех независимых "
        "симуляторах»."
    )
    w("")
    w("Три свойства обеспечивают ценность этой формулировки:")
    w("")
    w(
        "1. **Парное сравнение.** Все руки видят одни и те же профили и один и "
        "тот же снимок инвентаря в каждом мире. Руки отличаются только "
        "ранжированием."
    )
    w(
        "2. **Общие карточки.** Рекомендация считается один раз на "
        "(мир, пользователь, рука), затем её судят все симуляторы — они спорят "
        "об одних и тех же данных."
    )
    w(
        "3. **Отрицательный контроль.** Случайный ранжировщик участвует как "
        "рука. Если стенд не показывает его проигрыш — стенд не измеряет "
        "ранжирование."
    )
    w("")
    w("---")
    w("")

    # --- validity first -------------------------------------------------
    w("## 1. Валидность стенда (читать первым)")
    w("")
    checks = result.discrimination_check()
    w("Лучшая доля побед среди кандидатных рук против каждого контроля:")
    w("")
    w("| Контроль | Лучшая рука выигрывает | Вывод |")
    w("|---|---:|---|")
    for control, rate in sorted(checks.items()):
        verdict_text = (
            "стенд различает" if rate > 0.6 else "**ни одна рука не лучше шума**"
        )
        w(f"| `{control}` | {rate:.0%} | {verdict_text} |")
    w("")
    if result.bench_discriminates:
        w(
            "Стенд обладает различающей способностью: хотя бы один контроль "
            "уверенно отбраковывается. Значит числа ниже что-то означают."
        )
    else:
        w(
            "**СТЕНД СЛЕП.** Ни одна рука не отличается от случайной. Всё, что "
            "ниже, — шум, и читать это не нужно."
        )
    w("")
    w("---")
    w("")

    # --- arm ranking ----------------------------------------------------
    w("## 2. Руки")
    w("")
    w(
        "Основная метрика — `cook_conversion_rate`: доля карточек, по которым "
        "пользователь готовил. Замена на готовое (`substitute`) намеренно **не** "
        "засчитывается: она случается, когда готовое дешевле корзины, то есть "
        "чаще всего именно тогда, когда рецепт был плохим советом. Ранняя версия "
        "этого стенда считала `buy + substitute` и поставила случайную руку на "
        "первое место — она гнала людей на полку готовой еды."
    )
    w("")
    w("| Рука | cook_conversion | substitute | ignore | Контроль |")
    w("|---|---:|---:|---:|:--:|")
    means = result.arm_means()
    control_names = set(result.control_arms())
    for arm, value in sorted(means.items(), key=lambda kv: -kv[1]):
        cells = [c for c in result.cells if c.arm == arm]
        subst = statistics.mean(c.substitute_rate for c in cells)
        ignore = statistics.mean(c.action_rate(UserAction.IGNORE) for c in cells)
        mark = "✓" if arm in control_names else ""
        w(f"| `{arm}` | {value:.4f} | {subst:.3f} | {ignore:.3f} | {mark} |")
    w("")
    w("Название руки — `<ранжировщик>/<политика>`.")
    w("")
    w("---")
    w("")

    # --- headline comparisons -------------------------------------------
    w("## 3. Сравнения")
    w("")
    for baseline, challenger, question in HEADLINE_COMPARISONS:
        if baseline not in means or challenger not in means:
            continue
        comparison = result.compare(baseline, challenger)
        w(f"### {challenger} против {baseline}")
        w("")
        w(f"*{question}*")
        w("")
        w(
            f"- побед в независимых ячейках: **{comparison.independent_win_rate:.0%}**"
        )
        by_responder = comparison.win_rate_by_responder()
        w(
            "- по симуляторам: "
            + ", ".join(
                f"`{name}` {rate:.0%}" for name, rate in sorted(by_responder.items())
            )
        )
        w(
            "- единогласно у независимых симуляторов: "
            + ("**да**" if comparison.is_unanimous_across_responders else "**нет**")
        )
        quantiles = comparison.delta_quantiles()
        if quantiles:
            w(
                f"- разброс эффекта: p10 {quantiles['p10']:+.4f}, "
                f"медиана {quantiles['median']:+.4f}, p90 {quantiles['p90']:+.4f}"
            )
        w("")
        for dial in DIALS:
            rates = win_rate_by_dial(comparison, dial)
            w(
                f"  - `{dial}`: "
                + ", ".join(f"{level} {rate:.0%}" for level, rate in rates.items())
            )
        w("")
    w("---")
    w("")

    # --- mechanism -------------------------------------------------------
    w("## 4. Механизм: почему руки сходятся")
    w("")
    w(
        "Сравнения выше показывают *что* происходит. Этот раздел показывает "
        "*почему*, и его можно перепроверить: `python -m recsys.diagnostics`."
    )
    w("")
    w("### 4.1 Effort протекает через всё признаковое пространство")
    w("")
    w(
        "Корреляция каждой фичи модели с `missing_count` — то есть с величиной, "
        "по которой `app.service.RankingPolicy` и так сортирует первым ключом:"
    )
    w("")
    w("| Фича | corr с missing_count |")
    w("|---|---:|")
    confound = effort_confound(n_profiles=diagnostic_profiles)
    for name, value in sorted(confound.items(), key=lambda kv: -abs(kv[1])):
        mark = " ⚠" if abs(value) > 0.5 else ""
        w(f"| `{name}` | {value:+.3f}{mark} |")
    w("")
    heavy = sorted(
        (n for n, v in confound.items() if abs(v) > 0.5),
        key=lambda n: -abs(confound[n]),
    )
    w(
        f"Фич с |r| > 0.5: **{len(heavy)}** из {len(confound)}"
        + (f" — {', '.join('`' + n + '`' for n in heavy)}." if heavy else ".")
    )
    w("")
    affinity_r = confound.get("history_affinity")
    if affinity_r is not None:
        w(
            f"`history_affinity` = {affinity_r:+.3f}. Раньше здесь было −0.79: "
            "фича считалась как |категории рецепта ∩ категории истории| / "
            "|ингредиенты рецепта|, то есть делила счётчик категорий на счётчик "
            "ингредиентов, а история любого пользователя покрывала все семь "
            "категорий. Она была константой формы рецепта под именем "
            "персонализации. Сейчас это средняя доля покупок пользователя в "
            "категориях рецепта — величина, которая действительно различает людей."
        )
    w("")
    w("")
    w("### 4.2 Сигнал модели при фиксированном effort")
    w("")
    w(
        "Решающая проверка: отделяет ли `model_score` релевантное от "
        "нерелевантного **внутри** групп с одинаковым `missing_count`. Мера — "
        "AUC, порога не требует."
    )
    w("")
    w("| Ранжировщик | AUC общий | AUC внутри групп | Разрыв |")
    w("|---|---:|---:|---:|")
    gaps: dict[str, float] = {}
    readable: dict[str, int] = {}
    for label, engine in _diagnostic_engines():
        signal = stratified_signal(engine, n_profiles=diagnostic_profiles)
        within = signal.within_stratum_auc
        if within is None:
            w(f"| {label} | {signal.overall_auc:.3f} | n/a | n/a |")
            continue
        gap = signal.overall_auc - within
        gaps[label] = gap
        readable[label] = len(signal.readable_strata)
        w(
            f"| {label} | {signal.overall_auc:.3f} | {within:.3f} | {gap:+.3f} |"
        )
    w("")
    w(
        "**Разрыв — это и есть диагноз.** Большой разрыв означает, что видимая "
        "точность держится на `missing_count`, который конвейер и так "
        "использует; маленький — что модель ранжирует внутри равного effort, "
        "то есть несёт свой сигнал."
    )
    w("")
    ml_gap = next((g for label, g in gaps.items() if label.startswith("`ml`")), None)
    if ml_gap is not None:
        if ml_gap > 0.15:
            w(
                f"Сейчас разрыв у прод-модели **{ml_gap:+.3f}** — сигнала сверх "
                "effort почти нет."
            )
        else:
            w(
                f"Сейчас разрыв у прод-модели **{ml_gap:+.3f}**. До починки метки "
                "он составлял +0.42 (AUC 0.955 общий против 0.532 внутри групп): "
                "метка гейтила на `missing_count > max_missing_tolerance`, из-за "
                "чего в стратах с шестью и более недостающими ингредиентами "
                "релевантных примеров не было вообще. Гейт снят — осуществимость "
                "это работа `RankingPolicy` и фильтра доступности, а не метки "
                "предпочтения."
            )
    w("")
    w("---")
    w("")

    # --- simulator disagreement -----------------------------------------
    w("## 5. Расхождение симуляторов")
    w("")
    w(
        "Если рука выигрывает только у одного симулятора — это свойство "
        "симулятора, а не руки. `oracle_selfref` показан отдельно: он происходит "
        "от тех же правил архетипов, на которых обучалась `recsys.model`, то есть "
        "у ML-рук там структурное преимущество, которого нет больше нигде."
    )
    w("")
    w("| Сравнение | " + " | ".join(f"`{n}`" for n in result.responder_names) + " |")
    w("|---" * (len(result.responder_names) + 1) + "|")
    for baseline, challenger, _ in HEADLINE_COMPARISONS:
        if baseline not in means or challenger not in means:
            continue
        comparison = result.compare(baseline, challenger)
        by_responder = comparison.win_rate_by_responder()
        cells = " | ".join(
            f"{by_responder.get(name, 0.0):.0%}" for name in result.responder_names
        )
        w(f"| {challenger} vs {baseline} | {cells} |")
    w("")
    w("---")
    w("")
    w("## 6. Угрозы валидности")
    w("")
    w(
        "- **Миры выбрали мы.** Сетка режимов — диапазон стресса, а не выборка из "
        "реальности. Доля побед не является p-value и не должна так читаться."
    )
    w(
        "- **Симуляторы написаны нами.** Три независимых симулятора расходятся по "
        "функциональной форме, но все написаны одним человеком за один заход и "
        "могут делить слепое пятно."
    )
    w(
        "- **`oracle_selfref` скомпрометирован по построению** и включён только "
        "как контроль-иллюстрация."
    )
    w(
        "- **Цены домашней корзины — оценка** (`price_is_estimate`), "
        "откалиброванная по реальному распределению чеков X5, но не поингредиентно "
        "истинная. Цены готовой еды наблюдаемые. Симулятор `economic` сравнивает "
        "эти две величины напрямую и потому наиболее чувствителен к калибровке."
    )
    w(
        "- **Каталог рецептов мал** (37). Доля побед на маленьком каталоге "
        "переоценивает роль отдельных блюд."
    )
    w("")
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--diagnostic-profiles", type=int, default=60)
    args = parser.parse_args(argv[1:])

    started = time.time()
    result = run_benchmark(
        default_arms(),
        regimes=REGIMES,
        responders=DEFAULT_RESPONDERS,
        users_per_regime=args.users,
        seed=args.seed,
    )
    runtime = time.time() - started
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = build(result, runtime, diagnostic_profiles=args.diagnostic_profiles)
    io.open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n").write(text)
    print(f"{OUTPUT_PATH}: {len(text.splitlines())} lines, {len(result.cells)} cells")
    print(f"metric={PRIMARY_METRIC} runtime={runtime:.0f}s")
    for arm, value in sorted(result.arm_means().items(), key=lambda kv: -kv[1]):
        print(f"  {arm:22} {value:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
