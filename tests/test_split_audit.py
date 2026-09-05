"""The split audit has to fail when the split is broken, not only pass when it
is fine. Each test breaks one guarantee and checks the audit notices."""

from __future__ import annotations

from dataclasses import replace

from recsys.panels import PanelSpec, build_panel, split_of
from recsys.split_audit import (
    audit,
    count_test_accesses,
    profile_content_hash,
    record_test_access,
)


def _splits(n: int = 200) -> dict:
    panel = build_panel(PanelSpec(name="audit_test_panel", n_users=n))
    return {name: panel.split(name) for name in ("train", "validation", "test")}


def test_a_healthy_split_passes() -> None:
    assert audit(_splits()).clean


def test_overlapping_splits_are_an_error() -> None:
    splits = _splits()
    # Put one training user into test as well.
    splits["test"].profiles.append(splits["train"].profiles[0])
    result = audit(splits)
    assert not result.clean
    assert any(f.check == "disjoint_ids" for f in result.errors)


def test_an_assignment_that_ignores_the_id_hash_is_an_error() -> None:
    splits = _splits()
    moved = splits["train"].profiles.pop()
    splits["validation"].profiles.append(moved)
    result = audit(splits)
    assert any(f.check == "stable_assignment" for f in result.errors)


def test_an_empty_split_is_an_error() -> None:
    splits = _splits()
    splits["test"].profiles.clear()
    splits["test"].inventories.clear()
    assert not audit(splits).clean


# --- content identity ------------------------------------------------------


def test_content_hash_ignores_the_user_id() -> None:
    """Two generators can hand different people the same id; the audit has to
    compare data, not names."""
    panel = build_panel(PanelSpec(name="audit_hash_panel", n_users=5))
    profile = panel.profiles[0]
    renamed = replace(
        profile, user=profile.user.model_copy(update={"user_id": "someone_else"})
    )
    assert profile_content_hash(profile) == profile_content_hash(renamed)


def test_content_hash_separates_different_baskets() -> None:
    panel = build_panel(PanelSpec(name="audit_hash_panel", n_users=5))
    assert profile_content_hash(panel.profiles[0]) != profile_content_hash(
        panel.profiles[1]
    )


def test_the_audit_reports_content_overlap_per_source() -> None:
    result = audit(_splits())
    checks = [f.detail for f in result.findings if f.check == "content_leak"]
    assert any("model_training" in d for d in checks)
    assert any("experiments_1_3" in d for d in checks)


# --- the ledger ------------------------------------------------------------


def test_reading_test_is_recorded(tmp_path) -> None:
    """Discipline that leaves no trace is an intention, not a control."""
    ledger = tmp_path / "ledger.json"
    assert count_test_accesses(ledger) == 0
    record_test_access("final number for ADR-004", ledger)
    record_test_access("second read — should be visible", ledger)
    assert count_test_accesses(ledger) == 2
    payload = record_test_access("third", ledger)
    assert [entry["reason"] for entry in payload["accesses"]][-1] == "third"
    assert all("at" in entry for entry in payload["accesses"])


def test_split_of_is_a_pure_function_of_the_id() -> None:
    assert split_of("synthetic_routine_0001") == split_of("synthetic_routine_0001")
