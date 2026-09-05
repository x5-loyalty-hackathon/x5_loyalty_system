"""Human-rating pilot: an independent label set, and the discipline around it.

Why
---
Every relevance number this project has is self-referential.
``recsys.evaluation.oracle_relevant`` is derived from the same archetype rules
as ``recsys.model._label_for_pair``, so agreement with it measures whether a
model reproduced a rule we wrote, not whether a person would cook the dish.
CatBoost scoring 100% against it is the proof: you cannot beat 100%, and a
metric at its ceiling has stopped measuring.

This module builds the smallest thing that can contradict the synthetic
oracle — a few hundred human judgments on blinded cards — and the analysis
that says how much they can contradict it before the difference is noise.

What it deliberately does *not* do
----------------------------------
It does not measure uplift, and it does not measure personalization.

*Uplift*: a rater saying "yes, appealing" is not a purchase. Nothing here
licenses a sentence about GMV.

*Personalization*: the rater judges **for the shopper shown on the card**,
from a basket and a history summary. That is the task the model performs, so
it is the right question — but a human inferring another person's taste from
seven categories of receipts is working with the same thin evidence the model
has, and will make correlated mistakes with it. A design that could separate
personalization from dish quality needs the same dish shown against different
baskets; that is a bigger study than a pilot, and §"Ограничения" of
``docs/research/recsys/human-eval-pilot.md`` says so out loud.

Two questions, not one
----------------------
``oracle_relevant`` collapses "I don't want this dish" and "I don't want to buy
four things for it" into one bit. The card asks them separately, because the
product responses differ: the first is a catalog problem, the second is a
ranking-policy problem. Whether raters actually separate them is itself a
measured output (``two_question_correlation``).
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from app.contracts import RecipeRecommendation, RecommendationRequest
from app.safety import SafetyPolicy
from app.service import MODEL_ORDER, RecommendationService
from recsys._seeds import stable_seed
from recsys.catalog_freeze import baseline_catalog
from recsys.evaluation import oracle_relevant
from recsys.model import compute_user_stats
from recsys.panels import Panel, development_splits
from recsys.profiles import SyntheticProfile
from recsys.ready_food_pairs import ready_meal_options

OUTPUT_ROOT = Path("recsys/data/human_eval")

#: Cards per rater. The upper end of the plan's 10-15: fifteen cards at ~20s
#: each is a five-minute task, which is about as much unpaid attention a pilot
#: can ask for before people start clicking through.
CARDS_PER_RATER = 12

#: Target raters. Below ~30 the by-rater bootstrap interval is wider than any
#: effect worth acting on.
TARGET_RATERS = 40

#: Every card is judged by this many people. Three is the minimum that lets a
#: disagreement be attributed rather than just observed.
RATINGS_PER_CARD = 3

#: 1..5 Likert on both questions. Binarised at >= 4 for comparison with the
#: binary oracle — stated here rather than chosen after seeing the data.
POSITIVE_THRESHOLD = 4

#: Buckets for the top-up axis. The boundaries match the thresholds the catalog
#: metric already uses (0 / <=1 / <=2), so a finding here lands on a number the
#: rest of the protocol already tracks.
def missing_bucket(missing_count: int) -> str:
    if missing_count == 0:
        return "0"
    if missing_count <= 2:
        return "1-2"
    if missing_count <= 4:
        return "3-4"
    return "5+"


@dataclass(frozen=True)
class CardContext:
    """What the rater is told about the shopper. Never the archetype label.

    The archetype is generation-time truth and not something the product would
    know; showing it would let a rater judge the generator instead of the
    recommendation.
    """

    top_categories: tuple[str, ...]
    mean_basket_size: float
    visit_cadence_days: float
    basket_today: tuple[str, ...]


@dataclass(frozen=True)
class RatingCard:
    """One blinded unit of work for a rater."""

    card_id: str
    title: str
    prep_minutes: int | None
    servings: int
    dish_type: str | None
    cuisine: str | None
    already_have: tuple[str, ...]
    to_buy: tuple[str, ...]
    missing_count: int
    missing_cost_rub: float
    context: CardContext

    def public(self) -> dict:
        """Exactly what a rater may see — no source, no oracle verdict."""
        return {
            "card_id": self.card_id,
            "title": self.title,
            "prep_minutes": self.prep_minutes,
            "servings": self.servings,
            "dish_type": self.dish_type,
            "cuisine": self.cuisine,
            "already_have": list(self.already_have),
            "to_buy": list(self.to_buy),
            "missing_count": self.missing_count,
            "missing_cost_rub": round(self.missing_cost_rub),
            "context": {
                "top_categories": list(self.context.top_categories),
                "mean_basket_size": round(self.context.mean_basket_size, 1),
                "visit_cadence_days": round(self.context.visit_cadence_days, 1),
                "basket_today": list(self.context.basket_today),
            },
        }


@dataclass(frozen=True)
class CardKey:
    """The half of a card a rater must not see until after they have rated."""

    card_id: str
    user_id: str
    recipe_id: str
    archetype: str
    #: Every engine that put this card in its top-k. More than one is common
    #: and is itself a finding: two rankers agreeing is not two votes.
    sources: tuple[str, ...]
    oracle_relevant: bool
    missing_count: int


def _card_id(user_id: str, recipe_id: str) -> str:
    """Opaque and stable. Not reversible by a curious rater reading the JSON."""
    digest = hashlib.sha256(f"{user_id}|{recipe_id}".encode("utf-8")).hexdigest()
    return f"c_{digest[:12]}"


def _context_for(profile: SyntheticProfile, request: RecommendationRequest) -> CardContext:
    stats = compute_user_stats(request)
    ranked = sorted(stats.category_share.items(), key=lambda kv: -kv[1])
    return CardContext(
        top_categories=tuple(name for name, share in ranked[:3] if share > 0),
        mean_basket_size=stats.mean_basket_size,
        visit_cadence_days=stats.mean_cadence_days,
        basket_today=tuple(sorted({item.name for item in profile.current_receipt.items})),
    )


def _card_from(
    card: RecipeRecommendation,
    recipe,
    profile: SyntheticProfile,
    request: RecommendationRequest,
) -> RatingCard:
    already_have = tuple(
        sorted(i.name for i in card.ingredients if not i.product_options)
    )
    to_buy = tuple(sorted(i.name for i in card.ingredients if i.product_options))
    cost = sum(
        i.product_options[0].price for i in card.ingredients if i.product_options
    )
    return RatingCard(
        card_id=_card_id(profile.user.user_id, card.recipe_id),
        title=card.title,
        prep_minutes=recipe.preparation_minutes,
        servings=recipe.servings,
        dish_type=recipe.dish_type,
        cuisine=recipe.cuisine,
        already_have=already_have,
        to_buy=to_buy,
        missing_count=card.missing_count,
        missing_cost_rub=cost,
        context=_context_for(profile, request),
    )


def build_engines() -> dict[str, object]:
    """The sources whose cards get rated, including the random control.

    The control is not decoration: if raters cannot tell random cards from
    ranked ones, the instrument is not measuring ranking and every other
    number from the pilot is void. Same role ``RandomEngine`` plays in
    ``recsys.benchmark``.
    """
    from recsys.benchmark import RandomEngine
    from recsys.catboost_model import CatBoostRecommendationEngine
    from recsys.coverage_heuristic_engine import CoverageHeuristicEngine
    from recsys.model import MLRecommendationEngine
    from recsys.oracle_ranking_engine import OracleRankingEngine

    catalog = baseline_catalog()
    return {
        "coverage": CoverageHeuristicEngine(),
        "ml": MLRecommendationEngine(recipe_catalog=catalog),
        "catboost": CatBoostRecommendationEngine(recipe_catalog=catalog),
        "oracle": OracleRankingEngine(),
        "random": RandomEngine(),
    }


def build_card_pool(
    panel: Panel,
    engines: dict[str, object],
    *,
    top_k: int = 1,
    seed: int = 20260905,
) -> tuple[list[RatingCard], dict[str, CardKey]]:
    """Collect each engine's top-k card for each user in the panel.

    ``MODEL_ORDER`` is the policy on purpose: the service still assembles the
    card (so the rater sees a real shopping list and a real price), but it does
    not reorder by ``missing_count``, so what reaches the rater is the
    *ranker's* pick rather than the policy's.
    """
    catalog = baseline_catalog()
    recipe_lookup = {recipe.recipe_id: recipe for recipe in catalog}
    meals = ready_meal_options(recipe_lookup)
    services = {
        name: RecommendationService(
            engine=engine, safety_policy=SafetyPolicy(), ranking_policy=MODEL_ORDER
        )
        for name, engine in engines.items()
    }

    cards: dict[str, RatingCard] = {}
    sources: dict[str, set[str]] = defaultdict(set)
    keys: dict[str, CardKey] = {}

    for profile, inventory in panel.pairs():
        request = RecommendationRequest(
            user=profile.user,
            current_receipt=profile.current_receipt,
            purchase_history=profile.purchase_history,
            recipe_catalog=catalog,
            inventory_snapshot=inventory,
            ready_meal_options=meals,
            now=profile.now,
            limit=max(top_k, 1),
        )
        for name, service in services.items():
            for served in service.recommend(request).recommendations[:top_k]:
                recipe = recipe_lookup[served.recipe_id]
                rating_card = _card_from(served, recipe, profile, request)
                cards[rating_card.card_id] = rating_card
                sources[rating_card.card_id].add(name)
                keys[rating_card.card_id] = CardKey(
                    card_id=rating_card.card_id,
                    user_id=profile.user.user_id,
                    recipe_id=served.recipe_id,
                    archetype=profile.archetype,
                    sources=(),
                    oracle_relevant=oracle_relevant(profile, recipe, request),
                    missing_count=served.missing_count,
                )

    for card_id, key in keys.items():
        keys[card_id] = CardKey(**{**key.__dict__, "sources": tuple(sorted(sources[card_id]))})
    return list(cards.values()), keys


def select_pool(
    cards: list[RatingCard],
    keys: dict[str, CardKey],
    *,
    target_cards: int,
    seed: int = 20260905,
) -> list[RatingCard]:
    """Stratified subsample: every (oracle verdict x top-up bucket) cell present.

    Random sampling would follow the population, and the population is
    lopsided — most cards are oracle-relevant with few missing items. The cells
    where the oracle is most likely to be *wrong* are exactly the rare ones, so
    they are sampled up rather than left to chance.
    """
    rng = random.Random(stable_seed("human_eval_pool", seed))
    by_cell: dict[tuple[bool, str], list[RatingCard]] = defaultdict(list)
    for card in cards:
        key = keys[card.card_id]
        by_cell[(key.oracle_relevant, missing_bucket(key.missing_count))].append(card)

    for bucket in by_cell.values():
        bucket.sort(key=lambda c: c.card_id)
        rng.shuffle(bucket)

    selected: list[RatingCard] = []
    cells = sorted(by_cell, key=lambda cell: (cell[0], cell[1]))
    while len(selected) < target_cards and any(by_cell[cell] for cell in cells):
        for cell in cells:
            if by_cell[cell] and len(selected) < target_cards:
                selected.append(by_cell[cell].pop())
    return sorted(selected, key=lambda c: c.card_id)


def assign(
    cards: list[RatingCard],
    keys: dict[str, CardKey],
    *,
    n_raters: int = TARGET_RATERS,
    cards_per_rater: int = CARDS_PER_RATER,
    seed: int = 20260905,
) -> dict[str, list[str]]:
    """Balanced incomplete block assignment.

    Two constraints beyond "spread the load": a rater never sees the same
    recipe twice (a second look at the same dish is not an independent
    judgment), and cards are dealt in a rotating order so no rater's block is a
    contiguous slice of one stratum.
    """
    rng = random.Random(stable_seed("human_eval_assign", seed))
    raters = [f"r{index:03d}" for index in range(1, n_raters + 1)]
    assignments: dict[str, list[str]] = {rater: [] for rater in raters}
    seen_recipes: dict[str, set[str]] = {rater: set() for rater in raters}

    def place(card_id: str, *, respect_recipe_rule: bool) -> bool:
        recipe_id = keys[card_id].recipe_id
        candidates = sorted(
            (r for r in raters if len(assignments[r]) < cards_per_rater),
            key=lambda r: (len(assignments[r]), r),
        )
        for rater in candidates:
            if card_id in assignments[rater]:
                continue
            if respect_recipe_rule and recipe_id in seen_recipes[rater]:
                continue
            assignments[rater].append(card_id)
            seen_recipes[rater].add(recipe_id)
            return True
        return False

    # Round by round rather than one shuffled deck of length cards*N. A single
    # deck strands the last cards: by the time it reaches them, the raters with
    # capacity left are exactly the ones who already hold that recipe. Dealing
    # one full pass per required rating keeps every rater's load even as the
    # constraint tightens.
    deferred: list[str] = []
    for _ in range(RATINGS_PER_CARD):
        order = [card.card_id for card in cards]
        rng.shuffle(order)
        for card_id in order:
            if not place(card_id, respect_recipe_rule=True):
                deferred.append(card_id)

    # Repair pass: a card short of its ratings is worse than a rater seeing two
    # cards of one dish, so the softer constraint yields first. Never place the
    # same card twice with one rater — that is not a second opinion.
    for card_id in deferred:
        place(card_id, respect_recipe_rule=False)
    return assignments


# --- analysis --------------------------------------------------------------


@dataclass(frozen=True)
class Rating:
    rater_id: str
    card_id: str
    #: 1..5, "how likely is this shopper to want to cook this"
    want_to_cook: int
    #: 1..5, "is buying these N items for it acceptable"
    topup_ok: int
    note: str = ""

    @property
    def wants(self) -> bool:
        return self.want_to_cook >= POSITIVE_THRESHOLD

    @property
    def accepts_topup(self) -> bool:
        return self.topup_ok >= POSITIVE_THRESHOLD


def _bootstrap_ci(
    values_by_rater: dict[str, list[float]],
    *,
    iterations: int = 2000,
    seed: int = 20260905,
) -> tuple[float, float, float]:
    """Mean and 95% interval, resampling **raters**, not ratings.

    Ratings from one person are not independent — a strict rater drags twelve
    numbers down together. Resampling ratings would treat those twelve as
    twelve independent facts and report an interval several times too narrow.
    """
    raters = sorted(values_by_rater)
    flat = [v for rater in raters for v in values_by_rater[rater]]
    if not flat:
        return 0.0, 0.0, 0.0
    point = statistics.mean(flat)
    if len(raters) < 2:
        return point, point, point

    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(iterations):
        drawn = [values_by_rater[rng.choice(raters)] for _ in raters]
        pooled = [v for block in drawn for v in block]
        if pooled:
            means.append(statistics.mean(pooled))
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[min(int(0.975 * len(means)), len(means) - 1)]
    return point, lo, hi


@dataclass
class PilotAnalysis:
    n_ratings: int
    n_raters: int
    n_cards_rated: int
    want_rate: tuple[float, float, float]
    topup_rate: tuple[float, float, float]
    #: Share of cards where the binarised human verdict matches the oracle.
    oracle_agreement: tuple[float, float, float]
    #: The asymmetric half that matters: oracle says relevant, humans do not.
    oracle_false_positive_rate: float
    oracle_false_negative_rate: float
    two_question_correlation: float
    by_source: dict[str, tuple[float, float, float]]
    by_missing_bucket: dict[str, tuple[float, float, float]]
    by_archetype: dict[str, tuple[float, float, float]]
    inter_rater_agreement: float
    detectable_difference_pp: float
    warnings: list[str] = field(default_factory=list)


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mx, my = statistics.mean(xs), statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def analyse(ratings: list[Rating], keys: dict[str, CardKey]) -> PilotAnalysis:
    known = [r for r in ratings if r.card_id in keys]
    by_rater_want: dict[str, list[float]] = defaultdict(list)
    by_rater_topup: dict[str, list[float]] = defaultdict(list)
    by_rater_agree: dict[str, list[float]] = defaultdict(list)
    by_source: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    by_bucket: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    by_archetype: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    per_card: dict[str, list[bool]] = defaultdict(list)

    false_pos = 0
    oracle_pos = 0
    false_neg = 0
    oracle_neg = 0

    for rating in known:
        key = keys[rating.card_id]
        by_rater_want[rating.rater_id].append(float(rating.wants))
        by_rater_topup[rating.rater_id].append(float(rating.accepts_topup))
        by_rater_agree[rating.rater_id].append(float(rating.wants == key.oracle_relevant))
        per_card[rating.card_id].append(rating.wants)
        for source in key.sources:
            by_source[source][rating.rater_id].append(float(rating.wants))
        by_bucket[missing_bucket(key.missing_count)][rating.rater_id].append(
            float(rating.wants)
        )
        by_archetype[key.archetype][rating.rater_id].append(float(rating.wants))

        if key.oracle_relevant:
            oracle_pos += 1
            false_pos += int(not rating.wants)
        else:
            oracle_neg += 1
            false_neg += int(rating.wants)

    shared = [verdicts for verdicts in per_card.values() if len(verdicts) >= 2]
    agreements: list[float] = []
    for verdicts in shared:
        pairs = [
            float(a == b)
            for i, a in enumerate(verdicts)
            for b in verdicts[i + 1 :]
        ]
        agreements.extend(pairs)

    n_raters = len(by_rater_want)
    # Half-width of the by-rater interval on a 50/50 split, in points: the
    # smallest gap this pilot could distinguish from noise. Stated so a null
    # result is read as "underpowered" rather than "no difference".
    detectable = (
        196.0 * (0.25 / max(n_raters, 1)) ** 0.5 if n_raters else 0.0
    )

    warnings: list[str] = []
    if n_raters < 30:
        warnings.append(f"only {n_raters} raters: intervals are wider than the plan assumed")
    if not shared:
        warnings.append("no card was rated twice: inter-rater agreement is unmeasured")

    return PilotAnalysis(
        n_ratings=len(known),
        n_raters=n_raters,
        n_cards_rated=len(per_card),
        want_rate=_bootstrap_ci(by_rater_want),
        topup_rate=_bootstrap_ci(by_rater_topup),
        oracle_agreement=_bootstrap_ci(by_rater_agree),
        oracle_false_positive_rate=false_pos / oracle_pos if oracle_pos else 0.0,
        oracle_false_negative_rate=false_neg / oracle_neg if oracle_neg else 0.0,
        two_question_correlation=_pearson(
            [float(r.want_to_cook) for r in known],
            [float(r.topup_ok) for r in known],
        ),
        by_source={name: _bootstrap_ci(v) for name, v in sorted(by_source.items())},
        by_missing_bucket={name: _bootstrap_ci(v) for name, v in sorted(by_bucket.items())},
        by_archetype={name: _bootstrap_ci(v) for name, v in sorted(by_archetype.items())},
        inter_rater_agreement=statistics.mean(agreements) if agreements else 0.0,
        detectable_difference_pp=detectable,
        warnings=warnings,
    )


# --- export ----------------------------------------------------------------


def export(
    cards: list[RatingCard],
    keys: dict[str, CardKey],
    assignments: dict[str, list[str]],
    root: Path = OUTPUT_ROOT,
) -> Path:
    """Write the task and, separately, the key.

    Two files rather than one, because the blinding is only real if the answer
    is somewhere the rating surface never reads.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "cards_public.json").write_text(
        json.dumps([card.public() for card in cards], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (root / "assignments.json").write_text(
        json.dumps(assignments, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (root / "cards_key.json").write_text(
        json.dumps(
            {
                card_id: {
                    "user_id": key.user_id,
                    "recipe_id": key.recipe_id,
                    "archetype": key.archetype,
                    "sources": list(key.sources),
                    "oracle_relevant": key.oracle_relevant,
                    "missing_count": key.missing_count,
                }
                for card_id, key in sorted(keys.items())
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    return root


def load_keys(root: Path = OUTPUT_ROOT) -> dict[str, CardKey]:
    payload = json.loads((root / "cards_key.json").read_text(encoding="utf-8"))
    return {
        card_id: CardKey(
            card_id=card_id,
            user_id=entry["user_id"],
            recipe_id=entry["recipe_id"],
            archetype=entry["archetype"],
            sources=tuple(entry["sources"]),
            oracle_relevant=entry["oracle_relevant"],
            missing_count=entry["missing_count"],
        )
        for card_id, entry in payload.items()
    }


def main() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print("building panels and engines...", flush=True)
    validation = development_splits()["validation"]
    engines = build_engines()

    print(f"collecting cards from {len(validation.profiles)} validation users...", flush=True)
    # top_k=2 rather than 1: five engines on 73 users deduplicate down to ~150
    # distinct cards, which is below the pool the rater budget can absorb and
    # leaves the "oracle said no" strata too thin to say anything about. The
    # second-ranked card is still a card that ranker would serve at limit=3.
    cards, keys = build_card_pool(validation, engines, top_k=2)
    target = (TARGET_RATERS * CARDS_PER_RATER) // RATINGS_PER_CARD
    pool = select_pool(cards, keys, target_cards=target)
    pool_keys = {card.card_id: keys[card.card_id] for card in pool}
    assignments = assign(pool, pool_keys)

    export(pool, pool_keys, assignments)

    dealt = Counter(len(v) for v in assignments.values())
    coverage = Counter()
    for card_ids in assignments.values():
        for card_id in card_ids:
            coverage[card_id] += 1

    print(f"\ncards collected: {len(cards)}, pool: {len(pool)}")
    print(f"raters: {len(assignments)}, cards each: {sorted(dealt.items())}")
    print(f"ratings per card: {sorted(Counter(coverage.values()).items())}")
    print("\nsource coverage in pool (a card can have several):")
    source_counts = Counter(s for k in pool_keys.values() for s in k.sources)
    for source, count in source_counts.most_common():
        print(f"  {source:<10} {count:>4}")
    print("\noracle verdict x top-up bucket:")
    cells = Counter(
        (k.oracle_relevant, missing_bucket(k.missing_count)) for k in pool_keys.values()
    )
    for (relevant, bucket), count in sorted(cells.items()):
        print(f"  oracle={'yes' if relevant else 'no ':<3} missing={bucket:<4} {count:>4}")
    print(f"\nwritten to {OUTPUT_ROOT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
