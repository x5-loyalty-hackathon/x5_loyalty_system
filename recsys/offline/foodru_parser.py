"""Parse public food.ru HTML without executing JavaScript or calling its API."""

from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse


class RecipeParseError(ValueError):
    pass


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[tuple[dict[str, str], str]] = []
        self.attrs: dict[str, str] | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "script":
            self.attrs = dict(attrs)
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.attrs is not None:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.attrs is not None:
            self.scripts.append((self.attrs, "".join(self.parts)))
            self.attrs = None


def objects(value: Any):
    """Walk both JSON-LD @graph and Next.js state without hashed store keys."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def rich_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    if value.get("type") == "text":
        return value.get("content", "")
    separator = "\n" if value.get("type") == "document" else ""
    return separator.join(rich_text(x) for x in value.get("children", []))


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def parse_recipe(html: str, url: str, fetched_at: str) -> dict:
    parser = _Scripts()
    parser.feed(html)
    structured, state = [], []
    for attrs, content in parser.scripts:
        if attrs.get("type") != "application/ld+json" and attrs.get("id") != "__NEXT_DATA__":
            continue
        try:
            data = json.loads(content)
        except (ValueError, TypeError):
            continue
        (state if attrs.get("id") == "__NEXT_DATA__" else structured).extend(objects(data))
    match = re.search(r"/recipes/(\d+)(?:-|$)", urlparse(url).path)
    if not match or urlparse(url).hostname != "food.ru":
        raise RecipeParseError(f"Not a food.ru recipe URL: {url}")
    source_id = int(match[1])
    ld = next((x for x in structured if "Recipe" in (
        x.get("@type", []) if isinstance(x.get("@type"), list) else [x.get("@type")]
    )), {})
    canonical = ld.get("url") or url
    canonical_id = re.search(r"/recipes/(\d+)(?:-|$)", urlparse(canonical).path)
    if urlparse(canonical).hostname != "food.ru" or not canonical_id:
        raise RecipeParseError(f"Unexpected canonical recipe URL: {canonical}")
    source_id = int(canonical_id[1])
    detail = next((x for x in state if x.get("id") == source_id
                   and "main_ingredients_block" in x), {})
    title = detail.get("title") or ld.get("name")
    ingredients = []
    blocks = [detail.get("main_ingredients_block") or {},
              *(detail.get("optional_ingredients_blocks") or [])]
    for block in blocks:
        for product in block.get("products", []):
            if not isinstance(product, dict) or not product.get("title"):
                raise RecipeParseError(f"Ingredient without a name: {url}")
            unit = product.get("custom_measure")
            unquantified = unit in {"по вкусу", "по желанию"}
            ingredients.append({
                "name": product["title"],
                "foodru_product_id": product.get("id"),
                "quantity": None if unquantified else _number(product.get("custom_measure_count")),
                "unit": unit,
                "weight_g": None if unquantified else _number(product.get("weight")),
                "group": block.get("title"),
            })
    if not ingredients:
        ingredients = [{"name": x, "raw": x, "quantity": None, "unit": None,
                        "weight_g": None, "group": None, "foodru_product_id": None}
                       for x in ld.get("recipeIngredient", []) if isinstance(x, str)]
    if not title or not ingredients:
        raise RecipeParseError(f"Missing title/ingredients: {url}")
    rating_state = next((x for x in state if x.get("material_id") == source_id
                         and x.get("material_type") == "recipe" and "total_rating" in x), {})
    aggregate = ld.get("aggregateRating") or {}
    count = _number(rating_state.get("rating_count", aggregate.get("ratingCount")))
    rating_value = _number(rating_state.get("total_rating", aggregate.get("ratingValue")))
    rating = None if count == 0 or rating_value is None else {
        "value": rating_value, "count": int(count) if count is not None else None,
        "best": _number(aggregate.get("bestRating")) or 5.0,
    }
    # Keep only comments belonging to this recipe. Never copy user/x5 IDs,
    # profiles, avatars or names from the page's serialized state.
    comments = {}
    totals = []
    for container in state:
        if not isinstance(container.get("comments"), list):
            continue
        rows = container["comments"]
        relevant = [x for x in rows if x.get("material_id") == source_id
                    and x.get("material_type") == "recipe"]
        if relevant and len(relevant) == len(rows) and isinstance(container.get("total_count"), int):
            totals.append(container["total_count"])
        for row in relevant:
            body = rich_text(row.get("content")).strip()
            if body:
                key = str(row.get("id") or hashlib.sha256(body.encode()).hexdigest())
                comments[key] = {"source_comment_id": row.get("id"), "text": body,
                                 "published_at": row.get("created_at")}
    # Empty comment state alone does not establish that there are no reviews:
    # some pages omit or lazy-load them. Preserve unknown separately from zero.
    total = max(totals) if totals else None
    reviews = list(comments.values())
    return {
        "recipe_id": f"foodru_{source_id}", "source_id": source_id,
        "title": title, "source_url": canonical,
        "fetched_at": fetched_at, "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
        "ingredients": ingredients, "ingredient_lines": ld.get("recipeIngredient", []),
        "servings": detail.get("measure_count"), "yield_text": ld.get("recipeYield"),
        "preparation_minutes": detail.get("total_cooking_time"),
        "category": ld.get("recipeCategory"), "cuisine": ld.get("recipeCuisine"),
        "rating": rating, "reviews": reviews,
        "reviews_total": total, "reviews_collected": len(reviews),
        "reviews_status": ("complete" if total is not None and len(reviews) >= total
                           else "partial" if reviews else "not_exposed"),
        "ingredients_source": "next_data" if detail else "json_ld",
    }
