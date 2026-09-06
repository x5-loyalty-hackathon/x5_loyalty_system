"""Catalog-only fields: preserve ML teammate metadata without changing API 1.2.

Serving quantity is approximate editorial data, not a safety or stock assertion.
See docs/integration-handoff.md before exposing new fields in the mobile API.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RecipeMetadata:
    servings: int
    dish_type: str
    cuisine: str


# Filled when recsys.recipes constructs RECIPES; not part of the HTTP schema.
RECIPE_METADATA: dict[str, RecipeMetadata] = {}
