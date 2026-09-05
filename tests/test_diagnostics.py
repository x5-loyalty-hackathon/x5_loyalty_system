from app.recommender import DeterministicMockEngine
from recsys.diagnostics import (
    MIN_STRATUM_SIZE,
    Stratum,
    StratifiedSignal,
    auc,
    effort_confound,
    pearson,
    stratified_signal,
)
from recsys.model import FEATURE_NAMES

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
