import itertools
from collections import Counter
from dataclasses import fields

from recsys.profiles import ARCHETYPES, ArchetypeParams
from recsys.regimes import (
    BALANCED_SAMPLE_9,
    DIALS,
    NEUTRAL_LEVEL,
    NEUTRAL_REGIME,
    REGIMES,
    Regime,
    build_regimes,
    regimes_where,
)


def test_grid_is_the_full_crossing_of_every_dial() -> None:
    expected = 1
    for levels in DIALS.values():
        expected *= len(levels)
    assert len(REGIMES) == expected
    assert len(REGIMES) == len({r.name for r in REGIMES})
    # The requested band was 20-30 worlds: enough to see a pattern, few enough
    # that a person can read the per-regime table.
    assert 20 <= len(REGIMES) <= 30


def test_neutral_regime_reproduces_the_shipped_population_exactly() -> None:
    """The grid must contain today's world, or nothing is comparable to it."""
    assert NEUTRAL_REGIME.is_neutral
    assert NEUTRAL_REGIME is REGIMES[0]
    assert NEUTRAL_REGIME.archetypes() == ARCHETYPES
    assert all(level == NEUTRAL_LEVEL for _, level in NEUTRAL_REGIME.levels)


def test_dials_move_only_the_three_behavioural_parameters() -> None:
    dialled = {"discovery_acceptance", "markdown_affinity", "repeat_probability"}
    extreme = max(REGIMES, key=lambda r: r.multiplier("novelty"))
    for name, params in extreme.archetypes().items():
        original = ARCHETYPES[name]
        for field in fields(ArchetypeParams):
            if field.name in dialled:
                continue
            assert getattr(params, field.name) == getattr(original, field.name), (
                f"{name}.{field.name} moved but is not a dial"
            )


def test_population_shares_are_untouched_by_any_regime() -> None:
    """Mixture is deliberately not a dial — see the module docstring."""
    for regime in REGIMES:
        table = regime.archetypes()
        for name, params in table.items():
            assert params.population_share == ARCHETYPES[name].population_share
        assert abs(sum(p.population_share for p in table.values()) - 1.0) < 1e-9


def test_dialled_parameters_stay_probabilities() -> None:
    for regime in REGIMES:
        for params in regime.archetypes().values():
            assert 0.0 <= params.discovery_acceptance <= 1.0
            assert 0.0 <= params.markdown_affinity <= 1.0
            assert 0.0 <= params.repeat_probability <= 1.0


def test_high_and_low_levels_actually_differ() -> None:
    """A grid whose worlds coincide would silently test nothing."""
    high = next(r for r in REGIMES if r.level_map["novelty"] == "high")
    low = next(r for r in REGIMES if r.level_map["novelty"] == "low")
    high_values = [p.discovery_acceptance for p in high.archetypes().values()]
    low_values = [p.discovery_acceptance for p in low.archetypes().values()]
    assert high_values != low_values
    assert all(h >= low for h, low in zip(high_values, low_values, strict=True))


def test_slicing_by_dial_level() -> None:
    for dial, levels in DIALS.items():
        sliced = [regimes_where(dial, level) for level in levels]
        assert sum(len(s) for s in sliced) == len(REGIMES)
        for level, subset in zip(levels, sliced, strict=True):
            assert all(r.level_map[dial] == level for r in subset)


def test_build_is_deterministic_and_regimes_are_hashable() -> None:
    assert build_regimes() == REGIMES
    assert len({r for r in REGIMES}) == len(REGIMES)
    assert isinstance(REGIMES[0], Regime)


def test_balanced_sample_covers_every_dial_level_equally() -> None:
    """The nine-world sample must be a design, not the head of a sorted list.

    ``REGIMES[:9]`` looked like a sample and was not: ``build_regimes`` sorts
    by name, ``"high" < "low" < "mid"``, so the first nine worlds were the
    neutral one plus every ``novelty=high`` world — a sweep that never varied
    the dial it looked like it was varying.
    """
    assert len(BALANCED_SAMPLE_9) == 9
    assert len(set(BALANCED_SAMPLE_9)) == 9
    for dial, levels in DIALS.items():
        counts = Counter(r.level_map[dial] for r in BALANCED_SAMPLE_9)
        assert set(counts) == set(levels), f"{dial} misses a level: {counts}"
        assert set(counts.values()) == {3}, f"{dial} is unbalanced: {counts}"


def test_balanced_sample_is_pairwise_orthogonal_and_contains_the_neutral_world() -> None:
    """Strength-2: every pair of levels across any two dials appears once.

    That is what buys a 9-cell sweep the right to talk about a dial's effect
    without the other dials being confounded with it.
    """
    assert NEUTRAL_REGIME in BALANCED_SAMPLE_9
    for left, right in itertools.combinations(DIALS, 2):
        pairs = Counter(
            (r.level_map[left], r.level_map[right]) for r in BALANCED_SAMPLE_9
        )
        assert len(pairs) == 9, f"{left}x{right} does not cover every pair: {pairs}"
        assert set(pairs.values()) == {1}, f"{left}x{right} is unbalanced: {pairs}"


def test_the_old_naive_slice_would_fail_the_balance_bar() -> None:
    """Guard the regression itself, so nobody reintroduces ``REGIMES[:9]``."""
    naive = REGIMES[:9]
    novelty_levels = Counter(r.level_map["novelty"] for r in naive)
    assert set(novelty_levels.values()) != {3}, (
        "REGIMES[:9] is balanced now — if the sort order changed, this test and "
        "BALANCED_SAMPLE_9's docstring both need rereading"
    )
