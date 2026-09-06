"""Produce the "10 profiles with real, different recommendations" artifact.

Unlike ``recsys.simulation`` (aggregate rates at 1-10k scale), this runs the
*real* pipeline — the actual ``app.service.RecommendationService`` and
``app.safety.SafetyPolicy`` (unmodified, imported as-is) wired to
``recsys.model.MLRecommendationEngine`` — for a small, human-reviewable set
of profiles spanning all four archetypes. Output is what the real API would
return for each profile, not a hand-written mock.

Run: ``python -m recsys.generate_examples``
Writes: ``recsys/examples/sample_recommendations.json``
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from app.contracts import RecommendationRequest
from app.safety import SafetyPolicy
from app.service import RecommendationService
from recsys.inventory import generate_inventory
from recsys.model import MLRecommendationEngine
from recsys.profiles import ARCHETYPES, generate_profile
from recsys.reason_codes import text as reason_text
from recsys.recipes import RECIPES

OUTPUT_PATH = Path(__file__).parent / "examples" / "sample_recommendations.json"

# Slightly weighted toward the two largest-population archetypes, but every
# archetype appears at least twice so all four show up in the sample.
ARCHETYPE_COUNTS: dict[str, int] = {"routine": 3, "value": 3, "explorer": 2, "time_limited": 2}
SEED = 4242
UNORDERED_RESPONSE_FIELDS = {
    "available_routes",
    "contained_categories",
    "fulfillment_options",
    "ingredient_ids",
}


def _stable_json_value(
    value: Any,
    *,
    field_name: str | None = None,
) -> Any:
    """Canonicalize schema sets after JSON conversion without reordering ranks."""
    if isinstance(value, dict):
        return {
            key: _stable_json_value(item, field_name=key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        normalized = [
            _stable_json_value(item, field_name=field_name) for item in value
        ]
        if field_name in UNORDERED_RESPONSE_FIELDS:
            return sorted(normalized)
        return normalized
    return value


def _sample_profiles(seed: int = SEED):
    rng = random.Random(seed)
    profiles = []
    index = 0
    for archetype_name, count in ARCHETYPE_COUNTS.items():
        collected = 0
        while collected < count:
            candidate = generate_profile(rng, index)
            index += 1
            if candidate.archetype != archetype_name:
                continue
            profiles.append(candidate)
            collected += 1
    return profiles


def generate_examples(seed: int = SEED) -> list[dict]:
    rng = random.Random(seed + 1)
    engine = MLRecommendationEngine()
    service = RecommendationService(engine=engine, safety_policy=SafetyPolicy())
    # Showcase the live request catalog, including recipes outside the frozen
    # training catalog. This is API output for inspection, not a quality metric
    # or a claim that training and evaluation use identical catalogs (0bf8240).
    recipe_catalog = list(RECIPES)

    records: list[dict] = []
    for profile in _sample_profiles(seed):
        inventory = generate_inventory(
            rng,
            now=profile.now,
            home_store_id=profile.current_receipt.store_id,
            user_radius_km=profile.user.radius_km,
        )
        request = RecommendationRequest(
            user=profile.user,
            current_receipt=profile.current_receipt,
            purchase_history=profile.purchase_history,
            recipe_catalog=recipe_catalog,
            inventory_snapshot=inventory,
            now=profile.now,
            limit=3,
        )
        response = service.recommend(request)
        records.append(
            {
                "user_id": profile.user.user_id,
                "archetype": profile.archetype,
                "radius_km": profile.user.radius_km,
                "current_receipt_items": [item.name for item in profile.current_receipt.items],
                "home_ingredients": sorted(profile.user.home_ingredient_ids),
                "saved_recipes": sorted(profile.user.saved_recipe_ids),
                "history_receipt_count": len(profile.purchase_history),
                "response": _stable_json_value(
                    json.loads(response.model_dump_json())
                ),
            }
        )
    return records


def _print_human_summary(records: list[dict]) -> None:
    for record in records:
        print(f"=== {record['user_id']} ({record['archetype']}, radius {record['radius_km']} km) ===")
        print(f"  today's receipt: {', '.join(record['current_receipt_items'])}")
        recs = record["response"]["recommendations"]
        if not recs:
            print("  -> no safe recommendation returned")
            continue
        for rec in recs:
            sources = ", ".join(f"{i['name']}:{i['source']}" for i in rec["ingredients"])
            reasons = "; ".join(reason_text(c) for c in rec["reason_codes"])
            print(
                f"  -> [{rec['mode']}] {rec['title']} "
                f"(score={rec['model_score']}, missing={rec['missing_count']})"
            )
            print(f"     ingredients: {sources}")
            print(f"     why: {reasons}")
        print()


def main() -> None:
    records = generate_examples()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(records)} profiles to {OUTPUT_PATH}")
    print()
    _print_human_summary(records)


if __name__ == "__main__":
    main()
