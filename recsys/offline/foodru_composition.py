"""Ingredient roles for the PoC proxy; the source recipe remains untouched.

Food.ru's optional_ingredients_blocks contain fillings, sauces and dough as
well as serving suggestions. Dropping all secondary blocks loses real food.
"""

from __future__ import annotations

import re

VERSION = "foodru-composition-v2"


def ingredient_role(ingredient: dict) -> str:
    group = " ".join((ingredient.get("group") or "").lower().replace("ё", "е").split()).strip(" :")
    if group in {"для подачи", "для украшения", "для подачи и украшения", "для украшения и подачи"}:
        return "serving"
    if re.search(r"подач|украшени", group):
        return "mixed"
    # A missing label is allowed for JSON-LD, but does not invent a serving
    # distinction the source did not provide.
    return "dish"


def split_composition(recipe: dict) -> dict:
    roles = {"dish": [], "serving": [], "mixed": []}
    for position, ingredient in enumerate(recipe["ingredients"]):
        roles[ingredient_role(ingredient)].append(position)
    return {
        "policy_version": VERSION,
        "included_indices": roles["dish"],
        "excluded_serving_indices": roles["serving"],
        "unresolved_indices": roles["mixed"],
        "mixed_groups": sorted({recipe["ingredients"][i].get("group") for i in roles["mixed"]}),
        "group_labels_available": any(i.get("group") for i in recipe["ingredients"]),
    }


def proxy_ingredients(recipe: dict, composition: dict) -> list[dict]:
    return [recipe["ingredients"][i] for i in composition["included_indices"]]
