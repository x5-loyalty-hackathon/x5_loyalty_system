"""Does the train/validation/test split actually hold?

A split is a promise, and promises about data rot quietly. This module checks
the promise four ways, and the fourth is the one that usually catches things:

1. **Disjoint by id** — the cheap check everyone does.
2. **Stable** — a user keeps its split as the population grows.
3. **Comparable** — test is not an accidentally weird sample; if it is, a drop
   on test means "test is odd", not "the change is bad".
4. **Disjoint by content** — the check that matters. Ids are names; two
   generators can hand different people the same name (measured: 87 collisions
   between the model's training population and the development panel), and the
   same person can appear under two names. Only the data answers "has this
   example been seen before", so profiles are compared by content hash.

Check 4 is aimed at a specific, real risk in this repo: ``MLRecommendationEngine``
trains on its own ``generate_population(300, seed=999)`` draw, and experiments
1-3 built their own populations too — all of that happened before panels
existed. If any of those rows are the same data now sitting in the test split,
the test split was burned before it was created.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from recsys.panels import SPLIT_WEIGHTS, Panel, development_splits, load_panel, split_of
from recsys.profiles import SyntheticProfile, generate_population
from recsys.regimes import REGIMES

#: Every read of the test split is appended here. The protocol says test is
#: read once, after a decision is final; discipline that is not recorded is
#: not discipline, it is an intention.
TEST_ACCESS_LEDGER = Path("docs/.test-access-ledger.json")


def profile_content_hash(profile: SyntheticProfile) -> str:
    """Identity by data, not by name.

    Deliberately excludes ``user_id``: the question is "is this the same
    person's data", and two generators reusing an index give different people
    the same id. Includes the basket and the full history, which is what a
    model would actually have learned from.
    """
    payload = {
        "archetype": profile.archetype,
        "current": sorted(
            (item.sku_id, round(item.unit_price, 2), item.quantity)
            for item in profile.current_receipt.items
        ),
        "history": [
            sorted(
                (item.sku_id, round(item.unit_price, 2), item.quantity)
                for item in receipt.items
            )
            for receipt in profile.purchase_history
        ],
        "radius": profile.user.radius_km,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


@dataclass
class SplitFinding:
    severity: str  # "error" | "warning" | "ok"
    check: str
    detail: str


@dataclass
class SplitAudit:
    sizes: dict[str, int]
    findings: list[SplitFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[SplitFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def clean(self) -> bool:
        return not self.errors


def _distribution_gap(splits: dict[str, Panel]) -> list[SplitFinding]:
    """Is any split a visibly different population from the others?

    Not a significance test — with 73 users in validation almost nothing is
    significant. It is a smell check with a wide band, so that "test looks
    nothing like train" cannot pass unnoticed while a 3-point wobble does not
    raise an alarm nobody should act on.
    """
    findings: list[SplitFinding] = []
    shares: dict[str, dict[str, float]] = {}
    for name, panel in splits.items():
        counts = Counter(p.archetype for p in panel.profiles)
        total = sum(counts.values()) or 1
        shares[name] = {a: counts.get(a, 0) / total for a in
                        {p.archetype for pan in splits.values() for p in pan.profiles}}

    for archetype in sorted(next(iter(shares.values()), {})):
        values = {name: shares[name].get(archetype, 0.0) for name in shares}
        spread = max(values.values()) - min(values.values())
        # 8 points, not 20. The test split is read once, so an unrepresentative
        # draw cannot be noticed and corrected later — it just produces one
        # wrong final number. At 400 users the explorer share ran 16% in train
        # against 27% in test, which a 20-point band waved through; explorers
        # are the most missing-tolerant archetype, so that draw quietly
        # flattered anything discovery-shaped.
        if spread > 0.08:
            detail = ", ".join(f"{n} {v:.0%}" for n, v in sorted(values.items()))
            findings.append(
                SplitFinding("warning", "distribution", f"{archetype}: {detail}")
            )

    for name, panel in splits.items():
        if not panel.profiles:
            findings.append(SplitFinding("error", "distribution", f"{name} is empty"))
            continue
        mean_basket = sum(len(p.current_receipt.items) for p in panel.profiles) / len(
            panel.profiles
        )
        mean_history = sum(len(p.purchase_history) for p in panel.profiles) / len(
            panel.profiles
        )
        mix = ", ".join(
            f"{archetype[:4]} {share:.0%}"
            for archetype, share in sorted(shares[name].items())
        )
        findings.append(
            SplitFinding(
                "ok",
                "distribution",
                f"{name}: basket {mean_basket:.1f}, history {mean_history:.1f}, {mix}",
            )
        )
    return findings


def _seen_before_hashes() -> dict[str, set[str]]:
    """Content hashes of every population this project has already learned from
    or measured on, reconstructed from how each caller built its own draw."""
    seen: dict[str, set[str]] = {}

    # What MLRecommendationEngine fits on, from recsys.model._train_classifier.
    seen["model_training"] = {
        profile_content_hash(p) for p in generate_population(300, seed=999)
    }

    # What experiments 1-3 and the benchmark measured on: one draw per regime,
    # seed + regime_index, 80 users, as recsys.benchmark/sensitivity do it.
    experiment_hashes: set[str] = set()
    for regime_index, regime in enumerate(REGIMES[:9]):
        for profile in generate_population(
            80, seed=20260905 + regime_index, archetypes=regime.archetypes()
        ):
            experiment_hashes.add(profile_content_hash(profile))
    seen["experiments_1_3"] = experiment_hashes
    return seen


def audit(splits: dict[str, Panel] | None = None) -> SplitAudit:
    splits = splits if splits is not None else development_splits()
    result = SplitAudit(sizes={name: len(p.profiles) for name, p in splits.items()})

    # 1. disjoint by id
    by_id: dict[str, str] = {}
    collisions = 0
    for name, panel in splits.items():
        for profile in panel.profiles:
            previous = by_id.get(profile.user.user_id)
            if previous is not None and previous != name:
                collisions += 1
            by_id[profile.user.user_id] = name
    result.findings.append(
        SplitFinding(
            "error" if collisions else "ok",
            "disjoint_ids",
            f"{collisions} user ids in more than one split",
        )
    )

    # 2. assignment is a function of identity alone
    unstable = [
        profile.user.user_id
        for name, panel in splits.items()
        for profile in panel.profiles
        if split_of(profile.user.user_id) != name
    ]
    result.findings.append(
        SplitFinding(
            "error" if unstable else "ok",
            "stable_assignment",
            f"{len(unstable)} users whose split does not match their id hash",
        )
    )

    # 3. comparability
    result.findings.extend(_distribution_gap(splits))

    # 4. content-level leak
    seen = _seen_before_hashes()
    for name, panel in splits.items():
        panel_hashes = {profile_content_hash(p) for p in panel.profiles}
        for source, source_hashes in seen.items():
            overlap = panel_hashes & source_hashes
            severity = "error" if overlap and name == "test" else (
                "warning" if overlap else "ok"
            )
            result.findings.append(
                SplitFinding(
                    severity,
                    "content_leak",
                    f"{name} x {source}: {len(overlap)} identical profiles",
                )
            )
    return result


# --- test-set access ledger ------------------------------------------------


def record_test_access(reason: str, ledger: Path = TEST_ACCESS_LEDGER) -> dict:
    """Log that the test split was read, and why.

    Returns the full ledger so a caller can see how many times it has happened.
    Reading test more than once for the same decision turns it into a
    validation set; the ledger is what makes that visible instead of
    deniable.
    """
    entries: list[dict] = []
    if ledger.exists():
        entries = json.loads(ledger.read_text(encoding="utf-8")).get("accesses", [])
    entries.append(
        {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reason": reason,
        }
    )
    payload = {"accesses": entries}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return payload


def count_test_accesses(ledger: Path = TEST_ACCESS_LEDGER) -> int:
    if not ledger.exists():
        return 0
    return len(json.loads(ledger.read_text(encoding="utf-8")).get("accesses", []))


def main() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    result = audit()

    print("split sizes:", ", ".join(f"{k}={v}" for k, v in result.sizes.items()))
    print(f"expected weights: {SPLIT_WEIGHTS}")
    print()
    icon = {"ok": "  ok   ", "warning": "  warn ", "error": "  ERROR"}
    for finding in result.findings:
        print(f"{icon[finding.severity]} {finding.check:<20} {finding.detail}")
    print()
    print(f"test split read {count_test_accesses()} time(s) so far")
    print("clean" if result.clean else "AUDIT FAILED")
    return 0 if result.clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
