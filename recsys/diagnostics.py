"""Why an arm wins or ties — the diagnostics behind the bench's headline.

``recsys.benchmark`` answers "does B beat A". It cannot say *why*, and the why
turned out to matter more than the score: the trained ranker ties with a random
one not because ranking is unimportant but because the pipeline was ranking on
the same quantity twice.

Two measurements establish that, and both live here so the claim in
``docs/benchmark-report.md`` can be re-derived rather than believed:

``effort_confound``
    How strongly each model feature tracks ``missing_count`` — the quantity
    ``app.service.RankingPolicy`` already sorts on.

``stratified_signal``
    Whether ``model_score`` still separates relevant from irrelevant recipes
    *within* groups of equal ``missing_count``. This is the decisive one. A
    model that only looks good across strata has learned effort; a model that
    also ranks well inside a stratum has learned something the policy does not
    already know.

Separation is measured as AUC over the pairs a stratum contains, which needs no
threshold and is unaffected by how imbalanced the stratum is.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from dataclasses import dataclass

from app.recommender import RecommendationEngine
from recsys.benchmark import _build_request
from recsys.inventory import generate_inventory
from recsys.model import FEATURE_NAMES, compute_features
from recsys.profiles import generate_population
from recsys.ready_food_pairs import ready_meal_options
from recsys.recipes import RECIPES

DEFAULT_PROFILES = 60
DEFAULT_SEED = 11

#: Strata thinner than this cannot support an AUC worth reading.
MIN_STRATUM_SIZE = 30


def pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    den = (
        sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)
    ) ** 0.5
    return num / den if den else 0.0


def auc(scores: list[float], labels: list[bool]) -> float | None:
    """P(score of a positive > score of a negative), ties counted as half.

    ``None`` when a stratum is single-class, which carries no information about
    ranking rather than a score of 0.5.
    """
    positives = [s for s, label in zip(scores, labels, strict=True) if label]
    negatives = [s for s, label in zip(scores, labels, strict=True) if not label]
    if not positives or not negatives:
        return None
    wins = 0.0
    for p in positives:
        for n in negatives:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(positives) * len(negatives))


@dataclass(frozen=True)
class Stratum:
    missing_count: int
    n: int
    positive_rate: float
    auc: float | None

    @property
    def is_readable(self) -> bool:
        return self.auc is not None and self.n >= MIN_STRATUM_SIZE


@dataclass
class StratifiedSignal:
    overall_auc: float | None
    strata: tuple[Stratum, ...]

    @property
    def readable_strata(self) -> tuple[Stratum, ...]:
        return tuple(s for s in self.strata if s.is_readable)

    @property
    def within_stratum_auc(self) -> float | None:
        """Size-weighted AUC inside equal-effort groups."""
        readable = self.readable_strata
        if not readable:
            return None
        total = sum(s.n for s in readable)
        return sum(s.auc * s.n for s in readable) / total

    @property
    def signal_beyond_effort(self) -> float | None:
        """How much of the apparent ranking skill survives holding effort fixed."""
        within = self.within_stratum_auc
        if within is None or self.overall_auc is None:
            return None
        return within - 0.5

    def summary(self) -> str:
        lines = [
            f"overall AUC: {self.overall_auc:.3f}"
            if self.overall_auc is not None
            else "overall AUC: n/a",
        ]
        within = self.within_stratum_auc
        lines.append(
            f"within-effort AUC: {within:.3f}" if within is not None else "within: n/a"
        )
        for s in self.strata:
            mark = "" if s.is_readable else "  (too thin / single-class)"
            value = f"{s.auc:.3f}" if s.auc is not None else "n/a"
            lines.append(
                f"  missing={s.missing_count:>2}  n={s.n:>5}  "
                f"pos={s.positive_rate:.2f}  AUC={value}{mark}"
            )
        return "\n".join(lines)


def _samples(n_profiles: int, seed: int):
    recipes = list(RECIPES)
    meals = ready_meal_options([r.recipe_id for r in recipes])
    rng = random.Random(seed)
    for profile in generate_population(n_profiles, seed=seed):
        inventory = generate_inventory(
            rng,
            now=profile.now,
            home_store_id=profile.current_receipt.store_id,
            user_radius_km=profile.user.radius_km,
        )
        request = _build_request(profile, recipes, inventory, meals)
        yield profile, request, recipes


def effort_confound(
    *, n_profiles: int = DEFAULT_PROFILES, seed: int = DEFAULT_SEED
) -> dict[str, float]:
    """Correlation of every model feature with the quantity the policy sorts on."""
    columns: dict[str, list[float]] = {name: [] for name in FEATURE_NAMES}
    missing: list[float] = []
    for _, request, recipes in _samples(n_profiles, seed):
        for recipe in recipes:
            features = compute_features(request, recipe)
            for name in FEATURE_NAMES:
                columns[name].append(features[name])
            missing.append(features["_missing_count"])
    return {name: pearson(values, missing) for name, values in columns.items()}


def stratified_signal(
    engine: RecommendationEngine,
    *,
    n_profiles: int = DEFAULT_PROFILES,
    seed: int = DEFAULT_SEED,
) -> StratifiedSignal:
    """Does ``model_score`` rank correctly once effort is held fixed?

    Relevance labels come from ``recsys.evaluation.oracle_relevant``. That
    oracle is self-referential for the trained model — but here it works *for*
    the argument rather than against it: if even a friendly judge shows no
    within-stratum separation, the model genuinely carries nothing the ranking
    policy does not already have.
    """
    from recsys.evaluation import oracle_relevant

    by_stratum: dict[int, tuple[list[float], list[bool]]] = defaultdict(
        lambda: ([], [])
    )
    all_scores: list[float] = []
    all_labels: list[bool] = []

    for profile, request, recipes in _samples(n_profiles, seed):
        scores = {r.recipe_id: r.score for r in engine.rank(request)}
        for recipe in recipes:
            if recipe.recipe_id not in scores:
                continue
            features = compute_features(request, recipe)
            label = oracle_relevant(profile, recipe, request)
            score = scores[recipe.recipe_id]
            bucket = int(features["_missing_count"])
            by_stratum[bucket][0].append(score)
            by_stratum[bucket][1].append(label)
            all_scores.append(score)
            all_labels.append(label)

    strata = tuple(
        Stratum(
            missing_count=bucket,
            n=len(scores),
            positive_rate=sum(labels) / len(labels) if labels else 0.0,
            auc=auc(scores, labels),
        )
        for bucket, (scores, labels) in sorted(by_stratum.items())
    )
    return StratifiedSignal(overall_auc=auc(all_scores, all_labels), strata=strata)


def main() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    from app.recommender import DeterministicMockEngine
    from recsys.model import MLRecommendationEngine

    print("=== feature correlation with missing_count (what the policy sorts on) ===")
    for name, value in sorted(
        effort_confound().items(), key=lambda kv: -abs(kv[1])
    ):
        flag = "  <-- effort in disguise" if abs(value) > 0.5 else ""
        print(f"  {name:24} {value:+.3f}{flag}")
    print()

    for label, engine in (
        ("ml (shipped)", MLRecommendationEngine()),
        (
            "ml (effort features zeroed)",
            MLRecommendationEngine(include_effort_features=False),
        ),
        ("heuristic", DeterministicMockEngine()),
    ):
        print(f"=== stratified signal: {label} ===")
        print(stratified_signal(engine).summary())
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
