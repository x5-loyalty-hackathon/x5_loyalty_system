"""The frozen baseline catalog, and the candidate pool measured against it.

Why a freeze exists
-------------------
Experiment 3 grew the catalog from 37 to 47 recipes. Every comparison after
that has to answer "against what?", and pointing at ``recsys.experimental.recipes.RECIPES``
is not an answer: that tuple moves whenever someone adds a dish, so a metric
quoted against it silently re-baselines itself and last week's number stops
meaning anything.

So the 37 recipes that existed before experiment 3 are pinned here by id, and
the 10 added by it are pinned separately as *candidates* — recipes proposed but
not yet earned. ``docs/research/recsys/evaluation-protocol.md`` is what says
how a candidate earns its place.

The ids are listed literally rather than derived (e.g. "everything except the
last 10") because a derivation re-computes itself against a moving catalog,
which is the exact failure this module exists to prevent. A test asserts the
listed ids still resolve, so a rename cannot rot the freeze silently.
"""

from __future__ import annotations

import hashlib
import json

from recsys.experimental.contracts import Recipe
from recsys.experimental.recipes import RECIPES, RECIPES_BY_ID

#: The catalog as it stood before experiment 3 — the baseline every catalog
#: claim is measured against.
BASELINE_RECIPE_IDS: tuple[str, ...] = (
    "vegetable_omelette",
    "cottage_cheese_bake",
    "healthy_cottage_cheese_bake",
    "syrniki",
    "bliny",
    "oatmeal_with_banana",
    "chicken_vegetable_stew",
    "buckwheat_with_mushrooms",
    "pasta_tomato",
    "chicken_pilaf",
    "beef_pilaf",
    "meat_cutlets_with_mash",
    "homemade_chicken_nuggets",
    "chicken_potato_soup",
    "borsch",
    "cheese_soup",
    "greek_salad",
    "caesar_salad",
    "apple_pie",
    "chicken_and_vegetables",
    "braised_pork_with_vegetables",
    "chicken_cucumber_salad",
    "vegetable_cheese_salad",
    "cheese_tomato_toast",
    "carrot_fritters",
    "korean_carrot",
    "teriyaki_chicken_noodles",
    "hummus",
    "vinegret",
    "olivier_salad",
    "herring_under_fur_coat",
    "grilled_chicken_skewers",
    "chicken_mushroom_salad",
    "solyanka",
    "meat_french_style",
    "pea_soup_with_smoked_meats",
    "pumpkin_cream_soup",
)

#: Added by experiment 3 (docs/research/recsys/experiment-3-catalog-coverage-report.md).
#: Held as candidates, not as baseline: their coverage gain was measured on a
#: held-out half, but the selection itself was made by looking at the data, and
#: one recipe carried most of the effect. The protocol's +5 comparison is what
#: decides which of these, if any, become baseline.
CANDIDATE_RECIPE_IDS: tuple[str, ...] = (
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
)


def baseline_catalog() -> list[Recipe]:
    """The 37 baseline recipes, in catalog order."""
    ids = set(BASELINE_RECIPE_IDS)
    return [recipe for recipe in RECIPES if recipe.recipe_id in ids]


def candidate_catalog() -> list[Recipe]:
    """The 10 candidate recipes, in catalog order."""
    ids = set(CANDIDATE_RECIPE_IDS)
    return [recipe for recipe in RECIPES if recipe.recipe_id in ids]


def catalog_with(candidate_ids: frozenset[str] | set[str]) -> list[Recipe]:
    """Baseline plus the named candidates — the shape every +N arm takes."""
    unknown = set(candidate_ids) - set(CANDIDATE_RECIPE_IDS)
    if unknown:
        raise KeyError(f"not candidate recipes: {sorted(unknown)}")
    return baseline_catalog() + [
        recipe for recipe in RECIPES if recipe.recipe_id in candidate_ids
    ]


def recipe_content_hash(recipes: list[Recipe]) -> str:
    """Hash of what the recipes *are*, not just which ids are present.

    Ingredient lists and prep times move coverage numbers, so a freeze that
    only pinned ids would let a recipe be silently rewritten under a stable
    name and take the baseline with it.
    """
    payload = json.dumps(
        [recipe.model_dump(mode="json") for recipe in recipes],
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def missing_ids() -> tuple[str, ...]:
    """Frozen ids that no longer resolve — a rename or deletion broke the freeze."""
    return tuple(
        recipe_id
        for recipe_id in BASELINE_RECIPE_IDS + CANDIDATE_RECIPE_IDS
        if recipe_id not in RECIPES_BY_ID
    )
