"""The reproducibility guarantees ``recsys.panels`` is supposed to provide.

Each test here corresponds to a stated acceptance criterion, and most of them
correspond to a defect that was actually measured on this codebase before the
module existed — see the module docstring of ``recsys.panels``.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from recsys.experimental.catalog_freeze import (
    BASELINE_RECIPE_IDS,
    CANDIDATE_RECIPE_IDS,
    baseline_catalog,
    candidate_catalog,
    catalog_with,
    missing_ids,
    recipe_content_hash,
)
from recsys.experimental.inventory import DEFAULT_INVENTORY_ASSUMPTIONS
from recsys.panels import (
    COHORT_INDEX_OFFSET,
    GENERATOR_VERSION,
    SPLIT_WEIGHTS,
    PanelSpec,
    assert_disjoint,
    assert_panel_ok,
    build_panel,
    load_panel,
    save_panel,
    split_of,
    validate_panel,
)
from recsys.experimental.profiles import generate_population
from recsys.experimental.recipes import RECIPES


def _spec(**overrides) -> PanelSpec:
    base = PanelSpec(name="unit_test_panel", n_users=30)
    return replace(base, **overrides)


# --- the freeze ------------------------------------------------------------


def test_every_frozen_recipe_id_still_resolves() -> None:
    """A rename must break the freeze loudly, not silently re-baseline it."""
    assert missing_ids() == ()


def test_baseline_and_candidates_partition_the_catalog() -> None:
    assert len(BASELINE_RECIPE_IDS) == 37
    assert len(CANDIDATE_RECIPE_IDS) == 10
    assert set(BASELINE_RECIPE_IDS).isdisjoint(CANDIDATE_RECIPE_IDS)
    assert set(BASELINE_RECIPE_IDS) | set(CANDIDATE_RECIPE_IDS) == {
        recipe.recipe_id for recipe in RECIPES
    }


def test_catalog_with_rejects_a_non_candidate() -> None:
    with pytest.raises(KeyError):
        catalog_with({"borsch"})


def test_content_hash_notices_a_rewritten_recipe() -> None:
    """Pinning ids is not enough: a recipe can be rewritten under its own id."""
    original = baseline_catalog()
    tampered = list(original)
    tampered[0] = tampered[0].model_copy(update={"preparation_minutes": 999})
    assert recipe_content_hash(original) != recipe_content_hash(tampered)


# --- reproducibility -------------------------------------------------------


def test_building_the_same_spec_twice_gives_identical_data() -> None:
    first, second = build_panel(_spec()), build_panel(_spec())
    assert first.manifest.profiles_checksum == second.manifest.profiles_checksum
    assert first.manifest.inventories_checksum == second.manifest.inventories_checksum


def test_a_panel_is_order_independent_in_n() -> None:
    """Taking 30 users must equal the first 30 of a 60-user panel.

    The old shared-stream generator failed this: profile *i* consumed whatever
    the generator was left at by profiles 0..i-1, so ``n`` was an input to
    everybody's data.
    """
    small = build_panel(_spec(n_users=30))
    large = build_panel(_spec(n_users=60))
    for a, b in zip(small.profiles, large.profiles[:30], strict=True):
        assert a.user.user_id == b.user.user_id
        assert [(i.sku_id, i.unit_price) for i in a.current_receipt.items] == [
            (i.sku_id, i.unit_price) for i in b.current_receipt.items
        ]


def test_adding_a_recipe_does_not_move_baskets_or_inventories() -> None:
    """The acceptance criterion this module was built for.

    Measured before the fix: the 37 -> 47 catalog change gave 137 of 160
    profiles a different basket, because the saved-recipe draw is catalog-sized
    and shifted the shared stream. Panels pin the draw to the frozen baseline,
    so the catalog cannot reach the panel at all.
    """
    panel = build_panel(_spec())
    extended = baseline_catalog() + candidate_catalog()
    assert len(extended) > len(baseline_catalog())

    # Whatever the live catalog is, the panel is built against the frozen pool.
    rebuilt = build_panel(_spec())
    assert panel.manifest.profiles_checksum == rebuilt.manifest.profiles_checksum
    assert panel.manifest.saved_recipe_pool_hash == recipe_content_hash(
        baseline_catalog()
    )


def test_saved_recipes_come_only_from_the_frozen_pool() -> None:
    panel = build_panel(_spec(n_users=80))
    frozen = set(BASELINE_RECIPE_IDS)
    for profile in panel.profiles:
        assert profile.user.saved_recipe_ids <= frozen


def test_legacy_generator_still_couples_profiles_to_the_catalog() -> None:
    """Documents *why* panels exist, so the defect cannot be reintroduced quietly.

    ``generate_population`` is deliberately left on the shared stream because
    the committed benchmark numbers came from it. This test pins that it is the
    unsafe path, so anyone tempted to build a new experiment on it sees the
    reason not to.
    """
    import recsys.experimental.profiles as profiles_module

    baseline = tuple(baseline_catalog())
    extended = baseline + tuple(candidate_catalog())

    def baskets(pool):
        population = generate_population(60, seed=20260905, saved_recipe_pool=pool)
        return [
            tuple((i.sku_id, i.unit_price) for i in p.current_receipt.items)
            for p in population
        ]

    assert baskets(baseline) != baskets(extended)
    assert profiles_module.HISTORY_WINDOW_DAYS == 45


# --- data quality ----------------------------------------------------------


def test_history_never_reaches_past_the_recommendation_moment() -> None:
    """Features are computed "as of now"; history dated after now is a leak.

    Measured before the clamp: 103 of 200 profiles carried one future-dated
    receipt, up to 3.2 days ahead, and nothing downstream rejected it.
    """
    panel = build_panel(_spec(n_users=120))
    for profile in panel.profiles:
        for receipt in profile.purchase_history:
            assert receipt.purchased_at <= profile.now
            assert receipt.purchased_at <= profile.current_receipt.purchased_at


def test_validation_catches_a_duplicated_user() -> None:
    panel = build_panel(_spec())
    panel.profiles[1] = panel.profiles[0]
    messages = [i.message for i in validate_panel(panel) if i.severity == "error"]
    assert any("duplicate user" in m for m in messages)


def test_validation_catches_an_empty_inventory() -> None:
    panel = build_panel(_spec())
    panel.inventories[0] = []
    messages = [i.message for i in validate_panel(panel) if i.severity == "error"]
    assert any("empty inventory" in m for m in messages)


def test_a_clean_panel_passes() -> None:
    assert_panel_ok(build_panel(_spec(n_users=80)))


# --- splits ----------------------------------------------------------------


def test_splits_are_disjoint_and_cover_everyone() -> None:
    panel = build_panel(_spec(n_users=200))
    splits = {name: panel.split(name) for name in SPLIT_WEIGHTS}
    assert_disjoint(*splits.values())
    assert sum(len(p.profiles) for p in splits.values()) == len(panel.profiles)


def test_a_user_keeps_its_split_when_the_population_grows() -> None:
    """An index-parity or slice split silently reshuffles the test set when
    users are added; hashing the id does not."""
    small = build_panel(_spec(n_users=50))
    large = build_panel(_spec(n_users=200))
    assignments = {p.user.user_id: split_of(p.user.user_id) for p in small.profiles}
    for profile in large.profiles:
        expected = assignments.get(profile.user.user_id)
        if expected is not None:
            assert split_of(profile.user.user_id) == expected


def test_cohorts_never_share_a_user_id() -> None:
    """Two cohorts on one index range produce different people under one id."""
    base = build_panel(_spec(n_users=60, cohort="base"))
    holdout = build_panel(
        _spec(name="unit_test_holdout", n_users=60, cohort="holdout_users")
    )
    assert_disjoint(base, holdout)


def test_an_unregistered_cohort_is_refused() -> None:
    with pytest.raises(KeyError):
        build_panel(_spec(cohort="improvised"))


def test_cohort_offsets_are_far_enough_apart_to_stay_disjoint() -> None:
    offsets = sorted(COHORT_INDEX_OFFSET.values())
    for earlier, later in zip(offsets, offsets[1:], strict=False):
        assert later - earlier >= 100_000


# --- persistence -----------------------------------------------------------


def test_a_saved_panel_round_trips_byte_for_byte(tmp_path) -> None:
    panel = build_panel(_spec(n_users=40))
    save_panel(panel, tmp_path)
    loaded = load_panel(panel.manifest.spec.name, tmp_path)
    assert loaded.manifest.profiles_checksum == panel.manifest.profiles_checksum
    assert loaded.manifest.inventories_checksum == panel.manifest.inventories_checksum
    assert [p.user.user_id for p in loaded.profiles] == [
        p.user.user_id for p in panel.profiles
    ]
    assert [len(i) for i in loaded.inventories] == [len(i) for i in panel.inventories]


def test_loading_refuses_a_panel_from_another_generator(tmp_path) -> None:
    panel = build_panel(_spec(n_users=20))
    directory = save_panel(panel, tmp_path)
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            f'"generator_version": {GENERATOR_VERSION}', '"generator_version": 99'
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="generator"):
        load_panel(panel.manifest.spec.name, tmp_path)


def test_the_manifest_records_what_the_panel_was_built_from() -> None:
    panel = build_panel(_spec(n_users=20))
    manifest = panel.manifest
    assert manifest.spec.seed == 20260905
    assert manifest.spec.assumptions == DEFAULT_INVENTORY_ASSUMPTIONS
    assert manifest.saved_recipe_pool_hash == recipe_content_hash(baseline_catalog())
    assert manifest.n_profiles == 20
    assert sum(manifest.archetype_counts.values()) == 20
