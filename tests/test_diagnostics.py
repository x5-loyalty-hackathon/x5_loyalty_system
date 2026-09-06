from app.recommender import DeterministicMockEngine
from recsys.catalog_freeze import baseline_catalog
from recsys.diagnostics import (
    MIN_STRATUM_SIZE,
    Stratum,
    StratifiedSignal,
    _samples,
    auc,
    effort_confound,
    effort_residual_variance,
    pearson,
    stratified_signal,
)
from recsys.model import (
    AVAILABILITY_FEATURE_NAMES,
    EFFORT_FEATURE_NAMES,
    FEATURE_NAMES,
)

SMALL = 8


def test_auc_of_a_perfect_and_a_useless_ranker() -> None:
    assert auc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) == 1.0
    assert auc([0.1, 0.2, 0.8, 0.9], [True, True, False, False]) == 0.0
    assert auc([0.5, 0.5, 0.5, 0.5], [True, True, False, False]) == 0.5


def test_auc_is_none_for_a_single_class_group() -> None:
    """No information about ranking is not the same as chance-level ranking."""
    assert auc([0.9, 0.1], [True, True]) is None
    assert auc([0.9, 0.1], [False, False]) is None


def test_pearson_edges() -> None:
    assert pearson([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == 1.0
    assert pearson([1.0, 2.0, 3.0], [6.0, 4.0, 2.0]) == -1.0
    assert pearson([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) == 0.0
    assert pearson([1.0], [1.0]) == 0.0


def test_effort_confound_scores_every_model_feature() -> None:
    confound = effort_confound(n_profiles=SMALL)
    assert set(confound) == set(FEATURE_NAMES)
    assert all(-1.0 <= value <= 1.0 for value in confound.values())


#: Below this share of surviving variance, a feature is missing count wearing
#: a different scale, and must be declared so ``_feature_vector`` can suppress
#: it for preference-only arms. Calibrated against the measured spread:
#: missing_vs_basket 0.19 and missing_cost_norm 0.35 (both effort) sit below,
#: time_fit 0.57 and prep_vs_cadence 0.65 (both genuine) sit above.
EFFORT_RESIDUAL_BAR = 0.45


def test_no_undeclared_feature_is_effort_in_disguise() -> None:
    """The registry must be checkable, not a thing engineers remember.

    ``missing_vs_basket`` was added to FEATURE_NAMES by the ADR-003 patch and
    left out of EFFORT_FEATURE_NAMES. It correlates 0.89 with missing count —
    higher than either declared effort feature — so the "effort counted once"
    property that ADR-002 fought for was quietly broken again, and only a
    print() in diagnostics could have caught it.

    The bar is residual variance, not correlation, on purpose: correlation
    alone flags ``time_fit`` (-0.59 through recipe length) which the label
    gates on directly and which must NOT be suppressed.
    """
    declared = EFFORT_FEATURE_NAMES | AVAILABILITY_FEATURE_NAMES
    residual = effort_residual_variance(n_profiles=SMALL)

    offenders = {
        name: round(share, 3)
        for name, share in residual.items()
        if name not in declared
        and share < EFFORT_RESIDUAL_BAR
        # A feature with no variance at all carries no signal either way; it is
        # a different defect (see history_is_known on a no-history population)
        # and not what this guard is about.
        and share > 0.0
    }
    assert not offenders, (
        f"features are effort re-expressed but not declared: {offenders}. "
        "Either add them to EFFORT_FEATURE_NAMES or explain why the pipeline "
        "should optimise the same quantity twice."
    )


def test_the_residual_bar_only_accuses_it_does_not_acquit() -> None:
    """The guard above is one-directional, and this pins down why.

    The tempting mirror-image check — "everything declared as effort must sit
    below the bar" — is false, and ``missing_ratio`` is the counterexample:
    it is missing count divided by the recipe's ingredient count, so it is
    pure effort by provenance, yet it keeps ~0.6 of its variance within a
    stratum because recipe length varies inside one missing-count bucket.

    So low residual variance proves a feature is effort re-expressed; high
    residual variance proves nothing either way. Membership in
    EFFORT_FEATURE_NAMES is decided by how a feature is computed, not by this
    number, and a future reader should not "tidy" the asymmetry away.
    """
    residual = effort_residual_variance(n_profiles=SMALL)
    assert "missing_ratio" in EFFORT_FEATURE_NAMES
    assert residual["missing_ratio"] > EFFORT_RESIDUAL_BAR
    assert residual["missing_vs_basket"] < EFFORT_RESIDUAL_BAR


def test_diagnostics_measure_the_catalog_the_model_trains_on() -> None:
    """The within-effort AUC in ADR-003 is decisive, so its catalog must match.

    ``_samples`` used to walk the live ``recsys.recipes.RECIPES`` (47) while
    the model under diagnosis fits on ``baseline_catalog()`` (37).
    """
    _, _, recipes = next(iter(_samples(2, seed=1)))
    assert [r.recipe_id for r in recipes] == [
        r.recipe_id for r in baseline_catalog()
    ]


def test_thin_and_single_class_strata_are_not_read() -> None:
    thin = Stratum(missing_count=1, n=MIN_STRATUM_SIZE - 1, positive_rate=0.5, auc=0.9)
    single = Stratum(missing_count=2, n=1000, positive_rate=1.0, auc=None)
    fine = Stratum(missing_count=3, n=MIN_STRATUM_SIZE, positive_rate=0.5, auc=0.6)
    assert not thin.is_readable
    assert not single.is_readable
    assert fine.is_readable

    signal = StratifiedSignal(overall_auc=0.9, strata=(thin, single, fine))
    assert signal.readable_strata == (fine,)
    assert signal.within_stratum_auc == 0.6


def test_within_stratum_auc_is_size_weighted() -> None:
    signal = StratifiedSignal(
        overall_auc=0.8,
        strata=(
            Stratum(missing_count=1, n=100, positive_rate=0.5, auc=0.6),
            Stratum(missing_count=2, n=300, positive_rate=0.5, auc=1.0),
        ),
    )
    assert signal.within_stratum_auc == (0.6 * 100 + 1.0 * 300) / 400
    assert signal.signal_beyond_effort == signal.within_stratum_auc - 0.5


def test_no_readable_strata_reports_nothing_rather_than_chance() -> None:
    signal = StratifiedSignal(
        overall_auc=0.9,
        strata=(Stratum(missing_count=1, n=5, positive_rate=1.0, auc=None),),
    )
    assert signal.within_stratum_auc is None
    assert signal.signal_beyond_effort is None
    assert "n/a" in signal.summary()


def test_stratified_signal_runs_end_to_end() -> None:
    signal = stratified_signal(DeterministicMockEngine(), n_profiles=SMALL)
    assert signal.strata
    assert signal.overall_auc is None or 0.0 <= signal.overall_auc <= 1.0
    for stratum in signal.strata:
        assert stratum.n > 0
        assert 0.0 <= stratum.positive_rate <= 1.0
        assert stratum.auc is None or 0.0 <= stratum.auc <= 1.0
    assert "overall AUC" in signal.summary()
