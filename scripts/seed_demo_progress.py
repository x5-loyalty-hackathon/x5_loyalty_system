"""Готовит синтетический профиль через обычные эндпоинты PoC.

XP в системе выводится из наград за планы с подтверждённой покупкой, и
одна покупка в день даёт максимум одну награду. Поэтому «прокачанный»
профиль нельзя просто записать в стейт: скрипт моделирует цикл
план → чек → награда по одному разу на каждый прошедший день.

    python scripts/seed_demo_progress.py [--base http://127.0.0.1:8000] [--days 50]

Состояние сервера держится в памяти: после перезапуска скрипт запускается
заново. Точные запросы сохраняются в outputs/demo-progress для безопасного
повтора после обрыва; это не реальные покупки и не результат пилота.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / "mobile/src/fixtures/mealRequest.json"
VETERAN_USER_ID = "user_mobile_veteran"


class SeedJournal:
    """Persist exact offer-bound requests BEFORE their first submission."""

    def __init__(self, path: Path, base: str):
        self.path = path
        self.data = {"base": base.rstrip("/"), "entries": {}}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
            if self.data.get("base") != base.rstrip("/") or not isinstance(self.data.get("entries"), dict):
                raise RuntimeError("Журнал относится к другому серверу или повреждён; используйте отдельный --state-file.")

    def put(self, tag: str, entry: dict) -> None:
        self.data["entries"][tag] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as output:
            json.dump(self.data, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
            temporary = output.name
        os.replace(temporary, self.path)


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


def prepare_day(base: str, fixture: dict, day: datetime) -> dict:
    stamp = day.isoformat()
    # A stable date ID alone is not enough: offer_id must also survive retries.
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
    fulfillment = product["fulfillment_options"][0]

    plan_id = f"{VETERAN_USER_ID}-plan-{tag}"
    plan = {
        "offer_id": meal["offer_id"], "plan_id": plan_id, "user_id": VETERAN_USER_ID,
        "meal_id": meal["meal_id"], "selected_route": "ready",
        "selected_product_ids": [product["sku_id"]],
        "fulfillment": fulfillment, "created_at": stamp,
    }

    receipt = {
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
    }
    return {"plan": plan, "receipt": receipt}


def seed_day(base: str, fixture: dict, day: datetime, journal: SeedJournal) -> str:
    tag = day.date().isoformat()
    entry = journal.data["entries"].get(tag)
    if entry is None:
        entry = prepare_day(base, fixture, day)
        journal.put(tag, entry)
    saved = post(base, "/api/v1/meal-plans", entry["plan"])
    if saved.get("status") == "rejected" and saved.get("reason_codes") == ["meal_offer_not_found"]:
        # A restarted in-memory backend no longer knows this offer/plan.
        # Refresh once; never reinterpret a conflicting existing plan as success.
        entry = prepare_day(base, fixture, day)
        journal.put(tag, entry)
        saved = post(base, "/api/v1/meal-plans", entry["plan"])
    if saved.get("status") not in {"created", "duplicate"} or not saved.get("plan"):
        raise RuntimeError(f"План {tag} не принят: {saved.get('reason_codes', saved)}. "
                           "Если профиль создан старым скриптом без журнала, нужен чистый demo-backend.")
    result = post(base, "/api/v1/events/receipts", entry["receipt"])
    if result.get("status") not in {"verified", "duplicate"}:
        raise RuntimeError(f"Чек {tag} не подтверждён: {result.get('reason_codes', result)}")
    plan = result.get("meal_plan") or {}
    reward = plan.get("reward") or {}
    if (plan.get("plan_id") != entry["plan"]["plan_id"] or plan.get("user_id") != VETERAN_USER_ID
            or plan.get("status") != "completed" or reward.get("status") != "awarded"
            or reward.get("xp") != 20 or reward.get("purchase_day") != tag):
        raise RuntimeError(f"Чек {tag} принят, но ожидаемое задание с наградой 20 XP не подтверждено.")
    return result["status"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--days", type=int, default=50,
                        help="сколько дней покупок набить; 50 даёт 1000 XP и 21-й уровень")
    parser.add_argument("--state-file", type=Path, help="журнал точных запросов для повторов; по умолчанию outputs/demo-progress")
    args = parser.parse_args()
    if not 1 <= args.days <= 365:
        parser.error("--days должен быть от 1 до 365")
    args.base = args.base.rstrip("/")
    server_tag = hashlib.sha256(args.base.encode()).hexdigest()[:12]
    state_file = args.state_file or FIXTURE.parents[3] / "outputs" / "demo-progress" / f"{server_tag}-veteran.json"
    journal = SeedJournal(state_file, args.base)

    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    start = datetime.fromisoformat(fixture["now"])

    for index in range(args.days):
        day = start - timedelta(days=args.days - index)
        status = seed_day(args.base, fixture, day, journal)
        if status != "verified":
            print(f"день {day.date()}: чек принят со статусом {status}")

    snapshot = get(args.base, f"/api/v1/progress/{VETERAN_USER_ID}")
    print(f"Демо · {VETERAN_USER_ID}: {snapshot['avatar_xp']} XP, "
          f"уровень {snapshot['avatar_level']}, "
          f"наград за блюда {snapshot['rewarded_meals']}")


if __name__ == "__main__":
    main()
