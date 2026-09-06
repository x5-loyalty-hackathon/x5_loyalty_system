"""Ingredient-to-SKU bridge for the synthetic catalog.

The PoC has no licensed X5 assortment feed, therefore ``sku_id`` values are
deliberately synthetic.  The mapping keeps that fact explicit and records
search terms for a future Open Food Facts / retailer resolver without
pretending that an EAN is an X5 SKU.
"""

from __future__ import annotations

from dataclasses import dataclass

from recsys.catalog import INGREDIENTS


@dataclass(frozen=True)
class IngredientSkuMapping:
    ingredient_id: str
    synthetic_sku_prefix: str
    external_search_terms: tuple[str, ...]


_SEARCH_TERM_OVERRIDES: dict[str, tuple[str, ...]] = {
    "greek_yogurt": ("йогурт греческий",),
    "processed_cheese": ("сыр плавленый",),
    "green_beans": ("фасоль стручковая",),
    "vegetable_mix": ("смесь овощная",),
    "beetroot": ("свекла",),
    "parsley_root": ("корень петрушки",),
    "romaine_lettuce": ("салат романо",),
    "cherry_tomato": ("томаты черри",),
    "cutlet_semi_finished": ("котлеты полуфабрикаты",),
    "black_pepper": ("перец черный молотый",),
    "dried_herbs": ("травы сушеные",),
    "dried_apricots": ("курага",),
    "caesar_dressing": ("соус цезарь",),
    "breadcrumbs": ("сухари панировочные",),
    "green_peas": ("горошек зеленый консервированный",),
    "pickled_cucumber": ("огурцы соленые",),
    "boiled_sausage": ("колбаса вареная",),
    "smoked_meats": ("копчености", "грудинка копченая"),
    "herring": ("сельдь соленая",),
    "sauerkraut": ("капуста квашеная",),
    "korean_seasoning": ("приправа для моркови по-корейски",),
    "soy_sauce": ("соус соевый",),
    "teriyaki_sauce": ("соус терияки",),
    "tahini": ("паста кунжутная тахини",),
    "dried_peas": ("горох сухой колотый",),
    "noodles": ("лапша пшеничная",),
}


INGREDIENT_SKU_MAPPINGS: dict[str, IngredientSkuMapping] = {
    ingredient_id: IngredientSkuMapping(
        ingredient_id=ingredient_id,
        synthetic_sku_prefix=f"syn_{ingredient_id}",
        external_search_terms=_SEARCH_TERM_OVERRIDES.get(
            ingredient_id, (definition.name.lower(),)
        ),
    )
    for ingredient_id, definition in INGREDIENTS.items()
}


def synthetic_sku_id(ingredient_id: str, source: str, index: int) -> str:
    """Return a transparent, deterministic synthetic SKU identifier."""
    return f"{INGREDIENT_SKU_MAPPINGS[ingredient_id].synthetic_sku_prefix}_{source}_{index}"
