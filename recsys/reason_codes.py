"""Reason code registry: explainability for the model layer.

Extends the ad hoc strings already used in
``app.recommender.DeterministicMockEngine`` (``current_receipt_overlap``,
``saved_recipe_repeat``, ``category_history_match``, ``quick_recipe``,
``personalized_discovery``) with the richer set implied by the worked
examples in ``docs/research/persona_vxofi/rescue-domovoi-concept.md §7/§14``.

Codes stay plain, context-free flags — matching the existing mock's
convention and the ``ModelRecommendation.reason_codes: list[str]`` schema —
so a frontend can map each code to localized copy once. Counts (e.g. "2 из 7
ингредиентов" or "докупить 2 продукта") are *not* baked into the code
string: they're already available separately on the API response
(``RecipeRecommendation.missing_count``), and ``overlap_text``/``missing_text``
below are just formatting helpers for this repo's own example output and
docs, not part of the API contract.
"""

from __future__ import annotations

REASON_CODE_TEXT: dict[str, str] = {
    "current_receipt_overlap": "часть ингредиентов уже есть в сегодняшнем чеке",
    "saved_recipe_repeat": "вы уже сохраняли этот рецепт",
    "category_history_match": "вы регулярно покупаете продукты этой категории",
    "quick_recipe": "рецепт занимает не больше 30 минут",
    "personalized_discovery": "новый рецепт, подобранный под вашу обычную кухню и бюджет",
    "low_missing_count": "нужно докупить совсем немного продуктов",
    "markdown_supply_likely": "часть недостающих продуктов часто встречается по уценке рядом",
    "brand_affinity_match": "среди ингредиентов есть ваши обычные бренды",
    "usual_price_band": "стоимость докупки соответствует вашему обычному чеку",
    "high_discovery_acceptance": "вы часто принимаете новые предложения рецептов",
    "home_ingredient_reuse": "часть ингредиентов вы уже отметили как «есть дома»",
    "wide_basket_fit": "рецепт хорошо сочетается с широтой вашей обычной корзины",
}


def text(code: str) -> str:
    """Generic, context-free Russian text for a reason code."""
    return REASON_CODE_TEXT.get(code, code)


def overlap_text(hits: int, total: int) -> str:
    return f"{hits} из {total} ингредиентов уже есть в сегодняшнем чеке"


def missing_text(missing_count: int) -> str:
    word = "продукт" if missing_count == 1 else ("продукта" if 1 < missing_count < 5 else "продуктов")
    return f"нужно докупить {missing_count} {word}"
