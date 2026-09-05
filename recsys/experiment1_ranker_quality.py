"""Experiment 1 — качество самого ранкера.

See ``docs/research/recsys/experiment-plan-ranker-service-catalog.md``
("Эксперимент 1 — качество самого ранкера") for the full spec this
implements. Three separate evaluations, deliberately kept apart (plan §0):

``run_eval_ab``
    Eval A (want-to-cook, before store availability: ``engine.rank(request)``
    called directly, judged by ``recsys.evaluation.oracle_relevant``) and
    Eval B (share of the same candidates that are actually purchasable in
    the live ``inventory_snapshot``, via
    ``RecommendationService._valid_products``) computed together in one pass
    over a shared basket panel, because both need the same requests — never
    blended into one number.
``run_eval_c``
    Full ``recsys.benchmark.run_benchmark`` pipeline, at reduced scale, as a
    secondary sanity check only.

Run: ``python -m recsys.experiment1_ranker_quality``
"""

from __future__ import annotations

import random
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.contracts import Recipe, RecommendationRequest
from app.safety import SafetyPolicy
from app.service import EFFORT_FIRST, RecommendationService
from recsys.benchmark import PRIMARY_METRIC, Arm, RandomEngine, run_benchmark
from recsys.catboost_model import GRADIENT_BOOSTER_BACKEND, CatBoostRecommendationEngine
from recsys.coverage_heuristic_engine import CoverageHeuristicEngine
from recsys.diagnostics import Stratum, StratifiedSignal, auc, pearson
from recsys.evaluation import oracle_relevant
from recsys.inventory import (
    DEFAULT_INVENTORY_ASSUMPTIONS,
    InventoryAssumptions,
    generate_inventory,
)
from recsys.model import MLRecommendationEngine, compute_features, compute_user_stats
from recsys.oracle_ranking_engine import OracleRankingEngine
from recsys.pantry import DISABLED_PANTRY, available_ingredient_ids
from recsys.profiles import generate_population
from recsys.recipes import RECIPES
from recsys.regimes import REGIMES

OUTPUT_PATH = Path("docs/research/recsys/experiment-1-ranker-quality-report.md")

#: The metric-0.19 passport (plan §0) fixes these for cross-experiment
#: comparability: same seed, same TOP_K, same REGIMES[:9]/80-per-regime scale.
DEFAULT_SEED = 20260905
TOP_K = 3
REGIMES_USED = REGIMES[:9]
USERS_PER_REGIME = 80

#: Report/table column order for the 4 candidates, matching build_engines().
ENGINE_ORDER = ("coverage", "ml", "catboost", "oracle")

#: Same low/base/high values already calibrated in recsys.sensitivity.DIALS
#: for `no_product_at_all` and `out_of_stock`, moved together as one
#: "shelf severity" axis rather than crossed 3x3 — the plan asks for "at
#: least 3 deficit levels", not a full independent sweep of each knob (that
#: sweep already exists, per-knob, in recsys.sensitivity).
DEFICIT_LEVELS: tuple[tuple[str, InventoryAssumptions], ...] = (
    ("низкий", InventoryAssumptions(no_product_at_all=0.02, out_of_stock=0.02)),
    ("база", DEFAULT_INVENTORY_ASSUMPTIONS),
    ("высокий", InventoryAssumptions(no_product_at_all=0.35, out_of_stock=0.35)),
)


def build_engines(*, seed: int = DEFAULT_SEED, training_profiles: int = 300) -> dict[str, object]:
    """The 4 candidates, in report order. Trained once, reused across every
    deficit level and every eval — training does not depend on the supply
    scenario being swept."""
    return {
        "coverage": CoverageHeuristicEngine(),
        "ml": MLRecommendationEngine(seed=seed, training_profiles=training_profiles),
        "catboost": CatBoostRecommendationEngine(seed=seed, training_profiles=training_profiles),
        "oracle": OracleRankingEngine(),
    }


@dataclass
class EngineAccumulator:
    precision_hits: list[float] = field(default_factory=list)
    stratum_scores: dict[int, list[float]] = field(default_factory=lambda: defaultdict(list))
    stratum_labels: dict[int, list[bool]] = field(default_factory=lambda: defaultdict(list))
    feasible_topk: int = 0
    total_topk: int = 0
    #: Rank agreement with the oracle ranker — only populated for "ml" and
    #: "catboost", the two candidates the plan asks to compare against it.
    top3_jaccard_vs_oracle: list[float] = field(default_factory=list)
    spearman_vs_oracle: list[float] = field(default_factory=list)

    def stratified_signal(self) -> StratifiedSignal:
        strata = tuple(
            Stratum(
                missing_count=bucket,
                n=len(labels),
                positive_rate=sum(labels) / len(labels) if labels else 0.0,
                auc=auc(self.stratum_scores[bucket], labels),
            )
            for bucket, labels in sorted(self.stratum_labels.items())
        )
        all_scores = [s for scores in self.stratum_scores.values() for s in scores]
        all_labels = [l for labels in self.stratum_labels.values() for l in labels]
        return StratifiedSignal(overall_auc=auc(all_scores, all_labels), strata=strata)

    @property
    def precision_at_k(self) -> float:
        return statistics.mean(self.precision_hits) if self.precision_hits else 0.0

    @property
    def feasible_share(self) -> float:
        return self.feasible_topk / self.total_topk if self.total_topk else 0.0

    @property
    def mean_top3_jaccard_vs_oracle(self) -> float | None:
        return statistics.mean(self.top3_jaccard_vs_oracle) if self.top3_jaccard_vs_oracle else None

    @property
    def mean_spearman_vs_oracle(self) -> float | None:
        return statistics.mean(self.spearman_vs_oracle) if self.spearman_vs_oracle else None


@dataclass
class DeficitLevelResult:
    label: str
    base_relevance_rate: float
    n_profiles: int
    by_engine: dict[str, EngineAccumulator]


def _is_feasible_today(
    service: RecommendationService,
    request: RecommendationRequest,
    recipe: Recipe,
    covered_ids: set[str],
) -> bool:
    """Mirrors the availability gate inside
    ``RecommendationService._assemble_recipe``: a recipe is feasible today
    if every *required* ingredient not already covered has at least one
    product that clears ``SafetyPolicy``. Optional/seasoning ingredients
    without a valid product do not block it, matching the shipped service."""
    for ingredient in recipe.ingredients:
        if ingredient.ingredient_id in covered_ids:
            continue
        valid = service._valid_products(request=request, ingredient=ingredient)
        if not valid and ingredient.required:
            return False
    return True


def run_eval_ab(
    engines: dict[str, object],
    *,
    regimes: tuple = REGIMES_USED,
    users_per_regime: int = USERS_PER_REGIME,
    seed: int = DEFAULT_SEED,
    deficit_levels: tuple = DEFICIT_LEVELS,
    progress: bool = False,
) -> list[DeficitLevelResult]:
    """Eval A (want-to-cook) and Eval B (store availability) in one pass.

    ``inventory_snapshot`` never gates Eval A — ``oracle_relevant`` and
    ``compute_features`` here see only ``current_receipt``/``purchase_history``
    for the relevance judgment. It is used only for Eval B's separate
    feasibility check and for the ``markdown_supply_signal`` feature, exactly
    as ``recsys.model`` already does.
    """
    service = RecommendationService(engine=RandomEngine(), safety_policy=SafetyPolicy())
    recipe_catalog = list(RECIPES)
    recipe_lookup = {r.recipe_id: r for r in recipe_catalog}
    results: list[DeficitLevelResult] = []

    for deficit_label, assumptions in deficit_levels:
        if progress:
            print(f"  Eval A/B: {deficit_label}", flush=True)
        by_engine = {name: EngineAccumulator() for name in engines}
        base_relevance_sum = 0.0
        n_profiles = 0

        for regime_index, regime in enumerate(regimes):
            profiles = generate_population(
                users_per_regime, seed=seed + regime_index, archetypes=regime.archetypes()
            )
            inventory_rng = random.Random(seed + 100_000 + regime_index)

            for profile in profiles:
                inventory = generate_inventory(
                    inventory_rng,
                    now=profile.now,
                    home_store_id=profile.current_receipt.store_id,
                    user_radius_km=profile.user.radius_km,
                    assumptions=assumptions,
                )
                request = RecommendationRequest(
                    user=profile.user,
                    current_receipt=profile.current_receipt,
                    purchase_history=profile.purchase_history,
                    recipe_catalog=recipe_catalog,
                    inventory_snapshot=inventory,
                    now=profile.now,
                    limit=TOP_K,
                )
                n_profiles += 1
                covered_ids = available_ingredient_ids(request, policy=DISABLED_PANTRY)
                user_stats = compute_user_stats(request)

                relevance_by_recipe: dict[str, bool] = {}
                missing_count_by_recipe: dict[str, int] = {}
                for recipe in recipe_catalog:
                    relevance_by_recipe[recipe.recipe_id] = oracle_relevant(profile, recipe, request)
                    features = compute_features(request, recipe, user_stats)
                    missing_count_by_recipe[recipe.recipe_id] = int(features["_missing_count"])
                base_relevance_sum += sum(relevance_by_recipe.values()) / len(recipe_catalog)

                ranked_by_engine = {name: engine.rank(request) for name, engine in engines.items()}
                oracle_top3_ids = {r.recipe_id for r in ranked_by_engine["oracle"][:TOP_K]}
                oracle_rank_position = {
                    r.recipe_id: i for i, r in enumerate(ranked_by_engine["oracle"])
                }

                for name, ranked in ranked_by_engine.items():
                    acc = by_engine[name]
                    top_k = ranked[:TOP_K]

                    if top_k:
                        acc.precision_hits.append(
                            sum(relevance_by_recipe[r.recipe_id] for r in top_k) / len(top_k)
                        )
                    for rec in top_k:
                        acc.total_topk += 1
                        if _is_feasible_today(
                            service, request, recipe_lookup[rec.recipe_id], covered_ids
                        ):
                            acc.feasible_topk += 1

                    for rec in ranked:
                        bucket = missing_count_by_recipe[rec.recipe_id]
                        acc.stratum_scores[bucket].append(rec.score)
                        acc.stratum_labels[bucket].append(relevance_by_recipe[rec.recipe_id])

                    if name in ("ml", "catboost"):
                        ranked_ids = [r.recipe_id for r in ranked]
                        top3_ids = set(ranked_ids[:TOP_K])
                        union = top3_ids | oracle_top3_ids
                        acc.top3_jaccard_vs_oracle.append(
                            len(top3_ids & oracle_top3_ids) / len(union) if union else 0.0
                        )
                        own_positions = list(range(len(ranked_ids)))
                        oracle_positions = [oracle_rank_position[rid] for rid in ranked_ids]
                        acc.spearman_vs_oracle.append(pearson(own_positions, oracle_positions))

        results.append(
            DeficitLevelResult(
                label=deficit_label,
                base_relevance_rate=base_relevance_sum / n_profiles,
                n_profiles=n_profiles,
                by_engine=by_engine,
            )
        )
    return results


def run_eval_c(
    engines: dict[str, object],
    *,
    regimes: tuple,
    users_per_regime: int,
    seed: int,
    deficit_levels: tuple,
    progress: bool = False,
) -> dict[str, object]:
    """Full ``recsys.benchmark.run_benchmark`` pipeline, secondary sanity
    check only. Deliberately smaller scale than Eval A/B: this exists to ask
    "does the full pipeline point the same direction", not to produce a
    headline number — see ``docs/benchmark-report.md`` for why the answer to
    that question under the shipped policy is usually "barely".
    """
    arms = tuple(
        Arm(name=name, engine=engine, ranking_policy=EFFORT_FIRST) for name, engine in engines.items()
    ) + (Arm(name="random/effort", engine=RandomEngine(), ranking_policy=EFFORT_FIRST, is_control=True),)

    out: dict[str, object] = {}
    for deficit_label, assumptions in deficit_levels:
        if progress:
            print(f"  Eval C: {deficit_label}", flush=True)
        result = run_benchmark(
            arms,
            regimes=regimes,
            users_per_regime=users_per_regime,
            seed=seed,
            inventory_assumptions=assumptions,
        )
        out[deficit_label] = result
    return out


def _fmt_pp(value: float) -> str:
    return f"{value * 100:+.1f} п.п."


def build_report(
    ab_results: list[DeficitLevelResult],
    c_results: dict[str, object],
    *,
    runtime_s: float,
    users_per_regime: int,
    n_regimes: int,
    eval_c_users_per_regime: int,
    eval_c_n_regimes: int,
) -> str:
    out: list[str] = []
    w = out.append

    w("# Эксперимент 1 — качество самого ранкера")
    w("")
    w(
        "Сгенерирован `python -m recsys.experiment1_ranker_quality`. "
        f"Eval A/B: {n_regimes} миров × {users_per_regime} пользователей × "
        f"{len(DEFICIT_LEVELS)} уровня дефицита = "
        f"{n_regimes * users_per_regime * len(DEFICIT_LEVELS)} профилей, {runtime_s:.0f} с."
    )
    w("")
    w(
        "Вопрос эксперимента: на одинаковых кандидатах, до `app.service`, какой "
        "скорер лучше отделяет желаемое от нежелательного? См. "
        "`docs/research/recsys/experiment-plan-ranker-service-catalog.md`, "
        "«Эксперимент 1»."
    )
    w("")
    w(
        f"**Бэкенд градиентного бустинга в этом прогоне: `{GRADIENT_BOOSTER_BACKEND}`.**"
    )
    if GRADIENT_BOOSTER_BACKEND != "catboost":
        w("")
        w(
            "**CatBoost не установился в этой песочнице (нет сети или колеса под "
            "платформу). Ниже вместо него — `sklearn.ensemble.GradientBoostingClassifier`, "
            "явно подписанный суррогат. Не читайте строки «catboost» ниже как измерение "
            "CatBoost — это измерение GBM-заменителя.**"
        )
    w("")
    w("---")
    w("")
    w("## 0. Кандидаты")
    w("")
    w("| Ранкер | Что это |")
    w("|---|---|")
    w("| `coverage` | `CoverageHeuristicEngine` — без обучения, сортировка по (coverage desc, missing_count asc) |")
    w("| `ml` | `recsys.model.MLRecommendationEngine`, `include_effort_features=True`, как в проде |")
    w(f"| `catboost` | тот же X/y конвейер, что и `ml`, классификатор — `{GRADIENT_BOOSTER_BACKEND}` |")
    w("| `oracle` | непрерывный аналог `oracle_relevant`/`_combined_affinity` — потолок ранжирования **при этих признаках**, не абсолютный (self-referential, см. ADR-003) |")
    w("")
    w("---")
    w("")
    w("## A. Желание приготовить (precision@k против `oracle_relevant`)")
    w("")
    w(
        "`engine.rank(request)` вызывается напрямую, минуя `RecommendationService`. "
        "`inventory_snapshot` не гейтит эту секцию — только `current_receipt` и "
        "`purchase_history`. Метка — `recsys.evaluation.oracle_relevant`, "
        "self-referential относительно `recsys.model` (см. ADR-003): читайте "
        "числа как *относительное* сравнение рангов, не как абсолютную релевантность."
    )
    w("")
    w("| Уровень дефицита | база релевантности | " + " | ".join(f"precision@{TOP_K} {n}" for n in ENGINE_ORDER) + " |")
    w("|---" * (2 + len(ENGINE_ORDER)) + "|")
    for level in ab_results:
        cells = " | ".join(f"{level.by_engine[n].precision_at_k:.0%}" for n in ENGINE_ORDER)
        w(f"| {level.label} | {level.base_relevance_rate:.0%} | {cells} |")
    w("")
    w("Лифт над базой (precision@k минус base relevance rate):")
    w("")
    w("| Уровень дефицита | " + " | ".join(ENGINE_ORDER) + " |")
    w("|---" * (1 + len(ENGINE_ORDER)) + "|")
    for level in ab_results:
        cells = " | ".join(
            _fmt_pp(level.by_engine[n].precision_at_k - level.base_relevance_rate)
            for n in ENGINE_ORDER
        )
        w(f"| {level.label} | {cells} |")
    w("")

    unanimous_order: list[bool] = []
    for level in ab_results:
        ordered = sorted(ENGINE_ORDER, key=lambda n: -level.by_engine[n].precision_at_k)
        unanimous_order.append(tuple(ordered))
    all_same_order = len(set(unanimous_order)) == 1
    w(
        "**Устойчивость порядка между уровнями дефицита:** "
        + ("порядок ранкеров по precision@k не меняется между низким/базовым/высоким дефицитом."
           if all_same_order else
           "порядок ранкеров по precision@k **меняется** между уровнями дефицита — см. таблицу выше, это не шум оформления, а разные лидеры на разных уровнях.")
    )
    w("")
    w("---")
    w("")
    w("## ADR-003-диагностика: AUC внутри равного missing_count")
    w("")
    w(
        "Общий AUC против AUC, усреднённого по стратам одинакового "
        "`missing_count` (страты с `n < 30` помечены как нечитаемые, как в "
        "`recsys.diagnostics`). Малый разрыв «общий − внутри» означает, что "
        "ранкер несёт сигнал сверх того, что и так знает `missing_count` — "
        "то есть сверх того, что `app.service.RankingPolicy` уже применяет "
        "первым ключом."
    )
    w("")
    for level in ab_results:
        w(f"### {level.label}")
        w("")
        w("| Ранкер | общий AUC | AUC внутри effort | разрыв |")
        w("|---|---:|---:|---:|")
        for name in ENGINE_ORDER:
            signal = level.by_engine[name].stratified_signal()
            overall = signal.overall_auc
            within = signal.within_stratum_auc
            gap = (overall - within) if (overall is not None and within is not None) else None
            overall_s = f"{overall:.3f}" if overall is not None else "n/a"
            within_s = f"{within:.3f}" if within is not None else "n/a"
            gap_s = f"{gap:+.3f}" if gap is not None else "n/a"
            w(f"| {name} | {overall_s} | {within_s} | {gap_s} |")
        w("")

    w("---")
    w("")
    w("## Согласие с оракулом по рангам (ml, catboost)")
    w("")
    w(
        "Доля пересечения топ-3 с топ-3 оракульного ранкера (Jaccard) и корреляция "
        "Пирсона по позициям во всём отранжированном каталоге (37 рецептов) — "
        "оценка ранговой корреляции без внешней зависимости от scipy."
    )
    w("")
    w("| Уровень дефицита | ранкер | Jaccard топ-3 vs oracle | rank-корреляция vs oracle |")
    w("|---|---|---:|---:|")
    for level in ab_results:
        for name in ("ml", "catboost"):
            acc = level.by_engine[name]
            jac = acc.mean_top3_jaccard_vs_oracle
            sp = acc.mean_spearman_vs_oracle
            jac_s = f"{jac:.2f}" if jac is not None else "n/a"
            sp_s = f"{sp:+.2f}" if sp is not None else "n/a"
            w(f"| {level.label} | {name} | {jac_s} | {sp_s} |")
    w("")
    w("---")
    w("")
    w("## B. Наличие в конкретном магазине (отдельно от A)")
    w("")
    w(
        "Доля кандидатов топ-k каждого ранкера, у которых каждый недостающий "
        "**обязательный** ингредиент имеет хотя бы один продукт, проходящий "
        "`RecommendationService._valid_products`/`SafetyPolicy.evaluate_product` "
        "на живом `inventory_snapshot` этого профиля. Не смешано с (A): ранкер "
        "может резонно хотеть рецепт, которого сегодня нет на полке."
    )
    w("")
    w("| Уровень дефицита | " + " | ".join(ENGINE_ORDER) + " |")
    w("|---" * (1 + len(ENGINE_ORDER)) + "|")
    for level in ab_results:
        cells = " | ".join(f"{level.by_engine[n].feasible_share:.0%}" for n in ENGINE_ORDER)
        w(f"| {level.label} | {cells} |")
    w("")
    w(
        "Ожидаемо падает с ростом дефицита одинаково для всех ранкеров — это "
        "свойство каталога/магазина, а не ранжирования; см. эксперимент 3 "
        "(покрытие каталога) для того, что с этим делать."
    )
    w("")
    w("---")
    w("")
    w("## C. Синтетическая готовка как проверка (вторично, не основной результат)")
    w("")
    w(
        f"Прогон через полный `recsys.benchmark.run_benchmark` (политика "
        f"`EFFORT_FIRST`, как в проде) на уменьшенном масштабе — "
        f"{eval_c_n_regimes} миров × {eval_c_users_per_regime} пользователей, "
        f"против A/B ({n_regimes} × {users_per_regime}) — потому что здесь "
        f"считается **вся** воронка (4 симулятора × 4 ранкера × миры), а не "
        f"один проход ранжирования. Только проверка направления согласованности "
        f"с (A)/(B), не самостоятельный результат."
    )
    w("")
    for deficit_label, result in c_results.items():
        w(f"### {deficit_label}")
        w("")
        means = result.arm_means(PRIMARY_METRIC)
        w(f"`{PRIMARY_METRIC}` по руке (среднее по независимым симуляторам):")
        w("")
        w("| Рука | " + PRIMARY_METRIC + " |")
        w("|---|---:|")
        for arm_name, value in sorted(means.items(), key=lambda kv: -kv[1]):
            w(f"| {arm_name} | {value:.4f} |")
        w("")
        consistent_with_a = None
        level = next((lv for lv in ab_results if lv.label == deficit_label), None)
        if level is not None:
            precision_order = sorted(
                ENGINE_ORDER, key=lambda n: -level.by_engine[n].precision_at_k
            )
            benchmark_order = sorted(
                (n for n in ENGINE_ORDER if n in means), key=lambda n: -means.get(n, 0.0)
            )
            consistent_with_a = precision_order == benchmark_order
            w(
                "Порядок по precision@k (A) "
                + ("совпадает" if consistent_with_a else "**не совпадает**")
                + f" с порядком по `{PRIMARY_METRIC}` (C) на этом уровне дефицита: "
                f"A={precision_order}, C={benchmark_order}."
            )
            w("")
    w("---")
    w("")
    w("## Угрозы валидности")
    w("")
    w(
        "- **`oracle_relevant` self-referential.** Он выведен из тех же правил "
        "архетипа, что и обучающая метка `_label_for_pair` (`recsys.model`), — "
        "см. паспорт метрики 0.19 и ADR-003. Precision@k и AUC-диагностика "
        "здесь показывают, кто лучше воспроизводит эту конкретную "
        "синтетическую метку, не независимо измеренную релевантность."
    )
    w(
        "- **`oracle`-ранкер — не абсолютный потолок.** Он не видит "
        "`discovery_acceptance` (параметр архетипа, недоступный как признак "
        "запроса), поэтому его непрерывный скор — упрощение ветки "
        "новизны/знакомости `oracle_relevant`, а не её точное воспроизведение."
    )
    w(
        f"- **Уровни дефицита выбраны нами.** Три точки "
        f"(`no_product_at_all`/`out_of_stock` низкий/база/высокий), "
        "откалиброванные в `recsys.sensitivity.DIALS`, двигаются вместе как "
        "одна ось «дефицит полки», а не крест 3×3 — раздельный эффект каждой "
        "ручки уже есть в `docs/sensitivity-report.md`."
    )
    w(
        "- **Eval B не проверяет исключения пользователя.** Считается только "
        "физическая доступность продукта (`_valid_products`), не "
        "`excluded_categories`/`excluded_ingredient_ids` — это отдельный "
        "фильтр сервиса, не про наличие в магазине."
    )
    w(
        "- **CatBoost/GBM обучается один раз на seed "
        f"{DEFAULT_SEED}**, как и `ml`; отчёт не проверяет чувствительность "
        "к сиду обучения классификатора (только к сиду генерации панели "
        "корзин, через уровни дефицита и 9 миров)."
    )
    w(
        "- **Eval C заведомо меньше по масштабу**, чем A/B "
        f"({eval_c_n_regimes}×{eval_c_users_per_regime} против "
        f"{n_regimes}×{users_per_regime}) — воронка там дороже "
        "(4 симулятора на каждую пару рука/мир/пользователь). Числа раздела C "
        "менее устойчивы, чем A/B, и заявлены только как sanity-check."
    )
    w(
        "- **Это не оценка продукта**, как и весь остальной стенд — "
        "устойчивость вывода на синтетике, не прогноз аплифта на реальных "
        "пользователях."
    )
    w("")
    return "\n".join(out) + "\n"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    started = time.time()

    print("training engines...", flush=True)
    engines = build_engines()
    print(f"  backend: {GRADIENT_BOOSTER_BACKEND}", flush=True)

    print("running Eval A/B...", flush=True)
    ab_results = run_eval_ab(engines, progress=True)

    eval_c_regimes = REGIMES[:5]
    eval_c_users = 30
    print("running Eval C (secondary sanity check)...", flush=True)
    c_results = run_eval_c(
        engines,
        regimes=eval_c_regimes,
        users_per_regime=eval_c_users,
        seed=DEFAULT_SEED,
        deficit_levels=DEFICIT_LEVELS[1:],  # база + высокий: skip "низкий", least interesting for a sanity check
        progress=True,
    )

    runtime = time.time() - started
    report = build_report(
        ab_results,
        c_results,
        runtime_s=runtime,
        users_per_regime=USERS_PER_REGIME,
        n_regimes=len(REGIMES_USED),
        eval_c_users_per_regime=eval_c_users,
        eval_c_n_regimes=len(eval_c_regimes),
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(report, encoding="utf-8", newline="\n")
    print(f"\n{OUTPUT_PATH}: {len(report.splitlines())} lines, {runtime:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
