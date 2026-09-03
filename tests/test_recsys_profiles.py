from collections import Counter

from app.contracts import Receipt, UserProfile
from recsys.profiles import ARCHETYPES, generate_balanced_sample, generate_population


def test_population_share_sums_to_one() -> None:
    assert abs(sum(a.population_share for a in ARCHETYPES.values()) - 1.0) < 1e-9


def test_generated_profiles_validate_against_the_real_contract_schema() -> None:
    for profile in generate_population(15, seed=1):
        assert isinstance(profile.user, UserProfile)
        assert isinstance(profile.current_receipt, Receipt)
        assert all(isinstance(r, Receipt) for r in profile.purchase_history)
        assert profile.archetype in ARCHETYPES
        assert profile.current_receipt.items
        assert profile.purchase_history, "profile should have purchase history to personalize on"


def test_generation_is_deterministic_given_a_seed() -> None:
    a = generate_population(20, seed=99)
    b = generate_population(20, seed=99)
    assert [p.user.user_id for p in a] == [p.user.user_id for p in b]
    assert [p.archetype for p in a] == [p.archetype for p in b]
    assert [len(p.purchase_history) for p in a] == [len(p.purchase_history) for p in b]


def test_large_population_roughly_matches_archetype_weights() -> None:
    population = generate_population(2000, seed=7)
    counts = Counter(p.archetype for p in population)
    for name, params in ARCHETYPES.items():
        observed_share = counts[name] / len(population)
        assert abs(observed_share - params.population_share) < 0.06, (
            f"{name}: observed {observed_share:.2f} vs configured {params.population_share:.2f}"
        )


def test_generate_balanced_sample_covers_every_archetype() -> None:
    sample = generate_balanced_sample(2, seed=3)
    assert len(sample) == 2 * len(ARCHETYPES)
    counts = Counter(p.archetype for p in sample)
    assert all(counts[name] == 2 for name in ARCHETYPES)


def test_radius_and_time_archetypes_are_behaviorally_distinct() -> None:
    # time_limited profiles should skew to smaller radii than explorer ones —
    # a cheap sanity check that the archetype parameters actually differ.
    time_limited = [p for p in generate_population(300, seed=11) if p.archetype == "time_limited"]
    explorer = [p for p in generate_population(300, seed=11) if p.archetype == "explorer"]
    assert time_limited and explorer
    avg_radius_time_limited = sum(p.user.radius_km for p in time_limited) / len(time_limited)
    avg_radius_explorer = sum(p.user.radius_km for p in explorer) / len(explorer)
    assert avg_radius_time_limited < avg_radius_explorer
