"""Compatibility helpers for rendering public recipe reasons in examples.

The executable public registry lives in :mod:`app.explanations`. Model
adapters may still emit richer internal feature codes, but those are consumed
by backend logic and must not be rendered as raw UI text.
"""

from __future__ import annotations

from app.explanations import RECIPE_REASON_TEXT

REASON_CODE_TEXT: dict[str, str] = RECIPE_REASON_TEXT


def text(code: str) -> str:
    """Generic, context-free Russian text for a reason code."""
    return REASON_CODE_TEXT.get(code, "Причина рекомендации недоступна")


def overlap_text(hits: int, total: int) -> str:
    return f"{hits} из {total} ингредиентов уже есть в сегодняшнем чеке"


def missing_text(missing_count: int) -> str:
    word = "продукт" if missing_count == 1 else ("продукта" if 1 < missing_count < 5 else "продуктов")
    return f"нужно докупить {missing_count} {word}"
