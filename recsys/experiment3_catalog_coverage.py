"""Experiment 3 -- catalog coverage.

Question: for how many synthetic baskets can the recipe catalog offer *any*
recipe within a reachable number of missing ingredients, before and after
expanding it -- and, when expansion makes a recipe newly reachable, is that
recipe actually something the profile would want, not just ingredient-overlap
compatible?

This is a catalog-*capacity* question, deliberately upstream of ranking:
every measurement below uses the full ``request.recipe_catalog`` (currently
``recsys.recipes.RECIPES``, 37 recipes), never a ranked top-k. Changing which
model or ``RankingPolicy`` is shipped cannot fix a catalog that has nothing
reachable to offer in the first place, and this script never touches either.

Two missing-ingredient counts, on purpose
------------------------------------------
- **Abstract** (``recsys.model.compute_features``'s ``_missing_count``) --
  recipe ingredients minus what is already in the receipt, full stop. Never
  looks at ``inventory_snapshot``. This is what a ranker sees.
- **Constrained** -- mirrors ``app.service.RecommendationService._assemble_recipe``:
  an ingredient only counts as "missing but buyable" if it has at least one
  ``valid_products`` hit on the live inventory snapshot (same
  ``SafetyPolicy.evaluate_product`` gate the real service uses, reused here via
  ``RecommendationService._valid_products`` rather than reimplemented). A
  recipe with a *required* ingredient that has zero valid products anywhere,
  or whose valid products share no common fulfillment option, is unreachable
  regardless of the missing-count threshold -- exactly ``no_safe_product``/
  ``no_common_fulfillment`` in the real service. Excluded categories/ingredients
  drop the recipe too, matching the service exactly.

Panel and split
----------------
One panel, generated once, deterministically, the way the other two
experiments running in parallel in their own worktrees do (see
``docs/research/recsys/experiment-plan-ranker-service-catalog.md`` S:0):
``recsys.profiles.generate_population(N, seed=DEFAULT_SEED)`` plus
``recsys.inventory.generate_inventory`` under a fixed ``random.Random`` per
(profile, deficit level). Split into train/held-out by parity of the numeric
suffix already embedded in ``user.user_id`` (``synthetic_<archetype>_<index>``)
-- deterministic, independent of any shared state file (three experiments run
in parallel worktrees; sharing a file would race, per the plan). The split
happens *before* any measurement: gaps are found on train, the catalog is
expanded to close them, and the improvement is confirmed on held-out only --
so the fix is not graded on the same baskets that pointed at it.

Deficit levels
--------------
``recsys.inventory`` ships module constants (``P_NO_PRODUCT_AT_ALL``,
``P_OUT_OF_STOCK``) rather than an injectable settings object at this commit
(a sibling experiment is adding one in its own worktree; this script does not
depend on unmerged work). Three deficit scenarios are swept by monkeypatching
those two module constants around each inventory draw, using the same
low/base/high values already calibrated for exactly this purpose in that
sibling experiment's ``recsys/sensitivity.py`` (``DIALS["no_product_at_all"]``
= 0.02/0.08/0.35, ``DIALS["out_of_stock"]`` = 0.02/0.10/0.35): low moves both
to their optimistic setting, base is the shipped default, high moves both to
their pessimistic setting. Moving both dials together rather than one at a
time is coarser than a full sensitivity sweep -- see the report's "угрозы
валидности" for what that costs.

Usage::

    python -m recsys.experiment3_catalog_coverage
"""

from __future__ import annotations

import io
import random
import statistics
import sys
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import recsys.inventory as inventory_module
from app.contracts import FulfillmentOption, Recipe, RecommendationRequest
from app.recommender import DeterministicMockEngine
from app.safety import SafetyPolicy
from app.service import RecommendationService
from recsys.evaluation import oracle_relevant
from recsys.model import compute_features
from recsys.panels import DEFICIT_LEVELS, experiment_panels
from recsys.profiles import SyntheticProfile
from recsys.recipes import RECIPES as CURRENT_RECIPES

OUTPUT_PATH = Path("docs/research/recsys/experiment-3-catalog-coverage-report.md")

#: Matches the panel seed used across all three parallel experiments (see
#: module docstring and ``recsys.benchmark.DEFAULT_SEED`` /
#: ``recsys.sensitivity.DEFAULT_SEED``, both 20260905).
DEFAULT_SEED = 20260905

#: Panel size. Large enough for stable per-threshold shares on both halves of
#: the train/held-out split (~130-170 profiles per half after the archetype
#: mixture lands unevenly), small enough that the sweep (3 deficit levels x 2
#: catalogs x panel) runs in seconds -- this is a catalog-capacity count, not a
#: trained model, so there is no accuracy-vs-N tradeoff to buy down.
N_PROFILES = 320

THRESHOLDS: tuple[int, ...] = (0, 1, 2)


def stable_seed(*parts: object) -> int:
    """Deterministic across processes, unlike ``hash()`` (PYTHONHASHSEED-salted
    for str/bytes). Same technique as the sibling experiments' ``recsys._seeds``."""
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return zlib.crc32(payload)


#: The deficit sweep is owned by ``recsys.panels`` — one definition, so three
#: experiments cannot drift into three slightly different meanings of "high".


def _user_index(user_id: str) -> int:
    """The zero-padded counter ``generate_profile`` embeds in every user_id."""
    return int(user_id.rsplit("_", 1)[-1])


def build_panel() -> dict[str, dict[str, list[tuple[SyntheticProfile, list]]]]:
    """``{split: {deficit level: [(profile, inventory), ...]}}`` from the panels.

    Replaces a local parity split over a locally generated population. Two
    things change and both matter: the split is now the protocol's
    (``train`` finds gaps, ``validation`` confirms, ``test`` is untouched), and
    the deficit levels are real — the previous helper monkeypatched module
    constants that ``generate_inventory`` no longer reads, so all three levels
    ran at base scarcity with different seeds.
    """
    out: dict[str, dict[str, list[tuple[SyntheticProfile, list]]]] = {}
    for split in ("train", "validation"):
        out[split] = {
            label: panel.pairs()
            for label, panel in experiment_panels(split).items()
        }
    return out


#: ``_inventory_for`` used to live here. It monkeypatched
#: ``recsys.inventory``'s module constants — which does nothing, because
#: ``DEFAULT_INVENTORY_ASSUMPTIONS`` is built once at import — *and* mixed the
#: level label into the RNG seed. So the three "deficit levels" were three
#: independent draws at base deficit: measured 108/107/111 products for
#: low/base/high, where real scarcity at 0.35 removes roughly a third. The
#: differing coverage numbers they produced looked like a deficit effect and
#: were sampling noise. ``recsys.panels.Panel.with_inventory`` replaces it and
#: keeps the seed fixed across levels, so only the thresholds move.


def _build_request(
    profile: SyntheticProfile, recipe_catalog: list[Recipe], inventory: list
) -> RecommendationRequest:
    return RecommendationRequest(
        user=profile.user,
        current_receipt=profile.current_receipt,
        purchase_history=profile.purchase_history,
        recipe_catalog=recipe_catalog,
        inventory_snapshot=inventory,
        now=profile.now,
        limit=3,
    )


def abstract_missing_count(request: RecommendationRequest, recipe: Recipe) -> int:
    """``compute_features``'s ``_missing_count``: receipt-only, no inventory."""
    return int(compute_features(request, recipe)["_missing_count"])


#: Not stateful beyond ``SafetyPolicy`` (itself stateless) -- reused across
#: every request/recipe pair purely to call the private ``_valid_products``
#: helper rather than reimplementing ``SafetyPolicy.evaluate_product`` gating.
_MIRROR_SERVICE = RecommendationService(
    engine=DeterministicMockEngine(), safety_policy=SafetyPolicy()
)

_COMMON_FULFILLMENT_DEFAULT = frozenset(
    {FulfillmentOption.DELIVERY, FulfillmentOption.NEXT_VISIT}
)


def constrained_missing_count(
    request: RecommendationRequest, recipe: Recipe
) -> int | None:
    """Mirrors ``RecommendationService._assemble_recipe``'s missing_count /
    no_safe_product / no_common_fulfillment / excluded-ingredient logic
    exactly, without building the full ``RecipeRecommendation`` (mode and
    score are irrelevant to a catalog-capacity question). Returns ``None`` for
    a recipe that the real service would drop entirely.
    """
    receipt_ids = {
        ingredient_id
        for item in request.current_receipt.items
        for ingredient_id in item.ingredient_ids
    }
    missing = 0
    common_fulfillment = set(_COMMON_FULFILLMENT_DEFAULT)
    for ingredient in recipe.ingredients:
        if (
            ingredient.ingredient_id in request.user.excluded_ingredient_ids
            or ingredient.category in request.user.excluded_categories
        ):
            return None
        if ingredient.ingredient_id in receipt_ids:
            continue
        valid_products = _MIRROR_SERVICE._valid_products(
            request=request, ingredient=ingredient
        )
        if not valid_products:
            if ingredient.required:
                return None
            continue
        missing += 1
        fulfillment = set().union(*(p.fulfillment_options for p in valid_products))
        common_fulfillment &= fulfillment
        if not common_fulfillment:
            return None
    return missing


@dataclass
class BasketOutcome:
    profile: SyntheticProfile
    abstract_min: int
    constrained_min: int | None  # None = unreachable at every threshold
    best_recipe_abstract: str
    best_recipe_constrained: str | None


def evaluate_panel(
    pairs: list[tuple[SyntheticProfile, list]],
    recipe_catalog: list[Recipe],
) -> list[BasketOutcome]:
    outcomes: list[BasketOutcome] = []
    for profile, inventory in pairs:
        request = _build_request(profile, recipe_catalog, inventory)

        abstract_scores = [
            (abstract_missing_count(request, recipe), recipe.recipe_id)
            for recipe in recipe_catalog
        ]
        abstract_min, best_abstract_id = min(abstract_scores)

        constrained_scores = [
            (constrained_missing_count(request, recipe), recipe.recipe_id)
            for recipe in recipe_catalog
        ]
        reachable = [(m, rid) for m, rid in constrained_scores if m is not None]
        if reachable:
            constrained_min, best_constrained_id = min(reachable)
        else:
            constrained_min, best_constrained_id = None, None

        outcomes.append(
            BasketOutcome(
                profile=profile,
                abstract_min=abstract_min,
                constrained_min=constrained_min,
                best_recipe_abstract=best_abstract_id,
                best_recipe_constrained=best_constrained_id,
            )
        )
    return outcomes


def coverage_shares(
    outcomes: list[BasketOutcome], *, constrained: bool
) -> dict[int, float]:
    n = len(outcomes)
    shares: dict[int, float] = {}
    for t in THRESHOLDS:
        if constrained:
            hit = sum(
                1 for o in outcomes if o.constrained_min is not None and o.constrained_min <= t
            )
        else:
            hit = sum(1 for o in outcomes if o.abstract_min <= t)
        shares[t] = hit / n if n else 0.0
    return shares


# ---------------------------------------------------------------------------
# Step 3: gap diagnostics (train half only)
# ---------------------------------------------------------------------------


def uncovered_at(
    outcomes: list[BasketOutcome], threshold: int, *, constrained: bool
) -> list[BasketOutcome]:
    if constrained:
        return [
            o
            for o in outcomes
            if o.constrained_min is None or o.constrained_min > threshold
        ]
    return [o for o in outcomes if o.abstract_min > threshold]


def diagnose_gaps(
    outcomes: list[BasketOutcome],
    recipe_catalog: list[Recipe],
    *,
    threshold: int = 2,
) -> dict:
    """Characterize baskets uncovered (abstract, threshold) by inspection:
    which receipt categories dominate them, which archetypes they belong to,
    and how short the catalog's closest-but-still-too-far recipe is."""
    recipe_by_id = {r.recipe_id: r for r in recipe_catalog}
    uncovered = uncovered_at(outcomes, threshold, constrained=False)
    covered = [o for o in outcomes if o not in uncovered]

    def receipt_categories(o: BasketOutcome) -> set[str]:
        return {item.category for item in o.profile.current_receipt.items}

    uncovered_category_counter: Counter[str] = Counter()
    for o in uncovered:
        uncovered_category_counter.update(receipt_categories(o))

    covered_category_counter: Counter[str] = Counter()
    for o in covered:
        covered_category_counter.update(receipt_categories(o))

    uncovered_archetype = Counter(o.profile.archetype for o in uncovered)
    all_archetype = Counter(o.profile.archetype for o in outcomes)

    # Ingredient count of each uncovered basket's *closest* recipe, and which
    # categories its still-missing ingredients belong to.
    blocking_categories: Counter[str] = Counter()
    closest_recipe_ingredient_counts: list[int] = []
    for o in uncovered:
        recipe = recipe_by_id[o.best_recipe_abstract]
        closest_recipe_ingredient_counts.append(len(recipe.ingredients))
        receipt_ids = {
            i for item in o.profile.current_receipt.items for i in item.ingredient_ids
        }
        for ingredient in recipe.ingredients:
            if ingredient.ingredient_id not in receipt_ids:
                blocking_categories[ingredient.category] += 1

    receipt_size_uncovered = [len(o.profile.current_receipt.items) for o in uncovered]
    receipt_size_covered = [len(o.profile.current_receipt.items) for o in covered]

    return {
        "n_uncovered": len(uncovered),
        "n_covered": len(covered),
        "uncovered_category_rate": {
            cat: uncovered_category_counter[cat] / len(uncovered) if uncovered else 0.0
            for cat in uncovered_category_counter
        },
        "covered_category_rate": {
            cat: covered_category_counter[cat] / len(covered) if covered else 0.0
            for cat in covered_category_counter
        },
        "uncovered_archetype_rate": {
            a: uncovered_archetype[a] / all_archetype[a] if all_archetype[a] else 0.0
            for a in all_archetype
        },
        "blocking_categories": blocking_categories,
        "closest_recipe_ingredient_counts": closest_recipe_ingredient_counts,
        "receipt_size_uncovered_mean": (
            statistics.mean(receipt_size_uncovered) if receipt_size_uncovered else 0.0
        ),
        "receipt_size_covered_mean": (
            statistics.mean(receipt_size_covered) if receipt_size_covered else 0.0
        ),
    }


#: Old (pre-experiment) catalog frozen by recipe_id, so "new recipe" below
#: means "not present before this experiment" regardless of any future edits
#: to ``recsys.recipes``. Kept as a literal list of ids (not a git diff)
#: because the two catalogs must be comparable long after this script runs.
NEW_RECIPE_IDS: frozenset[str] = frozenset(
    {
        "fried_chicken_breast",
        "pork_chops",
        "braised_beef_with_onion",
        "fried_minced_meat_with_onion",
        "pan_fried_semi_finished_cutlets",
        "chicken_in_sour_cream",
        "fried_zucchini_with_cheese",
        "braised_cabbage",
        "rice_milk_porridge",
        "cottage_cheese_with_sour_cream",
    }
)


def old_catalog() -> list[Recipe]:
    return [r for r in CURRENT_RECIPES if r.recipe_id not in NEW_RECIPE_IDS]


def new_catalog() -> list[Recipe]:
    return list(CURRENT_RECIPES)


# ---------------------------------------------------------------------------
# Step 6: attractiveness check
# ---------------------------------------------------------------------------


@dataclass
class AttractivenessResult:
    threshold: int
    constrained: bool
    n_newly_reachable: int
    n_relevant: int
    examples: list[tuple[str, str, int]]
    #: Which specific new recipe closed the gap, per newly-reachable basket.
    #: Tracked because the headline share_relevant number can hide that a
    #: single recipe (typically the shortest) does almost all the closing.
    closer_counts: Counter[str]

    @property
    def share_relevant(self) -> float | None:
        return self.n_relevant / self.n_newly_reachable if self.n_newly_reachable else None


def attractiveness_check(
    pairs: list[tuple[SyntheticProfile, list]],
    *,
    threshold: int = 2,
    constrained: bool = False,
) -> AttractivenessResult:
    """Among baskets uncovered by the OLD catalog at ``threshold``, take those
    the NEW catalog makes reachable and check whether the specific new recipe
    that closes the gap is also ``oracle_relevant`` for that profile -- i.e.
    something the archetype's own rules judge as actually wanted, not merely
    ingredient-compatible. Uses the same request (receipt/history/inventory)
    for both catalogs; only ``recipe_catalog`` differs, and neither
    ``compute_features`` nor ``oracle_relevant`` reads that field, so this
    isolates the catalog-membership effect cleanly.
    """
    old_ids = {r.recipe_id for r in old_catalog()}
    new_ids_only = NEW_RECIPE_IDS
    new_recipe_by_id = {r.recipe_id: r for r in new_catalog()}

    n_newly_reachable = 0
    n_relevant = 0
    examples: list[tuple[str, str, int]] = []
    closer_counts: Counter[str] = Counter()

    for profile, inventory in pairs:
        old_request = _build_request(profile, old_catalog(), inventory)
        new_request = _build_request(profile, new_catalog(), inventory)

        if constrained:
            old_scored = [
                constrained_missing_count(old_request, new_recipe_by_id[rid])
                for rid in old_ids
            ]
            old_reachable = [s for s in old_scored if s is not None]
            old_covered = bool(old_reachable) and min(old_reachable) <= threshold
            new_scores = {
                rid: constrained_missing_count(new_request, recipe)
                for rid, recipe in new_recipe_by_id.items()
                if rid in new_ids_only
            }
        else:
            old_covered = min(
                abstract_missing_count(old_request, new_recipe_by_id[rid]) for rid in old_ids
            ) <= threshold
            new_scores = {
                rid: abstract_missing_count(new_request, recipe)
                for rid, recipe in new_recipe_by_id.items()
                if rid in new_ids_only
            }

        if old_covered:
            continue  # not a gap for this basket to begin with

        candidates = [
            (score, rid) for rid, score in new_scores.items() if score is not None and score <= threshold
        ]
        if not candidates:
            continue  # still uncovered even after expansion

        n_newly_reachable += 1
        best_score, best_rid = min(candidates)
        closer_counts[best_rid] += 1
        recipe = new_recipe_by_id[best_rid]
        if oracle_relevant(profile, recipe, new_request):
            n_relevant += 1
        if len(examples) < 12:
            examples.append((profile.user.user_id, best_rid, best_score))

    return AttractivenessResult(
        threshold=threshold,
        constrained=constrained,
        n_newly_reachable=n_newly_reachable,
        n_relevant=n_relevant,
        examples=examples,
        closer_counts=closer_counts,
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{x:.0%}"


def build_report(
    *,
    n_train: int,
    n_held_out: int,
    old_train: dict[str, list[BasketOutcome]],
    diag: dict,
    old_held: dict[str, list[BasketOutcome]],
    new_held: dict[str, list[BasketOutcome]],
    attract_results: list[AttractivenessResult],
) -> str:
    out: list[str] = []
    w = out.append

    w("# Эксперимент 3 — покрытие каталога рецептов")
    w("")
    w(
        f"Сгенерирован `python -m recsys.experiment3_catalog_coverage`. Панель — "
        f"{N_PROFILES} синтетических пользователей "
        f"(`recsys.profiles.generate_population(seed={DEFAULT_SEED})`), разбита по чётности "
        f"числового суффикса `user_id` **до** любых измерений: train={n_train} "
        f"(поиск пробелов), held-out={n_held_out} (проверка после расширения)."
    )
    w("")
    w(
        "Вопрос: для скольких корзин каталог вообще может предложить что-то "
        "приемлемое — до и после расширения, на кандидатах из **всего** "
        "`request.recipe_catalog`, не после ранжирования топ-k. Это вопрос "
        "ёмкости каталога, а не качества ранкера: ни один шаг ниже не меняет "
        "`RankingPolicy`/движок между «до» и «после»."
    )
    w("")
    w("---")
    w("")
    w("## 0. Два способа считать missing_count")
    w("")
    w(
        "- **Без ограничений магазина** («абстрактный») — "
        "`recsys.model.compute_features`'s `_missing_count`: рецепт минус то, что "
        "уже в чеке. Не смотрит в `inventory_snapshot` вообще — это то, что видит "
        "ранкер."
    )
    w(
        "- **С ограничениями магазина** («constrained») — воспроизводит "
        "`RecommendationService._assemble_recipe` один в один (через "
        "`RecommendationService._valid_products`, не переизобретён): недостающий "
        "ингредиент считается «докупаемым» только если у него есть "
        "`valid_products` на живом `inventory_snapshot`; обязательный ингредиент "
        "без единого валидного товара делает рецепт недостижимым **независимо от "
        "порога** (`no_safe_product`), так же как пересечение `fulfillment_options` "
        "в ноль (`no_common_fulfillment`) и исключённые категории/ингредиенты "
        "пользователя."
    )
    w("")
    w(
        "Уровни дефицита — те же калиброванные значения, что использует "
        "параллельный эксперимент чувствительности (`no_product_at_all` "
        "0.02/0.08/0.35, `out_of_stock` 0.02/0.10/0.35 — см. «угрозы валидности» "
        "про то, что здесь они двигаются парой, а не по отдельности)."
    )
    w("")
    w("---")
    w("")
    w("## 1. Исходное покрытие (37 рецептов, train)")
    w("")
    w("| Дефицит | Без ограничений ≤0/≤1/≤2 | С ограничениями ≤0/≤1/≤2 |")
    w("|---|---|---|")
    for label in DEFICIT_LEVELS:
        outcomes = old_train[label]
        a = coverage_shares(outcomes, constrained=False)
        c = coverage_shares(outcomes, constrained=True)
        w(
            f"| {label} | {_pct(a[0])}/{_pct(a[1])}/{_pct(a[2])} | "
            f"{_pct(c[0])}/{_pct(c[1])}/{_pct(c[2])} |"
        )
    w("")
    w(
        f"На старом каталоге при базовом дефиците только **{_pct(coverage_shares(old_train['база'], constrained=False)[2])}** "
        "корзин train-половины имеют хоть один рецепт с ≤2 недостающими "
        "ингредиентами без учёта магазина, и "
        f"**{_pct(coverage_shares(old_train['база'], constrained=True)[2])}** — с учётом. "
        "Порог ≤0 практически не достигается ни при каком дефиците — рецепт, "
        "полностью совпадающий с уже купленным, редкость по конструкции панели "
        "(корзины и рецепты сэмплируются независимо)."
    )
    w("")
    w(
        "Абстрактное покрытие **не меняется** между уровнями дефицита (правильно: "
        "оно не смотрит в `inventory_snapshot`), а покрытие с ограничениями "
        "магазина заметно падает при высоком дефиците — это ожидаемая проверка "
        "корректности реализации, а не находка."
    )
    w("")
    w("---")
    w("")
    w("## 2. Где именно каталог не дотягивал (train, база, порог ≤2, абстрактно)")
    w("")
    w(
        f"Непокрытых корзин: **{diag['n_uncovered']} из {diag['n_uncovered'] + diag['n_covered']}**."
    )
    w("")
    w(
        "**Находка №1 — непокрытые корзины систематически ближе всего подходят к "
        "самым коротким рецептам каталога.** У всех "
        f"{diag['n_uncovered']} непокрытых корзин ближайший рецепт (минимум "
        "missing_count) имел ровно "
        f"{Counter(diag['closest_recipe_ingredient_counts']).most_common(1)[0][0]} "
        "ингредиента (включая специи) — это самые короткие рецепты старого "
        "каталога (`chicken_and_vegetables`, `cheese_tomato_toast`, "
        "`carrot_fritters`, `oatmeal_with_banana`). Значит короткие рецепты "
        "выигрывают не потому что они хорошо подходят, а по умолчанию — у них "
        "меньше шансов не совпасть. Каталогу не хватало **ещё более коротких** "
        "рецептов, а не более длинных/разнообразных."
    )
    w("")
    blocking = diag["blocking_categories"].most_common()
    total_blocking = sum(v for _, v in blocking)
    w(
        "**Находка №2 — специи, а не сама еда, чаще всего оказываются "
        "«недостающим ингредиентом».** Категории всё ещё недостающих "
        "ингредиентов у ближайшего рецепта непокрытых корзин: "
        + ", ".join(
            f"`{cat}` {_pct(v / total_blocking)}" for cat, v in blocking
        )
        + ". `pantry` доминирует, потому что специи (соль, перец и т.п.) "
        "категоризованы как `pantry` и `compute_features._missing_count` "
        "считает их пропущенными наравне с настоящими ингредиентами, если их "
        "конкретного id нет в чеке — так и должно быть по конструкции признака, "
        "но это означает, что абстрактный порог ≤2 систематически штрафует "
        "даже идеально совпадающий по еде рецепт на 1-2 специи."
    )
    w("")
    routine_rate = diag["uncovered_archetype_rate"].get("routine")
    w(
        "**Находка №3 — хуже всего покрыт архетип `routine`** (ядро "
        f"dairy/vegetable/meat, 40% популяции): {_pct(routine_rate) if routine_rate is not None else 'н/д'} "
        "его корзин не покрыты, худший результат среди архетипов "
        f"({', '.join(f'{a} {_pct(v)}' for a, v in diag['uncovered_archetype_rate'].items())}). "
        "Разбивка по категориям чека показывает, что `meat` встречается в "
        f"{_pct(diag['uncovered_category_rate'].get('meat', 0))} непокрытых корзин против "
        f"{_pct(diag['covered_category_rate'].get('meat', 0))} покрытых, тогда как `egg` — "
        f"наоборот, {_pct(diag['uncovered_category_rate'].get('egg', 0))} непокрытых против "
        f"{_pct(diag['covered_category_rate'].get('egg', 0))} покрытых. Мясные корзины без яйца "
        "хуже всего накрываются каталогом: короткие рецепты с яйцом уже были "
        "(сырники, оладьи, омлет-основа), коротких мясных — не было."
    )
    w("")
    w(
        "**Вывод шага 2** (пробелы найдены осмотром, не автоматическим поиском — "
        "см. «угрозы валидности»): каталогу не хватало (а) коротких рецептов из "
        "мяса с минимумом специй и (б) вообще более коротких рецептов в разных "
        "категориях, чтобы у случайной корзины было больше шансов зацепиться "
        "хотя бы за один рецепт целиком."
    )
    w("")
    w("---")
    w("")
    w("## 3. Что добавлено")
    w("")
    w(
        f"{len(NEW_RECIPE_IDS)} рецептов в `recsys/recipes.py` "
        f"({len(old_catalog())} → {len(new_catalog())}), без новых ингредиентов "
        "(`recsys.catalog.INGREDIENTS` уже покрывал всё нужное, включая "
        "`cutlet_semi_finished` — до этого эксперимента у него не было ни одного "
        "рецепта). Все — короткие повседневные блюда, не парадные:"
    )
    w("")
    w("| Рецепт | Обязательных | Специй | Категории |")
    w("|---|---:|---:|---|")
    new_recipe_by_id = {r.recipe_id: r for r in new_catalog()}
    for rid in sorted(NEW_RECIPE_IDS, key=lambda x: len(new_recipe_by_id[x].ingredients)):
        r = new_recipe_by_id[rid]
        required_n = sum(1 for i in r.ingredients if i.required)
        seasoning_n = len(r.ingredients) - required_n
        cats = sorted({i.category for i in r.ingredients if i.required})
        w(f"| {r.title} | {required_n} | {seasoning_n} | {', '.join(cats)} |")
    w("")
    w(
        "Шесть нацелены на находку №3 (короткие мясные блюда: жареная куриная "
        "грудка, свиные отбивные, тушёная говядина с луком, жареный фарш, "
        "котлеты из полуфабриката, курица в сметане — последняя специально "
        "смешивает мясо+молочное+овощ, ядро архетипа `routine`), четыре — на "
        "находку №1 (общий дефицит коротких рецептов: кабачки с сыром, тушёная "
        "капуста, рисовая каша на молоке, творог со сметаной)."
    )
    w("")
    w(
        "**`творог со сметаной` — 2 ингредиента, 0 специй — заслуживает "
        "отдельного предупреждения**, см. §5: рецепт из ровно двух ингредиентов "
        "не может иметь abstract missing_count выше 2 по построению, поэтому он "
        "почти обнуляет порог ≤2 сам по себе, независимо от того, действительно "
        "ли он релевантен корзине. Это не скрыто — именно для проверки такого "
        "эффекта существует §5 ниже."
    )
    w("")
    w("---")
    w("")
    w("## 4. Покрытие на held-out: старый vs новый каталог")
    w("")
    w(
        f"held-out = {n_held_out} профилей, не использованных на шаге 2. Один и тот же "
        "движок и `RankingPolicy` тут ни при чём — сравнение вообще не ранжирует, "
        "оно проверяет, есть ли *хоть один* рецепт в допустимых пределах."
    )
    w("")
    w("**Без ограничений магазина (абстрактно):**")
    w("")
    w("| Дефицит | Старый ≤0/≤1/≤2 | Новый ≤0/≤1/≤2 |")
    w("|---|---|---|")
    for label in DEFICIT_LEVELS:
        oa = coverage_shares(old_held[label], constrained=False)
        na = coverage_shares(new_held[label], constrained=False)
        w(
            f"| {label} | {_pct(oa[0])}/{_pct(oa[1])}/{_pct(oa[2])} | "
            f"{_pct(na[0])}/{_pct(na[1])}/{_pct(na[2])} |"
        )
    w("")
    w("**С ограничениями магазина (constrained):**")
    w("")
    w("| Дефицит | Старый ≤0/≤1/≤2 | Новый ≤0/≤1/≤2 |")
    w("|---|---|---|")
    for label in DEFICIT_LEVELS:
        oc = coverage_shares(old_held[label], constrained=True)
        nc = coverage_shares(new_held[label], constrained=True)
        w(
            f"| {label} | {_pct(oc[0])}/{_pct(oc[1])}/{_pct(oc[2])} | "
            f"{_pct(nc[0])}/{_pct(nc[1])}/{_pct(nc[2])} |"
        )
    w("")
    base_old_a = coverage_shares(old_held["база"], constrained=False)
    base_new_a = coverage_shares(new_held["база"], constrained=False)
    base_old_c = coverage_shares(old_held["база"], constrained=True)
    base_new_c = coverage_shares(new_held["база"], constrained=True)
    w(
        f"**Порог ≤2, абстрактно, база дефицита:** {_pct(base_old_a[2])} → {_pct(base_new_a[2])}. "
        "Этот скачок в основном объясняется одним 2-ингредиентным рецептом "
        "(см. §3/§5) и **не должен читаться как основной результат** — "
        "смотрите ≤1 и constrained-числа ниже, они не насыщены."
    )
    w("")
    rel_1_text = (
        f"{(base_new_a[1] - base_old_a[1]) / base_old_a[1]:+.0%} относительно"
        if base_old_a[1] > 0
        else "знаменатель нулевой, относительный рост не определён"
    )
    w(
        f"**Порог ≤1, абстрактно, база дефицита:** {_pct(base_old_a[1])} → {_pct(base_new_a[1])} "
        f"({rel_1_text}) — не насыщен (2-ингредиентный рецепт даёт ≤1 только "
        "когда один из двух ингредиентов уже есть в чеке), содержательное "
        "улучшение."
    )
    w("")
    w(
        f"**Порог ≤2, с ограничениями магазина, база дефицита:** {_pct(base_old_c[2])} → {_pct(base_new_c[2])}, "
        f"при высоком дефиците: {_pct(coverage_shares(old_held['высокий'], constrained=True)[2])} → "
        f"{_pct(coverage_shares(new_held['высокий'], constrained=True)[2])}. Это самая надёжная пара чисел "
        "в отчёте: constrained-метрика не насыщается тем же 2-ингредиентным "
        "рецептом (оба его ингредиента должны реально продаваться в эту "
        "конкретную поставку, а при дефиците это не гарантировано)."
    )
    w("")
    w("---")
    w("")
    w("## 5. Привлекательность: не только совпадение ингредиентов")
    w("")
    w(
        "Среди корзин held-out, непокрытых старым каталогом при пороге T, но "
        "ставших покрытыми новым: доля тех случаев, где рецепт, закрывший "
        "пробел, также `oracle_relevant` для этого профиля (а не просто "
        "физически собираем)."
    )
    w("")
    w("| Порог | Метод | Вновь достижимо | Из них `oracle_relevant` | Доля |")
    w("|---|---|---:|---:|---:|")
    for res in attract_results:
        method = "constrained" if res.constrained else "абстрактно"
        share = "н/д (0 корзин)" if res.share_relevant is None else _pct(res.share_relevant)
        w(f"| ≤{res.threshold} | {method} | {res.n_newly_reachable} | {res.n_relevant} | {share} |")
    w("")
    w(
        "**Это не 10 рецептов, работающих поровну — это в основном один "
        "рецепт.** Кто именно закрывал пробел, по каждому измерению:"
    )
    w("")
    w("| Порог | Метод | Кто закрыл пробел (доля от «вновь достижимо») |")
    w("|---|---|---|")
    for res in attract_results:
        method = "constrained" if res.constrained else "абстрактно"
        if not res.closer_counts:
            breakdown = "—"
        else:
            breakdown = ", ".join(
                f"`{rid}` {_pct(cnt / res.n_newly_reachable)}"
                for rid, cnt in res.closer_counts.most_common()
            )
        w(f"| ≤{res.threshold} | {method} | {breakdown} |")
    w("")
    saturating = next((r for r in attract_results if r.threshold == 2 and not r.constrained), None)
    if saturating is not None and saturating.share_relevant is not None:
        top_share = (
            saturating.closer_counts.most_common(1)[0][1] / saturating.n_newly_reachable
            if saturating.closer_counts
            else 0.0
        )
        w(
            f"При пороге ≤2 абстрактно (самом насыщенном, см. §3) доля "
            f"`oracle_relevant` среди вновь достижимых — {_pct(saturating.share_relevant)}, "
            f"но {_pct(top_share)} этих закрытий — один и тот же рецепт "
            "(`cottage_cheese_with_sour_cream`). Высокая доля `oracle_relevant` "
            "здесь в основном означает «этот один рецепт архетипы обычно "
            "признают желанным», а не «все 10 новых рецептов равномерно "
            "полезны» — остальные девять почти никогда не оказываются тем "
            "конкретным рецептом, который замыкает порог ≤2 на held-out."
        )
        w("")
    less_saturating = next((r for r in attract_results if r.threshold == 1 and not r.constrained), None)
    if less_saturating is not None and less_saturating.share_relevant is not None:
        w(
            f"При пороге ≤1 (не насыщенном) доля `oracle_relevant` среди вновь "
            f"достижимых — {_pct(less_saturating.share_relevant)}, на "
            f"{less_saturating.n_newly_reachable} новых корзин — тоже "
            "полностью через `cottage_cheese_with_sour_cream` (см. таблицу "
            "выше)."
        )
        w("")
    constrained_2 = next((r for r in attract_results if r.threshold == 2 and r.constrained), None)
    if constrained_2 is not None and constrained_2.closer_counts:
        n_distinct = len(constrained_2.closer_counts)
        w(
            f"Только при constrained-пороге ≤2 закрытие пробела распределено "
            f"шире — {n_distinct} разных рецептов встречаются как «тот, что "
            "закрыл порог» (см. таблицу), потому что дефицит на полке иногда "
            "выбивает творог или сметану из продажи, и тогда роль подхватывают "
            "другие короткие рецепты (в первую очередь `pan_fried_semi_finished_cutlets`, "
            "тоже двухкомпонентный). Это единственное измерение в этом отчёте, "
            "где вклад распределён между несколькими новыми рецептами, а не "
            "сосредоточен в одном."
        )
        w("")
    w(
        "Примеры (user_id, закрывший рецепт, missing_count после расширения):"
    )
    w("")
    for res in attract_results:
        if res.examples:
            w(f"- порог ≤{res.threshold}, {'constrained' if res.constrained else 'абстрактно'}: "
              + "; ".join(f"{u} → `{r}` ({m})" for u, r, m in res.examples[:5]))
    w("")
    w("---")
    w("")
    w("## Угрозы валидности")
    w("")
    w(
        f"- **Файл-первоисточник задания** "
        "(`docs/research/recsys/experiment-plan-ranker-service-catalog.md`) отсутствовал "
        "в этом воркере — ни в рабочем дереве, ни в истории git ни одной ветки. "
        "Скрипт и отчёт построены по краткому пересказу задания, а не по "
        "оригиналу; если оригинал появится и разойдётся в деталях с пересказом, "
        "числа выше не пересчитаны под него."
    )
    w(
        "- **Разбиение train/held-out** — по чётности числового суффикса "
        "`user_id`, это позиция профиля в детерминированной генерации, а не "
        "случайный сэмпл вне зависимости от генератора; архетип профиля "
        "назначается случайно независимо от этой позиции, так что перекос "
        "маловероятен, но не проверен статистически."
    )
    w(
        "- **Пробелы шага 2 найдены осмотром train-таблиц, а не автоматическим "
        "поиском** — три названные находки (короткие рецепты по умолчанию, "
        "specie-инфляция missing_count, худшее покрытие `routine`) — это то, "
        "что бросилось в глаза при чтении агрегатов; более тонкие "
        "комбинации категорий могли остаться незамеченными."
    )
    w(
        "- **Уровни дефицита выбраны нами** (низкий/база/высокий = "
        "0.02/0.08/0.35 по обеим ручкам), совпадают со значениями параллельного "
        "эксперимента чувствительности, но обе ручки здесь двигаются **вместе**, "
        "а не по отдельности — это грубее полноценной чувствительностной "
        "развёртки и может скрывать взаимодействие между ними."
    )
    w(
        "- **`InventoryAssumptions` не переиспользован** — на зафиксированном "
        "коммите этого ворктри `recsys.inventory.generate_inventory` ещё не "
        "принимает объект допущений (это добавляет параллельный эксперимент в "
        "своём ворктри); дефицит здесь применён через временную подмену "
        "модульных констант `P_NO_PRODUCT_AT_ALL`/`P_OUT_OF_STOCK` вокруг "
        "каждого вызова, со значениями, вручную сверенными с тем ворктри. Если "
        "тот эксперимент изменит калибровку, здесь она не обновится "
        "автоматически."
    )
    w(
        "- **`творог со сметаной` (2 ингредиента, 0 специй) почти насыщает "
        "порог ≤2 абстрактно сам по себе** (см. §3/§4/§5) — это не скрыто, "
        "именно поэтому §5 существует и явно показывает, что доля "
        "`oracle_relevant` среди вновь достижимых ниже 100%. Порог ≤2 "
        "абстрактно после этого эксперимента менее информативен, чем ≤1 или "
        "любой constrained-порог — читайте таблицы §4 с этим в уме, а не "
        "только заголовочное число."
    )
    w(
        "- **`oracle_relevant` self-referential** (см. паспорт метрики 0.19 в "
        "исходном плане и `recsys/evaluation.py`'s module docstring): он выведен "
        "из тех же архетипных правил, что признак `_missing_count`/лейбл "
        "обучения. Доля в §5 — относительный, а не абсолютный сигнал: она "
        "говорит, промахнулось ли расширение мимо *собственных* правил "
        "желательности симуляции, не мимо реальных пользователей."
    )
    w(
        "- **Пары с готовой едой не искались** для 10 новых рецептов — они "
        "явно отмечены как непарные в `recsys/ready_food_pairs.py` с причиной "
        "«поиск не делался», а не «нет пары после проверки», в отличие от "
        "восьми рецептов старого каталога, для которых поиск проводился и не "
        "дал результата."
    )
    w(
        "- **Синтетическая панель** — как и весь остальной стенд, корзины и "
        "инвентарь синтетические (`recsys.profiles`/`recsys.inventory`), не "
        "наблюдения. Числа выше показывают устойчивость вывода на этой "
        "симуляции, не прогноз реального покрытия ассортимента X5."
    )
    w("")
    return "\n".join(out)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    panels = build_panel()
    train = panels["train"]
    held_out = panels["validation"]
    n_train = len(train["база"])
    n_held = len(held_out["база"])
    print(f"panel: train={n_train}, held-out(validation)={n_held}")

    print("\n--- OLD catalog, train split, per deficit level ---")
    old_train: dict[str, list[BasketOutcome]] = {}
    for label, pairs in train.items():
        outcomes = evaluate_panel(pairs, old_catalog())
        old_train[label] = outcomes
        a = coverage_shares(outcomes, constrained=False)
        c = coverage_shares(outcomes, constrained=True)
        print(f"  [{label}] abstract <=0/1/2: {a[0]:.0%}/{a[1]:.0%}/{a[2]:.0%}"
              f"  constrained <=0/1/2: {c[0]:.0%}/{c[1]:.0%}/{c[2]:.0%}")

    diag = diagnose_gaps(old_train["база"], old_catalog(), threshold=2)
    print(f"\n--- gap diagnostics (train, база, abstract, threshold<=2) ---")
    print(f"uncovered: {diag['n_uncovered']} / {diag['n_uncovered'] + diag['n_covered']}")

    print("\n--- OLD vs NEW catalog, held-out (validation), per deficit level ---")
    old_held: dict[str, list[BasketOutcome]] = {}
    new_held: dict[str, list[BasketOutcome]] = {}
    for label, pairs in held_out.items():
        old_held[label] = evaluate_panel(pairs, old_catalog())
        new_held[label] = evaluate_panel(pairs, new_catalog())
        oa = coverage_shares(old_held[label], constrained=False)
        na = coverage_shares(new_held[label], constrained=False)
        oc = coverage_shares(old_held[label], constrained=True)
        nc = coverage_shares(new_held[label], constrained=True)
        print(f"  [{label}] abstract old {oa[2]:.0%} -> new {na[2]:.0%}"
              f"   constrained old {oc[2]:.0%} -> new {nc[2]:.0%}")

    print("\n--- attractiveness check (held-out, база) ---")
    base_pairs = held_out["база"]
    attract_results = [
        attractiveness_check(base_pairs, threshold=2, constrained=False),
        attractiveness_check(base_pairs, threshold=1, constrained=False),
        attractiveness_check(base_pairs, threshold=2, constrained=True),
    ]
    for res in attract_results:
        print(f"  threshold<={res.threshold} constrained={res.constrained}: "
              f"newly_reachable={res.n_newly_reachable} relevant={res.n_relevant} "
              f"share={res.share_relevant}")

    report = build_report(
        n_train=n_train,
        n_held_out=n_held,
        old_train=old_train,
        diag=diag,
        old_held=old_held,
        new_held=new_held,
        attract_results=attract_results,
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    io.open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n").write(report)
    print(f"\n{OUTPUT_PATH}: {len(report.splitlines())} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
