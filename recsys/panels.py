"""Materialised evaluation panels: the data an experiment is allowed to see.

Why this exists
---------------
Every experiment so far rebuilt its own population from a seed. That looked
reproducible and was not, for two reasons measured on this codebase:

**A shared generator stream couples every profile to every other one.**
``recsys.profiles.generate_population`` walks one ``random.Random`` across the
whole population, and the number of draws per profile is not constant — the
saved-recipe draw is sized by the catalog. Growing the catalog from 37 to 47
recipes gave **137 of 160 profiles a completely different basket**, starting at
profile 9 and propagating to everyone after it. Any "same panel, bigger
catalog" comparison built that way is not paired, whatever the seed says.

**A seed is not a record of what ran.** It reproduces data only against the
exact generator, catalog and parameters that were in the tree at the time. None
of that is captured by the number, so a report quoting `seed=20260905` cannot
be checked a month later.

So a panel here is *materialised* — profiles, histories and inventories are
built, hashed, written down, and re-loaded rather than re-derived. The manifest
records the generator version, the catalog hash, the parameters and the content
checksums, so "did this rerun see the same data" is a question with an answer.

Design
------
*Per-entity streams.* Each profile draws from ``stable_seed("profile", seed,
index)`` and each inventory from ``stable_seed("inventory", seed, user_id)``.
Nothing is sequential, so a profile depends on neither ``n`` nor on any other
profile, and adding a user or a recipe changes nothing else in the panel.

*A pinned saved-recipe pool.* Panels pin the draw to
``recsys.catalog_freeze.baseline_catalog()``, so a candidate recipe entering
the catalog cannot alter the panel it is about to be measured on.

*Splits by user identity, not by position.* ``split_of`` hashes the user id, so
a user keeps its split when the population grows — unlike an index-parity or
slice split, where adding users silently reshuffles who is in the test set.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

from app.contracts import InventoryProduct, Receipt, UserProfile
from recsys._seeds import stable_seed
from recsys.catalog_freeze import baseline_catalog, recipe_content_hash
from recsys.inventory import (
    DEFAULT_INVENTORY_ASSUMPTIONS,
    InventoryAssumptions,
    generate_inventory,
)
from recsys.profiles import ARCHETYPES, DEFAULT_NOW, SyntheticProfile, generate_profile
from recsys.regimes import NEUTRAL_REGIME, Regime

#: Bump when generation semantics change in a way that invalidates stored
#: panels. Loading a panel written by a different version is an error, not a
#: warning: silently mixing two generators is the failure this module exists
#: to prevent.
#:
#: v1 — first materialised generator. Includes the fix that keeps history
#: strictly before ``now`` (see ``recsys.profiles.MIN_HISTORY_AGE_DAYS``);
#: numbers published before it, including ``docs/benchmark-report.md`` and
#: ``docs/sensitivity-report.md``, came from the pre-fix generator and are not
#: comparable to panel-based numbers at the third decimal.
GENERATOR_VERSION = 1

PANEL_ROOT = Path("recsys/data/panels")

#: The seed every standard panel derives from. One number, recorded in each
#: manifest, so a panel can say where it came from.
DEFAULT_PANEL_SEED = 20260905

#: Share of users in each split. Development happens on train+validation; the
#: test split is not read until a decision is final.
SPLIT_WEIGHTS: dict[str, int] = {"train": 60, "validation": 20, "test": 20}

#: Disjoint index ranges per cohort. ``recsys.profiles.generate_profile`` names
#: a user ``synthetic_<archetype>_<index>``, so the index is the identity: two
#: cohorts sharing an index range produce *different people under the same id*.
#: Measured before this existed: the "new users" probe collided with 56 of the
#: development panel's ids while holding different baskets, which is worse than
#: an honest overlap because ``assert_disjoint`` and any per-user join would
#: silently treat them as the same person.
COHORT_INDEX_OFFSET: dict[str, int] = {
    "base": 0,
    "holdout_users": 1_000_000,
}


def split_of(user_id: str, *, salt: str = "split_v1") -> str:
    """Which split a user belongs to, from its id alone.

    Deterministic and position-free: growing the population never moves an
    existing user between splits, so a test set stays a test set. ``salt``
    exists so a deliberate re-split is a visible, named act rather than a
    quiet change of the same function's output.
    """
    bucket = stable_seed(salt, user_id) % 100
    threshold = 0
    for name, weight in SPLIT_WEIGHTS.items():
        threshold += weight
        if bucket < threshold:
            return name
    return "test"


@dataclass(frozen=True)
class PanelSpec:
    """Everything that determines a panel's content."""

    name: str
    n_users: int
    seed: int = DEFAULT_PANEL_SEED
    #: Regime name, resolved through ``recsys.regimes`` at build time.
    regime: str = NEUTRAL_REGIME.name
    assumptions: InventoryAssumptions = DEFAULT_INVENTORY_ASSUMPTIONS
    now: datetime = DEFAULT_NOW
    #: Extra namespace for the profile stream. Two panels with the same seed
    #: and different cohorts share no users — this is how the "new users"
    #: probe gets people the model has genuinely never seen.
    cohort: str = "base"

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "n_users": self.n_users,
            "seed": self.seed,
            "regime": self.regime,
            "assumptions": asdict(self.assumptions),
            "now": self.now.isoformat(),
            "cohort": self.cohort,
        }

    @staticmethod
    def from_json(payload: dict) -> PanelSpec:
        return PanelSpec(
            name=payload["name"],
            n_users=payload["n_users"],
            seed=payload["seed"],
            regime=payload["regime"],
            assumptions=InventoryAssumptions(**payload["assumptions"]),
            now=datetime.fromisoformat(payload["now"]),
            cohort=payload["cohort"],
        )


@dataclass(frozen=True)
class PanelManifest:
    """Provenance: what built this panel, and what came out."""

    spec: PanelSpec
    generator_version: int
    #: Content hash of the catalog the saved-recipe draw was pinned to.
    saved_recipe_pool_hash: str
    profiles_checksum: str
    inventories_checksum: str
    n_profiles: int
    n_products: int
    archetype_counts: dict[str, int]
    split_counts: dict[str, int]

    def to_json(self) -> dict:
        return {
            "spec": self.spec.to_json(),
            "generator_version": self.generator_version,
            "saved_recipe_pool_hash": self.saved_recipe_pool_hash,
            "profiles_checksum": self.profiles_checksum,
            "inventories_checksum": self.inventories_checksum,
            "n_profiles": self.n_profiles,
            "n_products": self.n_products,
            "archetype_counts": self.archetype_counts,
            "split_counts": self.split_counts,
        }

    @staticmethod
    def from_json(payload: dict) -> PanelManifest:
        return PanelManifest(
            spec=PanelSpec.from_json(payload["spec"]),
            generator_version=payload["generator_version"],
            saved_recipe_pool_hash=payload["saved_recipe_pool_hash"],
            profiles_checksum=payload["profiles_checksum"],
            inventories_checksum=payload["inventories_checksum"],
            n_profiles=payload["n_profiles"],
            n_products=payload["n_products"],
            archetype_counts=payload["archetype_counts"],
            split_counts=payload["split_counts"],
        )


@dataclass
class Panel:
    """One materialised population plus the shelf each user faced."""

    manifest: PanelManifest
    profiles: list[SyntheticProfile]
    inventories: list[list[InventoryProduct]]

    def __post_init__(self) -> None:
        if len(self.profiles) != len(self.inventories):
            raise ValueError(
                f"{len(self.profiles)} profiles vs {len(self.inventories)} inventories"
            )

    def pairs(self) -> list[tuple[SyntheticProfile, list[InventoryProduct]]]:
        return list(zip(self.profiles, self.inventories, strict=True))

    def with_inventory(self, assumptions: InventoryAssumptions) -> Panel:
        """The same people, facing a different shelf.

        The profile stream is untouched and the inventory stream keeps its
        seed, so only the *thresholds* applied to the same random numbers move.
        That is common random numbers, and it is what makes a deficit sweep a
        paired comparison: a recipe that vanishes at high scarcity vanished
        because the shelf changed, not because the draw did. Regenerating with
        a fresh seed would let supply noise pose as a deficit effect — the same
        discipline ``recsys.true_pantry`` follows for its consumption dial.
        """
        spec = replace(self.manifest.spec, assumptions=assumptions)
        inventories = [
            generate_inventory(
                random.Random(
                    stable_seed("inventory", spec.cohort, spec.seed, profile.user.user_id)
                ),
                now=profile.now,
                home_store_id=profile.current_receipt.store_id,
                user_radius_km=profile.user.radius_km,
                assumptions=assumptions,
            )
            for profile in self.profiles
        ]
        return Panel(
            manifest=_manifest_for(spec, self.profiles, inventories),
            profiles=list(self.profiles),
            inventories=inventories,
        )

    def split(self, name: str) -> Panel:
        """The sub-panel for one split, manifest re-derived over what's kept."""
        keep = [
            (profile, inventory)
            for profile, inventory in self.pairs()
            if split_of(profile.user.user_id) == name
        ]
        profiles = [p for p, _ in keep]
        inventories = [i for _, i in keep]
        return Panel(
            manifest=_manifest_for(
                replace(self.manifest.spec, name=f"{self.manifest.spec.name}/{name}"),
                profiles,
                inventories,
            ),
            profiles=profiles,
            inventories=inventories,
        )


def _canonical_obj(payload: object) -> object:
    """Order-stable view of a dumped model, for hashing only.

    Several contract fields are ``set``s (``ingredient_ids``,
    ``saved_recipe_ids``, ``fulfillment_options``, ...). ``model_dump`` turns
    them into lists in set-iteration order, which does not survive a JSON
    round-trip — so a panel written and read back hashed differently and
    looked corrupted when nothing had changed. Sorting scalar lists fixes the
    fingerprint without touching the stored data; lists of objects (receipt
    items, purchase history) keep their order, because there it is meaningful.
    """
    if isinstance(payload, dict):
        return {key: _canonical_obj(value) for key, value in sorted(payload.items())}
    if isinstance(payload, list):
        if all(isinstance(item, (str, int, float, bool)) or item is None for item in payload):
            return sorted(payload, key=repr)
        return [_canonical_obj(item) for item in payload]
    return payload


def _canonical(payload: object) -> str:
    return json.dumps(
        _canonical_obj(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def _checksum(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:16]


def _profile_to_json(profile: SyntheticProfile) -> dict:
    return {
        "archetype": profile.archetype,
        "user": profile.user.model_dump(mode="json"),
        "current_receipt": profile.current_receipt.model_dump(mode="json"),
        "purchase_history": [r.model_dump(mode="json") for r in profile.purchase_history],
        "now": profile.now.isoformat(),
    }


def _profile_from_json(payload: dict) -> SyntheticProfile:
    return SyntheticProfile(
        archetype=payload["archetype"],
        user=UserProfile.model_validate(payload["user"]),
        current_receipt=Receipt.model_validate(payload["current_receipt"]),
        purchase_history=[Receipt.model_validate(r) for r in payload["purchase_history"]],
        now=datetime.fromisoformat(payload["now"]),
    )


def _manifest_for(
    spec: PanelSpec,
    profiles: list[SyntheticProfile],
    inventories: list[list[InventoryProduct]],
) -> PanelManifest:
    pool = baseline_catalog()
    return PanelManifest(
        spec=spec,
        generator_version=GENERATOR_VERSION,
        saved_recipe_pool_hash=recipe_content_hash(pool),
        profiles_checksum=_checksum([_profile_to_json(p) for p in profiles]),
        inventories_checksum=_checksum(
            [[product.model_dump(mode="json") for product in inv] for inv in inventories]
        ),
        n_profiles=len(profiles),
        n_products=sum(len(inv) for inv in inventories),
        archetype_counts=dict(Counter(p.archetype for p in profiles)),
        split_counts=dict(Counter(split_of(p.user.user_id) for p in profiles)),
    )


def _regime_archetypes(regime_name: str) -> dict:
    from recsys.regimes import REGIMES

    for regime in REGIMES:
        if regime.name == regime_name:
            return regime.archetypes()
    raise KeyError(f"unknown regime {regime_name!r}")


def build_panel(spec: PanelSpec) -> Panel:
    """Materialise a panel from its spec.

    Every profile and every inventory gets its own stream, so this is
    order-independent: building 100 users and taking the first 50 gives
    exactly the same 50 as building 50.
    """
    archetypes = _regime_archetypes(spec.regime)
    pool = baseline_catalog()
    if spec.cohort not in COHORT_INDEX_OFFSET:
        raise KeyError(
            f"unknown cohort {spec.cohort!r}; add it to COHORT_INDEX_OFFSET with a "
            f"range no other cohort uses"
        )
    offset = COHORT_INDEX_OFFSET[spec.cohort]

    profiles: list[SyntheticProfile] = []
    for i in range(spec.n_users):
        index = offset + i
        rng = random.Random(stable_seed("profile", spec.cohort, spec.seed, index))
        profiles.append(
            generate_profile(
                rng,
                index,
                now=spec.now,
                archetypes=archetypes,
                saved_recipe_pool=pool,
            )
        )

    inventories: list[list[InventoryProduct]] = []
    for profile in profiles:
        rng = random.Random(
            stable_seed("inventory", spec.cohort, spec.seed, profile.user.user_id)
        )
        inventories.append(
            generate_inventory(
                rng,
                now=profile.now,
                home_store_id=profile.current_receipt.store_id,
                user_radius_km=profile.user.radius_km,
                assumptions=spec.assumptions,
            )
        )

    return Panel(
        manifest=_manifest_for(spec, profiles, inventories),
        profiles=profiles,
        inventories=inventories,
    )


def response_rng(
    panel: Panel, user_id: str, card_index: int, responder: str
) -> random.Random:
    """The stream a response simulator must use for one card.

    Kept separate from the profile and inventory streams on purpose: a
    simulator drawing from a shared generator makes its coin flips depend on
    how many cards the arm before it produced, which turns "arm B got luckier"
    into a measurable win.
    """
    return random.Random(
        stable_seed(
            "response", panel.manifest.spec.seed, user_id, card_index, responder
        )
    )


# --- validation ------------------------------------------------------------


@dataclass
class PanelIssue:
    severity: str  # "error" | "warning"
    message: str


def validate_panel(panel: Panel, *, expect_distribution: bool = True) -> list[PanelIssue]:
    """Structural checks a panel must pass before it is used for anything.

    Returns issues rather than raising so a caller can report all of them at
    once; ``assert_panel_ok`` is the raising wrapper.
    """
    issues: list[PanelIssue] = []

    user_ids = [p.user.user_id for p in panel.profiles]
    duplicates = [uid for uid, count in Counter(user_ids).items() if count > 1]
    if duplicates:
        issues.append(
            PanelIssue("error", f"duplicate user ids: {sorted(duplicates)[:5]}")
        )

    receipt_ids = [
        receipt.receipt_id
        for profile in panel.profiles
        for receipt in [profile.current_receipt, *profile.purchase_history]
    ]
    dup_receipts = [rid for rid, count in Counter(receipt_ids).items() if count > 1]
    if dup_receipts:
        issues.append(
            PanelIssue("error", f"duplicate receipt ids: {sorted(dup_receipts)[:5]}")
        )

    for profile in panel.profiles:
        for receipt in profile.purchase_history:
            if receipt.purchased_at > profile.now:
                issues.append(
                    PanelIssue(
                        "error",
                        f"{profile.user.user_id}: history receipt {receipt.receipt_id} "
                        f"is in the future relative to now",
                    )
                )
                break

    empty = [i for i, inv in enumerate(panel.inventories) if not inv]
    if empty:
        issues.append(
            PanelIssue("error", f"{len(empty)} users have an empty inventory")
        )

    if expect_distribution:
        counts = Counter(p.archetype for p in panel.profiles)
        total = sum(counts.values()) or 1
        for name, params in ARCHETYPES.items():
            observed = counts.get(name, 0) / total
            expected = params.population_share
            # Wide band on purpose: this catches "an archetype vanished", not
            # sampling noise, which at panel sizes here is several points.
            if abs(observed - expected) > 0.12:
                issues.append(
                    PanelIssue(
                        "warning",
                        f"archetype {name}: {observed:.0%} vs expected {expected:.0%}",
                    )
                )
    return issues


def assert_panel_ok(panel: Panel) -> None:
    errors = [i for i in validate_panel(panel) if i.severity == "error"]
    if errors:
        raise ValueError("; ".join(i.message for i in errors))


def assert_disjoint(*panels: Panel) -> None:
    """No user may appear in two panels that are meant to be independent."""
    seen: dict[str, str] = {}
    for panel in panels:
        for profile in panel.profiles:
            uid = profile.user.user_id
            previous = seen.get(uid)
            if previous is not None and previous != panel.manifest.spec.name:
                raise ValueError(
                    f"user {uid} appears in both {previous!r} and "
                    f"{panel.manifest.spec.name!r}"
                )
            seen[uid] = panel.manifest.spec.name


# --- persistence -----------------------------------------------------------


def panel_dir(name: str, root: Path = PANEL_ROOT) -> Path:
    return root / name.replace("/", "__")


def save_panel(panel: Panel, root: Path = PANEL_ROOT) -> Path:
    """Write the panel and its manifest. Payload is gzipped; manifest is not.

    The manifest stays plain text so it can be committed and read in a diff —
    that is the part a reviewer needs. The payload is regenerable from the
    spec, and its checksum in the manifest is what proves the regeneration
    matched.
    """
    directory = panel_dir(panel.manifest.spec.name, root)
    directory.mkdir(parents=True, exist_ok=True)

    (directory / "manifest.json").write_text(
        json.dumps(panel.manifest.to_json(), indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    payload = {
        "profiles": [_profile_to_json(p) for p in panel.profiles],
        "inventories": [
            [product.model_dump(mode="json") for product in inv]
            for inv in panel.inventories
        ],
    }
    with gzip.open(directory / "panel.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    return directory


def load_panel(name: str, root: Path = PANEL_ROOT) -> Panel:
    """Read a stored panel, refusing anything a different generator wrote."""
    directory = panel_dir(name, root)
    manifest = PanelManifest.from_json(
        json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    )
    if manifest.generator_version != GENERATOR_VERSION:
        raise ValueError(
            f"panel {name!r} was written by generator v{manifest.generator_version}, "
            f"this is v{GENERATOR_VERSION} — rebuild it rather than mixing the two"
        )
    payload_path = directory / "panel.json.gz"
    if not payload_path.exists():
        raise FileNotFoundError(
            f"panel {name!r} has a manifest but no payload at {payload_path}. "
            f"The payload is gitignored and regenerable, so a fresh clone "
            f"always looks like this — build it with `python -m recsys.panels`, "
            f"or call load_or_build, which rebuilds and verifies against the "
            f"committed manifest."
        )
    with gzip.open(payload_path, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)

    panel = Panel(
        manifest=manifest,
        profiles=[_profile_from_json(p) for p in payload["profiles"]],
        inventories=[
            [InventoryProduct.model_validate(product) for product in inv]
            for inv in payload["inventories"]
        ],
    )
    rebuilt = _manifest_for(manifest.spec, panel.profiles, panel.inventories)
    if rebuilt.profiles_checksum != manifest.profiles_checksum:
        raise ValueError(f"panel {name!r}: profiles checksum mismatch")
    if rebuilt.inventories_checksum != manifest.inventories_checksum:
        raise ValueError(f"panel {name!r}: inventories checksum mismatch")
    return panel


def load_or_build(spec: PanelSpec, root: Path = PANEL_ROOT) -> Panel:
    """Load the stored panel if it is there and matches, else rebuild it.

    A fresh clone has the manifest but not the payload — the manifest is
    committed, the gzip is ignored — so keying the decision on the manifest
    alone tried to open a file that was never checked out. That is the normal
    state of any clone, not an error.

    Rebuilding is the right response, and it is also the reproducibility check
    the committed manifest exists for: if the rebuild does not reproduce the
    recorded checksums, the generator has drifted from what the manifest
    describes, and every number quoted against that panel is stale. That is
    worth failing loudly over rather than silently regenerating different data
    under an unchanged name.
    """
    directory = panel_dir(spec.name, root)
    stored: PanelManifest | None = None
    manifest_path = directory / "manifest.json"
    if manifest_path.exists():
        stored = PanelManifest.from_json(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )

    usable = (
        stored is not None
        and stored.spec == spec
        and stored.generator_version == GENERATOR_VERSION
    )
    if usable and (directory / "panel.json.gz").exists():
        return load_panel(spec.name, root)

    panel = build_panel(spec)
    if usable:
        assert stored is not None
        mismatches = [
            f"{field}: manifest {getattr(stored, field)} != rebuild "
            f"{getattr(panel.manifest, field)}"
            for field in ("profiles_checksum", "inventories_checksum")
            if getattr(stored, field) != getattr(panel.manifest, field)
        ]
        if mismatches:
            raise ValueError(
                f"panel {spec.name!r} no longer rebuilds to its committed "
                f"manifest — " + "; ".join(mismatches) + ". Either the "
                f"generator changed without a GENERATOR_VERSION bump, or the "
                f"manifest is stale; regenerate with `python -m recsys.panels` "
                f"and commit the result."
            )
    save_panel(panel, root)
    return panel


# --- the standard set ------------------------------------------------------

#: Size of the development panel, before the train/validation/test split.
#:
#: Raised from 400 after auditing the split it produced: at 400 the test half
#: drew 27% explorers against 16% in train. That is ordinary sampling noise at
#: n=77 (~1.5 sd), and ordinarily you would shrug — but the protocol reads test
#: exactly once, so an unlucky draw cannot be spotted and repaired afterwards,
#: it just yields one wrong final number. Explorers are the most
#: missing-tolerant archetype, so that particular draw would have flattered
#: every discovery-shaped change and understated every price-shaped one.
#: 1000 users puts ~200 in test, where the same share moves by about 3 points.
DEVELOPMENT_PANEL_USERS = 1000

#: Probe panels, each isolating one way the world can differ from development.
#: They are deliberately separate panels rather than slices of the main one:
#: a slice shares users with development, and "does this hold for someone we
#: have never seen" is exactly the question a shared user cannot answer.
PROBE_USERS = 200

_HIGH_DEFICIT = replace(
    DEFAULT_INVENTORY_ASSUMPTIONS, no_product_at_all=0.35, out_of_stock=0.35
)


def _shifted_preferences_regime() -> str:
    """A world where novelty, promo-sensitivity and repeat all sit high.

    The point is not that this world is likely, it is that a conclusion which
    only survives at the neutral dial setting is a conclusion about the dial.
    """
    return "novelty=high/promo=high/repeat=high"


def standard_specs() -> dict[str, PanelSpec]:
    """Every panel the protocol names, by role."""
    return {
        "development": PanelSpec(
            name="development", n_users=DEVELOPMENT_PANEL_USERS, cohort="base"
        ),
        # Users from a cohort the development panel never draws from.
        "probe_new_users": PanelSpec(
            name="probe_new_users", n_users=PROBE_USERS, cohort="holdout_users"
        ),
        "probe_shifted_preferences": PanelSpec(
            name="probe_shifted_preferences",
            n_users=PROBE_USERS,
            cohort="base",
            regime=_shifted_preferences_regime(),
        ),
        "probe_shifted_availability": PanelSpec(
            name="probe_shifted_availability",
            n_users=PROBE_USERS,
            cohort="base",
            assumptions=_HIGH_DEFICIT,
        ),
    }


def development_splits(root: Path = PANEL_ROOT) -> dict[str, Panel]:
    """train / validation / test, built once and split by user identity."""
    panel = load_or_build(standard_specs()["development"], root)
    return {name: panel.split(name) for name in SPLIT_WEIGHTS}


#: The deficit sweep every experiment runs, by the same calibrated values as
#: ``recsys.sensitivity``'s dials. Held here so three experiments cannot drift
#: into three slightly different definitions of "high deficit".
DEFICIT_LEVELS: dict[str, InventoryAssumptions] = {
    "низкий": replace(
        DEFAULT_INVENTORY_ASSUMPTIONS, no_product_at_all=0.02, out_of_stock=0.02
    ),
    "база": DEFAULT_INVENTORY_ASSUMPTIONS,
    "высокий": replace(
        DEFAULT_INVENTORY_ASSUMPTIONS, no_product_at_all=0.35, out_of_stock=0.35
    ),
}


def experiment_panels(
    split: str = "train", root: Path = PANEL_ROOT
) -> dict[str, Panel]:
    """One split of the development panel, at each deficit level.

    This is the population every experiment runs on, and ``split`` defaults to
    ``train`` on purpose: experiments select things — a ranker, a policy, a set
    of recipes — and selection happens on train, confirmation on validation,
    and test is read once at the end by whoever writes the final number.

    Behavioural worlds (``recsys.regimes``) are deliberately not swept here.
    An experiment asks "which arm wins on our population"; "does that survive a
    different kind of shopper" is a robustness question, and
    ``recsys.sensitivity`` already owns it. Splitting the two keeps each run on
    one large, properly-split population instead of nine small unsplit ones,
    which also makes per-user paired comparison possible.
    """
    base = development_splits(root)[split]
    return {name: base.with_inventory(a) for name, a in DEFICIT_LEVELS.items()}


def main() -> int:
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    specs = standard_specs()
    rows: list[tuple[str, PanelManifest]] = []
    for role, spec in specs.items():
        panel = build_panel(spec)
        issues = validate_panel(panel)
        errors = [i for i in issues if i.severity == "error"]
        if errors:
            for issue in errors:
                print(f"  ERROR {spec.name}: {issue.message}", file=sys.stderr)
            return 1
        for issue in issues:
            print(f"  warning {spec.name}: {issue.message}")
        save_panel(panel, PANEL_ROOT)
        rows.append((role, panel.manifest))

    development = load_or_build(specs["development"])
    splits = {name: development.split(name) for name in SPLIT_WEIGHTS}
    assert_disjoint(*splits.values())
    # The probe only answers "does this hold for people we have never seen" if
    # it actually holds nobody we have seen.
    assert_disjoint(development, load_or_build(specs["probe_new_users"]))

    print(f"\n{'panel':<28} {'users':>6} {'products':>9}  profiles_sha  inventories_sha")
    for role, manifest in rows:
        print(
            f"{manifest.spec.name:<28} {manifest.n_profiles:>6} "
            f"{manifest.n_products:>9}  {manifest.profiles_checksum}  "
            f"{manifest.inventories_checksum}"
        )
    print()
    for name, panel in splits.items():
        print(f"  development/{name:<12} {len(panel.profiles):>4} users")
    print(f"\nwritten to {PANEL_ROOT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
