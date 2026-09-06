"""Public explainability vocabulary for the API contract.

Model adapters may use richer internal features. Only codes registered here
are allowed to leave the backend, so the frontend never has to display an
unknown identifier or infer what a score meant.
"""

NO_RESERVATION_WARNING = (
    "Markdown availability is best-effort: the item is not reserved."
)
NO_SAFE_RECOMMENDATIONS_WARNING = (
    "No safe recommendations are currently available."
)

PUBLIC_WARNING_TEXT: dict[str, str] = {
    "markdown_not_reserved": NO_RESERVATION_WARNING,
    "no_safe_recommendations_available": NO_SAFE_RECOMMENDATIONS_WARNING,
}
PUBLIC_WARNING_VALUES = frozenset(PUBLIC_WARNING_TEXT.values())

CHALLENGE_REASON_TEXT: dict[str, str] = {
    "explicit_mode_request": "Тип челленджа выбран пользователем.",
    "current_basket_strategy": "Используем продукты из текущего чека.",
    "saved_recipe_strategy": "Предлагаем повторить сохранённый рецепт.",
    "novel_recipe_strategy": "Предлагаем новый для пользователя рецепт.",
    "selected_by_effort_then_relevance": (
        "Это самый простой подходящий вариант: меньше докупок, затем выше релевантность."
    ),
    "full_basket_requires_explicit_choice": (
        "Для рецепта нужна полная новая корзина, поэтому он доступен только по выбору."
    ),
}

RECIPE_REASON_TEXT: dict[str, str] = {
    "current_receipt_overlap": "Часть ингредиентов уже есть в текущем чеке.",
    "category_history_match": "Эта категория встречалась в истории покупок.",
    "quick_recipe": "Приготовление занимает не больше 30 минут.",
    "low_missing_count": "Нужно докупить не больше двух продуктов.",
    "home_ingredient_reuse": "Используются продукты, отмеченные как имеющиеся дома.",
    "safe_markdown_option_available": "Есть прошедший проверку вариант по уценке.",
    "preferred_brand_option_available": "Среди вариантов есть предпочитаемый бренд.",
    "safe_ready_option_available": "Есть прошедший проверку вариант готового блюда.",
    "safe_recipe_available": "Рецепт можно безопасно собрать из доступных вариантов.",
}

ROUTE_REASON_TEXT: dict[str, str] = {
    "explicit_cook_preference": "Пользователь предпочитает готовить.",
    "explicit_ready_preference": "Пользователь предпочитает готовую еду.",
    "prepared_food_share_supports_ready": (
        "В истории покупок не меньше половины позиций приходится на готовую еду."
    ),
    "ingredient_purchase_history_supports_cook": (
        "История покупок больше соответствует приготовлению дома."
    ),
    "cook_route_unavailable": "Безопасный вариант приготовления сейчас недоступен.",
    "ready_route_unavailable": "Безопасный вариант готового блюда сейчас недоступен.",
    "cook_route_fallback": "Поэтому используем доступный сценарий приготовления.",
    "ready_route_fallback": "Поэтому используем доступный вариант готового блюда.",
    "only_ready_route_available": "Сейчас доступен только вариант готового блюда.",
}

STORE_REASON_TEXT: dict[str, str] = {
    "explicit_store_choice": "Точка выбрана пользователем.",
    "maximum_ingredient_coverage": (
        "В этой точке доступно больше всего недостающих ингредиентов."
    ),
    "preferred_store_for_anchor": (
        "При равном покрытии выбрана привычная точка для этого места."
    ),
    "nearest_store_tiebreak": (
        "При равном покрытии выбрана ближайшая точка."
    ),
}

CHALLENGE_REASON_CODES = frozenset(CHALLENGE_REASON_TEXT)
RECIPE_REASON_CODES = frozenset(RECIPE_REASON_TEXT)
ROUTE_REASON_CODES = frozenset(ROUTE_REASON_TEXT)
STORE_REASON_CODES = frozenset(STORE_REASON_TEXT)


def public_reason_text(code: str) -> str | None:
    """Return safe localized copy; unknown/internal codes are never echoed."""
    return (
        CHALLENGE_REASON_TEXT.get(code)
        or RECIPE_REASON_TEXT.get(code)
        or ROUTE_REASON_TEXT.get(code)
        or STORE_REASON_TEXT.get(code)
    )
