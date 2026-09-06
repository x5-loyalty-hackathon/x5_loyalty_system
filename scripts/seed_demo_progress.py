"""Набивает опыт демо-пользователю через боевые эндпоинты.

XP в системе выводится из наград за планы с подтверждённой покупкой, и
одна покупка в день даёт максимум одну награду. Поэтому «прокачанный»
профиль нельзя просто записать в стейт: скрипт честно проходит цикл
план → чек → награда по одному разу на каждый прошедший день.

    python scripts/seed_demo_progress.py [--base http://127.0.0.1:8000] [--days 50]

Состояние сервера держится в памяти, так что после его перезапуска скрипт
нужно прогнать заново.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "mobile/src/fixtures/mealRequest.json"
VETERAN_USER_ID = "user_mobile_veteran"


def post(base: str, path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"{path} -> {error.code}: {error.read().decode('utf-8')}")


def get(base: str, path: str) -> dict:
    with urllib.request.urlopen(f"{base}{path}", timeout=15) as response:
        return json.loads(response.read())


def seed_day(base: str, fixture: dict, day: datetime) -> str:
    stamp = day.isoformat()
    # Идентификаторы привязаны к дате, а не к номеру шага: повторный прогон
    # по живому серверу тогда возвращает duplicate и ничего не сдвигает.
    tag = day.date().isoformat()
    request = {**fixture, "now": stamp,
               "user": {**fixture["user"], "user_id": VETERAN_USER_ID}}
    response = post(base, "/api/v1/meal-recommendations", request)

    meal = next((item for item in response["recommendations"]
                 if "ready" in item["available_routes"]), None)
    if meal is None:
        raise SystemExit("в выдаче нет блюда с готовым вариантом — нечего покупать")
    variant = meal["ready_variant"]
    product = variant["product_options"][0]
    fulfillment = variant["fulfillment_options"][0]

    plan_id = f"{VETERAN_USER_ID}-plan-{tag}"
    post(base, "/api/v1/meal-plans", {
        "offer_id": meal["offer_id"], "plan_id": plan_id, "user_id": VETERAN_USER_ID,
        "meal_id": meal["meal_id"], "selected_route": "ready",
        "selected_product_ids": [product["sku_id"]],
        "fulfillment": fulfillment, "created_at": stamp,
    })

    receipt = post(base, "/api/v1/events/receipts", {
        "user_id": VETERAN_USER_ID, "meal_plan_id": plan_id, "now": stamp,
        "receipt": {
            "receipt_id": f"{VETERAN_USER_ID}-receipt-{tag}",
            "purchased_at": stamp, "store_id": product["store_id"],
            "items": [{
                "sku_id": product["sku_id"], "name": product["name"],
                "category": "prepared_food", "quantity": 1,
                "unit_price": product["price"], "is_prepared_food": True,
            }],
        },
    })
    return receipt["status"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--days", type=int, default=50,
                        help="сколько дней покупок набить; 50 даёт 1000 XP и 21-й уровень")
    args = parser.parse_args()

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    start = datetime.fromisoformat(fixture["now"])

    for index in range(args.days):
        day = start - timedelta(days=args.days - index)
        status = seed_day(args.base, fixture, day)
        if status != "verified":
            print(f"день {day.date()}: чек принят со статусом {status}")

    snapshot = get(args.base, f"/api/v1/progress/{VETERAN_USER_ID}")
    print(f"{VETERAN_USER_ID}: {snapshot['avatar_xp']} XP, "
          f"уровень {snapshot['avatar_level']}, "
          f"наград за блюда {snapshot['rewarded_meals']}")


if __name__ == "__main__":
    main()
