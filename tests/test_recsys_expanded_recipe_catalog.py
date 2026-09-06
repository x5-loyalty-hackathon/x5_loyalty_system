from recsys.catalog import BASE_PRICE_RUB, INGREDIENTS
from recsys.recipes import RECIPES_BY_ID
from recsys.sku_mapping import INGREDIENT_SKU_MAPPINGS, synthetic_sku_id


TXT_RECIPE_IDS = {
    "vegetable_omelette", "cottage_cheese_bake", "healthy_cottage_cheese_bake",
    "syrniki", "bliny", "oatmeal_with_banana", "chicken_vegetable_stew",
    "buckwheat_with_mushrooms", "pasta_tomato", "chicken_pilaf", "beef_pilaf",
    "meat_cutlets_with_mash", "homemade_chicken_nuggets", "chicken_potato_soup",
    "borsch", "cheese_soup", "greek_salad", "caesar_salad", "apple_pie",
}


def test_every_recipe_from_the_supplied_file_is_in_the_catalog() -> None:
    assert TXT_RECIPE_IDS.issubset(RECIPES_BY_ID)


def test_every_recipe_ingredient_has_price_and_synthetic_sku_mapping() -> None:
    recipe_ingredient_ids = {
        ingredient.ingredient_id
        for recipe_id in TXT_RECIPE_IDS
        for ingredient in RECIPES_BY_ID[recipe_id].ingredients
    }
    assert recipe_ingredient_ids.issubset(INGREDIENTS)
    assert recipe_ingredient_ids.issubset(BASE_PRICE_RUB)
    assert recipe_ingredient_ids.issubset(INGREDIENT_SKU_MAPPINGS)


def test_synthetic_skus_are_explicitly_not_retailer_skus() -> None:
    assert synthetic_sku_id("garlic", "fp", 3) == "syn_garlic_fp_3"
