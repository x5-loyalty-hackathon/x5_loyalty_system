"""Which of our invented numbers would change the answer if we are wrong?

The bench in ``recsys.benchmark`` sweeps *behaviour* — how novelty-seeking or
price-sensitive people are. This module sweeps the other half: the supply and
cost constants we made up because we have no X5 data. ``P_MARKDOWN_OFFERED =
0.50`` says half of all rescue-category products have a markdown twin on the
shelf. Nobody measured that. Neither did anyone measure the out-of-stock rate,
the share of products within delivery radius, or what an hour of cooking is
worth to a shopper.

Sweeping them is not about getting better numbers — we cannot, not without the
retailer. It is about learning **which guesses matter**. A conclusion that
survives a dial moving from 0.10 to 0.90 does not depend on that dial, and the
team can stop arguing about it. A conclusion that flips is a question to take
to the case owner, and it deserves the meeting time.

So the output is deliberately not "conversion moves by X%". It is a table of
*claims* and whether each claim still holds at each setting:

    markdown_offered 0.10 -> best arm still heuristic/effort, bench still
    discriminates, ml still no better than noise under the shipped policy

Claims, not metrics, because a claim is what a person acts on.

Cost: one benchmark run per (dial, level). The defaults are deliberately
smaller than a headline run — this measures whether a conclusion is stable, not
its third decimal place.
"""

from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from app.recommender import DeterministicMockEngine
from app.service import EFFORT_FIRST, RELEVANCE_FIRST
from recsys.benchmark import (
    PRIMARY_METRIC,
    Arm,
    BenchmarkResult,
    RandomEngine,
    run_benchmark,
)
from recsys.inventory import DEFAULT_INVENTORY_ASSUMPTIONS, InventoryAssumptions
from recsys.profiles import ARCHETYPES, ArchetypeTable
from recsys.regimes import BALANCED_SAMPLE_9, Regime
from recsys.response_models import (
    EconomicResponder,
    ProbabilisticResponder,
    RuleBasedResponder,
)

OUTPUT_PATH = Path("docs/sensitivity-report.md")

#: Nine worlds, balanced across every dial — see
#: ``recsys.regimes.BALANCED_SAMPLE_9``. This used to be ``REGIMES[:9]``,
#: which alphabetical sorting made "the neutral world plus eight
#: novelty=high worlds", so the whole sweep ran in high-novelty territory.
DEFAULT_REGIMES = BALANCED_SAMPLE_9

#: Raised from 40 after a seed-stability check: at 30 users the *baseline*
#: claims flipped between seeds, so the sweep was measuring noise rather than
#: sensitivity. At 80 every claim except ``leader_is_clear`` repeats across
#: seeds. ``--stability`` re-runs that check.
DEFAULT_USERS = 80
DEFAULT_SEED = 20260905

#: A leader has to be ahead by this much, relatively, to count as ahead at all.
LEADER_MARGIN = 0.05


@dataclass(frozen=True)
class ToleranceShiftedRegime:
    """A regime with every archetype's missing-item tolerance moved.

    Duck-types ``Regime`` for ``run_benchmark``: it only ever asks for ``name``
    and ``archetypes()``. Tolerance lives on the archetype rather than in
    ``InventoryAssumptions``, so it cannot ride along with the other dials.
    """

    inner: Regime
    shift: int

    @property
    def name(self) -> str:
        return self.inner.name

    def archetypes(self) -> ArchetypeTable:
        return {
            key: replace(
                params, max_missing_tolerance=max(0, params.max_missing_tolerance + self.shift)
            )
            for key, params in self.inner.archetypes().items()
        }


@dataclass(frozen=True)
class Setting:
    """One point on one dial, and how to apply it to a run."""

    label: str
    assumptions: InventoryAssumptions = DEFAULT_INVENTORY_ASSUMPTIONS
    time_value_rub_per_hour: float | None = None
    tolerance_shift: int = 0


@dataclass(frozen=True)
class Dial:
    name: str
    question: str
    settings: tuple[Setting, ...]


def _assume(**kwargs) -> InventoryAssumptions:
    return replace(DEFAULT_INVENTORY_ASSUMPTIONS, **kwargs)


#: The dials, each with the value we shipped plus a pessimistic and an
#: optimistic reading. Ranges are wide on purpose: the point is to bracket the
#: truth, not to guess it. ``no_product_at_all`` is specifically an ingredient
#: assumption. Do not calibrate it from ``availability_reference.json``: that
#: file measures ready food, a separately replenished category.
DIALS: tuple[Dial, ...] = (
    Dial(
        name="markdown_offered",
        question="Какая доля товаров rescue-категорий реально имеет уценённый вариант?",
        settings=(
            Setting("0.10 (уценки почти нет)", _assume(markdown_offered=0.10)),
            Setting("0.50 (наше допущение)"),
            Setting("0.90 (уценка почти всегда)", _assume(markdown_offered=0.90)),
        ),
    ),
    Dial(
        name="no_product_at_all",
        question="Как часто нужного ингредиента нет в магазине вообще?",
        settings=(
            Setting("0.02 (ассортимент полный)", _assume(no_product_at_all=0.02)),
            Setting("0.08 (наше допущение)"),
            Setting("0.35 (частые дыры)", _assume(no_product_at_all=0.35)),
        ),
    ),
    Dial(
        name="out_of_stock",
        question="Как часто товар есть в каталоге, но закончился на полке?",
        settings=(
            Setting("0.02", _assume(out_of_stock=0.02)),
            Setting("0.10 (наше допущение)"),
            Setting("0.35", _assume(out_of_stock=0.35)),
        ),
    ),
    Dial(
        name="within_radius",
        question="Какая доля предложений попадает в радиус доставки пользователя?",
        settings=(
            Setting("0.40 (далеко)", _assume(within_radius=0.40)),
            Setting("0.70 (наше допущение)"),
            Setting("0.95 (рядом)", _assume(within_radius=0.95)),
        ),
    ),
    Dial(
        name="price_level",
        question="Насколько верна калибровка цен домашней корзины (коэффициент 2.4x)?",
        settings=(
            Setting("x0.5 (мы завысили вдвое)", _assume(price_level=0.5)),
            Setting("x1.0 (наша калибровка)"),
            Setting("x2.0 (мы занизили вдвое)", _assume(price_level=2.0)),
        ),
    ),
    Dial(
        name="time_value",
        question="Сколько стоит час готовки для покупателя?",
        settings=(
            Setting("100 руб/час", time_value_rub_per_hour=100.0),
            Setting("300 руб/час (наше допущение)"),
            Setting("900 руб/час", time_value_rub_per_hour=900.0),
        ),
    ),
    Dial(
        name="missing_tolerance",
        question="Сколько позиций человек готов докупить ради рецепта?",
        settings=(
            Setting("-1 к терпимости", tolerance_shift=-1),
            Setting("наше допущение (2-5)"),
            Setting("+2 к терпимости", tolerance_shift=2),
        ),
    ),
)


def sensitivity_arms() -> tuple[Arm, ...]:
    """Enough arms to evaluate every claim, few enough to sweep cheaply."""
    from recsys.model import MLRecommendationEngine

    ml = MLRecommendationEngine()
    return (
        Arm(name="heuristic/effort", engine=DeterministicMockEngine(), ranking_policy=EFFORT_FIRST),
        Arm(name="ml/effort", engine=ml, ranking_policy=EFFORT_FIRST),
        Arm(name="ml/relevance", engine=ml, ranking_policy=RELEVANCE_FIRST),
        Arm(name="random/effort", engine=RandomEngine(), ranking_policy=EFFORT_FIRST, is_control=True),
        Arm(name="random/relevance", engine=RandomEngine(), ranking_policy=RELEVANCE_FIRST, is_control=True),
    )


@dataclass(frozen=True)
class Claim:
    key: str
    text: str
    evaluate: Callable[[BenchmarkResult], object]


def _wins(result: BenchmarkResult, baseline: str, challenger: str) -> bool:
    return result.compare(baseline, challenger).independent_win_rate > 0.5


def _leader_is_clear(result: BenchmarkResult) -> bool:
    """Is the best non-control arm meaningfully ahead of the runner-up?

    This replaces an earlier claim that simply named the top arm. That claim
    never stabilised at any sample size, and for a good reason: the candidate
    arms sit within one or two percent of each other, so "who is first" is a
    coin toss dressed up as a result. Asking whether anyone is *clearly* ahead
    has a stable answer, and the answer is itself the finding.
    """
    controls = set(result.control_arms())
    means = sorted(
        (value for arm, value in result.arm_means().items() if arm not in controls),
        reverse=True,
    )
    if len(means) < 2 or means[1] <= 0:
        return False
    return (means[0] - means[1]) / means[1] > LEADER_MARGIN


CLAIMS: tuple[Claim, ...] = (
    Claim(
        key="bench_discriminates",
        text="стенд отличает осмысленное ранжирование от шума",
        evaluate=lambda r: r.bench_discriminates,
    ),
    Claim(
        key="ml_beats_noise_shipped",
        text="под текущей политикой модель лучше случайной",
        evaluate=lambda r: _wins(r, "random/effort", "ml/effort"),
    ),
    Claim(
        key="ml_beats_noise_relevance",
        text="когда политика пропускает ранжирование, модель лучше случайной",
        evaluate=lambda r: _wins(r, "random/relevance", "ml/relevance"),
    ),
    Claim(
        key="leader_is_clear",
        text="есть рука, заметно опережающая остальные",
        evaluate=_leader_is_clear,
    ),
    Claim(
        key="heuristic_holds",
        text="эвристика не хуже модели",
        evaluate=lambda r: not _wins(r, "heuristic/effort", "ml/effort"),
    ),
)


@dataclass
class Observation:
    dial: str
    setting: str
    is_baseline: bool
    claims: dict[str, object]
    arm_means: dict[str, float]
    #: Per-user, not per-card: the only outcome comparable across settings.
    #: See ``CellOutcome.cooks_per_user``.
    arm_cooks_per_user: dict[str, float]


def run_setting(
    setting: Setting,
    *,
    dial: str,
    arms: tuple[Arm, ...],
    regimes: tuple,
    users: int,
    seed: int,
) -> Observation:
    responders = (
        RuleBasedResponder(),
        ProbabilisticResponder(),
        EconomicResponder(setting.time_value_rub_per_hour),
    )
    used_regimes = (
        tuple(ToleranceShiftedRegime(r, setting.tolerance_shift) for r in regimes)
        if setting.tolerance_shift
        else regimes
    )
    result = run_benchmark(
        arms,
        regimes=used_regimes,
        responders=responders,
        users_per_regime=users,
        seed=seed,
        inventory_assumptions=setting.assumptions,
    )
    return Observation(
        dial=dial,
        setting=setting.label,
        is_baseline="наше" in setting.label or "наша" in setting.label,
        claims={claim.key: claim.evaluate(result) for claim in CLAIMS},
        arm_means=result.arm_means(),
        arm_cooks_per_user=result.arm_means("cooks_per_user"),
    )


def run_sweep(
    *,
    dials: tuple[Dial, ...] = DIALS,
    regimes: tuple = DEFAULT_REGIMES,
    users: int = DEFAULT_USERS,
    seed: int = DEFAULT_SEED,
    progress: bool = False,
    on_observation=None,
) -> list[Observation]:
    """``on_observation`` is called after each setting.

    A full sweep takes long enough that it gets interrupted, and losing an
    hour of benchmarks because the last dial did not finish is not acceptable.
    The CLI uses this to persist after every setting.
    """
    arms = sensitivity_arms()
    observations: list[Observation] = []
    # Every dial repeats the shipped setting as its reference point, and those
    # runs are byte-identical. Caching them turns 7 redundant benchmarks into 1.
    cache: dict[tuple, Observation] = {}
    for dial in dials:
        for setting in dial.settings:
            key = (
                setting.assumptions,
                setting.time_value_rub_per_hour,
                setting.tolerance_shift,
            )
            cached = cache.get(key)
            if cached is not None:
                if progress:
                    print(f"  {dial.name}: {setting.label} (из кэша)", flush=True)
                reused = Observation(
                    dial=dial.name,
                    setting=setting.label,
                    is_baseline=cached.is_baseline,
                    claims=cached.claims,
                    arm_means=cached.arm_means,
                    arm_cooks_per_user=cached.arm_cooks_per_user,
                )
                observations.append(reused)
                if on_observation is not None:
                    on_observation(reused)
                continue
            if progress:
                print(f"  {dial.name}: {setting.label}", flush=True)
            observation = run_setting(
                setting,
                dial=dial.name,
                arms=arms,
                regimes=regimes,
                users=users,
                seed=seed,
            )
            cache[key] = observation
            observations.append(observation)
            if on_observation is not None:
                on_observation(observation)
    return observations


def observations_to_json(observations: list[Observation]) -> list[dict]:
    return [
        {
            "dial": o.dial,
            "setting": o.setting,
            "is_baseline": o.is_baseline,
            "claims": o.claims,
            "arm_means": o.arm_means,
            "arm_cooks_per_user": o.arm_cooks_per_user,
        }
        for o in observations
    ]


def observations_from_json(payload: list[dict]) -> list[Observation]:
    return [Observation(**entry) for entry in payload]


def seed_stability(
    *,
    seeds: tuple[int, ...] = (20260905, 7, 42),
    regimes: tuple = DEFAULT_REGIMES,
    users: int = DEFAULT_USERS,
) -> dict[str, bool]:
    """Does each claim give the same answer at the baseline across seeds?

    A sweep is only meaningful if its reference point is stable. Reporting
    "dial X flips claim Y" is worthless when Y flips on its own between seeds,
    which is what happened at 30 users per regime.
    """
    arms = sensitivity_arms()
    per_seed = [
        run_setting(
            Setting("наше"),
            dial="stability",
            arms=arms,
            regimes=regimes,
            users=users,
            seed=seed,
        ).claims
        for seed in seeds
    ]
    return {
        claim.key: len({str(c[claim.key]) for c in per_seed}) == 1 for claim in CLAIMS
    }


def fragile_claims(observations: list[Observation]) -> dict[str, list[str]]:
    """claim -> dials that change its value. Empty list means the claim is robust."""
    baselines = {
        claim.key: next(
            (o.claims[claim.key] for o in observations if o.is_baseline), None
        )
        for claim in CLAIMS
    }
    out: dict[str, list[str]] = {claim.key: [] for claim in CLAIMS}
    for observation in observations:
        if observation.is_baseline:
            continue
        for claim in CLAIMS:
            if observation.claims[claim.key] != baselines[claim.key]:
                if observation.dial not in out[claim.key]:
                    out[claim.key].append(observation.dial)
    return out


def _fmt(value: object) -> str:
    if isinstance(value, bool):
        return "да" if value else "нет"
    return str(value)


def build_report(
    observations: list[Observation],
    runtime_s: float,
    users: int,
    stability: dict[str, bool] | None = None,
) -> str:
    out: list[str] = []
    w = out.append
    fragile = fragile_claims(observations)
    stability = stability or {}

    w("# Чувствительность к нашим допущениям")
    w("")
    w(
        "Сгенерирован `python -m recsys.sensitivity`. "
        f"{len(DIALS)} ручек × {len(DIALS[0].settings)} значений, "
        f"по {users} пользователей на мир, {runtime_s:.0f} с."
    )
    w("")
    w(
        "Вопрос не «как поедут числа», а **перевернётся ли вывод**. Вывод, "
        "устойчивый к движению ручки от края до края, от этой ручки не зависит — "
        "и спорить о её значении не нужно. Вывод, который переворачивается, — это "
        "вопрос кейсодателю, и он заслуживает времени на встрече."
    )
    w("")
    w("---")
    w("")
    w("## 0. Устойчивость самой развёртки (читать первым)")
    w("")
    if not stability:
        w("Проверка стабильности не запускалась (`--stability`).")
    else:
        w(
            "Развёртка имеет смысл, только если её точка отсчёта не пляшет сама "
            "по себе. Здесь базовая настройка прогнана на трёх сидах: если "
            "вывод меняется между ними, строки про него ниже читать нельзя."
        )
        w("")
        w("| Вывод | Одинаков на всех сидах |")
        w("|---|:--:|")
        for claim in CLAIMS:
            ok = stability.get(claim.key)
            mark = "—" if ok is None else ("да" if ok else "**НЕТ**")
            w(f"| {claim.text} | {mark} |")
        w("")
        unstable = [c.text for c in CLAIMS if stability.get(c.key) is False]
        if unstable:
            w(
                "**Не опирайтесь на:** "
                + "; ".join(unstable)
                + ". Эти выводы меняются от одного лишь сида, значит развёртка по "
                "ним меряет шум, а не чувствительность."
            )
        else:
            w("Все выводы воспроизводятся на всех сидах.")
    w("")
    w("---")
    w("")
    w("## Итог: что спрашивать у эксперта")
    w("")
    w("| Вывод | Устойчив к | Ломается от |")
    w("|---|---|---|")
    for claim in CLAIMS:
        broken = fragile[claim.key]
        robust = [d.name for d in DIALS if d.name not in broken]
        note = "" if stability.get(claim.key, True) else " ⚠ шумит по сидам"
        w(
            f"| {claim.text}{note} | {len(robust)} из {len(DIALS)} ручек | "
            + (", ".join(f"`{d}`" for d in broken) if broken else "**ничего**")
            + " |"
        )
    w("")
    critical = sorted(
        {dial for dials in fragile.values() for dial in dials},
        key=lambda d: -sum(1 for v in fragile.values() if d in v),
    )
    if critical:
        w("**Ручки, которые вообще что-то ломают, по убыванию влияния:**")
        w("")
        for dial_name in critical:
            dial = next(d for d in DIALS if d.name == dial_name)
            broken = [c.text for c in CLAIMS if dial_name in fragile[c.key]]
            w(f"- `{dial_name}` — {dial.question}")
            w(f"  - ломает: {'; '.join(broken)}")
        w("")
        untouched = [d.name for d in DIALS if d.name not in critical]
        if untouched:
            w(
                "**Ничего не ломают** (значение можно не уточнять): "
                + ", ".join(f"`{d}`" for d in untouched)
                + "."
            )
    else:
        w(
            "**Ни одна ручка не переворачивает ни один вывод.** Выводы стенда не "
            "зависят от наших допущений в проверенном диапазоне."
        )
    w("")
    w("---")
    w("")
    w("## Влияние на ценность продукта (это другой вопрос)")
    w("")
    w(
        "Раздел выше отвечает: «изменится ли **вывод о ранжировании**». Он "
        "молчит о том, есть ли продукт вообще. Это разные вопросы, и путать их "
        "опасно: ручка может не менять ни один вывод и при этом решать судьбу "
        "проекта."
    )
    w("")
    w("| Ручка | готовок на юзера: мин → база → макс | размах |")
    w("|---|---|---:|")
    for dial in DIALS:
        rows = [o for o in observations if o.dial == dial.name]
        if len(rows) < 2:
            continue
        values = [max(o.arm_cooks_per_user.values()) for o in rows]
        base = next(
            (max(o.arm_cooks_per_user.values()) for o in rows if o.is_baseline), None
        )
        low, high = min(values), max(values)
        swing = (high - low) / low if low else 0.0
        base_text = f"{base:.3f}" if base is not None else "—"
        w(
            f"| `{dial.name}` | {low:.3f} → {base_text} → {high:.3f} | "
            f"{swing:+.0%} |"
        )
    w("")
    w(
        "**Читать так:** большой размах при устойчивых выводах означает «на выбор "
        "алгоритма не влияет, на бизнес-кейс влияет сильно». Такую ручку всё "
        "равно нужно уточнять у кейсодателя — просто не ради выбора модели, а "
        "ради оценки самой затеи."
    )
    w("")
    w("---")
    w("")
    w("## Подробно по ручкам")
    w("")
    covered = {o.dial for o in observations}
    for dial in DIALS:
        if dial.name not in covered:
            continue
        w(f"### `{dial.name}`")
        w("")
        w(f"*{dial.question}*")
        w("")
        header = (
            "| Значение | "
            + " | ".join(c.text for c in CLAIMS)
            + " | готовок на юзера |"
        )
        w(header)
        w("|---" * (len(CLAIMS) + 2) + "|")
        for observation in observations:
            if observation.dial != dial.name:
                continue
            cells = " | ".join(_fmt(observation.claims[c.key]) for c in CLAIMS)
            best = max(observation.arm_cooks_per_user.values())
            mark = " **(база)**" if observation.is_baseline else ""
            w(f"| {observation.setting}{mark} | {cells} | {best:.4f} |")
        w("")
    w("---")
    w("")
    w("## Оговорки")
    w("")
    w(
        f"- Диапазоны ручек выбрали мы. Они широкие, чтобы **содержать** правду, "
        f"а не угадать её."
    )
    w(
        "- Прогон меньше основного (по "
        f"{users} пользователей, {len(DEFAULT_REGIMES)} миров): цель — устойчивость "
        "вывода, а не третий знак после запятой."
    )
    w(
        "- Ручки крутятся по одной. Взаимодействия между ними не проверены: "
        "две безобидные по отдельности могут ломать вывод вместе."
    )
    w(
        "- Колонка «готовок на юзера» намеренно не «конверсия на карточку». "
        "При дефиците карточек становится меньше, а выживают лёгкие — "
        "конверсия на карточку растёт, тогда как готовок на человека падает. "
        "Между настройками сравнимо только на пользователя."
    )
    w("")
    return "\n".join(out) + "\n"


def main() -> int:
    import argparse
    import time

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=DEFAULT_USERS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--dials",
        default=None,
        help="Comma-separated dial names; the full sweep is slow, so it can be "
        "run in pieces and combined via --state.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=Path("docs/.sensitivity-state.json"),
        help="Observations accumulate here across partial runs.",
    )
    parser.add_argument("--fresh", action="store_true", help="Ignore saved state.")
    parser.add_argument(
        "--stability",
        action="store_true",
        help="Re-run the baseline on three seeds and report which claims repeat.",
    )
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()

    saved: dict = {}
    if args.state.exists() and not args.fresh:
        saved = json.loads(args.state.read_text(encoding="utf-8"))
    known = {(o["dial"], o["setting"]): o for o in saved.get("observations", [])}

    started = time.time()
    if not args.report_only:
        selected = (
            DIALS
            if not args.dials
            else tuple(d for d in DIALS if d.name in set(args.dials.split(",")))
        )
        if not selected:
            print(f"no dials matched {args.dials!r}", file=sys.stderr)
            return 1
        def persist(observation: Observation) -> None:
            entry = observations_to_json([observation])[0]
            known[(entry["dial"], entry["setting"])] = entry
            args.state.parent.mkdir(parents=True, exist_ok=True)
            args.state.write_text(
                json.dumps(
                    {
                        "observations": list(known.values()),
                        "stability": saved.get("stability") or {},
                    },
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )

        run_sweep(
            dials=selected,
            users=args.users,
            seed=args.seed,
            progress=True,
            on_observation=persist,
        )

    stability = saved.get("stability") or {}
    if args.stability:
        print("  stability: baseline across seeds", flush=True)
        stability = seed_stability(users=args.users)

    runtime = time.time() - started
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(
        json.dumps(
            {"observations": list(known.values()), "stability": stability},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    observations = observations_from_json(
        [known[key] for key in sorted(known, key=lambda k: (k[0], k[1]))]
    )
    covered = {o.dial for o in observations}
    missing = [d.name for d in DIALS if d.name not in covered]
    if missing:
        print(f"  (ещё не посчитаны: {', '.join(missing)})")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = build_report(observations, runtime, args.users, stability)
    io.open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n").write(text)
    print(f"\n{OUTPUT_PATH}: {len(text.splitlines())} lines, {runtime:.0f}s")

    fragile = fragile_claims(observations)
    for claim in CLAIMS:
        broken = fragile[claim.key]
        print(f"  {claim.key:26} ломается от: {broken or 'ничего'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
