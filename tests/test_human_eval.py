"""Guarantees the human-rating pilot has to provide to be worth running.

Blinding, balance and the by-rater interval are not niceties here: each one is
a way the pilot could produce a confident number that means nothing.
"""

from __future__ import annotations

import random
from collections import Counter

from recsys.human_eval import (
    CARDS_PER_RATER,
    POSITIVE_THRESHOLD,
    RATINGS_PER_CARD,
    CardContext,
    CardKey,
    Rating,
    RatingCard,
    _bootstrap_ci,
    analyse,
    assign,
    missing_bucket,
    select_pool,
)


def _card(index: int, *, missing: int = 2) -> RatingCard:
    return RatingCard(
        card_id=f"c_{index:04d}",
        title=f"Блюдо {index}",
        prep_minutes=30,
        servings=2,
        dish_type="Основное блюдо",
        cuisine="Русская",
        already_have=("Молоко",),
        to_buy=tuple(f"Товар {i}" for i in range(missing)),
        missing_count=missing,
        missing_cost_rub=100.0 * missing,
        context=CardContext(
            top_categories=("dairy", "vegetable"),
            mean_basket_size=6.0,
            visit_cadence_days=3.0,
            basket_today=("Молоко", "Хлеб"),
        ),
    )


def _key(index: int, *, missing: int = 2, relevant: bool = True, sources=("ml",)) -> CardKey:
    return CardKey(
        card_id=f"c_{index:04d}",
        user_id=f"synthetic_routine_{index:04d}",
        recipe_id=f"recipe_{index % 7}",
        archetype="routine",
        sources=tuple(sources),
        oracle_relevant=relevant,
        missing_count=missing,
    )


def _pool(n: int) -> tuple[list[RatingCard], dict[str, CardKey]]:
    cards = [_card(i, missing=i % 6) for i in range(n)]
    keys = {
        card.card_id: _key(i, missing=i % 6, relevant=(i % 3 != 0))
        for i, card in enumerate(cards)
    }
    return cards, keys


# --- blinding --------------------------------------------------------------


def test_the_public_card_reveals_neither_source_nor_oracle_verdict() -> None:
    """A rater who can see which engine produced a card is not rating blind."""
    public = _card(1).public()
    flat = repr(public)
    assert "source" not in public
    assert "oracle" not in flat.lower()
    assert "archetype" not in flat.lower()
    assert "user_id" not in public
    assert "recipe_id" not in public


def test_the_card_shows_the_shopper_without_naming_the_archetype() -> None:
    """The archetype is generation-time truth; showing it invites the rater to
    grade the generator instead of the recommendation."""
    context = _card(1).public()["context"]
    assert set(context) == {
        "top_categories",
        "mean_basket_size",
        "visit_cadence_days",
        "basket_today",
    }


# --- assignment ------------------------------------------------------------


def test_every_card_gets_the_planned_number_of_ratings() -> None:
    cards, keys = _pool(160)
    assignments = assign(cards, keys, n_raters=40, cards_per_rater=CARDS_PER_RATER)
    counts = Counter(cid for ids in assignments.values() for cid in ids)
    assert set(counts.values()) == {RATINGS_PER_CARD}


def test_every_rater_gets_a_full_block() -> None:
    cards, keys = _pool(160)
    assignments = assign(cards, keys, n_raters=40, cards_per_rater=CARDS_PER_RATER)
    assert {len(ids) for ids in assignments.values()} == {CARDS_PER_RATER}


def test_no_rater_sees_the_same_card_twice() -> None:
    """A second look at the same card is not a second opinion."""
    cards, keys = _pool(160)
    assignments = assign(cards, keys, n_raters=40, cards_per_rater=CARDS_PER_RATER)
    for card_ids in assignments.values():
        assert len(card_ids) == len(set(card_ids))


def test_assignment_is_deterministic() -> None:
    cards, keys = _pool(120)
    first = assign(cards, keys, n_raters=30, cards_per_rater=12)
    second = assign(cards, keys, n_raters=30, cards_per_rater=12)
    assert first == second


# --- stratification --------------------------------------------------------


def test_selection_spreads_across_oracle_and_topup_strata() -> None:
    """Sampling by population would follow the majority cell; the cells where
    the oracle is most likely wrong are the rare ones."""
    cards, keys = _pool(300)
    pool = select_pool(cards, keys, target_cards=60)
    cells = Counter(
        (keys[c.card_id].oracle_relevant, missing_bucket(keys[c.card_id].missing_count))
        for c in pool
    )
    assert len(cells) >= 4
    assert max(cells.values()) <= 3 * min(cells.values())


def test_selection_is_deterministic() -> None:
    cards, keys = _pool(300)
    assert [c.card_id for c in select_pool(cards, keys, target_cards=60)] == [
        c.card_id for c in select_pool(cards, keys, target_cards=60)
    ]


# --- uncertainty -----------------------------------------------------------


def test_the_interval_clusters_by_rater_not_by_rating() -> None:
    """Ratings from one person are not independent observations.

    Two raters who each answer twelve times consistently carry about as much
    information as two opinions, not twenty-four. Resampling ratings would
    report an interval several times too narrow, which is how a pilot ends up
    "proving" a difference it never had the power to see.
    """
    strict = {f"strict{i}": [0.0] * 12 for i in range(10)}
    lenient = {f"lenient{i}": [1.0] * 12 for i in range(10)}
    by_rater = {**strict, **lenient}

    _, lo, hi = _bootstrap_ci(by_rater, iterations=500)
    clustered_width = hi - lo

    flat = {"everyone": [v for block in by_rater.values() for v in block]}
    _, flo, fhi = _bootstrap_ci(flat, iterations=500)
    assert clustered_width > (fhi - flo)


def test_a_single_rater_yields_no_interval_rather_than_a_fake_one() -> None:
    point, lo, hi = _bootstrap_ci({"only": [1.0, 0.0, 1.0]}, iterations=100)
    assert lo == hi == point


# --- analysis --------------------------------------------------------------


def _ratings_for(assignments, keys, *, agree_with_oracle: bool) -> list[Rating]:
    out: list[Rating] = []
    for rater, card_ids in assignments.items():
        for card_id in card_ids:
            relevant = keys[card_id].oracle_relevant
            wants = relevant if agree_with_oracle else not relevant
            score = POSITIVE_THRESHOLD if wants else POSITIVE_THRESHOLD - 2
            out.append(
                Rating(rater_id=rater, card_id=card_id, want_to_cook=score, topup_ok=score)
            )
    return out


def test_perfect_agreement_reads_as_perfect() -> None:
    cards, keys = _pool(60)
    assignments = assign(cards, keys, n_raters=15, cards_per_rater=12)
    result = analyse(_ratings_for(assignments, keys, agree_with_oracle=True), keys)
    assert result.oracle_agreement[0] == 1.0
    assert result.oracle_false_positive_rate == 0.0
    assert result.oracle_false_negative_rate == 0.0


def test_total_disagreement_is_attributed_to_the_right_side() -> None:
    """The asymmetry matters: "oracle said relevant, humans said no" is a
    synthetic false positive and points at the label, not at the ranker."""
    cards, keys = _pool(60)
    assignments = assign(cards, keys, n_raters=15, cards_per_rater=12)
    result = analyse(_ratings_for(assignments, keys, agree_with_oracle=False), keys)
    assert result.oracle_agreement[0] == 0.0
    assert result.oracle_false_positive_rate == 1.0
    assert result.oracle_false_negative_rate == 1.0


def test_analysis_reports_how_small_a_difference_it_could_have_seen() -> None:
    """A null result must be readable as "underpowered" rather than "no effect"."""
    cards, keys = _pool(60)
    assignments = assign(cards, keys, n_raters=15, cards_per_rater=12)
    result = analyse(_ratings_for(assignments, keys, agree_with_oracle=True), keys)
    assert result.detectable_difference_pp > 0


def test_analysis_warns_when_the_pilot_is_too_small() -> None:
    keys = {"c_0000": _key(0)}
    ratings = [Rating(rater_id="r1", card_id="c_0000", want_to_cook=5, topup_ok=5)]
    result = analyse(ratings, keys)
    assert any("raters" in w for w in result.warnings)
    assert any("rated twice" in w for w in result.warnings)


def test_the_two_questions_are_measured_separately() -> None:
    """If raters answer both identically the correlation says so, which is
    itself the finding — it would mean the card cannot separate "wrong dish"
    from "too much shopping"."""
    cards, keys = _pool(60)
    assignments = assign(cards, keys, n_raters=15, cards_per_rater=12)
    rng = random.Random(7)
    ratings = [
        Rating(
            rater_id=rater,
            card_id=card_id,
            want_to_cook=rng.randint(1, 5),
            topup_ok=rng.randint(1, 5),
        )
        for rater, card_ids in assignments.items()
        for card_id in card_ids
    ]
    result = analyse(ratings, keys)
    assert -0.4 < result.two_question_correlation < 0.4


def test_ratings_for_unknown_cards_are_ignored() -> None:
    keys = {"c_0000": _key(0)}
    ratings = [
        Rating(rater_id="r1", card_id="c_0000", want_to_cook=5, topup_ok=5),
        Rating(rater_id="r1", card_id="c_9999", want_to_cook=1, topup_ok=1),
    ]
    assert analyse(ratings, keys).n_ratings == 1
