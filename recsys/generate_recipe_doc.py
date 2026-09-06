"""Rebuild ``docs/recipe-catalog.md`` from the recipe catalog and pair table.

The document is a review surface: it is what someone reads to check the recipes
themselves — ingredient lists, what is seasoning, which dishes X5 already sells
ready-made and for how much. It is generated rather than written so it cannot
drift from ``recsys.recipes`` the way a hand-maintained list would.

Usage::

    python -m recsys.generate_recipe_doc
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from recsys.catalog import (
    BASE_PRICE_RUB,
    PRICE_REFERENCE,
    REFERENCE_MEDIAN_PRICE_RUB,
    observed_price_era_multiplier,
)
from recsys.ready_food_pairs import (
    PAIRS_BY_RECIPE_ID,
    READY_FOOD_CATALOG,
    RECIPES_WITHOUT_READY_FOOD_PAIR,
    SNAPSHOT_IDS,
)
from recsys.recipes import QUICK_RECIPE_MINUTES, RECIPES

OUTPUT_PATH = Path("docs/recipe-catalog.md")

#: Recipes added because the ready-food snapshot showed a stocked counterpart.

NEW_FOR_READY_FOOD = {
    "korean_carrot", "teriyaki_chicken_noodles", "hummus", "vinegret",
    "olivier_salad", "herring_under_fur_coat", "grilled_chicken_skewers",
    "chicken_mushroom_salad", "solyanka", "meat_french_style",
    "pea_soup_with_smoked_meats", "pumpkin_cream_soup",
}

#: Why a recipe has no counterpart, so the table states a reviewed reason
#: rather than an empty cell.
NO_PAIR_REASON = {
    "cheese_soup": "ноль совпадений в снимке",
    "greek_salad": "ноль совпадений в снимке",
    "apple_pie": "по названию ловится только слойка с яблоком — ложный матч",
    "carrot_fritters": "по названию ловится «оладушек куриный» — ложный матч",
    "buckwheat_with_mushrooms": (
        "гречка в снимке есть, но ни одного варианта с грибами — "
        "только с маслом, индейкой или печенью"
    ),
    "chicken_vegetable_stew": "аналоги есть в снимке, но не в Москве",
    "braised_pork_with_vegetables": "слишком общее блюдо, готового эквивалента нет",
    "chicken_cucumber_salad": "слишком общее блюдо, готового эквивалента нет",
    "vegetable_cheese_salad": "слишком общее блюдо, готового эквивалента нет",
    # Added for docs/research/recsys/experiment-3-catalog-coverage-report.md;
    # поиск пары по снимку не делался (см. отчёт).
    "fried_chicken_breast": "слишком общее блюдо, поиск пары не делался",
    "pork_chops": "слишком общее блюдо, поиск пары не делался",
    "braised_beef_with_onion": "слишком общее блюдо, поиск пары не делался",
    "fried_minced_meat_with_onion": "слишком общее блюдо, поиск пары не делался",
    "pan_fried_semi_finished_cutlets": "слишком общее блюдо, поиск пары не делался",
    "chicken_in_sour_cream": "слишком общее блюдо, поиск пары не делался",
    "fried_zucchini_with_cheese": "слишком общее блюдо, поиск пары не делался",
    "braised_cabbage": "слишком общее блюдо, поиск пары не делался",
    "rice_milk_porridge": "слишком общее блюдо, поиск пары не делался",
    "cottage_cheese_with_sour_cream": "слишком общее блюдо, поиск пары не делался",
}


def required(recipe):
    return [i for i in recipe.ingredients if i.required]


def seasonings(recipe):
    return [i for i in recipe.ingredients if not i.required]


def basket(recipe):
    return round(sum(BASE_PRICE_RUB[i.ingredient_id] for i in required(recipe)))


def build() -> str:
    out = []
    w = out.append

    w("# Каталог рецептов")
    w("")
    w(
        f"**{len(RECIPES)} рецептов**, из них {len(NEW_FOR_READY_FOOD)} добавлены под собранную базу готовой "
        f"еды. У {len(PAIRS_BY_RECIPE_ID)} есть готовый аналог с реальным PLU, "
        f"у {len(RECIPES_WITHOUT_READY_FOOD_PAIR)} — нет."
    )
    w("")
    w("Файл сгенерирован из `recsys/recipes.py` и `recsys/ready_food_pairs.py`. Правится не он, а код.")
    w("")
    w("---")
    w("")
    w("## Как читать цифры")
    w("")
    w("**«Корзина» и «Готовое» сравнивать напрямую нельзя.** Это разные вещи:")
    w("")
    w(
        "- **Корзина ₽** — сумма упаковок всех обязательных ингредиентов по "
        "`recsys.catalog.BASE_PRICE_RUB`. Это стоимость купить всё с нуля: пачку муки, "
        "бутылку масла, целую банку майонеза. Граммовка в рецепте показывает, "
        "сколько из этого реально уйдёт в блюдо — обычно малая доля."
    )
    w(
        "- **Готовое ₽** — наблюдаемая цена самого дешёвого готового аналога в московском "
        "срезе, обычно порция 200–250 г."
    )
    w("")
    w(
        "То есть «Корзина» отвечает на вопрос «во что обойдётся **начать** готовить это "
        "блюдо, если дома нет ничего», а не «сколько стоит порция»."
    )
    w("")
    w(
        "**Чего не хватает для настоящей себестоимости.** Нормы закладки у нас как раз "
        "есть — это граммовка ниже, приближённые кулинарные порции на 2/4/6 человек. "
        "Нет другого: фасовок и цены за грамм или миллилитр по каждому SKU. Пока их нет, "
        "нельзя сказать, сколько стоят «250 г нута», если в продаже банка 400 г."
    )
    w("")
    w(
        "**Первая покупка на порцию** — колонка `₽/порц.` — это корзина, делённая на число "
        "порций. Справочная величина: столько человек заплатит за порцию, готовя блюдо "
        "**впервые**, с нуля. Второй раз выйдет заметно дешевле — мука, масло и специи "
        "уже дома. Это не себестоимость порции, и сравнивать её с ценой готового блюда "
        "напрямую всё ещё нельзя, но она ближе к тому, что человек реально ощущает."
    )
    w("")
    sample = f"{PRICE_REFERENCE['usable_unit_prices']:,}".replace(",", " ")
    w(
        f"Цены корзины — **оценка**, помеченная в API как `price_is_estimate`. Они "
        f"откалиброваны по {sample} реальных строк чеков X5 "
        f"({PRICE_REFERENCE['era']}, медиана {REFERENCE_MEDIAN_PRICE_RUB} ₽) с наблюдённым "
        f"коэффициентом ×{observed_price_era_multiplier():.2f} на 2026 год."
    )
    w("")
    w(
        "Цены готового — наблюдаемые, из снимков "
        f"`{SNAPSHOT_IDS[0]}` и `{SNAPSHOT_IDS[1]}` — {len(READY_FOOD_CATALOG)} товаров Москвы."
    )
    w("")
    w(
        "**Граммовка приблизительная.** Базовая порция на 2 человек задана в "
        "`recsys.catalog.PORTION_PER_TWO_SERVINGS` и масштабируется на `servings` "
        "рецепта; там, где масштабирование врёт (сахар в борще — приправа, а не "
        "основа), стоит точечный override. Это меры повара, а не нормы закладки."
    )
    w("")
    w(
        "**Специи не квантованы вовсе** — они помечены «по вкусу», не имеют "
        "количества и никогда не блокируют доступность рецепта."
    )
    w("")
    w("---")
    w("")
    w("## Сводная таблица")
    w("")
    w(
        "| Рецепт | Тип | Кухня | Мин | Порций | Ингр. | Корзина ₽ | ₽/порц. | "
        "Готовое ₽ | Аналогов |"
    )
    w("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")

    for recipe in sorted(RECIPES, key=lambda r: (r.dish_type, r.title)):
        pair = PAIRS_BY_RECIPE_ID.get(recipe.recipe_id)
        cheapest = pair.cheapest_meal() if pair else None
        mark = " 🆕" if recipe.recipe_id in NEW_FOR_READY_FOOD else ""
        ready = f"{cheapest.median_price_rub:.0f}" if cheapest else "—"
        count = str(len(pair.meals)) if pair else "—"
        w(
            f"| {recipe.title}{mark} | {recipe.dish_type} | {recipe.cuisine} | "
            f"{recipe.preparation_minutes} | {recipe.servings} | {len(required(recipe))} | "
            f"{basket(recipe)} | {round(basket(recipe) / recipe.servings)} | "
            f"{ready} | {count} |"
        )

    w("")
    w("🆕 — добавлен под базу готовой еды.")
    w("")
    w("---")
    w("")
    w("## Рецепты")
    w("")

    by_type = {}
    for recipe in RECIPES:
        by_type.setdefault(recipe.dish_type, []).append(recipe)

    for dish_type in sorted(by_type):
        w(f"### {dish_type}")
        w("")
        for recipe in sorted(by_type[dish_type], key=lambda r: r.title):
            pair = PAIRS_BY_RECIPE_ID.get(recipe.recipe_id)
            mark = " 🆕" if recipe.recipe_id in NEW_FOR_READY_FOOD else ""
            quick = " · быстрый" if recipe.preparation_minutes <= QUICK_RECIPE_MINUTES else ""
            w(f"#### {recipe.title}{mark}")
            w("")
            w(
                f"`{recipe.recipe_id}` · {recipe.cuisine} · "
                f"{recipe.preparation_minutes} мин{quick} · {recipe.servings} порции"
            )
            w("")
            amounts = ", ".join(
                f"{i.name} — {i.quantity:g} {i.unit}" for i in required(recipe)
            )
            w(f"**На {recipe.servings} порции:** {amounts}")
            spice = seasonings(recipe)
            if spice:
                w("")
                w("**По вкусу:** " + ", ".join(i.name for i in spice))
            w("")
            per_serving = round(basket(recipe) / recipe.servings)
            w(
                f"**Корзина целиком:** ~{basket(recipe)} ₽ — это "
                f"~{per_serving} ₽ на порцию при первой готовке (оценка)"
            )
            w("")
            if pair:
                cheapest = pair.cheapest_meal()
                w(
                    f"**Готовый аналог:** {len(pair.meals)} шт. в Москве, дешевле всего — "
                    f"{cheapest.name} за **{cheapest.median_price_rub:.2f} ₽** "
                    f"({cheapest.chain}, PLU {cheapest.plu})"
                )
                if pair.facet_confirmed_count:
                    w("")
                    w(
                        f"<sub>{pair.facet_confirmed_count} из {len(pair.meals)} "
                        f"подтверждены карточкой товара «Тип блюда»/«Кухня»</sub>"
                    )
            else:
                w(
                    f"**Готовый аналог:** нет — {NO_PAIR_REASON.get(recipe.recipe_id, 'нет данных')}"
                )
            w("")
        w("")

    w("---")
    w("")
    w("## Рецепты без готового аналога")
    w("")
    w("| Рецепт | Почему |")
    w("|---|---|")
    for recipe_id in sorted(RECIPES_WITHOUT_READY_FOOD_PAIR):
        title = next(r.title for r in RECIPES if r.recipe_id == recipe_id)
        w(f"| {title} | {NO_PAIR_REASON[recipe_id]} |")
    w("")
    w(
        "Отсутствие пары зафиксировано явно в `RECIPES_WITHOUT_READY_FOOD_PAIR`, чтобы это "
        "был проверенный факт, а не молчаливый промах поиска."
    )
    w("")
    return "\n".join(out)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = build()
    io.open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n").write(text)
    print(f"{OUTPUT_PATH}: {len(text.splitlines())} lines, {len(RECIPES)} recipes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
